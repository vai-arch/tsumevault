// AR0 (WORKPLAN_ARCHIVO.md): el visor de Games + AN2 viven en js/game_viewer.js y se cargan
// con <script src> antes del script principal de tsumevault.html (ámbito global compartido).
// 1) Estructura: etiqueta <script>, nada duplicado entre los dos ficheros, contrato completo.
// 2) Humo: el visor REAL con el WGo REAL y la página simulada (tablero falso que registra piedras).
//
//     node tests/test_game_viewer.js
const fs = require('fs'), path = require('path'), vm = require('vm');
let FAILS = 0, N = 0;
function check(name, cond, extra) { N++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && extra ? '  ' + extra : '')); if (!cond) FAILS++; }

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'tsumevault.html'), 'utf8');
const viewer = fs.readFileSync(path.join(ROOT, 'js', 'game_viewer.js'), 'utf8');
const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).sort((a, b) => b.length - a.length)[0];

// ── 1. Estructura ──
const tag = '<script src="js/game_viewer.js"></script>';
const iTag = html.indexOf(tag), iKifu = html.indexOf('<script src="wgo/kifu.js"></script>'), iMain = html.indexOf('<script>\n') >= 0 ? html.indexOf('<script>\n') : html.indexOf('<script>\r\n');
check('tsumevault.html carga js/game_viewer.js una sola vez', iTag >= 0 && html.indexOf(tag, iTag + 1) < 0);
check('…después de WGo y antes del script principal', iKifu >= 0 && iTag > iKifu && iMain > iTag, `kifu=${iKifu} tag=${iTag} main=${iMain}`);

// declaraciones de nivel superior: en el visor empiezan en la columna 0; en la página, con 4 espacios
const declRe = (indent) => new RegExp(`^${indent}(?:async\\s+)?(?:function\\s+([A-Za-z_$][\\w$]*)|(?:let|const|var)\\s+([A-Za-z_$][\\w$]*))`, 'gm');
// en let/const/var también los nombres siguientes de la misma línea (let a = 1, b = 2;), separando por
// comas de profundidad 0 para no confundir comas de objetos o llamadas
function lineNames(rest) {
  const out = []; let d = 0, cur = '';
  for (const ch of rest) { if ('([{'.includes(ch)) d++; else if (')]}'.includes(ch)) d--; if (ch === ',' && d === 0) { out.push(cur); cur = ''; } else if (ch === ';' && d === 0) break; else cur += ch; }
  out.push(cur);
  return out.map(x => (x.match(/^\s*([A-Za-z_$][\w$]*)\s*(=|$)/) || [])[1]).filter(Boolean);
}
const decls = (code, indent) => {
  const s = new Set();
  for (const m of code.matchAll(declRe(indent))) {
    if (m[1]) { s.add(m[1]); continue; }
    const line = code.slice(m.index, code.indexOf('\n', m.index) < 0 ? code.length : code.indexOf('\n', m.index));
    for (const n of lineNames(line.replace(/^\s*(let|const|var)\s+/, '').replace(/\/\/.*$/, ''))) s.add(n);
  }
  return s;
};
// AR3a: el núcleo del tablero y las funciones puras de la IA están en js/board_core.js y js/ai_pure.js
const core = fs.readFileSync(path.join(ROOT, 'js', 'board_core.js'), 'utf8') + '\n' + fs.readFileSync(path.join(ROOT, 'js', 'ai_pure.js'), 'utf8');
const V = decls(viewer, ''), P = new Set([...decls(inline, '    '), ...decls(core, '')]);
check('anti-vacío: el visor declara al menos 55 nombres', V.size >= 55, String(V.size));
check('anti-vacío: la página declara al menos 500 nombres', P.size >= 500, String(P.size));
const dup = [...V].filter(x => P.has(x));
check('ningún nombre de nivel superior declarado en los dos ficheros', dup.length === 0, dup.join(', '));
const leftover = ['gmOpenGame', 'gmNext', 'gmPrev', 'gmRenderCurrentNode', 'gmInitControls', 'anReset', 'anInitControls', 'anAfterRender']
  .filter(x => new RegExp(`function ${x}\\(`).test(inline));
