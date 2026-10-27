import isoflowPack from '@isoflow/isopacks/dist/isoflow';

const pack = isoflowPack.default || isoflowPack;

export const colors = [
  { id: 'trusted', value: '#2563eb' },
  { id: 'iot', value: '#ea580c' },
  { id: 'mgmt', value: '#7c3aed' },
  { id: 'lab', value: '#16a34a' },
  { id: 'wan', value: '#0f172a' },
  { id: 'vpn', value: '#0ea5e9' },
  { id: 'trunk', value: '#334155' },
  { id: 'mirror', value: '#db2777' },
  { id: 'block', value: '#dc2626' },
  { id: 'direct', value: '#0891b2' },
  { id: 'agent', value: '#0d9488' }
];

// ---------------------------------------------------------------------------
// FICTIONAL reference model. Addresses, IDs and devices are examples - edit
// them to match your own network.
//
// Label cards are as wide as their LONGEST line, and card width is what drives
// collisions and the fit-to-view zoom. Keep every line under ~24 characters.
// ---------------------------------------------------------------------------
export const items = [
  // ---- edge ----
  { id: 'isp', name: 'ISP', icon: 'cloud',
    description: 'WAN uplink<br><b>default gw for</b><br>MGMT · LAB · DIRECT' },
  { id: 'direct', name: 'DIRECT wifi', icon: 'mobiledevice',
    description: 'VLAN 150<br>10.10.150.0/24<br><b>no VPN</b><br>isolated from all<br>internal segments' },
  { id: 'vpnprov', name: 'VPN provider', icon: 'lock',
    description: 'WireGuard<br><b>TRUSTED egress</b><br>not IDS-inspected' },

  // ---- core (MGMT) ----
  { id: 'opnsense', name: 'firewall', icon: 'firewall',
    description: 'OPNsense VM 200<br>router · DHCP · DNS<br>Suricata (IDS)<br>gw .1 on each VLAN' },
  { id: 'pve', name: 'hypervisor', icon: 'tower',
    description: 'Proxmox VE<br>10.10.130.10<br>VLAN-aware bridge' },
  { id: 'switch', name: 'switch', icon: 'switch-module',
    description: 'managed PoE switch<br>trunk to hypervisor' },
  { id: 'ap1', name: 'AP 1', icon: 'router',
    description: 'SSIDs → VLANs' },
  { id: 'ap2', name: 'AP 2', icon: 'router',
    description: 'SSIDs → VLANs' },

  // ---- TRUSTED ----
  { id: 'workstation', name: 'admin workstation', icon: 'desktop',
    description: 'VLAN 110<br>MCP clients<br>Wazuh agent' },

  // ---- DIRECT ----
  { id: 'laptop', name: 'laptop', icon: 'laptop', description: 'VLAN 150' },
  { id: 'phone', name: 'phone', icon: 'mobiledevice', description: 'VLAN 150' },

  // ---- LAB (SOC) ----
  { id: 'wazuh', name: 'wazuh CT 201', icon: 'server',
    description: '10.10.140.11<br>SIEM · indexer · dash<br>syslog sink :514' },
  { id: 'zeek', name: 'zeek CT 206', icon: 'server',
    description: '10.10.140.21<br>JSON logs<br><b>Intel framework</b><br>fed by SPAN mirror' },
  { id: 'netalertx', name: 'netalertx CT 203', icon: 'server',
    description: '10.10.140.13<br>device discovery' },
  { id: 'greenbone', name: 'greenbone CT 202', icon: 'server',
    description: '10.10.140.12<br>on-demand scans<br>KEV/EPSS ranking' },
  { id: 'guac', name: 'guac CT 205', icon: 'server',
    description: '10.10.140.20<br>Apache Guacamole<br>remote-access gateway' },
  { id: 'kali', name: 'kali VM 204', icon: 'block',
    description: 'stopped by default<br>reached via guac only' },

  // ---- IoT ----
  { id: 'cameras', name: 'cameras', icon: 'image', description: 'cloud-connected' },
  { id: 'media', name: 'media devices', icon: 'desktop', description: 'TVs · speakers' },
  { id: 'smarthome', name: 'smart-home', icon: 'cube', description: 'lights · plugs ·<br>sensors' }
];

