#!/bin/bash
# Serve the homelab network map from pve on the MGMT interface only.
#
# Deliberately narrow:
#   - binds to the MGMT address only, NOT 0.0.0.0 - so it is not exposed on any
#     other network the host has an address on.
#   - runs as an unprivileged user with a read-only view of the filesystem.
#   - serves one directory containing one file.
set -euo pipefail

DIR=/opt/homelab-map
BIND=${MAP_BIND:-10.10.130.10}   # override: MAP_BIND=x.x.x.x ./install-map-server.sh
PORT=${MAP_PORT:-8088}
SVCUSER=homelab-map

echo "== 1. content directory"
mkdir -p "$DIR"
chmod 755 "$DIR"

echo "== 2. unprivileged service user"
if ! id -u "$SVCUSER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SVCUSER"
  echo "   created user $SVCUSER"
else
  echo "   user $SVCUSER exists"
fi
chown -R root:"$SVCUSER" "$DIR"
chmod 750 "$DIR"

echo "== 3. systemd unit"
cat > /etc/systemd/system/homelab-map.service <<EOF
[Unit]
Description=Homelab network map (static, MGMT only)
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=$SVCUSER
Group=$SVCUSER
WorkingDirectory=$DIR
ExecStart=/usr/bin/python3 -m http.server $PORT --bind $BIND --directory $DIR
Restart=on-failure
RestartSec=5

# hardening - this serves one static file and needs nothing else
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
ReadOnlyPaths=$DIR
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "   unit written"

echo "== 4. waiting for content before enabling"
if [ -s "$DIR/index.html" ]; then
  systemctl enable --now homelab-map.service
  sleep 2
  systemctl is-active homelab-map.service | sed 's/^/   service: /'
  echo "   listening on: http://$BIND:$PORT/"
else
  echo "   index.html not present yet - unit installed but NOT started."
  echo "   push the map, then: systemctl enable --now homelab-map.service"
fi