check('las funciones del visor ya no están en tsumevault.html', leftover.length === 0, leftover.join(', '));
const pageUses = ['gmOpenGame', 'gmInitControls', 'gmStopTimer', 'gmRenderCurrentNode', 'gmRootNode', 'gmActive'];
check('lo que la página usa del visor está declarado en el visor', pageUses.every(x => V.has(x)), pageUses.filter(x => !V.has(x)).join(', '));
check('la lista de colecciones de Games se queda en la página', ['gmCollections', 'gmLoadCollections', 'gmLoadGameList'].every(x => P.has(x) && !V.has(x)));
const host = ['wgoBoard', 'boardSize', 'initBoard', 'clearBoard', 'addLastMoveMark', 'moveQualityMark', 'switchToBoard',
  'playStoneSound', 'capturedAny', 'sgfUrl', 'lsGet', 'lsSet', 'aiPost', 'aiToGtp', 'aiFromGtp', 'AI_OWN_HANDLER',
  'anAnalysisText', 'anEstText', 'anGameInfoRows', 'anGraphCaption', 'anMistakes', 'anMoveTimes', 'anPosition',
  'anSgfRootProps', 'anStatusText', 'anThinkTxt'];
const hostMissing = host.filter(x => !P.has(x));
check('el contrato con la página está completo (tsumevault.html + board_core.js + ai_pure.js)', hostMissing.length === 0, hostMissing.join(', '));
check('el contrato está documentado en game_viewer.js', host.every(x => viewer.includes(x)) && viewer.includes('Contrato con la página anfitriona'));

// ── 2. Humo: visor real + WGo real + página simulada ──
function el() {
  const e = { style: {}, dataset: {}, children: [], textContent: '', innerHTML: '', value: '', disabled: false, className: '', title: '',
    classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle(c, f) { const on = f === undefined ? !this._s.has(c) : f; on ? this._s.add(c) : this._s.delete(c); return on; }, contains(c) { return this._s.has(c); } },
    listeners: {}, addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }, removeEventListener() { },
    appendChild(c) { this.children.push(c); return c; }, removeChild() { }, insertBefore(c) { return c; }, setAttribute() { }, getAttribute() { return null; },
    querySelector: () => el(), querySelectorAll: () => [], getContext: () => new Proxy({}, { get: () => () => ({}) }), getBoundingClientRect: () => ({ width: 300, height: 100, left: 0, top: 0 }),
    remove() { }, focus() { }, clientWidth: 300, clientHeight: 100, offsetWidth: 300 };
  return e;
}
const els = {};
const ctx = { console, setTimeout, clearTimeout, setInterval, clearInterval, Map, Set, Promise, JSON, Math, Date };
ctx.window = ctx; ctx.self = ctx;
ctx.navigator = { userAgent: 'node' };
ctx.document = { createElement: () => el(), createElementNS: () => el(), getElementsByTagName: () => [{ src: 'wgo/wgo.min.js' }], querySelector: () => null, querySelectorAll: () => [],
  getElementById: id => (els[id] = els[id] || el()), body: el(), addEventListener() { } };
ctx.localStorage = { _m: {}, getItem(k) { return this._m[k] ?? null; }, setItem(k, v) { this._m[k] = String(v); }, removeItem(k) { delete this._m[k]; } };
ctx.alert = (m) => { ctx.__alerts.push(m); }; ctx.__alerts = [];
vm.createContext(ctx);
for (const f of ['wgo.min.js', 'sgfparser.js', 'kifu.js']) vm.runInContext(fs.readFileSync(path.join(ROOT, 'wgo', f), 'utf8'), ctx, { filename: f });
// página simulada: el contrato mínimo (tablero falso que guarda los objetos dibujados)
vm.runInContext(`
  let wgoBoard = null, boardSize = 19;
  const __log = { init: 0, sounds: [], marks: [] };
  function initBoard(size) { boardSize = size || 19; __log.init++; wgoBoard = { size: boardSize, objs: [], addObject(o) { this.objs.push(o); }, removeObject() { }, redraw() { }, addEventListener() { } }; }
  function clearBoard() { if (wgoBoard) wgoBoard.objs = []; }
  function addLastMoveMark(x, y, q) { __log.marks.push([x, y]); wgoBoard.addObject({ x, y, type: 'CR' }); }
  function moveQualityMark(node) { return null; }
  function switchToBoard() { }
  function playStoneSound(c) { __log.sounds.push(!!c); }
  function capturedAny(r) { return Array.isArray(r) && r.length > 0; }
  function sgfUrl(p) { return '/tsumevault/' + p; }
  function lsGet(k) { return localStorage.getItem(k); }
  function lsSet(k, v) { localStorage.setItem(k, v); }
  async function aiPost() { throw new Error('sin servidor en el test'); }
  function aiToGtp() { return 'A1'; } function aiFromGtp() { return null; }
  const AI_OWN_HANDLER = 'own';
  function anAnalysisText() { return ''; } function anEstText() { return ''; } function anGameInfoRows() { return []; }
  function anGraphCaption() { return ''; } function anMistakes() { return []; } function anMoveTimes() { return null; }
  function anPosition() { return null; } function anSgfRootProps() { return {}; } function anStatusText() { return ''; } function anThinkTxt() { return ''; }
`, ctx, { filename: 'host_stub.js' });
let loadErr = null;
try { vm.runInContext(viewer, ctx, { filename: 'game_viewer.js' }); } catch (e) { loadErr = e; }
check('game_viewer.js se carga sin errores con la página simulada', !loadErr, loadErr && loadErr.stack);

