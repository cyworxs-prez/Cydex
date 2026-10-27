import React, { useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
// Not the published package: patch-isoflow.mjs vendors a copy with three
// surgical fixes, chiefly exposing the uiState store so ./zoom.js can drive
// real zoom + scroll. Run `node patch-isoflow.mjs` after any npm install.
import Isoflow from './vendor/isoflow.patched.js';
import { model } from './model.js';
import { useIsoGestures, useLandingZoom, ZoomControls, PHONE_LANDING_ZOOM } from './zoom.js';

// isoflow's own breadcrumb view-switcher is not interactive in
// EXPLORABLE_READONLY, so the second view was unreachable. This wraps it with
// our own switcher (remount via `key`) and keeps the read-only guarantee.
//
// Zoom: isoflow's own zoom control is unusable here - it
// renders bottom-left, underneath the phone control bar, its buttons clamp to
// [0.2, 1], and its disabled conditions are swapped so 100% is a dead end.
// patch-isoflow.mjs removes it; ./zoom.js supplies pinch, wheel, double-tap,
// keys and the control stack on the right.
//
// Mobile: controls are not a fixed top-left overlay on narrow screens.
// On a phone that card covered a third of the canvas and the buttons were
// below the 44px touch minimum. Narrow viewports now get a bottom bar - within
// thumb reach, out of the way of the map - and the legend opens as a sheet
// instead of sitting open permanently.

// Short labels for the phone grid: "Security controls" does not fit a 2-up cell
// at 375px, and truncation would hide which view you are on.
const SHORT = { 'Security controls': 'Controls', 'SOC flows': 'SOC' };
const VIEWS = model.views.map((v) => ({
  id: v.id, name: v.name, short: SHORT[v.name] || v.name
}));

const LEGEND = [
  ['#2563eb', 'TRUSTED · VLAN 110'],
  ['#ea580c', 'IoT · VLAN 120'],
  ['#7c3aed', 'MGMT · VLAN 130'],
  ['#16a34a', 'LAB · VLAN 140'],
  ['#0891b2', 'DIRECT · VLAN 150 (no VPN)'],
  ['#0ea5e9', 'VPN egress'],
  ['#db2777', 'telemetry / SPAN'],
  ['#dc2626', 'blocked']
];

const FONT = '13px/1.45 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif';

const useIsPhone = () => {
  const q = '(max-width: 700px)';
  const [is, setIs] = useState(
    typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia(q).matches
      : false
  );
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(q);
    const on = (e) => setIs(e.matches);
    // addListener is the pre-Safari-14 spelling; keep both so older mobile Safari works.
    if (mq.addEventListener) mq.addEventListener('change', on);
    else mq.addListener(on);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener('change', on);
      else mq.removeListener(on);
    };
  }, []);
  return is;
};

const cardBase = {
  background: 'rgba(255,255,255,.94)',
  border: '1px solid #e2e8f0',
  borderRadius: 12,
  boxShadow: '0 1px 3px rgba(15,23,42,.12)',
  backdropFilter: 'blur(6px)',
  WebkitBackdropFilter: 'blur(6px)'
};

const Legend = ({ compact }) => (
  <div style={{ marginTop: 8, display: 'grid', gap: compact ? 8 : 5 }}>
    {LEGEND.map(([c, label]) => (
      <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          width: compact ? 14 : 12, height: compact ? 14 : 12, borderRadius: 3,
          background: c, flexShrink: 0, border: '1px solid rgba(15,23,42,.15)'
        }} />
        <span style={{ fontSize: compact ? 13 : 11, color: '#334155' }}>{label}</span>
      </div>
    ))}
    <div style={{
      fontSize: compact ? 12 : 10, color: '#94a3b8', marginTop: 4,
      maxWidth: compact ? 'none' : 170
    }}>
      dashed = wireless / logical · dotted = telemetry or hosted-on
    </div>
  </div>
);

const ViewTabs = ({ view, setView, phone }) => (
  <div style={{
    display: 'flex', gap: 6,
    ...(phone ? { flex: 1, flexWrap: 'wrap' } : { marginTop: 8 })
  }}>
    {VIEWS.map((v) => (
      <button
        key={v.id}
        onClick={() => setView(v.id)}
        style={{
          cursor: 'pointer', borderRadius: 8,
          padding: phone ? '0 14px' : '5px 10px',
          minHeight: phone ? 44 : 0,          // iOS touch-target minimum
          flex: phone ? '1 1 calc(50% - 3px)' : '0 0 auto',   // 2x2 grid on phone
          fontSize: phone ? 14 : 12,
          border: '1px solid ' + (view === v.id ? '#0f172a' : '#cbd5e1'),
          background: view === v.id ? '#0f172a' : '#fff',
          color: view === v.id ? '#fff' : '#334155',
          fontWeight: view === v.id ? 600 : 400,
          touchAction: 'manipulation'          // kills the 300ms tap delay
        }}
      >
        {phone ? v.short : v.name}
      </button>
    ))}
  </div>
);

