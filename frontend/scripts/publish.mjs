// Publishes a staged Vite build (.build-stage) into the served folder without breaking open tabs.
//
// Why: `vite build` empties its output folder, so a tab still running the previous build asks for chunks that no
// longer exist ("Failed to fetch dynamically imported module", 404). Here the new fingerprinted chunks are copied
// next to the old ones, everything else is updated, and index.html is replaced last (atomically), so the new entry
// point never names a file that is not on disk yet. Old chunks not used by this build are pruned after KEEP_DAYS.
//
// Usage: node scripts/publish.mjs [outDir=dist]
import fs from 'node:fs';
import path from 'node:path';

const KEEP_DAYS = 14;
const stage = path.resolve('.build-stage');
const out = path.resolve(process.argv[2] || 'dist');
if (!fs.existsSync(path.join(stage, 'index.html'))) { console.error('No staged build in', stage); process.exit(1); }
fs.mkdirSync(out, { recursive: true });

let added = 0, kept = 0, updated = 0;
function copyTree(src, dst, rel = '') {
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, e.name), d = path.join(dst, e.name), r = path.join(rel, e.name);
    if (e.isDirectory()) { fs.mkdirSync(d, { recursive: true }); copyTree(s, d, r); continue; }
    if (r === 'index.html') continue;                                   // written last
    const fingerprinted = rel.split(path.sep)[0] === 'assets';
    if (fingerprinted && fs.existsSync(d)) { kept++; continue; }       // same hash = same content
    const tmp = d + '.tmp-publish';
    fs.copyFileSync(s, tmp); fs.renameSync(tmp, d);
    fingerprinted ? added++ : updated++;
  }
}
copyTree(stage, out);

// index.html last, atomically.
const tmp = path.join(out, 'index.html.tmp-publish');
fs.copyFileSync(path.join(stage, 'index.html'), tmp);
fs.renameSync(tmp, path.join(out, 'index.html'));

// Prune chunks this build no longer uses once they are older than KEEP_DAYS (open tabs keep working meanwhile).
const current = new Set(fs.readdirSync(path.join(stage, 'assets')));
let pruned = 0;
const cutoff = Date.now() - KEEP_DAYS * 86400e3;
for (const f of fs.readdirSync(path.join(out, 'assets'))) {
  if (current.has(f)) continue;
  const p = path.join(out, 'assets', f);
  if (fs.statSync(p).mtimeMs < cutoff) { fs.unlinkSync(p); pruned++; }
}
const entry = (fs.readFileSync(path.join(out, 'index.html'), 'utf8').match(/assets\/index-[\w-]+\.js/) || ['?'])[0];
console.log(`published to ${path.relative(process.cwd(), out)}: ${added} new chunks, ${kept} unchanged, ${updated} other files, ${pruned} pruned; entry ${entry}`);
