# 9. Network map

An isometric map (isoflow) with four views - Topology, SOC flows, Devices, Security
controls - built to one self-contained HTML file and served from the Proxmox host on MGMT.

![Security controls view](../img/controls.png)

## 9.1 Build

```bash
cd map
npm ci
npm run check            # regenerates model.mjs + static layout check
npm run build            # vendors patched isoflow, bundles, emits homelab-map.html
npx playwright install chromium && npm run render-check   # headless: 0 label collisions
```

`model.js` is authored in **screen space** (`u = x-y`, `v = x+y`) - see `map/LAYOUT.md`.
Authoring in raw `(x, y)` produces overlapping labels. `patch-isoflow.mjs` adds pinch/wheel
zoom (isoflow 1.1.1 has none) and aborts if its anchors stop matching after an upgrade.

## 9.2 Serve it from the host

```bash
# on the Proxmox host (once)
MAP_BIND=10.10.130.10 bash map/install-map-server.sh
# from the workstation, after every model change
map/publish-local.sh     # build -> push -> byte-compare what is served
```

The unit runs `python3 -m http.server` as an unprivileged user, bound to the MGMT address
only, with systemd sandboxing.

A published map that no longer matches the network is worse than no map. Change a segment
or host -> update `model.js` -> publish.
