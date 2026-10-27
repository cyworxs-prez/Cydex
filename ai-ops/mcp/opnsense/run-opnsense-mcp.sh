#!/bin/sh
# opnsense MCP launcher. Credentials: config/opnsense.env (op:// refs or plain values).
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")" || exit 1
ROOT="$(cd ../../.. && pwd)"
. ../_launch-lib.sh
launch_with_env "$ROOT/config/opnsense.env" \
  node "${OPNSENSE_MCP_INDEX:-$(npm root -g)/@richard-stovall/opnsense-mcp-server/index.js}"
