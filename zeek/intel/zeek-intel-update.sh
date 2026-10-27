#!/bin/sh
# zeek-intel-update.sh -- rebuild the Zeek Intel master feed from public sources.
#
# Design notes:
#  * master.dat is truncated and rewritten in place (cat >), never renamed, so
#    the inode is stable and Zeek's Input::REREAD picks the change up live.
#  * Input::REREAD ADDS new indicators live but does NOT retire removed ones
#    (verified on Zeek 8.x: a canary indicator kept matching for
#    5+ minutes after it was deleted from master.dat). So when a refresh drops
#    indicators, Zeek is restarted to actually let go of them -- otherwise a
#    false-positive indicator could never be pulled without manual action.
#  * A sanity floor aborts the swap if the rebuild is implausibly small, so a
#    failed fetch degrades to "yesterday's indicators" rather than "no
#    indicators". A feed that silently empties is the failure mode this guards.
#  * Every outcome is logged via logger -t zeek-intel; Wazuh rules 100906-100909
#    alert if a refresh fails or goes stale.
set -u

DIR=/opt/zeek/share/zeek/site/intel
MASTER="$DIR/master.dat"
LOCAL="$DIR/local-iocs.dat"
FLOOR=500
UA='zeek-intel-update/1.0 (homelab sensor)'
TMP=$(mktemp -d /tmp/zeek-intel.XXXXXX) || exit 1
trap 'rm -rf "$TMP"' EXIT

log() { logger -t zeek-intel "$*"; }
fetch() {  # fetch URL OUTFILE ; non-fatal
  curl -sS --max-time 90 -A "$UA" -o "$2" "$1" 2>"$TMP/err" && [ -s "$2" ] && return 0
  log "FETCH FAILED $1 $(tr -d '\n' < "$TMP/err" | cut -c1-120)"
  return 1
}

# --- 1. abuse.ch Feodo Tracker -- botnet C2 IPs -----------------------------
if fetch https://feodotracker.abuse.ch/downloads/ipblocklist.txt "$TMP/feodo"; then
  grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}[[:space:]]*$' "$TMP/feodo" | tr -d '\r' \
    | awk '{print $1"\tIntel::ADDR\tfeodo\tFeodo Tracker botnet C2"}' > "$TMP/o.feodo"
fi

# --- 2. abuse.ch ThreatFox -- recent ip:port IOCs ---------------------------
if fetch https://threatfox.abuse.ch/export/csv/ip-port/recent/ "$TMP/tf"; then
  grep -oE '"[0-9]{1,3}(\.[0-9]{1,3}){3}:[0-9]+"' "$TMP/tf" | tr -d '"' \
    | cut -d: -f1 | sort -u \
    | awk '{print $1"\tIntel::ADDR\tthreatfox\tThreatFox recent C2"}' > "$TMP/o.tf"
fi

# --- 3. abuse.ch URLhaus -- currently-online malware URLs -------------------
# Zeek's Intel::URL indicator carries no scheme, so strip it.
if fetch https://urlhaus.abuse.ch/downloads/text_online/ "$TMP/uh"; then
  tr -d '\r' < "$TMP/uh" | grep -E '^https?://' \
    | sed -E 's#^https?://##' \
    | awk 'length($0)>4 {print $0"\tIntel::URL\turlhaus\tURLhaus online malware URL"}' > "$TMP/o.uh"

  # Domains from the same list give DNS-time detection, which URL matching
  # cannot do for HTTPS. Higher FP risk (compromised legit sites), so these
  # are alerted a level lower in Wazuh. IP-literal hosts are dropped -- the
  # ADDR feeds cover those -- as are hosts on the exclusion list below.
  tr -d '\r' < "$TMP/uh" | sed -E 's#^https?://##; s#[/:?].*$##' \
    | grep -E '^[A-Za-z0-9._-]+\.[A-Za-z]{2,}$' \
    | grep -vE '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' \
    | tr 'A-Z' 'a-z' | sort -u > "$TMP/uh.dom"
  if [ -s "$DIR/domain-exclude.txt" ]; then
    grep -vxF -f "$DIR/domain-exclude.txt" "$TMP/uh.dom" > "$TMP/uh.dom2" || true
    mv "$TMP/uh.dom2" "$TMP/uh.dom"
  fi
  awk '{print $0"\tIntel::DOMAIN\turlhaus-domain\tURLhaus online malware host"}' \
    "$TMP/uh.dom" > "$TMP/o.uhd"
fi

# --- 4. Tor exit nodes -- informational, not a page -------------------------
if fetch https://check.torproject.org/torbulkexitlist "$TMP/tor"; then
  grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' "$TMP/tor" | tr -d '\r' \
    | awk '{print $1"\tIntel::ADDR\ttor-exit\tTor exit node"}' > "$TMP/o.tor"
fi

# --- 5. Local hand-curated indicators ---------------------------------------
if [ -f "$LOCAL" ]; then
  grep -v '^[[:space:]]*#' "$LOCAL" | grep -v '^[[:space:]]*$' > "$TMP/o.local" || true
fi

# --- assemble ----------------------------------------------------------------
{
  printf '#fields\tindicator\tindicator_type\tmeta.source\tmeta.desc\n'
  cat "$TMP"/o.* 2>/dev/null
} | awk -F'\t' 'NR==1 || !seen[$1]++' > "$TMP/master.new"

# Which indicators is this refresh dropping? Needed to decide on a restart.
if [ -f "$MASTER" ]; then
  grep -v '^#' "$MASTER" 2>/dev/null | cut -f1 | sort -u > "$TMP/old.ind"
else
  : > "$TMP/old.ind"
fi
grep -v '^#' "$TMP/master.new" | cut -f1 | sort -u > "$TMP/new.ind"
REMOVED=$(comm -23 "$TMP/old.ind" "$TMP/new.ind" | wc -l)

N=$(grep -cv '^#' "$TMP/master.new" 2>/dev/null || echo 0)
if [ "$N" -lt "$FLOOR" ]; then
  log "REFRESH ABORTED: rebuild had $N indicators, floor is $FLOOR; keeping existing master.dat"
  exit 1
fi

cat "$TMP/master.new" > "$MASTER"   # in place: preserves inode for Input::REREAD
chmod 644 "$MASTER"
log "REFRESH OK: $N indicators ($(cat "$TMP/o.feodo" 2>/dev/null | wc -l) feodo, $(cat "$TMP/o.tf" 2>/dev/null | wc -l) threatfox, $(cat "$TMP/o.uh" 2>/dev/null | wc -l) urlhaus-url, $(cat "$TMP/o.uhd" 2>/dev/null | wc -l) urlhaus-domain, $(cat "$TMP/o.tor" 2>/dev/null | wc -l) tor, $(cat "$TMP/o.local" 2>/dev/null | wc -l) local)"
# Retire dropped indicators. Additions are picked up live; removals are not.
if [ "$REMOVED" -gt 0 ]; then
  if /opt/zeek/bin/zeekctl restart >"$TMP/restart.out" 2>&1 \
     && /opt/zeek/bin/zeekctl status 2>/dev/null | grep -q running; then
    log "RESTART OK: $REMOVED indicators retired, Zeek restarted to drop them"
  else
    log "RESTART FAILED after intel refresh - THE SENSOR MAY BE DOWN: $(tail -3 "$TMP/restart.out" | tr '\n' ' ' | cut -c1-200)"
    exit 1
  fi
fi

exit 0
