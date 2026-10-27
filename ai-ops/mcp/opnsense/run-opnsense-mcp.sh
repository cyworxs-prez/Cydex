#!/bin/sh
# opnsense MCP launcher.
# Secrets live in 1Password; `op run` resolves the op:// refs in config/opnsense.env at launch.
# Requires the 1Password desktop app to be unlocked.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
if ! command -v op >/dev/null 2>&1; then
  echo "FATAL: 1Password CLI (op) not found on PATH" >&2; exit 1
fi
# Headless secrets. Prefer the 1Password service-account token stored in the login
# Keychain so this resolves op:// refs with the desktop app locked or absent.
# Falls back to the desktop-app path if the Keychain item is missing, but says so on
# stderr rather than failing silently - a silent fallback would look headless until
# the first time the Mac is locked.
# NOTE: $(id -un), not $USER - this is spawned by Claude Desktop, where USER can be unset.
if _T=$(security find-generic-password -a "$(id -un)" -s op-service-account -w 2>/dev/null) && [ -n "$_T" ]; then
  OP_SERVICE_ACCOUNT_TOKEN="$_T"; export OP_SERVICE_ACCOUNT_TOKEN
else
  echo "WARN: op service-account token not in Keychain; falling back to 1Password desktop app" >&2
fi
unset _T

exec op run --no-masking --env-file="$(cd ../../.. && pwd)/config/opnsense.env" -- node "${OPNSENSE_MCP_INDEX:-$(npm root -g)/@richard-stovall/opnsense-mcp-server/index.js}"
