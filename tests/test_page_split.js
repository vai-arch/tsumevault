// AR3a (docs/WORKPLAN_ARCHIVO.md): el núcleo del tablero (js/board_core.js) y las funciones puras de la IA
// (js/ai_pure.js) salieron de tsumevault.html TAL CUAL. Comprueba que la división sigue sana:
//  1) orden de las <script>, 2) cada marca "⇢ #N" tiene su bloque "⇠ #N" y al revés (page_source.js),
//  3) nada declarado en dos ficheros, 4) lo movido ya no está en la página, 5) los tres ficheros cargan
//  solos en orden (sin usar al cargar nada de la página: TDZ), 6) el núcleo funciona con el WGo real.
//
//     node tests/test_page_split.js
const fs = require('fs'), path = require('path'), vm = require('vm');
const { pageSource } = require('./page_source.js');
let FAILS = 0, N = 0;
function check(name, cond, extra) { N++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && extra ? '  ' + extra : '')); if (!cond) FAILS++; }

const ROOT = path.join(__dirname, '..');
const rd = f => fs.readFileSync(path.join(ROOT, f), 'utf8').replace(/\r\n/g, '\n');
const html = rd('tsumevault.html'), core = rd('js/board_core.js'), ai = rd('js/ai_pure.js'), viewer = rd('js/game_viewer.js');
const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).sort((a, b) => b.length - a.length)[0];

// 1. orden de carga
const pos = t => html.indexOf(t);
const tags = ['<script src="wgo/kifu.js"></script>', '<script src="js/board_core.js"></script>', '<script src="js/ai_pure.js"></script>',
  '<script src="js/game_viewer.js"></script>', '<script>\n'];
const ps = tags.map(pos);
check('orden: WGo → board_core → ai_pure → game_viewer → script principal', ps.every(p => p >= 0) && ps.every((p, i) => i === 0 || p > ps[i - 1]), JSON.stringify(ps));
check('cada <script src> nuevo aparece una sola vez', tags.slice(1, 4).every(t => html.split(t).length === 2));

