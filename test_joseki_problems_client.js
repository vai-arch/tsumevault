// JP: prueba de humo de los SGF generados con el parser REAL del cliente
// (wgo/wgo.min.js + wgo/sgfparser.js + wgo/kifu.js) y las funciones reales de
// tsumevault.html que preparan un problema (parseSgfTree, getSetupStones,
// getPlayerToMove, getMarkup).
//
//     python test_generate_joseki.py && node test_joseki_problems_client.js
//
// Lee los SGF que deja test_generate_joseki.py en jp_test_out/.
const fs = require('fs'), path = require('path'), vm = require('vm');
let FAILS = 0, N = 0;
function check(name, cond, extra) { N++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && extra ? '  ' + extra : '')); if (!cond) FAILS++; }

const ctx = { console };
ctx.window = ctx; ctx.self = ctx;
ctx.document = { createElement: () => ({ getContext: () => ({}), style: {} }), getElementsByTagName: () => [{ src: 'wgo/wgo.min.js' }], querySelector: () => null };
ctx.navigator = { userAgent: 'node' };
vm.createContext(ctx);
for (const f of ['wgo.min.js', 'sgfparser.js', 'kifu.js']) vm.runInContext(fs.readFileSync(path.join(__dirname, 'wgo', f), 'utf8'), ctx, { filename: f });

// funciones reales del cliente
const html = fs.readFileSync(path.join(__dirname, 'tsumevault.html'), 'utf8');
function grab(sig) {
  const i = html.indexOf(sig); if (i < 0) throw new Error('no encontrado: ' + sig);
  let d = 0, j = html.indexOf('{', i);
  for (let k = j; k < html.length; k++) { if (html[k] === '{') d++; else if (html[k] === '}') { d--; if (d === 0) return html.slice(i, k + 1); } }
  throw new Error('sin cerrar: ' + sig);
}
vm.runInContext(['function parseSgfTree(', 'function getSetupStones(', 'function getPlayerToMove(', 'function getMarkup('].map(grab).join('\n') +
  '\nthis.__f = { parseSgfTree, getSetupStones, getPlayerToMove, getMarkup };', ctx);
const F = ctx.__f;

const OUT = path.join(__dirname, 'jp_test_out');
const files = [];
for (const col of fs.readdirSync(OUT)) for (const f of fs.readdirSync(path.join(OUT, col))) files.push(path.join(OUT, col, f));
check('hay SGF generados que probar (15 del 4-4 + 8 del 3-3 + 8 del 5-5 con contexto + 6 del 6-6 con errores)', files.length === 37, String(files.length));

const xy = s => ({ x: s.charCodeAt(0) - 97, y: s.charCodeAt(1) - 97 });
let allOk = true;
const bad = [];
for (const file of files) {
  const sgf = fs.readFileSync(file, 'utf8');
  const name = path.basename(file, '.sgf');
  const color = name[0] === 'B' ? 1 : -1;
  const root = F.parseSgfTree(sgf);
  const errs = [];
  if (!root) { bad.push(name + ': no parsea'); allOk = false; continue; }
  if (F.getPlayerToMove(root) !== color) errs.push('color');
  // setup = AB/AW del fichero
  const ab = ((sgf.match(/AB((?:\[[a-s]{2}\])+)/) || [, ''])[1].match(/[a-s]{2}/g) || []).map(xy);
  const aw = ((sgf.match(/AW((?:\[[a-s]{2}\])+)/) || [, ''])[1].match(/[a-s]{2}/g) || []).map(xy);
  const st = F.getSetupStones(root);
  const same = (a, b) => a.length === b.length && a.every(p => b.some(q => q.x === p.x && q.y === p.y));
  if (!same(ab, st.black) || !same(aw, st.white) || !ab.length) errs.push('setup');
  const cr = (sgf.match(/CR\[([a-s]{2})\]/) || [])[1];
  if (cr && !F.getMarkup(root).some(m => m.type === 'CR' && m.x === xy(cr).x && m.y === xy(cr).y)) errs.push('marca CR');
  if (!/Juegas [BW]/.test(root.comment || '')) errs.push('comentario inicial');
  // recorrer la línea como el motor: el jugador elige su jugada (la que no es WRONG),
  // el rival responde con su único hijo; alternancia estricta de colores.
  let node = root, turn = color, steps = 0;
  while (node.children.length) {
    const kids = node.children;
    let next;
    if (turn === color) {
      const wrongs = kids.filter(k => /^WRONG/.test(k.comment || ''));
      const mains = kids.filter(k => !/^WRONG/.test(k.comment || ''));
      if (mains.length !== 1) { errs.push('jugador: ' + mains.length + ' jugadas válidas'); break; }
      if (wrongs.some(w => w.children.length || !w.move || w.move.pass || w.move.c !== color)) errs.push('WRONG mal formada');
      next = mains[0];
    } else {
      if (kids.length !== 1) { errs.push('rival con ' + kids.length + ' respuestas'); break; }
      next = kids[0];
    }
    if (!next.move || next.move.c !== turn) { errs.push('alternancia'); break; }
    const last = !next.children.length;
    if (last !== /^RIGHT/.test(next.comment || '')) errs.push('RIGHT ' + (last ? 'falta al final' : 'a mitad'));
    if (!last && /^WRONG/.test(next.comment || '')) errs.push('WRONG a mitad');
    node = next; turn = -turn; steps++;
  }
  if (!steps) errs.push('sin jugadas');
  if (errs.length) { allOk = false; bad.push(name + ': ' + errs.join(', ')); }
}
check('los 37 SGF: parsean con WGo, color, piedras de inicio, marca, comentario inicial, línea jugable hasta RIGHT', allOk, bad.join(' | '));

