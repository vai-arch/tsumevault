// Tests de js/board_style.js (docs/WORKPLAN_ESTILOS.md): modelo de estilos por sección, migración desde las claves
// antiguas, descolocación fija, aplicación al tablero sin recrearlo y piedras planas. Sin navegador: WGo + board_core +
// board_style en un contexto vm con un DOM mínimo.  Uso: node tests/test_board_style.js
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = path.join(__dirname, '..');
let N = 0, FAILS = 0;
function check(name, cond, extra) { N++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && extra ? '  ' + extra : '')); if (!cond) FAILS++; }
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function el() {
  return { style: {}, dataset: {}, classList: { add() { }, remove() { }, toggle() { }, contains() { return false; } }, addEventListener() { }, appendChild(c) { return c; },
    setAttribute() { }, querySelector: () => null, querySelectorAll: () => [], children: [], textContent: '', innerHTML: '' };
}
function env(store, fetchImpl) {
  const ctx = { console, setTimeout, clearTimeout, setInterval, clearInterval, Promise, JSON, Math, Date, Map, Set, URL,
    navigator: { userAgent: 'node' }, localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
    matchMedia: () => ({ matches: false, addEventListener() { } }), Audio: function () { this.play = () => Promise.resolve(); }, Image: function () { },
    fetch: fetchImpl || (async () => { throw new Error('sin red'); }), AbortSignal: { timeout: () => undefined }, innerWidth: 1200, innerHeight: 800 };
  ctx.window = ctx; ctx.self = ctx;
  ctx.document = { createElement: () => el(), createElementNS: () => el(), getElementById: () => el(), getElementsByTagName: () => [{ src: 'wgo/wgo.min.js' }],
    querySelector: () => null, querySelectorAll: () => [], body: el(), documentElement: el(), addEventListener() { } };
  vm.createContext(ctx);
  for (const f of ['wgo/wgo.min.js', 'js/board_core.js', 'js/board_style.js']) vm.runInContext(fs.readFileSync(path.join(ROOT, f), 'utf8'), ctx, { filename: f });
  return c => vm.runInContext(c, ctx);
}

// 1. carga y migración
let run = env({ board_background: '#5c3a1e', stone_set_label: 'Kaya' });
check('carga sin la página: board_style.js después de board_core.js', run('typeof bsApply') === 'function');
check('migración: sin board_style_v1, el estilo por defecto sale de las claves antiguas y no hay excepciones',
  eq(run('bsModel'), { default: { bg: '#5c3a1e', stones: 'Kaya', jitter: false }, problems: null, games: null, joseki: null, play: null, archive: null }), JSON.stringify(run('bsModel')));
check('migración: sin nada guardado, Classic y realistas', eq(run(`bsParseModel(null, null, null).default`), { bg: '#c4943a', stones: '', jitter: false }));
check('modelo corrupto → se reconstruye con las claves antiguas', eq(run(`bsParseModel('{no json', '#e8dab0', '').default`), { bg: '#e8dab0', stones: '', jitter: false }));
const parsed = run(`bsParseModel(JSON.stringify({ default: { bg: '#c8d1b0', stones: 'Flat', jitter: true }, games: { bg: 7, stones: null, jitter: 'si' }, play: null, raro: {} }), '#000', 'X')`);
check('modelo guardado: se respeta y se limpia (valores raros → por defecto; claves desconocidas fuera)',
  eq(parsed.default, { bg: '#c8d1b0', stones: 'Flat', jitter: true }) && eq(parsed.games, { bg: '#c4943a', stones: '', jitter: false }) && parsed.play === null && !('raro' in parsed), JSON.stringify(parsed));

// 2. secciones
check('pestañas → secciones (las cuatro de problemas juntas)', eq(['collections', 'focus', 'free', 'review', 'games', 'josekis', 'play', 'otra'].map(t => run(`bsSectionOfTab('${t}')`)),
  ['problems', 'problems', 'problems', 'problems', 'games', 'joseki', 'play', 'problems']));
run(`globalThis.M0 = bsParseModel(null, '#5c3a1e', 'Kaya')`);
run(`globalThis.M1 = bsWithStyle(M0, 'joseki', { stones: 'Flat' })`);
check('excepción nueva: parte del estilo por defecto y solo cambia lo tocado', eq(run('M1.joseki'), { bg: '#5c3a1e', stones: 'Flat', jitter: false }));
check('el estilo por defecto y el modelo original no cambian', eq(run('M1.default'), run('M0.default')) && run('M0.joseki') === null);
check('bsStyleFor: la sección con excepción usa la suya; las demás, la de por defecto', run(`bsStyleFor(M1, 'joseki').stones`) === 'Flat' && run(`bsStyleFor(M1, 'games').stones`) === 'Kaya' && run(`bsStyleFor(M1, null).stones`) === 'Kaya');
run(`globalThis.M2 = bsWithStyle(M1, 'default', { bg: '#c8d1b0' })`);
check('cambiar el de por defecto afecta a las secciones sin excepción, no a las que tienen la suya', run(`bsStyleFor(M2, 'games').bg`) === '#c8d1b0' && run(`bsStyleFor(M2, 'joseki').bg`) === '#5c3a1e');
check('«Use default» quita la excepción', run(`bsWithoutOverride(M2, 'joseki').joseki`) === null && run(`bsStyleFor(bsWithoutOverride(M2, 'joseki'), 'joseki').bg`) === '#c8d1b0');

