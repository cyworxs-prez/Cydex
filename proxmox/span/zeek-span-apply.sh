#!/bin/bash
# Mirror the OPNsense LAN trunk (all VLANs, ingress + egress) into the Zeek capture
# interface with tc mirred, then VERIFY exactly one filter per direction.
#
# tc state is runtime-only and the VM tap is recreated on every VM restart, so this
# runs at host boot (zeek-mirror.service) and after every VM start (zeek-span.pl).
# Idempotent: both hooks are cleared before re-adding, so it can never double-mirror.
# Every outcome is logged with tag zeek-span; Wazuh span_rules.xml pages on failure.
set -u
[ -f /etc/default/zeek-span ] && . /etc/default/zeek-span
SRC=${MIRROR_SRC:?set MIRROR_SRC in /etc/default/zeek-span}
DST=${MIRROR_DST:?set MIRROR_DST in /etc/default/zeek-span}
WAIT=${WAIT_SECS:-180}
log() { logger -t zeek-span -p "daemon.$1" -- "$2"; echo "[$1] $2"; }

for _ in $(seq 1 "$WAIT"); do
    [ -e "/sys/class/net/$SRC" ] && [ -e "/sys/class/net/$DST" ] && break
    sleep 1
done
[ -e "/sys/class/net/$SRC" ] || { log err "span NOT applied: $SRC absent - Zeek is blind"; exit 1; }
[ -e "/sys/class/net/$DST" ] || { log err "span NOT applied: $DST absent (is the Zeek CT running?) - Zeek is blind"; exit 1; }

tc qdisc add dev "$SRC" clsact 2>/dev/null || true
tc filter del dev "$SRC" ingress 2>/dev/null || true
tc filter del dev "$SRC" egress  2>/dev/null || true
tc filter add dev "$SRC" ingress matchall action mirred egress mirror dev "$DST"
tc filter add dev "$SRC" egress  matchall action mirred egress mirror dev "$DST"

IN=$(tc filter show dev "$SRC" ingress 2>/dev/null | grep -c mirred)
OUT=$(tc filter show dev "$SRC" egress  2>/dev/null | grep -c mirred)
if [ "$IN" = 1 ] && [ "$OUT" = 1 ]; then
    log notice "span re-applied: $SRC ingress+egress -> $DST"
else
    log err "span WRONG: ingress=$IN egress=$OUT (expected 1 and 1)"; exit 1
fi
