// Render every view headless and report label collisions.
//
//   node check-render.mjs            # uses ./homelab-map.html
//   node check-render.mjs <path>
//
// Three classes of defect, all of which have shipped to the live map before:
//   card<>card        two label cards overlap
//   card<>other icon  a label lands on a NEIGHBOUR's icon
//   own icon          a label sits on the icon it belongs to (labelHeight too low)
// A clean run prints 0 for all three in all four views.
import { chromium } from 'playwright';
const FILE = process.argv[2] || new URL('./homelab-map.html', import.meta.url).pathname;
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1700, height: 1050 } })).newPage();
const errs = [];
p.on('pageerror', e => errs.push(e.message.slice(0, 140)));
await p.goto('file://' + FILE + '?cb=' + Date.now(), { waitUntil: 'networkidle', timeout: 60000 });
await p.waitForTimeout(3500);
console.log('page errors:', errs.length ? errs.join(' | ') : 'none');
let bad = 0;
for (const v of ['Topology', 'SOC flows', 'Segments', 'Security controls']) {
  await p.locator(`button:has-text("${v}")`).first().click();
  await p.waitForTimeout(3000);
  const r = await p.evaluate(() => {
    const zoomEl = [...document.querySelectorAll('*')].find(e => /^\d+%$/.test((e.innerText || '').trim()));
    const cards = [], icons = [];
    document.querySelectorAll('.css-1cgo1qv').forEach(el => {           // isoflow label card
      const b = el.getBoundingClientRect();
      if (b.width > 5) cards.push({ name: (el.innerText || '').trim().split('\n')[0].slice(0, 20),
                                    x: b.x, y: b.y, w: b.width, h: b.height });
    });
    document.querySelectorAll('img').forEach(el => {
      const b = el.getBoundingClientRect();
      if (b.width > 8 && !el.closest('[style*="fixed"]')) icons.push({ x: b.x, y: b.y, w: b.width, h: b.height });
    });
    // greedy 1:1 match card -> the icon it labels (icon sits directly below)
    const pairs = [];
    cards.forEach((c, i) => icons.forEach((ic, j) => {
      const dx = Math.abs((c.x + c.w / 2) - (ic.x + ic.w / 2));
      const dy = (ic.y + ic.h) - (c.y + c.h);
      if (dy >= -5) pairs.push({ i, j, cost: dx * 4 + dy });
    }));
    pairs.sort((a, b) => a.cost - b.cost);
    const ci = new Array(cards.length).fill(-1), used = new Set();
    pairs.forEach(pr => { if (ci[pr.i] === -1 && !used.has(pr.j)) { ci[pr.i] = pr.j; used.add(pr.j); } });
    icons.forEach((ic, j) => { const k = ci.indexOf(j); ic.own = k >= 0 ? cards[k].name : null; });
    const ov = (a, c) => ({ ox: Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x),
                            oy: Math.min(a.y + a.h, c.y + c.h) - Math.max(a.y, c.y) });
    const cc = [], fi = [], own = [];
    for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) {
      const o = ov(cards[i], cards[j]);
      if (o.ox > 0 && o.oy > 0) cc.push(`${cards[i].name} <> ${cards[j].name}`);
    }
    cards.forEach(c => icons.forEach(ic => {
      const o = ov(c, ic);
      if (o.ox <= 0 || o.oy <= 0) return;
      if (ic.own === c.name) own.push(`${c.name} (${Math.round(o.oy)}px)`);
      else fi.push(`${c.name} <> ${ic.own || '?'}'s icon`);
    }));
    return { zoom: zoomEl ? zoomEl.innerText.trim() : '?', nc: cards.length, cc, fi, own };
  });
  bad += r.cc.length + r.fi.length + r.own.length;
  console.log(`\n== ${v}  zoom ${r.zoom}  cards ${r.nc}`);
  console.log(`   card<>card ${r.cc.length}`); r.cc.forEach(s => console.log('      ' + s));
  console.log(`   card<>other icon ${r.fi.length}`); r.fi.forEach(s => console.log('      ' + s));
  console.log(`   label on own icon ${r.own.length}`); r.own.forEach(s => console.log('      ' + s));
}
await b.close();
console.log(bad ? `\n${bad} collision(s)` : '\nno collisions');
process.exit(bad ? 1 : 0);
