// model.mjs is a GENERATED twin of model.js — identical except that the isopack
// import carries the .js extension so plain `node` can resolve it (the bundler
// does not need it; bare node does). It used to be hand-maintained, and it had
// silently drifted: check-layout.mjs was validating a stale layout while the
// build used the real one. Regenerate it with `node gen-model-mjs.mjs` after
// every model.js edit; never edit model.mjs directly.
import { readFileSync, writeFileSync } from 'node:fs';
const src = readFileSync('model.js', 'utf8');
const from = "from '@isoflow/isopacks/dist/isoflow'";
const to = "from '@isoflow/isopacks/dist/isoflow.js'";
if (src.split(from).length - 1 !== 1) {
  console.error('FATAL: expected exactly one isopack import in model.js'); process.exit(1);
}
writeFileSync('model.mjs', src.replace(from, to));
console.log('model.mjs regenerated from model.js (' + src.length + ' bytes)');
