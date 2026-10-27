#!/bin/bash
# Restore the SPAN mirror feeding the Zeek sensor, and make it survive reboots.
# The mirror is tc runtime state - a reboot silently drops it and Zeek runs blind
# while still reporting healthy. This installs it as a boot-time systemd unit
# that VERIFIES the filter landed.
#
#   MIRROR_SRC  OPNsense LAN-trunk tap   (tap<FW_VMID>i<n>, default tap200i1)
#   MIRROR_DST  Zeek capture veth        (veth<ZEEK_CTID>i<n>, default veth206i1)
set -euo pipefail
MIRROR_SRC=${MIRROR_SRC:-tap200i1}
MIRROR_DST=${MIRROR_DST:-veth206i1}

cat > /usr/local/sbin/zeek-mirror.sh <<EOF
#!/bin/bash
# Mirror the OPNsense LAN trunk (all VLANs) into the Zeek sensor's capture port.
SRC=$MIRROR_SRC      # OPNsense LAN trunk
DST=$MIRROR_DST     # Zeek sensor capture interface
log() { logger -t zeek-mirror -p daemon."\$1" -- "\$2"; echo "[\$1] \$2"; }

for i in \$(seq 1 90); do
    ip link show "\$SRC" >/dev/null 2>&1 && ip link show "\$DST" >/dev/null 2>&1 && break
    sleep 2
done
if ! ip link show "\$SRC" >/dev/null 2>&1 || ! ip link show "\$DST" >/dev/null 2>&1; then
    log err "gave up waiting for \$SRC / \$DST - mirror NOT installed, Zeek will be blind"
    exit 1
fi

tc qdisc del dev "\$SRC" clsact 2>/dev/null || true
tc qdisc add dev "\$SRC" clsact
tc filter add dev "\$SRC" ingress matchall action mirred egress mirror dev "\$DST"
tc filter add dev "\$SRC" egress  matchall action mirred egress mirror dev "\$DST"

if tc filter show dev "\$SRC" ingress 2>/dev/null | grep -q mirred; then
    log notice "mirror active: \$SRC (ingress+egress) -> \$DST"
else
    log err "mirror install did not verify - Zeek will be blind"
    exit 1
fi
EOF
chmod 750 /usr/local/sbin/zeek-mirror.sh

cat > /etc/systemd/system/zeek-mirror.service <<'EOF'
[Unit]
Description=SPAN mirror: OPNsense LAN trunk -> Zeek sensor
After=pve-guests.service
Wants=pve-guests.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/zeek-mirror.sh
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable zeek-mirror.service
echo "INSTALLED + ENABLED (not started yet)"
