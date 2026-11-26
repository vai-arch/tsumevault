// AR3a: gemelo en JS de tests/page_source.py (reconstruye tsumevault.html tal como era; ver allí).
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..');
const FILES = ['board_core', 'ai_pure'];
function blocks(f, root) {
  const p = path.join(root, 'js', f + '.js');
  if (!fs.existsSync(p)) return {};
  const lines = fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n').split('\n');
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  const out = {}; let cur = null;
  for (const l of lines) {
    const m = l.match(/^\/\/ ⇠ #(\d+) /);
    if (m) { cur = +m[1]; out[cur] = []; continue; }
    if (cur !== null) out[cur].push(l === '' ? '' : '    ' + l);
  }
  return out;
}
function pageSource(root = ROOT) {
  const raw = fs.readFileSync(path.join(root, 'tsumevault.html'), 'utf8');
  const crlf = raw.includes('\r\n');
  const src = raw.replace(/\r\n/g, '\n');
  const b = Object.fromEntries(FILES.map(f => [f, blocks(f, root)]));
  const used = new Set(), out = [];
  for (const l of src.split('\n')) {
    const m = l.match(/^    \/\/ ⇢ js\/(\w+)\.js #(\d+)$/);
    if (m) {
      const key = m[1] + '#' + m[2];
      if (used.has(key) || !(b[m[1]] || {})[+m[2]]) throw new Error('page_source: marca sin bloque o repetida: ' + l.trim());
      used.add(key); out.push(...b[m[1]][+m[2]]); continue;
    }
    out.push(l);
  }
  for (const f of FILES) for (const k of Object.keys(b[f])) if (!used.has(f + '#' + k)) throw new Error(`page_source: bloque #${k} de js/${f}.js sin marca`);
  let text = out.join('\n').replace(FILES.map(f => `  <script src="js/${f}.js"></script>\n`).join(''), '');
  return crlf ? text.replace(/\n/g, '\r\n') : text;
}
module.exports = { pageSource };
