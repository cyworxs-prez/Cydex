#!/bin/bash
# Wazuh MCP server setup. Run on the admin workstation (macOS), from Terminal:
#     bash ai-ops/mcp/wazuh/setup-wazuh-mcp.sh
#
# WHY IT RUNS ON THE WORKSTATION AND NOT ON THE PROXMOX HOST:
#   The credentials live on CT201; `op` and the service-account token live here. This
#   script is the only place the two meet. Passwords are pulled over ssh into shell
#   variables, verified against the live APIs, written into 1Password, and never printed,
#   never written to disk, and never placed in argv (op reads them on stdin).
#
# PRIVILEGE MODEL:
#   Manager API :55000 -> user 'wazuh'   - full API rights. Needed: the agent, rules,
#                                          stats and cluster tools all live here.
#   Indexer     :9200  -> user 'readall' - READ-ONLY, and it already exists from install.
#     It can read what the server needs: wazuh-alerts-* and
#     wazuh-states-vulnerabilities-*.
#     It CANNOT read _cluster/health - that is a cluster-level right a read-only user is
#     not meant to have, and the first probe of it looked like an auth failure. It is not.
#     If a tool ever needs indexer cluster state it will fail visibly; swap the op:// ref
#     to the admin item and nothing else changes.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
[ -f "$ROOT/config/homelab.env" ] && . "$ROOT/config/homelab.env"
VAULT=${OP_VAULT:-Homelab}   # avoid '&' in vault names - op:// refs cannot carry it
ITEM="wazuh-mcp"
PVE=${PVE_SSH:-root@10.10.130.10}
WZ_HOST=${WAZUH_IP:-10.10.140.11}
WZ_CT=${WAZUH_CTID:-201}
ENVFILE="$ROOT/config/wazuh.env"
BIN="$HERE/mcp-server-wazuh"
REL=https://github.com/gbrigandi/mcp-server-wazuh/releases/latest/download/mcp-server-wazuh-macos-arm64

say(){ printf '\n\033[1m%s\033[0m\n' "$*"; }
die(){ printf '\n!! %s\n' "$*" >&2; exit 1; }

say "1. Preflight"
command -v op >/dev/null || die "1Password CLI (op) not on PATH"
OP_SERVICE_ACCOUNT_TOKEN=$(security find-generic-password -a "$(id -un)" -s op-service-account -w 2>/dev/null) \
  || die "service-account token not in Keychain (service: op-service-account)"
[ -n "$OP_SERVICE_ACCOUNT_TOKEN" ] || die "Keychain returned an empty token"
export OP_SERVICE_ACCOUNT_TOKEN
op vault get "$VAULT" >/dev/null 2>&1 || die "service account cannot see vault $VAULT"
echo "   op authenticates, vault reachable"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$PVE" true 2>/dev/null || die "cannot ssh to $PVE"
echo "   ssh to pve OK"

say "2. Fetching the binary"
if [ ! -x "$BIN" ]; then
  curl -fsSL -o "$BIN" "$REL" || die "download failed"
  chmod +x "$BIN"
  # macOS quarantines anything curl'd; without this Gatekeeper kills it and the MCP
  # server just never starts, with no useful error in the Claude Desktop log.
  xattr -d com.apple.quarantine "$BIN" 2>/dev/null || true
  echo "   downloaded $(file -b "$BIN" | cut -c1-40)"
else
  echo "   already present"
fi
"$BIN" --help >/dev/null 2>&1 || "$BIN" --version >/dev/null 2>&1 || echo "   (note: binary produced no --help/--version; continuing)"

say "3. Reading credentials from the Wazuh CT (never printed)"
CREDS=$(ssh -o BatchMode=yes "$PVE" \
  "pct exec $WZ_CT -- tar xOf /root/wazuh-install-files.tar wazuh-install-files/wazuh-passwords.txt" 2>/dev/null) \
  || die "could not read wazuh-passwords.txt from CT$WZ_CT"