// 3. descolocación fija
const J = run(`(() => { const out = []; for (let x = 0; x < 19; x++) for (let y = 0; y < 19; y++) out.push(bsJitter(x, y)); return out; })()`);
check('descolocación: siempre la misma para la misma posición', eq(run('bsJitter(3, 15)'), run('bsJitter(3, 15)')) && eq(run('bsJitter(0, 0)'), run('bsJitter(0, 0)')));
check('descolocación: dentro del límite en los dos ejes', J.every(([dx, dy]) => Math.abs(dx) <= 0.04 && Math.abs(dy) <= 0.04));
check('anti-vacío: cambia de una posición a otra y usa todo el rango', new Set(J.map(j => j.join())).size > 340 && Math.max(...J.map(j => Math.abs(j[0]))) > 0.033 && Math.max(...J.map(j => Math.abs(j[1]))) > 0.033);
check('descolocación: (x, y) y (y, x) no coinciden', !eq(run('bsJitter(2, 5)'), run('bsJitter(5, 2)')));
const overlaps = run(`(() => { const R = BS_FLAT_RADIUS / 2, bad = [];   // radio de la piedra en casillas
  for (let x = 0; x < 19; x++) for (let y = 0; y < 19; y++) for (const [ox, oy] of [[1, 0], [0, 1], [1, 1], [1, -1]]) {
    const x2 = x + ox, y2 = y + oy; if (x2 > 18 || y2 < 0 || y2 > 18) continue;
    const [a, b] = bsJitter(x, y), [c, d] = bsJitter(x2, y2);
    if (Math.hypot(x2 + c - x - a, y2 + d - y - b) < 2 * R - 1e-9) bad.push([x, y, x2, y2]);
  } return bad; })()`);
check('descolocación: ninguna pareja de vecinas se pisa en todo el 19×19 (como mucho se tocan)', overlaps.length === 0, JSON.stringify(overlaps.slice(0, 5)));

// 4. aplicar y guardar
const store = {};
run = env(store);
run(`bsModel = bsWithStyle(bsWithStyle(bsParseModel(null, '#c4943a', ''), 'joseki', { bg: '#c8d1b0', stones: 'Flat', jitter: true }), 'default', { bg: '#5c3a1e' }); bsSave()`);
check('bsSave guarda el modelo y las claves antiguas con el estilo por defecto', JSON.parse(store.board_style_v1).joseki.stones === 'Flat' && store.board_background === '#5c3a1e' && store.stone_set_label === '');
run(`bsApply('joseki')`);
check('bsApply: fondo, piedras planas y descolocación de la sección', run('currentBoardBg') === '#c8d1b0' && run('!!(currentStoneSet && currentStoneSet.flat)') && run('currentJitter') === true && run('bsSection') === 'joseki');
run(`bsApply('games')`);
check('bsApply: sección sin excepción → estilo por defecto (realistas)', run('currentBoardBg') === '#5c3a1e' && run('currentStoneSet') === null && run('currentJitter') === false);
check('juego de piedras desconocido (o aún sin cargar) → realistas', run(`bsResolveStones('NoExiste')`) === null && run(`bsResolveStones('')`) === null);

// 5. repintado sin recrear el tablero
run(`globalThis.FB = { theme: { gridLinesColor: 'orig', starColor: '#000' }, element: { style: {} }, redraws: 0, redraw() { this.redraws++; } }; wgoBoard = FB; bsApply('joseki')`);
check('repinta el MISMO tablero: fondo, piedras planas, líneas oscuras, sombra y un repintado',
  run('FB.background') === '#c8d1b0' && run('FB.element.style.backgroundColor') === '#c8d1b0' && run('FB.element.style.backgroundImage') === 'none' &&
  run('typeof FB.stoneHandler.shadow.draw') === 'function' && run('FB.theme.gridLinesColor') !== 'orig' && run('FB.element.style.boxShadow') !== '' && run('FB.redraws') === 1);
run(`bsModel = bsWithStyle(bsModel, 'default', { bg: 'img/boards/kaya.jpg' }); bsApply('games')`);
check('al volver a realistas se recupera el tema original y el fondo de imagen se pone como imagen',
  run('FB.theme.gridLinesColor') === 'orig' && run('FB.element.style.boxShadow') === '' && run('FB.element.style.backgroundImage') === "url('img/boards/kaya.jpg')" &&
  run('FB.element.style.backgroundColor') === '' && run('FB.stoneHandler === WGo.Board.drawHandlers.REALISTIC') && run('FB.redraws') === 2);
