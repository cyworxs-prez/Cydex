#!/bin/sh
# Run a local shell script ON the OPNsense firewall, via the pve guest agent.
#
#   ./runfw-via-pve.sh <local-script.sh>
#
# Why base64: the payload travels workstation sh -> ssh -> pve sh -> qm guest exec ->
# FreeBSD /bin/sh. Every layer eats quotes, and OPNsense's root shell is csh.
# Base64 is [A-Za-z0-9+/=] only, so nothing in the payload can be re-interpreted
# on the way. It needs neither SSH to OPNsense nor API credentials - only
# the qemu-guest-agent plugin on OPNsense and SSH to the Proxmox host.
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
[ -f "$ROOT/config/homelab.env" ] && . "$ROOT/config/homelab.env"
[ -f "$1" ] || { echo "usage: $0 <local-script.sh>"; exit 2; }
PVE=${PVE_SSH:-root@10.10.130.10}
VMID=${FW_VMID:-200}
B64=$(base64 < "$1" | tr -d '\n')

ssh -o ConnectTimeout=30 "$PVE" "qm guest exec $VMID --timeout 60 -- /bin/sh -c 'echo $B64 | openssl base64 -d -A > /tmp/_fwrun.sh; sh /tmp/_fwrun.sh'" 2>&1 \
 | python3 -c '
import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw[raw.index("{"):raw.rindex("}")+1])
    out = d.get("out-data", "")
    err = d.get("err-data", "")
    if out: print(out, end="")
    if err: print("--- stderr ---\n" + err, end="")
    if d.get("exitcode"): print("\n[exit %s]" % d["exitcode"])
except Exception:
    print(raw[:800])'
