#!/bin/bash
# Deploy YARA host-scanning integrated with Wazuh.
#  - installs yara + YARA-Forge core ruleset
#  - TEST-COMPILES the ruleset; aborts before touching config if it fails
#  - installs a scan wrapper that emits JSON lines for the Wazuh agent
#  - registers a localfile + daily cron
# Idempotent: safe to re-run.
set -u
LOGDIR=/var/log/yara
RULEDIR=/var/ossec/etc/yara/rules
RULES=$RULEDIR/yara-rules-core.yar
SCAN=/usr/local/bin/yara-scan.sh
URL="https://github.com/YARAHQ/yara-forge/releases/latest/download/yara-forge-rules-core.zip"

echo "== 1. install yara"
export DEBIAN_FRONTEND=noninteractive
command -v yara >/dev/null || apt-get install -y yara unzip >/dev/null 2>&1
command -v yara >/dev/null || { echo "YARA-INSTALL-FAILED"; exit 1; }
yara --version

echo "== 2. fetch ruleset"
mkdir -p "$RULEDIR" "$LOGDIR"
cd /tmp || exit 1
if ! curl -sSL --max-time 180 -o /tmp/yf.zip "$URL"; then
  echo "RULES-DOWNLOAD-FAILED"; exit 1
fi
unzip -o -q /tmp/yf.zip -d /tmp/yf || { echo "UNZIP-FAILED"; exit 1; }
SRC=$(find /tmp/yf -name 'yara-rules-core.yar' | head -1)
[ -n "$SRC" ] || { echo "RULES-NOT-FOUND-IN-ZIP"; exit 1; }

echo "== 3. TEST COMPILE (abort if the local yara cannot parse these rules)"
if ! yara -w "$SRC" /etc/hostname >/dev/null 2>/tmp/yara_compile_err; then
  echo "RULES-COMPILE-FAILED -- not deploying. First errors:"
  head -5 /tmp/yara_compile_err
  exit 1
fi
echo "COMPILE-OK ($(grep -c '^rule ' "$SRC") rules)"
mv "$SRC" "$RULES"
chmod 640 "$RULES"

echo "== 4. install scan wrapper"
cat > "$SCAN" <<'WRAPPER'
#!/bin/bash
# Scan common malware drop locations; emit one JSON object per match.
RULES=/var/ossec/etc/yara/rules/yara-rules-core.yar
OUT=/var/log/yara/yara-scan.log
TARGETS="/tmp /var/tmp /dev/shm /root /home /usr/local/bin /usr/local/sbin"
HOST=$(hostname)
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
[ -f "$RULES" ] || exit 0
for T in $TARGETS; do
  [ -e "$T" ] || continue
  # -r recursive, -w no warnings, -N no follow symlinks, timeout guard
  nice -n 19 ionice -c3 yara -r -w -N --timeout=120 "$RULES" "$T" 2>/dev/null | \
  while read -r RULE FILEPATH; do
    [ -n "$RULE" ] || continue
    # escape backslashes and quotes for JSON safety
    ESC=$(printf '%s' "$FILEPATH" | sed 's/\\/\\\\/g; s/"/\\"/g')
    printf '{"yara_rule":"%s","yara_file":"%s","yara_host":"%s","yara_scan_ts":"%s"}\n' \
      "$RULE" "$ESC" "$HOST" "$TS" >> "$OUT"
  done
done
exit 0
WRAPPER
chmod 750 "$SCAN"

echo "== 5. logrotate + log file"
touch "$LOGDIR/yara-scan.log"; chmod 640 "$LOGDIR/yara-scan.log"
cat > /etc/logrotate.d/yara <<'LR'
/var/log/yara/yara-scan.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
LR

echo "== 6. register localfile with the Wazuh agent"
CONF=/var/ossec/etc/ossec.conf
if ! grep -q 'yara-scan.log' "$CONF"; then
  cp "$CONF" "$CONF.bak-pre-yara"
  cat >> "$CONF" <<'LF'
<ossec_config>
  <localfile>
    <log_format>json</log_format>
    <location>/var/log/yara/yara-scan.log</location>
  </localfile>
</ossec_config>
LF
  echo "LOCALFILE-ADDED"
else
  echo "LOCALFILE-PRESENT"
fi

echo "== 7. daily cron (03:30, lowest priority)"
( crontab -l 2>/dev/null | grep -v yara-scan.sh; echo "30 3 * * * $SCAN" ) | crontab -
crontab -l | grep yara-scan.sh

systemctl restart wazuh-agent 2>/dev/null && echo "AGENT-RESTARTED"
echo "YARA-DEPLOY-DONE"
