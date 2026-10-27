#!/bin/sh
# Pull the live Wazuh rule files back into the repo so the repo copies match
# what is actually deployed. A repo that disagrees with the box is how stale
# detection content survives in the first place. Read-only on the Wazuh side.
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
[ -f "$ROOT/config/homelab.env" ] && . "$ROOT/config/homelab.env"
PVE=${PVE_SSH:-root@10.10.130.10}
CT=${WAZUH_CTID:-201}
DIR="$ROOT/wazuh/rules"

for f in "$DIR"/*.xml; do
  b=$(basename "$f")
  if ssh -o ConnectTimeout=25 "$PVE" "pct exec $CT -- cat /var/ossec/etc/rules/$b" > "$f.deployed" 2>/dev/null \
     && [ -s "$f.deployed" ]; then
    if cmp -s "$f" "$f.deployed"; then echo "  same     $b"; rm -f "$f.deployed"
    else mv "$f.deployed" "$f"; echo "  UPDATED  $b  ($(wc -l < "$f") lines)"; fi
  else
    rm -f "$f.deployed"; echo "  not deployed / unreadable: $b"
  fi
done
echo "Review with: git diff wazuh/rules"
