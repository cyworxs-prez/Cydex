// Zoom, pinch and wheel for the read-only isoflow canvas.
//
// What isoflow 1.1.1 gives us on its own:
//   * touch handlers that read touches[0] and nothing else, so a two-finger
//     pinch is processed as a one-finger pan - there is no pinch zoom at all;
//   * no wheel listener, so a mouse or trackpad cannot zoom;
//   * +/- buttons with their disabled conditions swapped, which strands you at
//     100% with zoom-out greyed out (patch-isoflow.mjs removes these buttons;
//     the ones below replace them);
//   * zoom anchored on the renderer centre, so magnifying walks away from
//     whatever you were actually looking at.
//
// We drive isoflow's own zoom + scroll state rather than CSS-scaling a wrapper.
// A wrapper transform looks equivalent and is not: isoflow converts pointer
// positions to tiles using the renderer's own rect and zoom, so an outer scale
// would make dragging pan at the wrong rate and break hit-testing.
//
// Geometry. isoflow renders the scene in a layer pinned to the centre of the
// renderer, translated by scroll.position and scaled by zoom:
//
//     screen = centre + scroll + zoom * point
//
// To hold the scene point that was under `from` (client coords, measured
// against `base`) underneath `to` while zoom goes base.zoom -> z:
//
//     scroll = to - centre - (z / base.zoom) * (from - centre - base.scroll)
//
// For a wheel tick or a button press `from` and `to` are the same point. For a
// pinch they differ, which is what lets two fingers zoom and pan at once.

import React, { useEffect, useState } from 'react';

// isoflow's own range is [0.2, 1]. 1 is native tile size, and fit-to-view on a
// phone lands near 0.35, so a ceiling of 1 leaves labels unreadable on the
// devices that need magnification most.
// 0.05 rather than isoflow's 0.2 because fit-to-view on a 375px phone lands
// around 8% - a floor above that would leave the zoom-out button dead the
// moment you pressed "fit".
export const MIN_ZOOM = 0.05;
export const MAX_ZOOM = 3;

// Fitting this map to a phone means 8%, where not one label is readable. A
// phone therefore lands at a legible zoom on the centre of the diagram and
// treats the whole-map overview as something you ask for with the fit button.
export const PHONE_LANDING_ZOOM = 0.45;

const STEP = 1.35;          // one button press, key press or double-tap
const DOUBLE_TAP_MS = 300;
const DOUBLE_TAP_PX = 30;

