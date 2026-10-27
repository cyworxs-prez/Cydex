#!/bin/bash
# Install the OPNsense liveness watchdog on the Proxmox host. Run as root on pve.
# Installs but does NOT enable the timer - run a DRY_RUN first (see docs).
set -euo pipefail
cd "$(dirname "$0")"
install -m 750 opnsense-watchdog.sh       /usr/local/sbin/opnsense-watchdog.sh
install -m 644 opnsense-watchdog.service  /etc/systemd/system/opnsense-watchdog.service
install -m 644 opnsense-watchdog.timer    /etc/systemd/system/opnsense-watchdog.timer
[ -f /etc/default/opnsense-watchdog ] || install -m 644 opnsense-watchdog.default /etc/default/opnsense-watchdog
mkdir -p /var/lib/opnsense-watchdog
bash -n /usr/local/sbin/opnsense-watchdog.sh && echo "SYNTAX OK"
systemctl daemon-reload
echo "INSTALLED (timer NOT enabled)."
echo "  1. edit /etc/default/opnsense-watchdog"
echo "  2. DRY_RUN=1 /usr/local/sbin/opnsense-watchdog.sh"
echo "  3. systemctl enable --now opnsense-watchdog.timer"