// casos concretos
const load = rel => F.parseSgfTree(fs.readFileSync(path.join(OUT, rel), 'utf8'));
let r = load('4-4 Joseki/B-pdncqfpbqckc.sgf');
check('Low Enclosure · B: Q16 negra y O17 blanca de inicio, juega negro', F.getPlayerToMove(r) === 1 &&
  F.getSetupStones(r).black.length === 1 && F.getSetupStones(r).white.length === 1 && /→ Ahora: Low Enclosure/.test(r.comment));
r = load('4-4 Joseki/W-pdncqfpbqckcttqbqi.sgf');
let n = r; while (n.children.length && !(n.move && n.move.pass)) n = n.children[0];
check('el pase del rival lo entiende WGo como pase (move.pass) y lleva su aviso', n.move && n.move.pass === true && n.move.c === 1 && /Tenuki\./.test(n.comment), JSON.stringify(n.move));
r = load('4-4 Joseki/B-pdncqfpbqckcqbttobocpcnbpatt.sgf');
n = r; while (n.children.length) n = n.children[0];
check('pase final del rival: pase + RIGHT', n.move.pass === true && /^RIGHT/.test(n.comment));
r = load('3-3 Test/B-pdqcqdpcodqfqg.sgf');
const pc = r.children[0].children[0];
check('3-3 · B: dos ramas WRONG con su comentario colgando de la respuesta del rival',
  pc.children.length === 3 && pc.children.filter(k => /^WRONG Too tight$/.test(k.comment) || /^WRONG Dudosa\. Strange$/.test(k.comment)).length === 2);
check('3-3 · B: el ] escapado llega como texto', pc.children[0].children[0].comment === 'Live ] with bracket', pc.children[0].children[0].comment);
check('3-3 · B: el comentario intermedio que empezaba por RIGHT no cierra el problema', /^· RIGHT/.test(pc.children[0].comment));

// T32: renderLabels real del cliente — la caja de comentarios tras cada jugada
{
  const box = { textContent: '', style: {} };
  const c2 = { console, WGo: ctx.WGo };
  c2.document = { getElementById: id => (id === 'comment-box' ? box : null) };
  c2.wgoBoard = { obj_arr: Array.from({ length: 19 }, () => Array.from({ length: 19 }, () => [])), addObject() {} };
  vm.createContext(c2);
  vm.runInContext(grab('function renderLabels(') + '\nthis.__r = renderLabels;', c2);
  const R = c2.__r;
  const r = load('4-4 Joseki/B-pdncqfpbqckcqboc.sgf');
  box.textContent = r.comment;                       // como renderProblem
  const seen = [];
  let n = r;
  while (n.children.length) { n = n.children[0]; R(n); seen.push(box.textContent); }
  const kc = r.children[0].children[0].children[0].children[0];
  check('T32: jugada del rival SIN marcas (L17) → su comentario y la instrucción ¿y si? se ven',
    kc.markup === undefined && seen[3] === '2 spaces extension\n→ ¿Y si…? If we play this endgame move', JSON.stringify(seen[3]));
  check('T32: comentarios intermedios sin marcas se ven (Slide, Take the corner)', seen[1] === 'Slide' && seen[2] === 'Take the corner', JSON.stringify(seen));
  box.textContent = 'enunciado';
  R({ comment: '' });
  check('T32: una jugada sin comentario no borra la caja', box.textContent === 'enunciado');
  R({ comment: 'RIGHT bien' }); R({ comment: 'wrong mal' });
  check('T32: RIGHT/WRONG sin marcas no se escriben en crudo (los muestra showResult)', box.textContent === 'enunciado');
  R({ comment: 'con marca', markup: [{ type: 'TR', x: 1, y: 1 }] });
  check('T32: con marcas, comportamiento de siempre', box.textContent === 'con marca');
}