run('wgoBoard = null');

// 6. piedras planas: dibujo
run(`globalThis.mkCtx = () => { const c = { ops: [], arc(x, y, r) { this.ops.push(['arc', x, y, r]); }, beginPath() { }, fill() { this.ops.push(['fill', this.fillStyle]); },
  stroke() { this.ops.push(['stroke']); }, createRadialGradient() { return { addColorStop() { } }; } }; return c; };
  globalThis.BD = { getX: x => 100 + x * 20, getY: y => 100 + y * 20, stoneRadius: 10, fieldWidth: 20, fieldHeight: 20 };
  globalThis.FH = bsFlatHandler();`);
run(`currentJitter = false; globalThis.cB = mkCtx(); FH.stone.draw.call(cB, { x: 3, y: 4, c: WGo.B }, BD); globalThis.cW = mkCtx(); FH.stone.draw.call(cW, { x: 3, y: 4, c: WGo.W }, BD);`);
check('plana: centrada en la intersección y con radio menor que la casilla', run('cB.ops[0][1] === 160 && cB.ops[0][2] === 180 && Math.abs(cB.ops[0][3] - 9.2) < 1e-9'));
check('plana: negra sin borde; blanca con borde fino', run('cB.ops.some(o => o[0] === "stroke")') === false && run('cW.ops.some(o => o[0] === "stroke")') === true);
run(`currentJitter = true; globalThis.cJ = mkCtx(); FH.stone.draw.call(cJ, { x: 3, y: 4, c: WGo.B }, BD); globalThis.cS = mkCtx(); FH.shadow.draw.call(cS, { x: 3, y: 4, c: WGo.B }, BD); globalThis.JJ = bsJitter(3, 4);`);
check('plana con descolocación: se mueve exactamente lo que dice bsJitter', Math.abs(run('cJ.ops[0][1]') - (160 + run('JJ[0]') * 20)) < 1e-9 && Math.abs(run('cJ.ops[0][2]') - (180 + run('JJ[1]') * 20)) < 1e-9);
check('sombra: en el mismo sitio que la piedra y algo mayor', run('cS.ops[0][1] === cJ.ops[0][1] && cS.ops[0][2] === cJ.ops[0][2] && cS.ops[0][3] > cJ.ops[0][3]'));
run(`globalThis.IH = buildStoneHandler({ label: 'X', black: ['b.png'], white: ['w.png'] }); getImg = () => ({ complete: true, naturalWidth: 1 });
  globalThis.cI = { drawImage(img, x, y, w) { this.args = [x, y, w]; } }; IH.stone.draw.call(cI, { x: 3, y: 4, c: WGo.B }, BD);`);
check('piedras de imagen con descolocación: se mueven y se dibujan del tamaño de las planas (no se pisan)', Math.abs(run('cI.args[0]') - (160 + run('JJ[0]') * 20 - 9.2)) < 1e-9 && Math.abs(run('cI.args[2]') - 18.4) < 1e-9);
run(`currentJitter = false; IH.stone.draw.call(cI, { x: 3, y: 4, c: WGo.B }, BD);`);
check('piedras de imagen sin descolocación: centradas y de tamaño completo, como siempre', run('cI.args[0]') === 150 && run('cI.args[2]') === 20);
check('buildStoneHandler: null → realistas; Flat → planas', run('buildStoneHandler(null) === WGo.Board.drawHandlers.REALISTIC') && run(`typeof buildStoneHandler({ flat: true }).shadow.draw`) === 'function');

// 7. carga de stones.json / boards.json (una sola vez)
(async () => {
  let calls = 0;
  const st = {};
  const r2 = env({ stone_set_label: 'Kaya' }, async (u) => {
    calls++;
    if (u.includes('stones.json')) return { ok: true, json: async () => [{ label: 'Kaya', black: ['kb.png'], white: ['kw.png'] }] };
    return { ok: true, json: async () => [{ file: 'kaya.jpg' }] };
  });
  await r2('bsLoadVisual()'); await r2('bsLoadVisual()');
  await new Promise(r => setTimeout(r, 10));
  check('al cargar, las piedras guardadas se aplican sin abrir ⚙ (E1)', r2('currentStoneSet && currentStoneSet.label') === 'Kaya' && r2(`currentStoneSet.black[0]`) === 'img/stones/kb.png');
  check('fondos de imagen con su ruta y nombre', eq(r2('boardImages'), [{ label: 'kaya', value: 'img/boards/kaya.jpg' }]));
  check('stones.json y boards.json se piden una sola vez', calls === 2, String(calls));
  const r3 = env({});
  await r3('bsLoadVisual()');
  check('sin red: listas vacías y realistas, sin errores', r3('stoneSets.length') === 0 && r3('currentStoneSet') === null);
  console.log(`\n${N - FAILS}/${N} PASS`);
  process.exit(FAILS ? 1 : 0);
})();
