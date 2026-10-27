// Static layout check for model.js — run this BEFORE building.
//
//   node check-layout.mjs
//
// isoflow projects tiles as u = x-y (screen horizontal) and v = x+y (screen
// VERTICAL, up), so two nodes that look far apart in (x, y) can be stacked on
// top of each other on screen. This checks the layout in SCREEN space:
//   - a label card is ~178px wide (1.9 u), so two nodes need du >= 2;
//   - two nodes in the same screen column need dv >= (labelHeight + 80) / 47.6,
//     which is what it takes for the lower label to clear the upper icon;
//   - labelHeight must exceed (icon height - 39) or the label lands on its own icon;
//   - zone plates must not intersect (a plate's screen width is dx+dy of its
//     contents, so plates sprawl much further than the cluster they contain);
//   - text boxes are drawn along the u axis and are WIDE.
// It also prints dx+dy per view, which is what sets the fit-to-view zoom:
// zoom ~= 1789 / (dx + dy).
//
// check-render.mjs is the empirical counterpart — it renders and measures the
// real DOM. Run both; this one is fast, that one is authoritative.
import { model } from './model.mjs';
const PXU = 95, PXV = 47.6, CARD_W = 178, CARD_H = 80;   // measured from the DOM
const ICON_H = { tower:223, image:135, cloud:121, lock:116, mobiledevice:116, truck:120,
  speech:114, desktop:112, firewall:107, laptop:106, server:105, router:103,
  diamond:103, printer:102, cube:100, 'switch-module':76, block:70 };
const icon = Object.fromEntries(model.items.map(i => [i.id, i.icon]));
let bad = 0;
const say = (s) => { console.log('   ' + s); bad++; };

for (const view of model.views) {
  console.log(`\n== ${view.name}`);
  const P = view.items.map(it => ({ id: it.id, u: it.tile.x - it.tile.y, v: it.tile.x + it.tile.y,
                                    lh: it.labelHeight, ih: ICON_H[icon[it.id]] || 110 }));
  for (let i = 0; i < P.length; i++) for (let j = i + 1; j < P.length; j++) {
    const a = P[i], b = P[j];
    const du = Math.abs(a.u - b.u) * PXU;
    if (du >= CARD_W + 20) continue;                      // labels can never touch
    const lo = a.v < b.v ? a : b, hi = a.v < b.v ? b : a;  // lo sits lower on screen
    const need = (lo.lh + CARD_H) / PXV;                   // lo's label must clear hi's icon
    const dv = hi.v - lo.v;
    if (dv < need) say(`${lo.id} / ${hi.id}: du=${(du/PXU).toFixed(0)}u dv=${dv} but needs dv>=${need.toFixed(1)}`);
  }
  for (const it of view.items) {
    const need = (ICON_H[icon[it.id]] || 110) - 39;
    if (it.labelHeight < need) say(`${it.id}: labelHeight ${it.labelHeight} < ${need} — label lands on its own icon`);
  }
  // text boxes are drawn along the u axis and are WIDE: ~0.17u per character
  for (const t of view.textBoxes || []) {
    const tu = t.tile.x - t.tile.y, tv = t.tile.x + t.tile.y;
    const halfU = t.content.length * 0.115 + 0.94;
    for (const p of P) {
      if (Math.abs(p.v - tv) >= 4) continue;
      if (Math.abs(p.u - tu) < halfU)
        say(`text "${t.content.slice(0,22)}" runs into ${p.id} (du=${Math.abs(p.u-tu)}, needs ${halfU.toFixed(1)})`);
    }
  }

  const R = view.rectangles || [];
  for (let i = 0; i < R.length; i++) for (let j = i + 1; j < R.length; j++) {
    const a = R[i], b = R[j];
    if (a.from.x <= b.to.x && b.from.x <= a.to.x && a.from.y <= b.to.y && b.from.y <= a.to.y)
      say(`zone plates ${a.id} and ${b.id} overlap`);
  }
  for (const it of [...view.items, ...(view.textBoxes || [])]) {
    for (const r of R) {
      const inside = it.tile.x >= r.from.x && it.tile.x <= r.to.x && it.tile.y >= r.from.y && it.tile.y <= r.to.y;
      const owns = (view.rectangles || []).length && r.id.includes('x');   // never true; kept explicit
      if (inside && !(view.items.includes(it) && true)) void owns;
    }
  }
  const all = [...view.items, ...(view.textBoxes || []), ...R.flatMap(r => [{tile:r.from},{tile:r.to}])];
  const xs = all.map(o => o.tile.x), ys = all.map(o => o.tile.y);
  const B = (Math.max(...xs) - Math.min(...xs)) + (Math.max(...ys) - Math.min(...ys));
  console.log(`   extent dx+dy = ${B}  -> fit zoom ~${(1789 / B).toFixed(0)}%`);
}
console.log(bad ? `\n${bad} layout problem(s)` : '\nlayout OK');
