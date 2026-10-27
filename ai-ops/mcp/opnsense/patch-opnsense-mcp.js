#!/usr/bin/env node
// Fix: the MCP dispatcher passes the whole params object as the POST body, so a
// documented {data: {...}} / {item: {...}} wrapper is sent verbatim and lands one
// level too deep. OPNsense's setBase then finds no matching top-level key, writes
// nothing, and still returns {"result":"saved"} - a silent write failure.
//
// Fix: unwrap a body that consists SOLELY of a single `data` or `item` key.
// Deliberately narrow so existing working calls are untouched:
//   {data:{ids:{...}}}          -> {ids:{...}}        (was broken, now works)
//   {item:{test:{...}}}         -> {test:{...}}       (was broken, now works)
//   {test:{...}}                -> unchanged          (already worked)
//   {searchPhrase, rowCount}    -> unchanged          (already worked)
//   {uuid}                      -> unchanged          (already worked)
//   {data:{...}, rowCount:5}    -> unchanged (>1 key, ambiguous - leave alone)
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
// Target: argv[2], else $OPNSENSE_MCP_INDEX, else the global npm install.
const F = process.argv[2] || process.env.OPNSENSE_MCP_INDEX ||
  path.join(execSync('npm root -g').toString().trim(), '@richard-stovall/opnsense-mcp-server/index.js');

const OLD = `    if (Object.keys(callParams).length > 0) {
      const { uuid, ...body } = callParams;
      if (uuid !== undefined && method.length >= 2) {
        return await method.call(moduleObj, uuid, Object.keys(body).length > 0 ? body : undefined);
      }
      return await method.call(moduleObj, callParams);
    } else {`;

const NEW = `    if (Object.keys(callParams).length > 0) {
      // Unwrap a sole {data:...} / {item:...} wrapper so the request body is the
      // object OPNsense actually expects, rather than that object nested one level
      // deeper. Without this, writes silently no-op and still report "saved".
      const unwrapBody = (o) => {
        if (!o || typeof o !== 'object' || Array.isArray(o)) return o;
        const k = Object.keys(o);
        if (k.length === 1 && (k[0] === 'data' || k[0] === 'item')) {
          const inner = o[k[0]];
          if (inner && typeof inner === 'object' && !Array.isArray(inner)) return inner;
        }
        return o;
      };
      const { uuid, ...body } = callParams;
      if (uuid !== undefined && method.length >= 2) {
        const b = unwrapBody(body);
        return await method.call(moduleObj, uuid, Object.keys(b).length > 0 ? b : undefined);
      }
      return await method.call(moduleObj, unwrapBody(callParams));
    } else {`;

// The stock 0.5.3 dispatcher (no uuid passthrough). NEW adds both fixes: uuid
// path-param passthrough AND the wrapper unwrap.
const PRISTINE = `    if (Object.keys(callParams).length > 0) {
      return await method.call(moduleObj, callParams);
    } else {`;

let s = fs.readFileSync(F, 'utf8');
if (s.includes('unwrapBody')) { console.log('ALREADY PATCHED'); process.exit(0); }
const anchor = s.includes(OLD) ? OLD : (s.includes(PRISTINE) ? PRISTINE : null);
if (!anchor) { console.error('ANCHOR NOT FOUND - refusing to patch'); process.exit(1); }

const bak = F + '.bak-prewrapfix';
if (!fs.existsSync(bak)) fs.copyFileSync(F, bak);
fs.writeFileSync(F, s.replace(anchor, NEW));
console.log('anchor: ' + (anchor === OLD ? 'uuid-patched' : 'stock') + ' dispatcher');
console.log('PATCHED (backup: ' + bak + ')');

// prove the unwrap logic in isolation
const unwrapBody = (o) => {
  if (!o || typeof o !== 'object' || Array.isArray(o)) return o;
  const k = Object.keys(o);
  if (k.length === 1 && (k[0] === 'data' || k[0] === 'item')) {
    const inner = o[k[0]];
    if (inner && typeof inner === 'object' && !Array.isArray(inner)) return inner;
  }
  return o;
};
const cases = [
  [{data:{ids:{general:{MPMAlgo:'hs'}}}}, {ids:{general:{MPMAlgo:'hs'}}}, 'data wrapper unwrapped'],
  [{item:{test:{name:'x'}}},              {test:{name:'x'}},              'item wrapper unwrapped'],
  [{test:{name:'x'}},                     {test:{name:'x'}},              'bare body untouched'],
  [{searchPhrase:'a',rowCount:5},         {searchPhrase:'a',rowCount:5},  'search params untouched'],
  [{data:{a:1},rowCount:5},               {data:{a:1},rowCount:5},        'ambiguous multi-key untouched'],
  [{data:'notanobject'},                  {data:'notanobject'},           'non-object data untouched'],
  [{data:[1,2]},                          {data:[1,2]},                   'array data untouched'],
];
let pass = 0;
for (const [inp, want, label] of cases) {
  const got = unwrapBody(inp);
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log((ok ? '  PASS  ' : '  FAIL  ') + label + (ok ? '' : ' got=' + JSON.stringify(got)));
  if (ok) pass++;
}
console.log(pass + '/' + cases.length + ' logic tests passed');
process.exit(pass === cases.length ? 0 : 1);
