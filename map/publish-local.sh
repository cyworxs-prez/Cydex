#!/bin/sh
# Rebuild the map from model.js and publish it to the pve map server.
#
#   ./publish-local.sh
#
# One command: bundle -> standalone HTML -> push to pve -> verify it serves.
# No Cloudflare, no token, no 1Password dependency.
set -e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
[ -f ../config/homelab.env ] && . ../config/homelab.env

PVE=${MAP_BIND:-10.10.130.10}
URL="http://$PVE:${MAP_PORT:-8088}/"

echo "==> building"
./build-local.sh

echo
echo "==> publishing to $PVE"
ssh -o ConnectTimeout=15 root@"$PVE" \
  'cat > /opt/homelab-map/index.html && chown root:homelab-map /opt/homelab-map/index.html && chmod 640 /opt/homelab-map/index.html' \
  < homelab-map.html

echo "==> verifying"
LOCAL=$(wc -c < homelab-map.html | tr -d ' ')
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL")
SERVED=$(curl -s -o /dev/null -w '%{size_download}' --max-time 10 "$URL")

echo "    local  : $LOCAL bytes"
echo "    served : $SERVED bytes (HTTP $CODE)"

if [ "$CODE" = "200" ] && [ "$LOCAL" = "$SERVED" ]; then
  echo "    OK - $URL"
else
  echo "    MISMATCH - check 'systemctl status homelab-map' on $PVE"
  exit 1
fi
