#!/bin/sh
# wazuh MCP launcher.
# Secrets live in 1Password; `op run` resolves the op:// refs in config/wazuh.env at launch.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")" || exit 1
if ! command -v op >/dev/null 2>&1; then
  echo "FATAL: 1Password CLI (op) not found on PATH" >&2; exit 1
fi
# Headless secrets via the service-account token in the login Keychain.
# $(id -un) not $USER: Claude Desktop spawns this with USER unset.
if _T=$(security find-generic-password -a "$(id -un)" -s op-service-account -w 2>/dev/null) && [ -n "$_T" ]; then
  OP_SERVICE_ACCOUNT_TOKEN="$_T"; export OP_SERVICE_ACCOUNT_TOKEN
else
  echo "WARN: op service-account token not in Keychain; falling back to 1Password desktop app" >&2
fi
unset _T
exec op run --no-masking --env-file="$(cd ../../.. && pwd)/config/wazuh.env" -- ./mcp-server-wazuh "$@"
