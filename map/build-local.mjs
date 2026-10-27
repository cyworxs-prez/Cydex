// Build the map as a single self-contained HTML file for local use.
// No Cloudflare, no token, no worker — just one file you can open or serve.
import { readFileSync, writeFileSync } from 'fs';

const bundle = readFileSync('bundle.js', 'utf8');
// MAP_NO_STAMP=1 omits the build timestamp (use it for screenshots you publish).
const built = process.env.MAP_NO_STAMP ? '' : new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, maximum-scale=1, user-scalable=no">
<meta name="color-scheme" content="light">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="robots" content="noindex, nofollow">
<title>Homelab Network Map — VLANs</title>
<style>
  /* user-scalable=no is deliberate: this is a pan/zoom canvas, so pinch must
     drive isoflow rather than the browser zooming the page. overscroll-behavior
     stops iOS pull-to-refresh firing mid-pan. 100dvh after 100vh so mobile
     browser chrome does not clip the bottom control bar. */
  html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden;
               overscroll-behavior: none; -webkit-text-size-adjust: 100%;
               background: #0f172a; }
  #root { width: 100vw; height: 100vh; height: 100dvh; touch-action: none; }
  #built { position: fixed; right: 8px; bottom: 6px; z-index: 9999;
           font: 11px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
           color: #64748b; background: rgba(255,255,255,.75);
           padding: 2px 6px; border-radius: 4px; pointer-events: none; }
  /* On a phone the bottom-right build stamp sits underneath the control bar,
     so move it to the top-right, clear of the title chip on the left. */
  @media (max-width: 700px) {
    #built { bottom: auto; top: calc(8px + env(safe-area-inset-top));
             right: calc(8px + env(safe-area-inset-right)); font-size: 10px; }
  }
</style>
</head>
<body>
<div id="root"></div>
${built ? '<div id="built">built ' + built + '</div>' : ''}
<script>${bundle}</script>
</body>
</html>`;

writeFileSync('homelab-map.html', html);
console.log('homelab-map.html:', html.length, 'bytes  (self-contained, no network deps)');
