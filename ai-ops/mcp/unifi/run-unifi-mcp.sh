#!/bin/sh
# unifi MCP launcher - OPTIONAL, only if your switch / APs / gateway are UniFi.
# Credentials: config/unifi.env (op:// refs or plain values). Install the server first:
#   pipx install unifi-mcp-server==0.2.5
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$(dirname "$0")" || exit 1
ROOT="$(cd ../../.. && pwd)"
. ../_launch-lib.sh
command -v unifi-mcp-server >/dev/null 2>&1 || { echo "FATAL: unifi-mcp-server not on PATH (pipx install unifi-mcp-server)" >&2; exit 1; }
# The server can send tool inputs/outputs to a third-party analytics service (agnost.ai).
# It is off by default; this keeps it off unless config/unifi.env deliberately turns it on.
export AGNOST_ENABLED=false
launch_with_env "$ROOT/config/unifi.env" unifi-mcp-server "$@"