const clampZ = (z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

// ---------------------------------------------------------------------------
// store plumbing
// ---------------------------------------------------------------------------

// vendor/isoflow.patched.js publishes the uiState store on window. It is
// rebuilt every time the Isoflow subtree remounts (view switch, fit), and
// rendererEl is filled by an effect a frame or two after that, so every
// consumer waits for both instead of grabbing whatever happens to be there.
//
// Polls on a timer rather than requestAnimationFrame: rAF is frozen while a tab
// is in the background, so a map restored into a background tab would come back
// with no gestures and a dead percentage readout until it was focused.
const whenReady = (cb) => {
  let timer = 0;
  let tries = 0;
  let dead = false;
  let cleanup = null;
  const tick = () => {
    if (dead) return;
    const store = typeof window !== 'undefined' ? window.__isoflowUiStore : null;
    const el = store && store.getState().rendererEl;
    if (store && el) { cleanup = cb(store, el) || null; return; }
    if (tries++ < 300) timer = setTimeout(tick, 16);        // give up after ~5s
  };
  tick();
  return () => {
    dead = true;
    if (timer) clearTimeout(timer);
    if (cleanup) cleanup();
  };
};

const centreOf = (el) => {
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
};

const liveBase = (store) => {
  const s = store.getState();
  return { zoom: s.zoom, scroll: { x: s.scroll.position.x, y: s.scroll.position.y } };
};

const zoomAnchored = (store, el, z, base, from, to) => {
  const next = clampZ(z);
  const c = centreOf(el);
  const k = next / base.zoom;
  const { actions } = store.getState();
  actions.setZoom(next);
  actions.setScroll({
    position: {
      x: to.x - c.x - k * (from.x - c.x - base.scroll.x),
      y: to.y - c.y - k * (from.y - c.y - base.scroll.y)
    }
  });
};

// Step about the centre of the viewport - what a button or key press means.
const stepAboutCentre = (store, el, factor) => {
  const base = liveBase(store);
  const c = centreOf(el);
  zoomAnchored(store, el, base.zoom * factor, base, c, c);
};

export const zoomStep = (dir) => {
  const store = typeof window !== 'undefined' ? window.__isoflowUiStore : null;
  const el = store && store.getState().rendererEl;
  if (!store || !el) return;
  stepAboutCentre(store, el, dir > 0 ? STEP : 1 / STEP);
};

// ---------------------------------------------------------------------------
// gestures
// ---------------------------------------------------------------------------

const attach = (store, el) => {
  const owns = (t) => !!t && el.contains(t);

  let pinch = null;       // { d0, m0, zoom, scroll } captured at gesture start
  let swallow = false;    // keep isoflow quiet until every finger has lifted
  let instantTimer = 0;
  let lastTapAt = 0;
  let lastTapPt = { x: 0, y: 0 };

  // Ask the patched bundle to skip its 250ms tween while a gesture is running.
  const instant = (on) => {
    window.__isoflowInstant = on;
    if (instantTimer) { clearTimeout(instantTimer); instantTimer = 0; }
  };
  const instantBurst = () => {
    window.__isoflowInstant = true;
    if (instantTimer) clearTimeout(instantTimer);
    instantTimer = setTimeout(() => { window.__isoflowInstant = false; instantTimer = 0; }, 140);
  };

  // isoflow keeps its own mousedown state off window events. The first finger
  // of a pinch has already started a pan there, so cancel it or the map keeps
  // sliding underneath the gesture.
  const cancelIsoflowDrag = (x, y) => {
    window.dispatchEvent(new MouseEvent('mouseup', { clientX: x, clientY: y, bubbles: true }));
  };

  const touchDist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  const touchMid = (t) => ({
    x: (t[0].clientX + t[1].clientX) / 2,
    y: (t[0].clientY + t[1].clientY) / 2
  });

  const onWheel = (e) => {
    if (!owns(e.target)) return;
    e.preventDefault();
    // deltaMode 1 is lines, 2 is pages. A trackpad pinch arrives as ctrl+wheel
    // in much finer steps than a mouse wheel's ~100px notches, so the two need
    // different sensitivities to land in the same place.
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
    const k = Math.exp(-e.deltaY * unit * (e.ctrlKey ? 0.012 : 0.0022));
    const p = { x: e.clientX, y: e.clientY };
    instantBurst();
    const base = liveBase(store);
    zoomAnchored(store, el, base.zoom * k, base, p, p);
  };

  const onTouchStart = (e) => {
    if (e.touches.length < 2 || !owns(e.target)) return;
    const base = liveBase(store);
    pinch = { d0: touchDist(e.touches), m0: touchMid(e.touches), ...base };
    swallow = true;
    instant(true);
    cancelIsoflowDrag(pinch.m0.x, pinch.m0.y);
    e.preventDefault();
    e.stopImmediatePropagation();
  };

  const onTouchMove = (e) => {
    if (!swallow) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (!pinch || e.touches.length < 2 || pinch.d0 < 1) return;
    zoomAnchored(
      store, el,
      pinch.zoom * (touchDist(e.touches) / pinch.d0),
      pinch, pinch.m0, touchMid(e.touches)
    );
  };

  const onTouchEnd = (e) => {
    if (swallow) {
      if (pinch && e.touches.length < 2) { pinch = null; instant(false); }
      e.preventDefault();
      e.stopImmediatePropagation();
      if (e.touches.length === 0) {
        swallow = false;
        cancelIsoflowDrag(0, 0);
        lastTapAt = 0;                 // a pinch must never seed a double-tap
      }
      return;
    }
    // double-tap to zoom, the one-handed gesture
    if (e.touches.length !== 0 || !owns(e.target)) return;
    const t = e.changedTouches[0];
    if (!t) return;
    const now = Date.now();
    const p = { x: t.clientX, y: t.clientY };
    if (now - lastTapAt < DOUBLE_TAP_MS && Math.hypot(p.x - lastTapPt.x, p.y - lastTapPt.y) < DOUBLE_TAP_PX) {
      lastTapAt = 0;
      instantBurst();
      const base = liveBase(store);
      zoomAnchored(store, el, base.zoom * STEP, base, p, p);
    } else {
      lastTapAt = now;
      lastTapPt = p;
    }
  };

  const onDblClick = (e) => {
    if (!owns(e.target)) return;
    e.preventDefault();
    const p = { x: e.clientX, y: e.clientY };
    instantBurst();
    const base = liveBase(store);
    zoomAnchored(store, el, base.zoom * (e.altKey ? 1 / STEP : STEP), base, p, p);
  };

  const onKey = (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    let f = 0;
    if (e.key === '+' || e.key === '=') f = STEP;
    else if (e.key === '-' || e.key === '_') f = 1 / STEP;
    else return;
    e.preventDefault();
    stepAboutCentre(store, el, f);
  };

  // Safari fires its own gesture* events alongside touch*; left alone they zoom
  // the page instead of the canvas.
  const swallowGesture = (e) => e.preventDefault();

  const cap = { capture: true, passive: false };
  window.addEventListener('wheel', onWheel, cap);
  window.addEventListener('touchstart', onTouchStart, cap);
  window.addEventListener('touchmove', onTouchMove, cap);
  window.addEventListener('touchend', onTouchEnd, cap);
  window.addEventListener('touchcancel', onTouchEnd, cap);
  window.addEventListener('dblclick', onDblClick, true);
  window.addEventListener('keydown', onKey);
  el.addEventListener('gesturestart', swallowGesture);
  el.addEventListener('gesturechange', swallowGesture);
  el.addEventListener('gestureend', swallowGesture);

  return () => {
    instant(false);
    window.removeEventListener('wheel', onWheel, cap);
    window.removeEventListener('touchstart', onTouchStart, cap);
    window.removeEventListener('touchmove', onTouchMove, cap);
    window.removeEventListener('touchend', onTouchEnd, cap);
    window.removeEventListener('touchcancel', onTouchEnd, cap);
    window.removeEventListener('dblclick', onDblClick, true);
    window.removeEventListener('keydown', onKey);
    el.removeEventListener('gesturestart', swallowGesture);
    el.removeEventListener('gesturechange', swallowGesture);
    el.removeEventListener('gestureend', swallowGesture);
  };
};

// Deliberately holds no React state: a pinch updates zoom every frame, and if
// this hook re-rendered the tree it would re-render <Isoflow> 60 times a second.
export const useIsoGestures = (sceneKey) => {
  useEffect(() => whenReady(attach), [sceneKey]);
};

// Raise the opening zoom to `floor` if isoflow's fit-to-view came in under it.
//
// fitToView runs a moment after the renderer element appears, so we cannot just
// read the zoom when the store is ready - we would race it and then be
// overwritten. Instead we wait for the one zoom change that fitToView makes,
// act on it, and stop listening. The timeout is the backstop for the case where
// fit lands on exactly the value we started from and no change is ever emitted.
export const useLandingZoom = (sceneKey, enabled, floor) => {
  useEffect(() => {
    if (!enabled) return undefined;
    return whenReady((store, el) => {
      let done = false;
      let unsub = null;
      let timer = 0;
      const apply = () => {
        if (done) return;
        done = true;
        if (unsub) unsub();
        if (timer) clearTimeout(timer);
        const z = store.getState().zoom;
        if (z > 0 && z < floor) stepAboutCentre(store, el, floor / z);
      };
      const z0 = store.getState().zoom;
      unsub = store.subscribe((s) => { if (s.zoom !== z0) apply(); });
      timer = setTimeout(apply, 1500);
      return () => { done = true; if (unsub) unsub(); if (timer) clearTimeout(timer); };
    });
  }, [sceneKey, enabled, floor]);
};

// ---------------------------------------------------------------------------
// controls
// ---------------------------------------------------------------------------

const btn = (enabled) => ({
  width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center',
  border: 'none', background: 'transparent', padding: 0,
  font: '20px/1 ui-sans-serif, system-ui, -apple-system, sans-serif',
  color: enabled ? '#0f172a' : '#cbd5e1',
  cursor: enabled ? 'pointer' : 'default',
  touchAction: 'manipulation', WebkitTapHighlightColor: 'transparent'
});

// Subscribes to the store by itself so the percentage readout can update on
// every frame of a pinch without dragging the rest of the app into the render.
export const ZoomControls = ({ sceneKey, phone, cardStyle, onFit }) => {
  const [zoom, setZoom] = useState(null);

  useEffect(() => whenReady((store) => {
    const push = (z) => setZoom((prev) => (prev === z ? prev : z));
    push(store.getState().zoom);
    return store.subscribe((s) => push(s.zoom));
  }), [sceneKey]);

  const canIn = zoom === null || zoom < MAX_ZOOM - 1e-3;
  const canOut = zoom === null || zoom > MIN_ZOOM + 1e-3;
  const line = { borderTop: '1px solid #e2e8f0' };

  return (
    <div style={{
      position: 'fixed', zIndex: 12,
      right: 'calc(10px + env(safe-area-inset-right))',
      ...(phone
        ? { top: '50%', transform: 'translateY(-50%)' }
        : { bottom: 'calc(34px + env(safe-area-inset-bottom))' }),
      ...cardStyle,
      display: 'flex', flexDirection: 'column', alignItems: 'stretch',
      padding: 0, overflow: 'hidden'
    }}>
      <button onClick={() => zoomStep(1)} disabled={!canIn} aria-label="Zoom in" style={btn(canIn)}>+</button>
      <div style={{
        ...line, padding: '4px 0', textAlign: 'center',
        font: '11px/1 ui-monospace, SFMono-Regular, Menlo, monospace', color: '#64748b'
      }}>
        {zoom === null ? '--' : Math.round(zoom * 100)}%
      </div>
      <button onClick={() => zoomStep(-1)} disabled={!canOut} aria-label="Zoom out" style={{ ...btn(canOut), ...line }}>&minus;</button>
      <button onClick={onFit} aria-label="Fit to screen" style={{ ...btn(true), ...line, fontSize: 15 }}>&#9974;</button>
    </div>
  );
};
