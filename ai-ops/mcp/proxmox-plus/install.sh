#!/bin/bash
# Install proxmox-mcp-plus into ~/.proxmoxmcp (or $1) from the pinned VERSION.
# NO SECRETS ARE STORED HERE - the API token and SSH key come from 1Password.
#   op://Homelab/proxmox-api-token/{token name,credential}
#   op://Homelab/proxmox-mcp-ssh-key/private key
# Requires: 1Password desktop app unlocked, `op` CLI on PATH.
set -euo pipefail
D=$(cd "$(dirname "$0")" && pwd)
T=${1:-$HOME/.proxmoxmcp}
ROOT=$(cd "$D/../../.." && pwd)
[ -f "$ROOT/config/homelab.env" ] && . "$ROOT/config/homelab.env"
PVE_HOST=${PVE_HOST:-10.10.130.10}
command -v op >/dev/null || { echo "FATAL: 1Password CLI (op) not found"; exit 1; }
echo "restoring into $T"
mkdir -p "$T"

# --- rebuild config.json from the sanitized template + 1Password ---
sed -e "s#__TARGET__#$T#g" -e "s#__PVE_HOST__#$PVE_HOST#g" "$D/config.template.json" \
  | op inject -o "$T/config.json"
chmod 600 "$T/config.json"

# --- SSH key ---
op read 'op://Homelab/proxmox-mcp-ssh-key/private key' > "$T/build_key"
chmod 600 "$T/build_key"
ssh-keygen -y -f "$T/build_key" > "$T/build_key.pub"

# --- venv + pinned package ---
python3 -m venv "$T/venv"
"$T/venv/bin/pip" install --quiet --upgrade pip
"$T/venv/bin/pip" install --quiet "$(head -1 "$D/VERSION")"
echo "installed: $("$T/venv/bin/python" -c 'import importlib.metadata as m;print(m.version("proxmox-mcp-plus"))')"
echo "NOTE: install $T/build_key.pub in root@$PVE_HOST:~/.ssh/authorized_keys for guest command execution"
echo "NOTE: replace the two REPLACE_ME approval tokens in $T/config.json if you enable approval mode"