// ---------------------------------------------------------------------------
// Placement helpers.
//
// isoflow projects tiles as  u = x - y  (screen horizontal, right)
//                            v = x + y  (screen VERTICAL, up).
// Laying out in (x, y) makes collisions impossible to reason about, so every
// view below is authored in SCREEN space and converted here. u + v must be
// even for the result to land on an integer tile.
//
// Clearance rules, measured from the rendered DOM (1 u ~= 95px unprojected,
// 1 v ~= 48px, a label card is ~170-245px wide and ~79px tall):
//   - a label card is ~174px wide = 1.83 u, so two nodes need du >= 3;
//   - two nodes in the SAME screen column need dv >= 6, which is what it takes
//     for a label to clear the icon of the node below it (icons are 69-223px).
// Zone rectangles are the expensive part: a rect's screen width is dx+dy of its
// contents, so a big cluster's plate sprawls far past the cluster and drags the
// fit-to-view zoom down. Topology keeps them (small clusters); the Segments view
// has more hosts and uses coloured headings instead.
// ---------------------------------------------------------------------------
const ICON_OF = Object.fromEntries(items.map((i) => [i.id, i.icon]));

// Label sits `labelHeight` above the tile; it has to clear its own icon, and
// icons vary from 69px (server) to 221px (tower).
const LABEL_HEIGHT = {
  tower: 250, image: 140, cloud: 126, lock: 121, mobiledevice: 121, truck: 125,
  speech: 119, desktop: 117, firewall: 112, laptop: 111, server: 110,
  router: 108, diamond: 108, printer: 107, cube: 105, 'switch-module': 81, block: 75
};

const at = (id, u, v) => {
  if ((u + v) % 2 !== 0) throw new Error(`${id}: u+v must be even (got ${u},${v})`);
  return { id, tile: { x: (u + v) / 2, y: (v - u) / 2 },
           labelHeight: LABEL_HEIGHT[ICON_OF[id]] || 115 };
};

const tx = (id, u, v, content, fontSize = 0.38) =>
  ({ id, tile: { x: (u + v) / 2, y: (v - u) / 2 }, content, fontSize });

// `via` = waypoint tiles, so routes bend around nodes instead of through them.
const conn = (id, fromItem, toItem, opts = {}) => {
  const { via = [], ...rest } = opts;
  const anchors = [{ id: `${id}-a`, ref: { item: fromItem } }];
  via.forEach((t, i) => anchors.push({ id: `${id}-v${i}`, ref: { tile: { x: t[0], y: t[1] } } }));
  anchors.push({ id: `${id}-b`, ref: { item: toItem } });
  return { id, anchors, ...rest };
};

// rectangle that hugs a set of screen-space points with a 1-tile margin
const hug = (id, color, pts, m = 1) => {
  const xs = pts.map(([u, v]) => (u + v) / 2);
  const ys = pts.map(([u, v]) => (v - u) / 2);
  return { id, color,
    from: { x: Math.min(...xs) - m, y: Math.min(...ys) - m },
    to:   { x: Math.max(...xs) + m, y: Math.max(...ys) + m } };
};

// ===========================================================================
// VIEW 1 — TOPOLOGY
// ===========================================================================
const P1 = {
  switch:   [-3, 3],  pve: [0, 0],   opnsense: [3, 3],
  ap1:      [-3, -3], ap2: [3, -3],
  wazuh:    [-3, 21], netalertx: [-3, 15],
  zeek:     [0, 24],  greenbone: [0, 18],
  guac:     [3, 21],  kali: [3, 15],
  smarthome:[-14, 6], media: [-11, 1], cameras: [-14, -2],
  workstation: [11, -1],
  direct:   [18, 6],  laptop: [21, 3],  phone: [21, 9],
  isp:      [-3, -13], vpnprov: [3, -13]
};

const topologyItems = Object.entries(P1).map(([id, [u, v]]) => at(id, u, v));

const topologyRects = [
  hug('r-mgmt', 'mgmt', [P1.switch, P1.pve, P1.opnsense, P1.ap1, P1.ap2]),
  hug('r-lab', 'lab', [P1.wazuh, P1.zeek, P1.guac, P1.netalertx, P1.greenbone, P1.kali]),
  hug('r-iot', 'iot', [P1.smarthome, P1.media, P1.cameras]),
  hug('r-trusted', 'trusted', [P1.workstation]),
  hug('r-direct', 'direct', [P1.direct, P1.laptop, P1.phone])
];

