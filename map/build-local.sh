#!/bin/sh
# Build the homelab map as ONE self-contained HTML file, for local use only.
#
#   esbuild  app.jsx + model.js -> bundle.js
#   node     build-local.mjs    -> homelab-map.html
#
# No Cloudflare, no deploy token, no 1Password dependency. The output is a single
# file with everything inlined — open it directly, or drop it on any static server.
set -e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"

command -v node >/dev/null || { echo "FATAL: node not found"; exit 1; }

echo "==> 1/3  vendoring the patched isoflow"
node patch-isoflow.mjs

echo "==> 2/3  bundling app.jsx + model.js"
./node_modules/.bin/esbuild app.jsx \
  --bundle \
  --format=iife \
  --loader:.js=jsx \
  --jsx=automatic \
  --define:process.env.NODE_ENV='"production"' \
  --minify \
  --outfile=bundle.js \
  --log-level=warning
echo "    bundle.js: $(wc -c < bundle.js | tr -d ' ') bytes"

echo "==> 3/3  emitting standalone HTML"
node build-local.mjs

echo
echo "==> homelab-map.html ready ($(wc -c < homelab-map.html | tr -d ' ') bytes)"
echo "    open locally :  open homelab-map.html"
echo "    serve on LAN :  python3 -m http.server 8088   (then http://<host>:8088/homelab-map.html)"
