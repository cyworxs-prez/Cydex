#!/bin/sh
# wazuh MCP launcher. Credentials: config/wazuh.env (op:// refs or plain values).
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")" || exit 1
ROOT="$(cd ../../.. && pwd)"
. ../_launch-lib.sh
launch_with_env "$ROOT/config/wazuh.env" ./mcp-server-wazuh "$@"