const topologyConnectors = [
  conn('c-wan', 'isp', 'opnsense', { color: 'wan', width: 12, description: 'WAN' }),
  conn('c-vpn', 'opnsense', 'vpnprov', { color: 'vpn', width: 10, style: 'DASHED',
        description: 'TRUSTED egress' }),
  conn('c-vm', 'pve', 'opnsense', { color: 'mgmt', width: 8, style: 'DOTTED',
        description: 'hosts the firewall VM' }),
  conn('c-trunk', 'pve', 'switch', { color: 'trunk', width: 12, description: 'VLAN trunk' }),
  conn('c-ap1', 'switch', 'ap1', { color: 'mgmt', width: 6, description: 'PoE' }),
  conn('c-ap2', 'switch', 'ap2', { color: 'mgmt', width: 6, description: 'PoE' }),
  conn('c-ws', 'ap2', 'workstation', { color: 'trusted', width: 8, style: 'DASHED',
        description: 'VLAN 110' }),
  conn('c-iot', 'ap1', 'media', { color: 'iot', width: 8, style: 'DASHED',
        description: 'VLAN 120' }),
  conn('c-direct', 'ap2', 'direct', { color: 'direct', width: 8, style: 'DASHED',
        description: 'VLAN 150' }),
  conn('c-direct-wan', 'direct', 'isp', { color: 'direct', width: 6, style: 'DOTTED',
        description: 'straight out — no VPN' }),
  conn('c-lab', 'pve', 'wazuh', { color: 'lab', width: 6, style: 'DOTTED',
        description: 'VLAN 140' })
];

const topologyText = [
  tx('t-internet', 0, -18, 'INTERNET', 0.45),
  tx('t-mgmt', -8, -6, 'MGMT — VLAN 130'),
  tx('t-lab', -9, 17, 'LAB — VLAN 140 (SOC)'),
  tx('t-iot', -20, 2, 'IoT — VLAN 120'),
  tx('t-trusted', 8, -8, 'TRUSTED — VLAN 110'),
  tx('t-direct', 27, 11, 'DIRECT — VLAN 150 (no VPN)')
];

// ===========================================================================
// VIEW 2 — SOC flows
// ===========================================================================
const P2 = {
  opnsense: [-9, 3],  pve: [-6, -6],
  zeek:     [-6, 6],  netalertx: [-3, -9],
  wazuh:    [0, 0],   greenbone: [3, -9],
  guac:     [6, 12],  kali: [9, 9],
  workstation: [3, 15]
};

const socItems = Object.entries(P2).map(([id, [u, v]]) => at(id, u, v));

const socConnectors = [
  conn('g-mirror', 'pve', 'zeek', { color: 'mirror', width: 12, style: 'DASHED',
        description: 'SPAN mirror (tc mirred)' }),
  conn('g-syslog', 'opnsense', 'wazuh', { color: 'mirror', width: 8, style: 'DOTTED',
        description: 'syslog :514' }),
  conn('g-guac-kali', 'guac', 'kali', { color: 'lab', width: 10, description: 'RDP' }),
  conn('g-guac-user', 'workstation', 'guac', { color: 'trusted', width: 8, style: 'DASHED',
        description: 'HTTPS browser session' }),
  conn('a-pve', 'pve', 'wazuh', { color: 'agent', width: 6, style: 'DOTTED', description: 'Wazuh agent' }),
  conn('a-zeek', 'zeek', 'wazuh', { color: 'agent', width: 6, style: 'DOTTED', description: 'Wazuh agent' }),
  conn('a-nax', 'netalertx', 'wazuh', { color: 'agent', width: 6, style: 'DOTTED', description: 'Wazuh agent' }),
  conn('a-gb', 'greenbone', 'wazuh', { color: 'agent', width: 6, style: 'DOTTED', description: 'Wazuh agent' }),
  conn('a-ws', 'workstation', 'wazuh', { color: 'agent', width: 6, style: 'DOTTED', description: 'Wazuh agent' })
];

const socText = [
  tx('g-t1', -15, 3, 'SOC — data flows', 0.5),
  tx('g-t2', 15, 9, 'kali is reached through guac', 0.34),
  tx('g-t3', -3, -15, 'teal dotted = Wazuh agent → manager', 0.34)
];