const run = (code) => vm.runInContext(code, ctx);
const stones = () => run('wgoBoard.objs').filter(o => o.c === 1 || o.c === -1).map(o => `${o.c === 1 ? 'B' : 'W'}${o.x},${o.y}`).sort().join(' ');
(async () => {
  if (!loadErr) {
    try { run('gmInitControls()'); check('gmInitControls engancha los botones', (els['gm-btn-next'] && els['gm-btn-next'].listeners.click || []).length === 1); }
    catch (e) { check('gmInitControls engancha los botones', false, e.stack); }
    // partida lineal: B pd, W dp, B pp
    await run(`gmOpenGame({ name: 'prueba.sgf', sgf: '(;GM[1]FF[4]SZ[19];B[pd];W[dp]C[hola];B[pp])' })`);
    check('gmOpenGame: abre sin alertas y activa el visor', ctx.__alerts.length === 0 && run('gmActive') === true, ctx.__alerts.join(' | '));
    check('gmOpenGame: inicializa el tablero de 19', run('__log.init') === 1 && run('boardSize') === 19);
    check('raíz: tablero vacío y ◀ desactivado', stones() === '' && els['gm-btn-prev'].disabled === true && els['gm-btn-next'].disabled === false);
    check('board-hint con el nombre sin .sgf', els['board-hint'].textContent === 'prueba');
    run('gmNext()'); run('gmNext()');
    check('dos ▶: piedras B pd y W dp', stones() === 'B15,3 W3,15', stones());
    check('comentario del nodo en comment-box', els['comment-box'].textContent === 'hola');
    check('marca de última jugada en W dp', JSON.stringify(run('__log.marks').slice(-1)) === '[[3,15]]');
    check('sonido al avanzar de una en una (2 jugadas, sin captura)', JSON.stringify(run('__log.sounds')) === '[false,false]');
    run('gmNext()');
    check('fin de partida: ▶ desactivado', els['gm-btn-next'].disabled === true && stones() === 'B15,15 B15,3 W3,15');
    run('gmPrev()');
    check('◀ quita la última jugada', stones() === 'B15,3 W3,15');
    // variantes: tras B pd hay dos respuestas; ↩ vuelve al punto de decisión
    await run(`gmOpenGame({ name: 'var.sgf', sgf: '(;SZ[19];B[pd](;W[dp];B[pp])(;W[dd]))' })`);
    run('gmNext()');
    const varLabels = run('wgoBoard.objs').filter(o => o.text === '1' || o.text === '2').length;
    check('variantes numeradas en el tablero (2)', varLabels === 2, String(varLabels));
    run('gmNext()');
    check('▶ en una bifurcación sigue la línea principal (W dp)', stones() === 'B15,3 W3,15', stones());
    run('gmPrev()');
    run('gmAdvanceTo(1)');
    check('elegir la variante 2 (W dd)', stones() === 'B15,3 W3,3', stones());
    run('gmGoToBranchStart()');
    check('↩ vuelve al punto de la bifurcación', stones() === 'B15,3', stones());
    // captura: suena el sonido de captura
    await run(`gmOpenGame({ name: 'cap.sgf', sgf: '(;SZ[9];B[ba];W[aa];B[ab])' })`);
    run('__log.sounds.length = 0'); run('gmNext()'); run('gmNext()'); run('gmNext()');
    check('tamaño 9 reinicia el tablero', run('boardSize') === 9);
    check('captura en la esquina: la piedra blanca desaparece y suena captura', stones() === 'B0,1 B1,0' && JSON.stringify(run('__log.sounds')) === '[false,false,true]', stones() + ' ' + JSON.stringify(run('__log.sounds')));
    run('gmStopTimer()');
  }
  console.log(`\n${N - FAILS}/${N} PASS`);
  process.exit(FAILS ? 1 : 0);
})();
