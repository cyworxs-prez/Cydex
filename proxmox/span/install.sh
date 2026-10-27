#!/bin/bash
# Install the Zeek SPAN mirror on the Proxmox host. Run as root on the host, from this
# directory. Installs files only; it does NOT attach the hookscript or enable the unit.
set -euo pipefail
cd "$(dirname "$0")"
install -m 750 zeek-span-apply.sh  /usr/local/sbin/zeek-span-apply.sh
[ -f /etc/default/zeek-span ] || install -m 644 zeek-span.default /etc/default/zeek-span
mkdir -p /var/lib/vz/snippets
install -m 755 zeek-span.pl        /var/lib/vz/snippets/zeek-span.pl
install -m 644 zeek-mirror.service /etc/systemd/system/zeek-mirror.service
systemctl daemon-reload
bash -n /usr/local/sbin/zeek-span-apply.sh && perl -c /var/lib/vz/snippets/zeek-span.pl
. /etc/default/zeek-span
cat <<MSG
INSTALLED. Next, in order:
  1. edit /etc/default/zeek-span      (now: FW_VMID=$FW_VMID MIRROR_SRC=$MIRROR_SRC MIRROR_DST=$MIRROR_DST)
  2. /usr/local/sbin/zeek-span-apply.sh            # must print "span re-applied"
  3. systemctl enable zeek-mirror.service          # host boot
  4. qm set $FW_VMID --hookscript local:snippets/zeek-span.pl   # VM restarts
MSG
