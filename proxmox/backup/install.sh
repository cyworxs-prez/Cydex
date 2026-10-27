#!/bin/bash
# Install the weekly encrypted backup on the Proxmox host. Run as root, from this
# directory. Installs files only; the timer is NOT enabled (see docs/configure.md §5).
set -euo pipefail
cd "$(dirname "$0")"
install -m 750 homelab-backup.sh /usr/local/sbin/homelab-backup.sh
[ -f /etc/default/homelab-backup ] || install -m 644 homelab-backup.default /etc/default/homelab-backup
install -m 644 homelab-backup.service homelab-backup.timer /etc/systemd/system/
. /etc/default/homelab-backup
grep -q "^RequiresMountsFor=$MNT\$" /etc/systemd/system/homelab-backup.service \
  || echo "WARN: RequiresMountsFor= in homelab-backup.service does not match MNT=$MNT - fix it"
case "$LUKS_DEV" in *REPLACE*) echo "WARN: set LUKS_DEV in /etc/default/homelab-backup";; esac
systemctl daemon-reload
bash -n /usr/local/sbin/homelab-backup.sh
cat <<MSG
INSTALLED (timer NOT enabled). Next:
  1. edit /etc/default/homelab-backup (LUKS_DEV, STORAGE, MNT, GUESTS)
  2. open + mount the LUKS volume, then: systemctl start homelab-backup
  3. read the newest /var/log/homelab-backup-*.log - it must end "verified"
  4. restore one guest to a new ID on an isolated bridge
  5. systemctl enable --now homelab-backup.timer
MSG