// T33: símbolos de calidad en la última jugada — motor REAL (setupInteractiveMode) en un entorno simulado
{
  const timers = [];
  // classList real (AV: el borde azul se comprueba por clase en #board-wrap)
  const el = () => { const cl = new Set(); return { textContent: '', style: {}, className: '', classList: { add(...c) { c.forEach(x => cl.add(x)); }, remove(...c) { c.forEach(x => cl.delete(x)); }, contains: c => cl.has(c), toggle(c, on) { if (on === undefined ? !cl.has(c) : on) cl.add(c); else cl.delete(c); } }, disabled: false, appendChild() {}, addEventListener() {}, removeEventListener() {}, getBoundingClientRect: () => ({ left: 0, top: 0 }) }; };
  const els = {}, sels = {};
  const sounds = [];
  const c3 = { console, WGo: ctx.WGo, Math, Date, JSON, Set, Array, Object, String, Number, Promise };
  c3.window = c3;
  c3.document = { getElementById: id => (els[id] = els[id] || el()), querySelector: q => (sels[q] = sels[q] || el()), querySelectorAll: () => [] };   // memoizado: el mismo #board-wrap en cada llamada
  const delays = [];   // AV: duracion pedida a cada setTimeout (en paralelo a timers)
  let tid = 0;
  c3.setTimeout = (f, ms) => { f.__id = ++tid; timers.push(f); delays.push(ms); return tid; };
  c3.clearTimeout = id => { const i = timers.findIndex(f => f.__id === id); if (i >= 0) { timers.splice(i, 1); delays.splice(i, 1); } };   // cancelar de verdad (AV)
  const mkArr = () => Array.from({ length: 19 }, () => Array.from({ length: 19 }, () => []));
  const typeName = t => (typeof t === 'string' ? t : (Object.keys(ctx.WGo.Board.drawHandlers).find(k => ctx.WGo.Board.drawHandlers[k] === t) || '?'));
  c3.wgoBoard = { obj_arr: mkArr(), element: el(), addEventListener() {}, removeEventListener() {},
    addObject(o) { if (o.x !== undefined) this.obj_arr[o.x][o.y].push(o); },
    removeObject(o) { const a = this.obj_arr[o.x][o.y]; this.obj_arr[o.x][o.y] = a.filter(k => !(o.type !== undefined && typeName(k.type) === typeName(o.type))); } };
  c3.clearBoard = () => { c3.wgoBoard.obj_arr = mkArr(); };
  c3.boardSize = 19;
  Object.assign(c3, { runMode: false, freeMode: true, tapConfirm: false, tapToAdvance: false, waitingForNext: false, NEXT_DELAY_MS: 1000,
    problemStartTime: 0, totalPaused: 0, sessionOk: 0, sessionNo: 0, activeRunId: null, runItems: [], runIdx: 0, everWrong: false,
    currentSource: 'joseki', playSound(n) { sounds.push(n); }, localInsertAttempt() {},
    // HTML posterior a JP (T37 fantasmas, Focus, Explorar): globales que el motor real consulta
    ghostMode: false, focusSessionActive: () => null, focusKey: () => '', focusOnAttempt() {}, totalPaused: 0, scheduleSaveDB() {}, tryAutoSync: () => Promise.resolve(),
    updatePendingBadge() {}, updateSessionUI() {}, nextProblem() {}, clearCrossMarks() {}, renderSetup() {}, hintWinsPlayer: () => false,
    showResult(ok) { c3.waitingForNext = true; c3.lastResult = ok; } });
  vm.createContext(c3);
  const choiceMs = html.match(/const CHOICE_ALERT_MS = \d+;/);   // AV: la duracion real del cliente
  if (!choiceMs) throw new Error('no encontrado: CHOICE_ALERT_MS');
  vm.runInContext(['function jsMarkInfo(', 'function moveQualityMark(', 'function addLastMoveMark(', 'function renderLabels(',
                   'function getSetupStones(', 'function parseSgfTree(', 'function choiceAlertOf(', 'function setupInteractiveMode('].map(grab).join('\n')
                  + '\n' + choiceMs[0] + '\nthis.CHOICE_ALERT_MS = CHOICE_ALERT_MS;', c3);
  const flush = () => { let n = 0; while (timers.length && n++ < 50) timers.shift()(); };
  const at = (m) => { const p = xy(m); return c3.wgoBoard.obj_arr[p.x][p.y].filter(o => o.c !== 1 && o.c !== -1).map(o => typeName(o.type) + (o.text ? ':' + o.text : '')); };
  // keepAlert: no vaciar los temporizadores al empezar (para ver el aviso AV antes de que se apague);
  // por defecto se vacian, asi los tests anteriores a AV no chocan con el bloqueo de clics.
  const start = (rel, keepAlert) => { c3.clearBoard(); const sgf = fs.readFileSync(path.join(OUT, rel), 'utf8'); const root = c3.parseSgfTree(sgf);
    c3.currentProblem = { tree: root, source: 'joseki', problem_id: rel }; c3.waitingForNext = false; c3.lastResult = undefined;
    els['result-flash'] && (els['result-flash'].className = '');   // como renderProblem
    c3.setupInteractiveMode(root, getPl(sgf)); if (!keepAlert) flush(); return root; };
  function getPl(sgf) { return /PL\[W\]/.test(sgf) ? -1 : 1; }
  const click = m => { const p = xy(m); c3.window._boardClickHandler(p.x, p.y); flush(); };

  // moveQualityMark: cada marca, sin marca, prioridad de J3
  const Q = c3.moveQualityMark;
  check('T33: moveQualityMark — IT ?, BM ✕, DO ▲, TE ★, sin marca null',
    Q({ IT: '' }).sym === '?' && Q({ BM: '1' }).sym === '✕' && Q({ DO: '1' }).sym === '▲' && Q({ TE: '1' }).sym === '★' && Q({}) === null && Q(null) === null);
  check('T33: prioridad de J3 (IT > BM > DO > TE) y colores', Q({ IT: '', BM: '1' }).sym === '?' && Q({ BM: '1', TE: '1' }).sym === '✕' &&
    Q({ DO: '1', TE: '1' }).sym === '▲' && Q({ BM: '1' }).color === '#d45030' && Q({ TE: '1' }).color === '#5cb868');

  // Problema con marcas: B-…qboc (tu R18 es IT, la O18 del rival es BM)
  start('4-4 Joseki/B-pdncqfpbqckcqboc.sgf');
  click('qf');
  check('T33 motor: jugadas sin marca → círculo de siempre en la última (Q18 del rival) y nada en la anterior',
    JSON.stringify(at('pb')) === '["CR"]' && at('qf').length === 0, JSON.stringify({ qf: at('qf'), pb: at('pb') }));
  click('qc');
  click('qb');
  check('T33 motor: tu jugada ¿y si? (IT) → ? en su piedra… y la siguiente del rival (BM) → ✕, la ? desaparece',
    at('qb').length === 0 && JSON.stringify(at('oc')) === '["LB:✕"]', JSON.stringify({ qb: at('qb'), oc: at('oc') }));
  check('T33 motor: el problema termina bien (RIGHT)', c3.lastResult === true);
  c3.window._studyRedraw();
  check('T33 motor: redimensionar (_studyRedraw) conserva el ✕', JSON.stringify(at('oc')) === '["LB:✕"]', JSON.stringify(at('oc')));
  c3.window._studyBack();
  check('T33 motor: Back restaura la marca anterior (círculo en L17) y quita el ✕', JSON.stringify(at('kc')) === '["CR"]' && at('oc').length === 0,
    JSON.stringify({ kc: at('kc'), oc: at('oc') }));
  // jugada propia IT vista antes de la respuesta: no vaciar los timers
  start('4-4 Joseki/B-pdncqfpbqckcqboc.sgf');
  click('qf'); click('qc');
  { const p = xy('qb'); c3.window._boardClickHandler(p.x, p.y); }
  check('T33 motor: tu jugada IT muestra ? azul en tu piedra mientras el rival piensa', JSON.stringify(at('qb')) === '["LB:?"]', JSON.stringify(at('qb')));
  flush();
  // marcada y luego SIN marca: R18 (IT ?) → pase del rival → P19 (sin marca) debe llevar círculo, no la ?
  start('4-4 Joseki/B-pdncqfpbqckcqbttobocpcnbpatt.sgf');
  click('qf'); click('qc'); click('qb');
  check('anti-vacío: tras el pase del rival la ? de R18 sigue (el pase no tiene piedra)', JSON.stringify(at('qb')) === '["LB:?"]', JSON.stringify(at('qb')));
  { const p = xy('ob'); c3.window._boardClickHandler(p.x, p.y); }   // sin vaciar timers: antes de que responda el rival
  check('T33 motor: jugada sin marca tras una marcada → círculo, y el símbolo anterior desaparece',
    JSON.stringify(at('ob')) === '["CR"]' && at('qb').length === 0, JSON.stringify({ ob: at('ob'), qb: at('qb') }));
  c3.window._studyRedraw();
  check('T33 motor: y al repintar (resize) sigue el círculo, no reaparece el símbolo viejo', JSON.stringify(at('ob')) === '["CR"]' && at('qb').length === 0,
    JSON.stringify({ ob: at('ob'), qb: at('qb') }));
  flush();
  check('T33 motor: …y la respuesta sin marca del rival (O18) lleva el círculo', JSON.stringify(at('oc')) === '["CR"]' && at('ob').length === 0, JSON.stringify({ oc: at('oc'), ob: at('ob') }));
  // TE en tu jugada: B-…ttqbqi (tu R10 lleva TE y es la primera jugada del problema)
  start('4-4 Joseki/B-pdncqfpbqckcttqbqi.sgf');
  check('T33 motor: posición inicial sin símbolos (la CR de la raíz es markup del SGF, no la tocamos)', at('qi').length === 0);
  { const p = xy('qi'); c3.window._boardClickHandler(p.x, p.y); }
  check('T33 motor: tu jugada TE → ★ verde', JSON.stringify(at('qi')) === '["LB:★"]', JSON.stringify(at('qi')));
  flush();
  // Problema SIN marcas: todo como antes (solo círculos, nunca LB)
  start('4-4 Joseki/B-pdncqfpbqckc.sgf');
  click('qf'); click('qc');
  const anyLB = c3.wgoBoard.obj_arr.some(col => col.some(cell => cell.some(o => typeName(o.type) === 'LB')));
  check('T33 motor: problema sin marcas → ningún símbolo, círculo en la última (L17)', !anyLB && JSON.stringify(at('kc')) === '["CR"]' && at('qc').length === 0,
    JSON.stringify({ kc: at('kc'), qc: at('qc') }));

  // ── AV: aviso de posición de elección (motor real, SGF generados con TVALERT) ──
  {
    const bw = () => c3.document.querySelector('#board-wrap');
    const fl = () => c3.document.getElementById('result-flash');
    const nSnd = () => sounds.filter(x => x === 'choice').length;
    const stoneAt = m => { const p = xy(m); return c3.wgoBoard.obj_arr[p.x][p.y].some(o => o.type === undefined && (o.c === 1 || o.c === -1)); };
    const tap = m => { const p = xy(m); c3.window._boardClickHandler(p.x, p.y); };   // sin vaciar temporizadores
    const step = () => { delays.shift(); timers.shift()(); };
    const reset = () => { timers.length = 0; delays.length = 0; };

    const A = c3.choiceAlertOf;
    check('AV: duración del aviso 1,2 s', c3.CHOICE_ALERT_MS === 1200);
    const rB = c3.parseSgfTree(fs.readFileSync(path.join(OUT, '4-4 Joseki/B-pdncqfpbqckc.sgf'), 'utf8'));
    const rW = c3.parseSgfTree(fs.readFileSync(path.join(OUT, '4-4 Joseki/W-pdncqfpbqckc.sgf'), 'utf8'));
    check('AV choiceAlertOf: elección en la raíz (la marca va en la jugada esperada) → ⑂ + nombre; sin marca → null',
      JSON.stringify(A(rB)) === JSON.stringify({ kind: 'choice', sym: '⑂', name: 'Low Enclosure' }) && A(rW) === null && A(null) === null, JSON.stringify(A(rB)));
    check('AV choiceAlertOf: whatif → ?, y un nombre con «:» se respeta', A({ children: [{ TVALERT: 'whatif:A: b' }] }).sym === '?'
      && A({ children: [{ TVALERT: 'whatif:A: b' }] }).name === 'A: b' && A({ children: [{ TVALERT: 'otro:x' }] }) === null);

    // 1) elección al empezar (Low Enclosure · B)
    reset(); let s0 = nSnd();
    start('4-4 Joseki/B-pdncqfpbqckc.sgf', true);
    check('AV al empezar: borde azul, destello «⑂ Low Enclosure» y sonido del aviso',
      bw().classList.contains('board-choice') && fl().textContent === '⑂ Low Enclosure' && fl().className === 'show choice' && nSnd() === s0 + 1,
      JSON.stringify({ t: fl().textContent, c: fl().className, s: nSnd() - s0 }));
    check('AV: el temporizador del destello es de 1,2 s', delays.length === 1 && delays[0] === 1200, JSON.stringify(delays));
    tap('qf');
    check('AV-09: un clic durante el destello no hace nada (ni piedra, ni fallo, ni sonido de piedra)',
      !stoneAt('qf') && c3.lastResult === undefined && bw().classList.contains('board-choice') && timers.length === 1);
    step();
    check('AV: al apagarse el destello se desvanece y el borde sigue', fl().className === 'hide choice' && bw().classList.contains('board-choice'));
    tap('qf');
    check('AV-07: al jugar, el borde azul desaparece y la jugada entra', stoneAt('qf') && !bw().classList.contains('board-choice'));
    flush();
    check('anti-vacío: tras la respuesta del rival (sin elección) no hay aviso', stoneAt('pb') && !bw().classList.contains('board-choice') && nSnd() === s0 + 1);
    // 2) Back y Restart repiten el aviso; repintar conserva el borde sin sonido
    reset(); c3.window._studyBack();
    check('AV-05: Back a la posición de elección repite el aviso completo', !stoneAt('qf') && bw().classList.contains('board-choice')
      && fl().textContent === '⑂ Low Enclosure' && nSnd() === s0 + 2 && timers.length === 1);
    tap('qf');
    check('AV-05: …con su bloqueo', !stoneAt('qf'));
    flush(); click('qf');
    reset(); c3.window._studyRestart();
    check('AV-05: Restart repite el aviso completo (renderSetup es un stub: no se mira el tablero)', bw().classList.contains('board-choice') && nSnd() === s0 + 3 && timers.length === 1, JSON.stringify({ st: stoneAt('qf'), b: bw().classList.contains('board-choice'), s: nSnd() - s0, t: timers.length }));
    flush();
    const s1 = nSnd();
    c3.window._studyRedraw();
    check('AV-06: repintar conserva el borde, sin destello ni sonido', bw().classList.contains('board-choice') && nSnd() === s1 && fl().className === 'hide choice');
    // 3) Explorar (Free): quita el aviso; al salir vuelve solo el borde
    reset(); c3.window._studyRestart();
    c3.window._studyExploreToggle();
    check('AV-15: entrar en Explorar quita borde, destello y bloqueo', !bw().classList.contains('board-choice') && fl().className === '' && timers.length === 0);
    c3.window._studyExploreToggle();
    check('AV-15: al salir vuelve el borde sin destello ni sonido', bw().classList.contains('board-choice') && fl().className === '' && nSnd() === s1 + 1 && timers.length === 0,
      JSON.stringify({ c: fl().className, s: nSnd() - s1, t: timers.length }));
    tap('qf');
    check('AV-15: …y se puede jugar en seguida (sin bloqueo)', stoneAt('qf'));
    flush();
    // 4) elección a mitad, tras el PASE del rival, de tipo ¿y si? (Corner Hane · W)
    reset(); s0 = nSnd();
    start('4-4 Joseki/W-pdncqfpbqckcttqbqi.sgf', true);
    check('anti-vacío: problema que no empieza en elección → sin aviso', !bw().classList.contains('board-choice') && nSnd() === s0 && timers.length === 0);
    click('pb');
    tap('kc'); step();   // respuesta del rival: pase de negro
    check('AV-03: tras la jugada del rival (aquí un pase) salta el aviso ¿y si?: «? Corner Hane»',
      bw().classList.contains('board-choice') && fl().textContent === '? Corner Hane' && nSnd() === s0 + 1 && timers.length === 1, JSON.stringify({ t: fl().textContent, s: nSnd() - s0 }));
    tap('qb');
    check('AV-09: bloqueo también a mitad de problema', !stoneAt('qb'));
    step(); tap('qb'); flush();
    check('AV: tras el destello se juega la rama y el problema termina bien', stoneAt('qb') && c3.lastResult === true && !bw().classList.contains('board-choice'));
    // 5) un problema sin ninguna marca nunca avisa
    reset(); s0 = nSnd();
    start('4-4 Joseki/W-pdncqfpbqckc.sgf', true);
    check('AV anti-vacío: Low Enclosure · W (sin instrucción) no avisa y se juega de inmediato',
      !bw().classList.contains('board-choice') && timers.length === 0 && nSnd() === s0 && (tap('pb'), stoneAt('pb')));
    flush();
    // 6) el temporizador de un problema anterior no toca el siguiente
    reset();
    start('4-4 Joseki/B-pdncqfpbqckc.sgf', true);
    start('4-4 Joseki/W-pdncqfpbqckc.sgf', true);
    check('AV: al cambiar de problema el borde del anterior no se queda', !bw().classList.contains('board-choice'));
    flush();
    check('AV: el temporizador del problema anterior no toca el destello del nuevo', fl().className === '', fl().className);
  }

  // Visor de partidas
  c3.gmGame = { getPosition: () => ({ get: () => 0 }) };
  c3.gmRebuildGameFromStack = () => {}; c3.gmSetupBoardClick = () => {};
  vm.runInContext(grab('function gmRenderCurrentNode('), c3);
  c3.clearBoard(); c3.gmCurrentNode = { move: { x: 3, y: 3, c: 1 }, BM: '1', children: [], comment: '' }; c3.gmRenderCurrentNode();
  const g1 = c3.wgoBoard.obj_arr[3][3].map(o => typeName(o.type) + (o.text ? ':' + o.text : ''));
  c3.gmCurrentNode = { move: { x: 4, y: 4, c: -1 }, children: [], comment: '' }; c3.gmRenderCurrentNode();
  const g2 = c3.wgoBoard.obj_arr[4][4].map(o => typeName(o.type));
  c3.gmCurrentNode = { move: { x: 5, y: 5, c: 1 }, TE: '1', markup: [{ type: 'LB', x: 5, y: 5, text: 'A' }], children: [], comment: '' }; c3.gmRenderCurrentNode();
  const g3 = c3.wgoBoard.obj_arr[5][5].map(o => typeName(o.type) + (o.text ? ':' + o.text : ''));
  check('T33 partidas: jugada BM → ✕; sin marca → círculo; con LB propio del SGF manda el LB',
    JSON.stringify(g1) === '["LB:✕"]' && JSON.stringify(g2) === '["CR"]' && JSON.stringify(g3) === '["LB:A"]', JSON.stringify({ g1, g2, g3 }));
}

// JP.4/JP.5: contexto y letras con el parser real
{
  const r = load('5-5 Ctx/B-pdqcctx-Bjcpcqdqe.sgf');
  const st = F.getSetupStones(r);
  const mk = F.getMarkup(r);
  check('JP.4 WGo: la piedra de contexto K17 está en la posición inicial con su cuadrado', st.black.some(p => p.x === 9 && p.y === 2) && mk.some(m => m.type === 'SQ' && m.x === 9 && m.y === 2), JSON.stringify(mk));
  const qd = r.children[0].children[0];
  check('JP.5 WGo: la letra A llega como markup LB en su jugada', (qd.markup || []).some(m => m.type === 'LB' && m.text === 'A' && m.x === 9 && m.y === 2), JSON.stringify(qd.markup));
  const g = load('5-5 Ctx/W-pdqcctx-Wcccdqdpcod.sgf');
  check('JP.4 WGo: contexto de dos piedras blancas en la posición inicial', F.getSetupStones(g).white.length === 3);
}

console.log('\nRESULTADO CLIENTE JP: ' + (FAILS ? FAILS + ' FALLOS' : 'TODO OK (' + N + ' checks)'));
process.exit(FAILS ? 1 : 0);