// 2. marcas ↔ bloques
let rec = null, err = null;
try { rec = pageSource(); } catch (e) { err = e; }
const marks = (html.match(/^    \/\/ ⇢ js\/(board_core|ai_pure)\.js #\d+$/gm) || []).length;
const heads = (core.match(/^\/\/ ⇠ #\d+ /gm) || []).length + (ai.match(/^\/\/ ⇠ #\d+ /gm) || []).length;
check('page_source reconstruye la página (todas las marcas con su bloque y al revés)', !err && rec && !rec.includes('⇢ js/') && !rec.includes('js/board_core.js'), err && err.message);
check('anti-vacío: hay al menos 15 bloques movidos y tantas marcas como bloques', marks >= 15 && marks === heads, `${marks} marcas / ${heads} bloques`);
check('la página reconstruida contiene los bloques IA3 y SFX completos', rec && rec.includes('// ── IA3: funciones puras') && rec.includes('// ── fin IA3 funciones puras ──') && rec.includes('// ── SFX: funciones puras'));

// 3. nada declarado dos veces (nivel superior: columna 0 en los .js, 4 espacios en la página)
function lineNames(rest) {
  const out = []; let d = 0, cur = '';
  for (const ch of rest) { if ('([{'.includes(ch)) d++; else if (')]}'.includes(ch)) d--; if (ch === ',' && d === 0) { out.push(cur); cur = ''; } else if (ch === ';' && d === 0) break; else cur += ch; }
  out.push(cur);
  return out.map(x => (x.match(/^\s*([A-Za-z_$][\w$]*)\s*(=|$)/) || [])[1]).filter(Boolean);
}
function decls(code, indent) {
  const s = new Set();
  const re = new RegExp(`^${indent}(?:(?:async\\s+)?function\\s+([A-Za-z_$][\\w$]*)|(?:let|const|var)\\s+(.*)$)`, 'gm');
  for (const m of code.matchAll(re)) { if (m[1]) s.add(m[1]); else lineNames(m[2].replace(/\/\/.*$/, '')).forEach(n => s.add(n)); }
  return s;
}
const D = { 'tsumevault.html': decls(inline, '    '), 'board_core.js': decls(core, ''), 'ai_pure.js': decls(ai, ''), 'game_viewer.js': decls(viewer, '') };
const all = Object.entries(D).flatMap(([f, s]) => [...s].map(n => [n, f]));
const seen = {}, dups = [];
for (const [n, f] of all) { if (seen[n] && seen[n] !== f) dups.push(`${n} (${seen[n]} y ${f})`); seen[n] = seen[n] || f; }
check('anti-vacío: board_core ≥ 30 declaraciones, ai_pure ≥ 50', D['board_core.js'].size >= 30 && D['ai_pure.js'].size >= 50, `${D['board_core.js'].size} / ${D['ai_pure.js'].size}`);
check('ningún nombre declarado en dos ficheros', dups.length === 0, dups.join('; '));

// 4. lo movido ya no está en la página
const CORE = ['wgoBoard', 'boardSize', 'initBoard', 'clearBoard', 'addLastMoveMark', 'moveQualityMark', 'switchToBoard', 'isMobilePortrait',
  'buildStoneHandler', 'getImg', 'imgCache', 'pickVariant', 'currentBoardBg', 'currentStoneSet', 'BOARD_BG_KEY', 'STONE_SFX', 'playStoneSound',
  'capturedAny', 'soundEnabled', 'sfxVolume', 'stoneSfxLast', 'SOUND_KEY', 'SFX_VOLUME_KEY', 'sfxPickIndex', 'lsGet', 'lsSet', 'sgfUrl',
  'SGF_BASE', 'syncFetch', 'SYNC_SERVER', 'SYNC_SERVER_KEY', 'SYNC_TOKEN_KEY', 'aiPost', 'AI_OWN_HANDLER', 'jsMarkInfo'];
const AI = ['anAnalysisText', 'anEstText', 'anGameInfoRows', 'anGraphCaption', 'anMistakes', 'anMoveTimes', 'anPosition', 'anSgfRootProps',
  'anStatusText', 'anThinkTxt', 'aiToGtp', 'aiFromGtp', 'AI_COLS'];
check('el núcleo está en board_core.js y no en la página', CORE.every(n => D['board_core.js'].has(n) && !D['tsumevault.html'].has(n)), CORE.filter(n => !D['board_core.js'].has(n) || D['tsumevault.html'].has(n)).join(', '));
check('las funciones puras de la IA están en ai_pure.js y no en la página', AI.every(n => D['ai_pure.js'].has(n) && !D['tsumevault.html'].has(n)));
check('SW_VERSION (bump_version.py) sigue en la página', /const SW_VERSION = '/.test(inline));

// 5. los tres ficheros cargan en orden con un entorno mínimo (sin la página): nada se usa al cargar antes de existir
function el() {
  return { style: {}, dataset: {}, classList: { add() { }, remove() { }, toggle() { }, contains() { return false; } }, addEventListener() { }, appendChild(c) { return c; },
    setAttribute() { }, querySelector: () => null, querySelectorAll: () => [], getContext: () => new Proxy({}, { get: () => () => ({}) }), children: [], textContent: '', innerHTML: '' };
}
const store = {};
const ctx = { console, setTimeout, clearTimeout, setInterval, clearInterval, Promise, JSON, Math, Date, Map, Set, URL,
  navigator: { userAgent: 'node' }, localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  matchMedia: () => ({ matches: false, addEventListener() { } }), Audio: function () { this.play = () => Promise.resolve(); this.cloneNode = () => new ctx.Audio(); }, Image: function () { },
  fetch: async () => { throw new Error('sin red en el test'); }, AbortSignal: { timeout: () => undefined }, innerWidth: 1200, innerHeight: 800 };
ctx.window = ctx; ctx.self = ctx;
ctx.document = { createElement: () => el(), createElementNS: () => el(), getElementById: () => el(), getElementsByTagName: () => [{ src: 'wgo/wgo.min.js' }],
  querySelector: () => null, querySelectorAll: () => [], body: el(), documentElement: el(), addEventListener() { } };
vm.createContext(ctx);
for (const f of ['wgo.min.js', 'sgfparser.js', 'kifu.js']) vm.runInContext(fs.readFileSync(path.join(ROOT, 'wgo', f), 'utf8'), ctx, { filename: f });
const loadErr = {};
for (const f of ['js/board_core.js', 'js/ai_pure.js', 'js/game_viewer.js']) {
  try { vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f }); } catch (e) { loadErr[f] = e.message; }
}
check('board_core.js, ai_pure.js y game_viewer.js cargan en orden sin la página', Object.keys(loadErr).length === 0, JSON.stringify(loadErr));

// 6. el núcleo real funciona: tablero, ajustes por defecto, URL de SGF, funciones puras
const run = c => vm.runInContext(c, ctx);
try {
  run(`document.getElementById = (id) => (globalThis.__els = globalThis.__els || {}, __els[id] = __els[id] || (${el.toString()})())`);
  check('lsSet/lsGet con localStorage', run(`lsSet('x', 'y'), lsGet('x')`) === 'y');
  check('sgfUrl escapa # y % como antes', run(`sgfUrl('a#b%c.sgf')`) === '/tsumevault/a%23b%25c.sgf');
  check('capturedAny', run('capturedAny([1]) === true && capturedAny([]) === false'));
  check('aiToGtp/aiFromGtp ida y vuelta (19x19, sin la I)', run(`JSON.stringify(aiFromGtp(aiToGtp(8, 0)))`) === JSON.stringify({ x: 8, y: 0 }) && run(`aiToGtp(8, 0)`) === 'J19', run(`aiToGtp(8, 0)`));
} catch (e) { check('núcleo utilizable en el entorno mínimo', false, e.stack); }

console.log(`\n${N - FAILS}/${N} PASS`);
process.exit(FAILS ? 1 : 0);