const App = () => {
  const phone = useIsPhone();
  const [legendOpen, setLegendOpen] = useState(!phone);

  // isoflow fits the scene to the viewport on mount and exposes no action to do
  // it again, so "fit" remounts the subtree - exactly what switching views
  // already does. `fit` records which of the two caused this remount, because
  // the phone landing zoom below must not undo a fit the user just asked for.
  const [scene, setScene] = useState({ view: VIEWS[0].id, nonce: 0, fit: false });
  const view = scene.view;
  const sceneKey = view + '#' + scene.nonce;
  const setView = (id) => setScene({ view: id, nonce: 0, fit: false });
  const refit = () => setScene((s) => ({ view: s.view, nonce: s.nonce + 1, fit: true }));

  useIsoGestures(sceneKey);
  useLandingZoom(sceneKey, phone && !scene.fit, PHONE_LANDING_ZOOM);

  // Collapse the legend when rotating down to a narrow viewport, so the sheet
  // never opens over the map on load.
  useEffect(() => { setLegendOpen(!phone); }, [phone]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', font: FONT, color: '#0f172a' }}>

      {/* ---------- desktop: floating panel, top-left ---------- */}
      {!phone && (
        <div style={{ position: 'fixed', zIndex: 10, left: 12, top: 12 }}>
          <div style={{ ...cardBase, padding: '10px 12px', marginBottom: 8 }}>
            <div style={{ fontWeight: 700, marginBottom: 2 }}>Cydex</div>
            <div style={{ color: '#64748b', fontSize: 11 }}>fictional reference network</div>
            <ViewTabs view={view} setView={setView} phone={false} />
          </div>
          <div style={{ ...cardBase, padding: '10px 12px' }}>
            <div
              onClick={() => setLegendOpen(!legendOpen)}
              style={{ cursor: 'pointer', fontWeight: 600, fontSize: 12, userSelect: 'none' }}
            >
              {legendOpen ? '▾' : '▸'} Legend
            </div>
            {legendOpen && <Legend compact={false} />}
          </div>
        </div>
      )}

      {/* ---------- phone: title chip top, controls bottom ---------- */}
      {phone && (
        <>
          <div style={{
            position: 'fixed', zIndex: 10,
            left: 'calc(10px + env(safe-area-inset-left))',
            top: 'calc(10px + env(safe-area-inset-top))',
            ...cardBase, padding: '6px 10px'
          }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>Cydex</div>
            <div style={{ color: '#64748b', fontSize: 10 }}>fictional reference network</div>
          </div>

          {legendOpen && (
            <div
              onClick={() => setLegendOpen(false)}
              style={{
                position: 'fixed', inset: 0, zIndex: 11,
                background: 'rgba(15,23,42,.35)'
              }}
            />
          )}

          <div style={{
            position: 'fixed', zIndex: 12,
            left: 'calc(10px + env(safe-area-inset-left))',
            right: 'calc(10px + env(safe-area-inset-right))',
            bottom: 'calc(10px + env(safe-area-inset-bottom))',
            ...cardBase, padding: 10
          }}>
            {legendOpen && (
              <div style={{
                maxHeight: '46vh', overflowY: 'auto', touchAction: 'pan-y',
                borderBottom: '1px solid #e2e8f0', paddingBottom: 10, marginBottom: 10
              }}>
                <Legend compact />
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <ViewTabs view={view} setView={setView} phone />
              <button
                onClick={() => setLegendOpen(!legendOpen)}
                aria-expanded={legendOpen}
                style={{
                  cursor: 'pointer', borderRadius: 8, border: '1px solid #cbd5e1',
                  background: legendOpen ? '#0f172a' : '#fff',
                  color: legendOpen ? '#fff' : '#334155',
                  minHeight: 44, minWidth: 60, alignSelf: 'stretch',
                  padding: '0 12px', fontSize: 14,
                  fontWeight: 600, touchAction: 'manipulation', flexShrink: 0
                }}
              >
                Key
              </button>
            </div>
          </div>
        </>
      )}

      <ZoomControls
        sceneKey={sceneKey}
        phone={phone}
        cardStyle={cardBase}
        onFit={refit}
      />

      <Isoflow
        key={sceneKey}
        initialData={{ ...model, fitToView: true, view }}
        editorMode="EXPLORABLE_READONLY"
        renderer={{ showGrid: false, backgroundColor: '#f8fafc' }}
        mainMenuOptions={['EXPORT.PNG', 'EXPORT.JSON']}
        width="100%"
        height="100%"
      />
    </div>
  );
};

createRoot(document.getElementById('root')).render(<App />);