getpw(){ printf '%s\n' "$CREDS" | grep -A1 "username: '$1'" | grep "password:" | head -1 | sed -E "s/.*password: '(.*)'.*/\1/"; }
API_PW=$(getpw wazuh)
IDX_PW=$(getpw readall)
[ -n "$API_PW" ] || die "could not parse the 'wazuh' API password"
[ -n "$IDX_PW" ] || die "could not parse the 'readall' indexer password"
echo "   parsed 2 credentials (${#API_PW} and ${#IDX_PW} chars)"

say "4. Verifying both against the live APIs BEFORE storing anything"
JWT=$(curl -sk -u "wazuh:$API_PW" -X POST \
  "https://$WZ_HOST:55000/security/user/authenticate?raw=true" -m 10 2>/dev/null)
case "$JWT" in ey*) echo "   manager api  wazuh   : OK (jwt ${#JWT} chars)";;
                 *) die "manager API auth FAILED - the tar may be stale (password changed since install)";; esac
CNT=$(curl -sk -u "readall:$IDX_PW" "https://$WZ_HOST:9200/wazuh-alerts-*/_count" -m 10 2>/dev/null | grep -oE '"count":[0-9]+')
[ -n "$CNT" ] || die "indexer auth FAILED for readall"
echo "   indexer      readall : OK ($CNT alerts readable)"

say "5. Writing to 1Password"
EXIST=$(op item get "$ITEM" --vault="$VAULT" --format=json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])' 2>/dev/null)
if [ -n "$EXIST" ]; then
  op item edit "$EXIST" --vault="$VAULT" \
    "api_password[password]=$API_PW" "indexer_password[password]=$IDX_PW" >/dev/null || die "op item edit failed"
  ID="$EXIST"; echo "   updated existing item"
else
  ID=$(op item create --category=login --title="$ITEM" --vault="$VAULT" \
    "username=wazuh" "api_password[password]=$API_PW" "indexer_password[password]=$IDX_PW" \
    "api_username[text]=wazuh" "indexer_username[text]=readall" \
    "notes[text]=Wazuh MCP server. Manager API uses 'wazuh' (full API). Indexer uses 'readall' (read-only, install-time user). Created by setup-wazuh-mcp.sh." \
    --format=json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])') || die "op item create failed"
  echo "   created item"
fi
unset API_PW IDX_PW CREDS
[ -n "$ID" ] || die "no item id returned"
echo "   item id: $ID"

say "6. Writing config/wazuh.env (op:// refs by item ID)"
cat > "$ENVFILE" <<ENV
# Resolved at launch by 'op run'. No secrets in this file.
# vault "Homelab" / item "$ITEM"
WAZUH_API_HOST=$WZ_HOST
WAZUH_API_PORT=55000
WAZUH_API_USERNAME=wazuh
WAZUH_API_PASSWORD=op://$VAULT/$ID/api_password
WAZUH_INDEXER_HOST=$WZ_HOST
WAZUH_INDEXER_PORT=9200
WAZUH_INDEXER_USERNAME=readall
WAZUH_INDEXER_PASSWORD=op://$VAULT/$ID/indexer_password
# Certs are the install-time self-signed set; verification would fail. Traffic is still
# TLS-encrypted; keep both endpoints on a segment only the admin VLAN can reach.
WAZUH_VERIFY_SSL=false
WAZUH_TEST_PROTOCOL=https
RUST_LOG=info
ENV
chmod 600 "$ENVFILE"
echo "   $ENVFILE"

say "7. Launcher: $HERE/run-wazuh-mcp.sh (shipped in the repo)"

say "8. Smoke test - resolve refs and start the server"
if timeout 12 "$HERE/run-wazuh-mcp.sh" </dev/null >/tmp/wz-mcp.out 2>/tmp/wz-mcp.err; then :; fi
if grep -qi "error\|fatal\|denied\|unauthor" /tmp/wz-mcp.err 2>/dev/null; then
  echo "   stderr said:"; head -5 /tmp/wz-mcp.err | sed 's/^/     /'
else
  echo "   started without auth errors ($(wc -c </tmp/wz-mcp.err) bytes stderr)"
fi

say "DONE - add this to claude_desktop_config.json under mcpServers"
cat <<JSON
    "wazuh": {
      "command": "$HERE/run-wazuh-mcp.sh",
      "args": []
    }
JSON
echo
echo "Then restart Claude Desktop. No secrets in that JSON."
