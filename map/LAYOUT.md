# Map layout checks

`model.js` is authored in **screen space**. isoflow projects a tile at `(x, y)` to

    u = x - y      screen horizontal, right
    v = x + y      screen VERTICAL, up

so two nodes that look well separated in `(x, y)` can land on top of each other
on screen. Every view therefore declares positions as `(u, v)` in a `P<n>` table
and `at()` converts them (`x = (u+v)/2`, `y = (v-u)/2`; `u + v` must be even).

## The two checks

    node check-layout.mjs        # static, fast — reads model.mjs
    node check-render.mjs        # renders headless and measures the real DOM

`check-layout.mjs` needs an ESM-resolvable copy of the model:

    sed 's|@isoflow/isopacks/dist/isoflow|@isoflow/isopacks/dist/isoflow.js|' model.js > model.mjs

Run the static one while editing; run the render one before publishing. The
static check predicts the fit-to-view zoom (`1789 / (dx + dy)`) and has matched
the rendered zoom to within ~2 points.

## Measured geometry (1700px viewport, from the DOM)

| thing | unprojected px | in tile units |
|---|---|---|
| 1 u (screen horizontal) | 95 | — |
| 1 v (screen vertical) | 47.6 | — |
| label card | 178 x 80 | 1.9 u x 1.7 v |
| icons | 69 (block) - 223 (tower) tall | up to 4.7 v |

`labelHeight` is per-icon: the gap between a label's bottom and its icon's top
is `labelHeight - iconHeight + 39`, so `labelHeight` has to be at least
`iconHeight - 39` and about `iconHeight + 5` looks right.

## Why label width matters more than anything else

A card is as wide as its **longest** description line, and card width is what
drives both collisions and the zoom. Keeping every line under ~24 characters
keeps cards narrow (~178px), which is what lets many hosts fit in one view. Add detail by adding **lines**, not by making lines longer.

## Why zone plates are expensive

A rectangle's screen width is `dx + dy` of its contents, so a plate always
sprawls well past the cluster inside it. Each plate costs a few zoom points. They are worth it — segmentation is the point of the map —
but the clusters have to be packed so the plates do not intersect, which
`check-layout.mjs` verifies.

## Zoom and gestures

isoflow 1.1.1 ships almost no usable zoom, so `zoom.js` replaces it:

| | before | now |
|---|---|---|
| pinch | none — the touch handlers read `touches[0]`, so two fingers panned | real pinch: zoom + pan together, anchored on the midpoint |
| wheel / trackpad | none | zoom anchored on the cursor; `ctrl`+wheel (trackpad pinch) is scaled separately |
| double tap / double click | none | zoom in a step at that point (`alt` to go out) |
| keys | none | `+` / `-` about the viewport centre |
| range | `[0.2, 1]`, and **the +/- buttons' `disabled` conditions are swapped**, so reaching 100% greyed out zoom-out and stranded you there | `[0.05, 3]`, symmetric — no dead ends |
| anchor | renderer centre, so magnifying walked away from what you were reading | the point you gestured on, to within 0.05px |
| phone landing view | fit-to-view = **8%**, where not one label is readable | 45%, centred; `⛶` still gives the 8% overview |

### Why the library is patched rather than wrapped

The uiState store lives behind a React context that is only readable from inside
`<Isoflow>`'s own subtree, and the component takes no children. `patch-isoflow.mjs`
therefore rewrites three exact strings in the shipped bundle — publishing the
store on `window`, letting a gesture skip the 250ms transform tween, and dropping
the built-in zoom control (it renders bottom-left, underneath the phone control
bar) — and writes `vendor/isoflow.patched.js`, which `app.jsx` imports instead of
the package. Each anchor must match **exactly once** or the build aborts; a
silently skipped patch would ship a subtly broken map with no error.

Re-run `node patch-isoflow.mjs` after any `npm install` (`build-local.sh` does).

### Why not just CSS-scale a wrapper

isoflow converts pointer positions to tiles using the renderer's own rect and its
`zoom` value. An outer `transform: scale()` is invisible to that maths, so
dragging would pan at the wrong rate and hit-testing would drift. `zoom.js`
drives isoflow's real `zoom` + `scroll` instead:

    screen = centre + scroll + zoom * point

so holding the point under `from` underneath `to` while zoom goes `z0 -> z1` is

    scroll = to - centre - (z1 / z0) * (from - centre - scroll0)

For a wheel tick, key or button `from == to`; for a pinch they differ, which is
what lets two fingers zoom and pan in one gesture.

### Gotcha: readiness polling must not use requestAnimationFrame

The store appears during Isoflow's render but `rendererEl` only lands an effect
or two later, so every consumer polls for both. That poll runs on `setTimeout`,
not `requestAnimationFrame`: rAF is frozen in a background tab, and the first
version of this attached no gestures at all when the map was opened in one.

---

## model.mjs is GENERATED — never edit it by hand

`check-layout.mjs` imports `model.mjs`, not `model.js`. The two files are identical
except that the isopack import in `.mjs` carries the `.js` extension, which bare `node`
needs and the bundler does not.

It used to be a hand-maintained twin, **and it had silently drifted**: the layout checker
was validating a stale model while `build-local.sh` bundled the real one. Same class of
bug as `build.mjs` vs `build-local.mjs` having separate HTML templates.

Regenerate it after every `model.js` edit, before running the checker:

```sh
node gen-model-mjs.mjs    # asserts exactly one isopack import, then rewrites model.mjs
node check-layout.mjs     # now validating what actually ships
sh  build-local.sh
```

`gen-model-mjs.mjs` fails loudly if the import it rewrites is missing or duplicated, so a
silent desync cannot come back.

## Verify against the built HTML, not the build log

`build-local.sh` exits 0 whether or not an edit reached the bundle. esbuild escapes
non-ASCII, so `—` becomes `—` and `·` becomes `\xB7` in `homelab-map.html`. A literal
grep for a heading containing those characters returns 0 even when the string is present.
Grep for an ASCII-only fragment, or grep for the escaped form.

## Stacking segments

When two zones would sit side by side and push the view extent out, stack them in
screen space instead (same `u` column, non-overlapping tile-space `y` ranges). `hug`
then produces non-intersecting rectangles and the fit-to-view zoom stays higher.
