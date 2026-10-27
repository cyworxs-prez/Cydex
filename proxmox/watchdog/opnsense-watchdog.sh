#!/bin/bash
# opnsense-watchdog - recover the OPNsense VM from a hung state.
#
# Probes three INDEPENDENT liveness signals. Only if ALL THREE fail does it count
# a failure. After FAIL_THRESHOLD consecutive failures it attempts recovery.
#
# Guards: VM must be running, must not be locked, cooldown between recoveries,
# and a hard daily cap so it can never sit in a reboot loop.
#
# DRY_RUN=1 -> log what it would do, change nothing.
# Settings: /etc/default/opnsense-watchdog (see opnsense-watchdog.default).
set -uo pipefail

[ -f /etc/default/opnsense-watchdog ] && . /etc/default/opnsense-watchdog
VMID=${VMID:-200}
GW=${GW:-10.10.130.1}                      # OPNsense MGMT address
FAIL_THRESHOLD=${FAIL_THRESHOLD:-5}         # consecutive failed probes (60s timer -> 5 min)
COOLDOWN=${COOLDOWN:-1800}                  # seconds between recovery attempts
MAX_PER_DAY=${MAX_PER_DAY:-3}
HEARTBEAT_EVERY=${HEARTBEAT_EVERY:-60}      # healthy runs between heartbeat log lines
STATE=/var/lib/opnsense-watchdog
DRY_RUN="${DRY_RUN:-0}"

mkdir -p "$STATE"
FAILFILE="$STATE/consecutive_failures"
LASTFILE="$STATE/last_recovery"
DAYFILE="$STATE/recoveries_today"
[ -f "$FAILFILE" ] || echo 0 > "$FAILFILE"

log() { logger -t opnsense-watchdog -p daemon.$1 -- "$2"; echo "[$1] $2"; }

# ---------- probes ----------
probe_agent() { timeout 10 qm agent "$VMID" ping >/dev/null 2>&1; }
probe_icmp()  { ping -c 2 -W 2 "$GW" >/dev/null 2>&1; }
probe_dns()   { timeout 4 bash -c "echo > /dev/tcp/$GW/53" >/dev/null 2>&1; }

# ---------- preconditions ----------
STATUS=$(qm status "$VMID" 2>/dev/null | awk '{print $2}')
if [ "$STATUS" != "running" ]; then
    log info "VM$VMID status='$STATUS' (not running) - standing down, not our job"
    echo 0 > "$FAILFILE"; exit 0
fi

LOCK=$(qm config "$VMID" 2>/dev/null | sed -n 's/^lock: *//p')
if [ -n "$LOCK" ]; then
    log info "VM$VMID is locked ('$LOCK' - backup/snapshot/migrate) - standing down"
    echo 0 > "$FAILFILE"; exit 0
fi

# ---------- evaluate ----------
A=0; I=0; D=0
probe_agent && A=1
probe_icmp  && I=1
probe_dns   && D=1
ALIVE=$(( A + I + D ))

if [ "$ALIVE" -gt 0 ]; then
    PREV=$(cat "$FAILFILE")
    if [ "$PREV" -ne 0 ]; then
        log notice "VM$VMID recovered on its own (agent=$A icmp=$I dns=$D) after $PREV failed probe(s)"
    fi
    echo 0 > "$FAILFILE"
    # HEARTBEAT: silence from a watchdog is indistinguishable from a dead
    # watchdog, so emit one info line every HEARTBEAT_EVERY healthy runs.
    HB="$STATE/heartbeat_counter"
    N=$(( $(cat "$HB" 2>/dev/null || echo 0) + 1 ))
    if [ "$N" -ge "$HEARTBEAT_EVERY" ]; then
        log info "heartbeat: VM$VMID healthy (agent=$A icmp=$I dns=$D), watchdog operating normally"
        N=0
    fi
    echo "$N" > "$HB"
    exit 0
fi

FAILS=$(( $(cat "$FAILFILE") + 1 ))
echo "$FAILS" > "$FAILFILE"
log warning "VM$VMID ALL probes failed (agent=$A icmp=$I dns=$D) - consecutive=$FAILS/$FAIL_THRESHOLD"
[ "$FAILS" -ge "$FAIL_THRESHOLD" ] || exit 0

# ---------- recovery guards ----------
NOW=$(date +%s)
TODAY=$(date +%Y-%m-%d)

LAST=$(cat "$LASTFILE" 2>/dev/null || echo 0)
if [ $(( NOW - LAST )) -lt "$COOLDOWN" ]; then
    log warning "VM$VMID still down but within cooldown ($(( NOW - LAST ))s < ${COOLDOWN}s) - NOT acting"
    exit 0
fi

DAY=$(cut -d' ' -f1 "$DAYFILE" 2>/dev/null || echo "")
CNT=$(cut -d' ' -f2 "$DAYFILE" 2>/dev/null || echo 0)
[ "$DAY" = "$TODAY" ] || { DAY="$TODAY"; CNT=0; }
if [ "$CNT" -ge "$MAX_PER_DAY" ]; then
    log err "VM$VMID down but already recovered $CNT times today (cap $MAX_PER_DAY) - REFUSING to act, needs a human"
    exit 0
fi

# ---------- recover ----------
if [ "$DRY_RUN" = "1" ]; then
    log notice "DRY_RUN: would recover VM$VMID now (shutdown --forceStop then start)"
    exit 0
fi

log err "VM$VMID unresponsive for $FAILS consecutive probes - RECOVERING"
echo "$NOW" > "$LASTFILE"
echo "$DAY $(( CNT + 1 ))" > "$DAYFILE"
echo 0 > "$FAILFILE"

qm shutdown "$VMID" --timeout 90 --forceStop 1 >/dev/null 2>&1
sleep 5
for i in $(seq 1 12); do
    [ "$(qm status "$VMID" 2>/dev/null | awk '{print $2}')" = "stopped" ] && break
    sleep 5
done
qm start "$VMID" >/dev/null 2>&1 && log notice "VM$VMID start issued" || log err "VM$VMID START FAILED"

for i in $(seq 1 24); do
    sleep 10
    if probe_icmp; then log notice "VM$VMID back online after recovery (${i}0s)"; exit 0; fi
done
log err "VM$VMID did NOT come back within 240s of recovery - manual intervention required"