// ===========================================================================
// VIEW 3 — SEGMENTS (client categories by segment)
// ===========================================================================
const P3 = {
  opnsense: [-3, -9],
  cameras: [-12, 4], media: [-12, -2], smarthome: [-9, 1],
  workstation: [12, 14],
  laptop: [12, 0], phone: [12, -6]
};

const deviceItems = Object.entries(P3).map(([id, [u, v]]) => at(id, u, v));

const deviceRects = [
  hug('d-iot', 'iot', [P3.cameras, P3.media, P3.smarthome]),
  hug('d-trusted', 'trusted', [P3.workstation]),
  hug('d-direct', 'direct', [P3.laptop, P3.phone])
];

const deviceConnectors = [
  conn('d-iot', 'opnsense', 'smarthome', { color: 'iot', width: 8, style: 'DASHED',
        description: 'VLAN 120 · DNS forced · 853 blocked' }),
  conn('d-tr', 'opnsense', 'workstation', { color: 'trusted', width: 8, style: 'DASHED',
        description: 'VLAN 110 · VPN egress' }),
  conn('d-dir', 'opnsense', 'phone', { color: 'direct', width: 8, style: 'DASHED',
        description: 'VLAN 150 · ISP direct, no VPN' })
];

const deviceText = [
  tx('d-t1', -18, 1, 'IoT — VLAN 120', 0.44),
  tx('d-t2', 6, 18, 'TRUSTED — VLAN 110', 0.44),
  tx('d-t4', 4, -8, 'DIRECT — VLAN 150 · no VPN', 0.44)
];

// ===========================================================================
// VIEW 4 — SECURITY CONTROLS
// ===========================================================================
const P4 = {
  isp: [-3, -9], vpnprov: [9, -3],
  opnsense: [0, 0],
  smarthome: [-9, -3],
  workstation: [9, 3], pve: [0, 12], zeek: [-6, 12], wazuh: [6, 12],
  direct: [12, -6]
};

const controlItems = Object.entries(P4).map(([id, [u, v]]) => at(id, u, v));

const controlConnectors = [
  conn('s-wan', 'isp', 'opnsense', { color: 'wan', width: 12, description: 'WAN' }),
  conn('s-vpn', 'opnsense', 'vpnprov', { color: 'vpn', width: 10, style: 'DASHED',
        description: 'TRUSTED egress — not IDS-inspected' }),
  conn('s-dns', 'smarthome', 'opnsense', { color: 'iot', width: 8, style: 'DASHED',
        description: 'DNS :53 force-redirected' }),
  conn('s-dot', 'smarthome', 'isp', { color: 'block', width: 6, style: 'DOTTED',
        description: 'DoT/DoQ :853 blocked' }),
  conn('s-mirror', 'pve', 'zeek', { color: 'mirror', width: 10, style: 'DASHED',
        description: 'SPAN → Zeek' }),
  conn('s-syslog', 'opnsense', 'wazuh', { color: 'mirror', width: 6, style: 'DOTTED',
        description: 'syslog :514' }),
  conn('s-dir-out', 'direct', 'opnsense', { color: 'block', width: 10, style: 'DOTTED',
        description: 'VLAN 150 → internal: blocked' })
];

const controlText = [
  tx('s-t1', 6, -12, 'ENFORCEMENT POINTS', 0.5),
  tx('s-t2', -15, -1, 'IoT: DNS forced · 853 blocked', 0.34),
  tx('s-t3', 0, 24, 'Telemetry: SPAN → Zeek · syslog → Wazuh', 0.34)
];

export const model = {
  version: '1.1.1',
  title: 'Homelab SOC — fictional reference network',
  icons: pack.icons,
  colors,
  items,
  views: [
    { id: 'topology', name: 'Topology', items: topologyItems, rectangles: topologyRects,
      connectors: topologyConnectors, textBoxes: topologyText },
    { id: 'soc', name: 'SOC flows', items: socItems, rectangles: [],
      connectors: socConnectors, textBoxes: socText },
    { id: 'devices', name: 'Segments', items: deviceItems, rectangles: deviceRects,
      connectors: deviceConnectors, textBoxes: deviceText },
    { id: 'controls', name: 'Security controls', items: controlItems, rectangles: [],
      connectors: controlConnectors, textBoxes: controlText }
  ]
};
