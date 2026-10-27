#!/bin/sh
# Run a local script inside a container via pve. base64 for quoting safety.
#   ./run-on-ct.sh <ctid> <script.sh>
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
[ -f "$ROOT/config/homelab.env" ] && . "$ROOT/config/homelab.env"
CT="$1"; F="$2"
[ -f "$F" ] || { echo "usage: $0 <ctid> <script.sh>"; exit 2; }
B64=$(base64 < "$F" | tr -d '\n')
ssh -o ConnectTimeout=30 "${PVE_SSH:-root@10.10.130.10}" "pct exec $CT -- /bin/sh -c 'echo $B64 | base64 -d > /tmp/_ctrun.sh; sh /tmp/_ctrun.sh'"
