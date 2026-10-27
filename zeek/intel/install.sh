#!/bin/sh
# Install the Zeek Intel framework wiring + daily feed updater. Run as root on the
# Zeek sensor, from this directory. Idempotent.
set -e
cd "$(dirname "$0")"
SITE=/opt/zeek/share/zeek/site
D=$SITE/intel
mkdir -p "$D"
install -m 644 intel-config.zeek "$SITE/intel-config.zeek"
[ -f "$D/local-iocs.dat" ] || install -m 644 local-iocs.dat "$D/local-iocs.dat"
install -m 644 domain-exclude.txt "$D/domain-exclude.txt"
install -m 755 zeek-intel-update.sh /usr/local/bin/zeek-intel-update.sh
install -m 644 zeek-intel-update.service /etc/systemd/system/zeek-intel-update.service
install -m 644 zeek-intel-update.timer /etc/systemd/system/zeek-intel-update.timer
grep -q '^@load ./intel-config' "$SITE/local.zeek" || echo '@load ./intel-config' >> "$SITE/local.zeek"
# Build master.dat once now so Zeek has something to read on deploy.
/usr/local/bin/zeek-intel-update.sh || echo "WARN: first feed refresh failed - check: journalctl -t zeek-intel"
systemctl daemon-reload
systemctl enable --now zeek-intel-update.timer >/dev/null 2>&1
/opt/zeek/bin/zeekctl deploy
echo INSTALLED
