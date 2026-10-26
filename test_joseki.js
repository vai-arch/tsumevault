#!/usr/bin/env node
/* J3: batería del modo aprender de josekis.
 *   python3 extract_joseki.py && node test_joseki.js
 * Parte 1: funciones PURAS extraídas del cliente real (joseki_bundle.js) contra
 *          el JSON real de "4-4 Joseki" compilado por import_joseki.py
 *          (test_joseki_fixture.json, versión con las dos correcciones) y, para
 *          J3.2, tu 4-4 real con el contexto N17 y letras (test_joseki_fixture_ctx.json).
 * Parte 2: las dos ramas nuevas de sw.js (manifiesto network-first y JSON
 *          direccionados por hash) con fetch/caches simulados.
 * Parte 3: humo de UI del módulo J3 real con DOM y WGo simulados.
 */
'use strict';
const fs = require('fs');
const vm = require('node:vm');

const fails = [];
let n = 0;
function check(name, cond, extra = '') {
  n++;
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (cond ? '' : `  ${extra}`));
  if (!cond) fails.push(name);
}

// ── Parte 1: funciones puras ──
const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('joseki_bundle.js', 'utf8'), ctx);
const { jsXform, jsXformInv, jsMarkInfo, jsOptions, jsIsEndpoint, jsSignal, jsNamePath, jsGhostsVisible } = ctx;
const J = JSON.parse(fs.readFileSync('test_joseki_fixture.json', 'utf8'));
const JC = JSON.parse(fs.readFileSync('test_joseki_fixture_ctx.json', 'utf8'));   // J3.2

// navegación por coordenadas: walk(['pd','nc',...]) -> nodo (los pases implícitos
// se recorren con 'pass', y los contextos con su token 'ctx-…')
function walk(path, root = J.root) {
  let node = root;
  for (const m of path) {
    node = node.ch.find(k => k.m === m);
    if (!node) throw new Error('ruta inexistente: ' + path.join('.'));
  }
  return node;
}
const opts = (node, w = true) => jsOptions(node, w).map(o => `${o.c}${o.m}${o.sym}${o.via ? '*' : ''}`).sort();

// Simetrías (J-40)
const all = [];
for (let x = 0; x < 19; x++) for (let y = 0; y < 19; y++) all.push(String.fromCharCode(97 + x) + String.fromCharCode(97 + y));
let invOk = true, inRange = true;
for (let t = 0; t < 8; t++) for (const m of all) {
  const r = jsXform(m, t);
  if (jsXformInv(r, t) !== m) invOk = false;
  if (!/^[a-s]{2}$/.test(r)) inRange = false;
}
check('simetrías: la inversa deshace la transformación en los 361 puntos × 8', invOk);
check('simetrías: el resultado siempre cae dentro del 19x19', inRange);
check('simetrías: t=0 es la identidad', all.every(m => jsXform(m, 0) === m));
const imgs = new Set([...Array(8).keys()].map(t => jsXform('pd', t)));
check('simetrías: Q16 (sobre la antidiagonal) da exactamente los 4 puntos 4-4', imgs.size === 4
  && ['dd', 'dp', 'pd', 'pp'].every(m => imgs.has(m)), [...imgs].join(','));
const imgs2 = new Set([...Array(8).keys()].map(t => jsXform('nc', t)));
check('simetrías: un punto fuera de ambas diagonales (O17, la aproximación keima) tiene 8 imágenes distintas', imgs2.size === 8, [...imgs2].join(','));
check('simetrías: el pase no cambia', [...Array(8).keys()].every(t => jsXform('pass', t) === 'pass' && jsXformInv('pass', t) === 'pass'));

// Símbolos (J-31)
check('símbolo: buena ●', jsMarkInfo({}).sym === '●' && jsMarkInfo({}).kind === 'good');
check('símbolo: tesuji ★', jsMarkInfo({ te: true }).sym === '★');
check('símbolo: dudosa ▲', jsMarkInfo({ q: 'doubtful' }).sym === '▲');
check('símbolo: mala ✕', jsMarkInfo({ q: 'bad' }).sym === '✕');
check('símbolo: ¿y si? ? (prioridad sobre la calidad)', jsMarkInfo({ it: true, q: 'bad' }).sym === '?');
check('símbolo: un pase implícito no se marca como ¿y si?', jsMarkInfo({ it: true, implicit: true }).kind === 'good');

// Opciones sobre el fichero real
check('raíz: una opción, B pd buena', JSON.stringify(opts(J.root)) === JSON.stringify(['Bpd●']), opts(J.root).join(','));
const nc = walk(['pd', 'nc']);
check('tras nc: bifurcación B qf / B pf, ambas buenas y con nombre',
  JSON.stringify(opts(nc)) === JSON.stringify(['Bpf●', 'Bqf●'])
  && jsOptions(nc, true).every(o => o.node.name), opts(nc).join(','));
const kc = walk(['pd', 'nc', 'qf', 'pb', 'qc', 'kc']);
check('tras kc (Low Enclosure): el pase implícito se aplana — W qb y W qh (vía implícito) + B qb, todos ¿y si?',
  JSON.stringify(opts(kc)) === JSON.stringify(['Bqb?', 'Wqb?*', 'Wqh?*']), opts(kc).join(','));
check('tras kc: ninguna opción es el propio pase implícito (anti-vacío del aplanado)',
  kc.ch.some(k => k.implicit) && !jsOptions(kc, true).some(o => o.node.implicit));
check('tras kc con ¿y si? ocultos: sin opciones', jsOptions(kc, false).length === 0);
check('kc es final de línea (solo cuelgan ramas ¿y si?)', jsIsEndpoint(kc) === true);
check('el pase implícito nunca es final de línea', jsIsEndpoint(kc.ch.find(k => k.implicit)) === false);
check('nc no es final de línea', jsIsEndpoint(nc) === false);
const kc2 = walk(['pd', 'nc', 'pf', 'pb', 'qc', 'kc']);
check('High 1 point tras kc: B qj buena y pase de B malo (chip)',
  JSON.stringify(opts(kc2)) === JSON.stringify(['Bpass✕', 'Bqj●']) && jsOptions(kc2, true).find(o => o.m === 'pass').pass === true, opts(kc2).join(','));
const qbB = walk(['pd', 'nc', 'qf', 'pb', 'qc', 'kc', 'qb']);
check('B qb (¿y si?) → W oc mala y W pase tesuji', JSON.stringify(opts(qbB)) === JSON.stringify(['Woc✕', 'Wpass★']), opts(qbB).join(','));
const oc = walk(['pd', 'nc', 'qf', 'pb', 'qc', 'kc', 'qb', 'oc']);
check('marcas: W oc trae TR en pb', JSON.stringify(oc.marks) === JSON.stringify({ TR: ['pb'] }), JSON.stringify(oc.marks));

// Señales (J-34)
const s1 = jsSignal(oc);
check('señal: jugada mala que además cierra la línea → bad y end', s1.bad === true && s1.end === true, JSON.stringify(s1));
const qj = walk(['pd', 'nc', 'pf', 'pb', 'qc', 'kc', 'qj']);
check('señal: final de línea bueno → end sin bad', jsSignal(qj).bad === false && jsSignal(qj).end === true);
check('señal: jugada intermedia buena → ni bad ni end', JSON.stringify(jsSignal(nc)) === JSON.stringify({ bad: false, end: false }));

// Ruta de nombres
const stack = [walk(['pd']), walk(['pd', 'nc']), walk(['pd', 'nc', 'qf'])];
check('ruta de nombres: solo los nodos con nombre', jsNamePath(stack) === 'Low Enclosure', jsNamePath(stack));
check('ruta de nombres: vacía en la raíz', jsNamePath([]) === '');

// J3.1: fantasmas visibles
check('J3.1 fantasmas: con "all ghosts" siempre, aunque haya una sola opción', jsGhostsVisible([1], true) === true);
check('J3.1 fantasmas: sin "all ghosts" y una sola opción → ocultos', jsGhostsVisible([1], false) === false);
check('J3.1 fantasmas: sin "all ghosts" y 2+ opciones (pases incluidos) → visibles', jsGhostsVisible(jsOptions(walk(['pd', 'nc', 'pf', 'pb', 'qc', 'kc']), true), false) === true);
check('J3.1 fantasmas: el filtro what-if cuenta (kc sin what-if → 0 opciones → ocultos)', jsGhostsVisible(jsOptions(kc, false), false) === false);

// Cobertura: cada línea del árbol (raíz → final de línea) se puede recorrer en el
// modo aprender SOLO eligiendo opciones de jsOptions (el pase implícito lo pone el
// sistema; los contextos se eligen con su chip).
function treeLines(root) {
  const out = [];
  (function dfs(node, path) {
    for (const k of node.ch) {
      const p = path.concat(k.m);
      if (jsIsEndpoint(k)) out.push(p);
      dfs(k, p);
    }
  })(root, []);
  return out;
}
function reachable(root, path) {
  let node = root, i = 0;
  while (i < path.length) {
    const child = node.ch.find(k => k.m === path[i]);
    const os = jsOptions(node, true);
    let o;
    if (child && child.implicit) { o = os.find(o => o.via === child && o.m === path[i + 1]); i += 2; }
    else { o = child && os.find(o => o.node === child); i += 1; }
    if (!o) return false;
    node = o.node;
  }
  return jsIsEndpoint(node);
}
const L1 = treeLines(J.root);
check('las 9 líneas del 4-4 de pruebas se recorren eligiendo opciones y acaban en final de línea',
  L1.length === 9 && L1.every(p => reachable(J.root, p)), `${L1.filter(p => reachable(J.root, p)).length}/${L1.length}`);
const L2 = treeLines(JC.root);
check('J3.2: las 49 líneas de tu 4-4 real (con el contexto N17) también, incluidas las que pasan por el contexto',
  L2.length === 49 && L2.every(p => reachable(JC.root, p)) && L2.filter(p => p.includes('ctx-Bmc')).length > 0,
  `${L2.filter(p => reachable(JC.root, p)).length}/${L2.length}`);

// J3.2: contexto
check('J3.2 símbolo: contexto ◆ (prioridad sobre todo lo demás)', jsMarkInfo({ ctx: { B: [], W: [] }, it: true }).sym === '◆'
  && jsMarkInfo({ ctx: { B: [], W: [] } }).kind === 'context');
const qcC = walk(['pd', 'qc'], JC.root);
const oQc = jsOptions(qcC, true);
check('J3.2 opciones: tras la invasión 3-3, el contexto es una opción ctx (no pase, con su nodo y nombre)',
  oQc.length === 1 && oQc[0].ctx === true && oQc[0].pass === false && oQc[0].node.name === 'SAN-SAN with O-Keima Extension', JSON.stringify(oQc.map(o => [o.m, o.ctx])));
check('J3.2 opciones: las jugadas normales llevan ctx=false', jsOptions(walk(['pd'], JC.root), true).every(o => o.ctx === false));
check('J3.2 opciones: un contexto no se oculta con "what-if" desmarcado', jsOptions(qcC, false).length === 1);
check('J3.2 fantasmas: un contexto no cuenta como alternativa (contexto + 1 jugada → ocultos)',
  jsGhostsVisible([{ ctx: true }, { ctx: false }], false) === false && jsGhostsVisible([{ ctx: true }, { ctx: false }, { ctx: false }], false) === true);
const ctxN = walk(['pd', 'qc', 'ctx-Bmc'], JC.root);
check('J3.2: el contexto no es final de línea y su señal no es ni mala ni final', jsIsEndpoint(ctxN) === false
  && JSON.stringify(jsSignal(ctxN)) === JSON.stringify({ bad: false, end: false }));
check('J3.2 ruta de nombres: el nombre del contexto aparece', /SAN-SAN with O-Keima Extension/.test(jsNamePath([walk(['pd'], JC.root), qcC, ctxN])));

// ── Parte 2: sw.js ──
(async () => {
  function makeSw(network) {
    const store = new Map();           // url completa -> Response clonable
    const keyOf = r => typeof r === 'string' ? new URL(r, 'https://h/').href : r.url;
    const cache = {
      match: async r => { const v = store.get(keyOf(r)); return v ? v.clone() : undefined; },
      put: async (r, resp) => { store.set(keyOf(r), resp); },
      keys: async () => [...store.keys()].map(u => ({ url: u })),
      delete: async r => store.delete(keyOf(r)),
      add: async () => {},
    };
    const listeners = {};
    const calls = [];
    const ctx2 = {
      URL, Response, Promise, console,
      caches: { open: async () => cache, keys: async () => [], delete: async () => true, match: async () => undefined },
      fetch: async (req) => { const u = typeof req === 'string' ? req : req.url; calls.push(u); return network(u); },
      self: { addEventListener: (t, f) => { listeners[t] = f; }, skipWaiting: () => {}, clients: { claim: () => {} } },
    };
    vm.createContext(ctx2);
    vm.runInContext(fs.readFileSync('sw.js', 'utf8'), ctx2);
    const go = async (url) => {
      let p = null;
      listeners.fetch({ request: { url }, respondWith: x => { p = x; } });
      if (!p) return null;   // el SW no intercepta
      try { const r = await p; return { status: r.status, text: await r.text() }; } catch (e) { return { error: e.message }; }
    };
    return { go, store, calls, setNetwork: f => { network = f; } };
  }
  const BASE = 'https://h/tsumevault/joseki/';
  let online = true, version = 'v1';
  const net = u => {
    if (!online) throw new Error('offline');
    if (u.endsWith('manifest.json')) return new Response(`{"v":"${version}"}`, { status: 200 });
    return new Response(`json:${u.split('?')[1]}`, { status: 200 });
  };
  const sw = makeSw(net);

  let r = await sw.go(BASE + 'manifest.json');
  check('SW manifiesto online: devuelve la red', r && r.text === '{"v":"v1"}', JSON.stringify(r));
  version = 'v2';
  r = await sw.go(BASE + 'manifest.json');
  check('SW manifiesto: network-first (ve la versión nueva, no la cacheada)', r && r.text === '{"v":"v2"}', JSON.stringify(r));
  online = false;
  r = await sw.go(BASE + 'manifest.json');
  check('SW manifiesto offline: sirve la última copia guardada', r && r.text === '{"v":"v2"}', JSON.stringify(r));
  const sw2 = makeSw(() => { throw new Error('offline'); });
  r = await sw2.go(BASE + 'manifest.json');
  check('SW manifiesto offline sin copia: 503 (el cliente muestra el aviso)', r && r.status === 503, JSON.stringify(r));

  online = true;
  const f1 = BASE + '4-4%20Joseki.json?h=aaa';
  r = await sw.go(f1);
  const callsAfterFirst = sw.calls.length;
  check('SW json: primera petición va a la red', r && r.text === 'json:h=aaa', JSON.stringify(r));
  r = await sw.go(f1);
  check('SW json: misma URL (mismo hash) sale de caché sin red', r && r.text === 'json:h=aaa' && sw.calls.length === callsAfterFirst, `calls=${sw.calls.length - callsAfterFirst}`);
  online = false;
  r = await sw.go(f1);
  check('SW json: offline con la versión cacheada funciona', r && r.text === 'json:h=aaa', JSON.stringify(r));
  online = true;
  const f2 = BASE + '4-4%20Joseki.json?h=bbb';
  r = await sw.go(f2);
  check('SW json: hash nuevo → se descarga la versión nueva', r && r.text === 'json:h=bbb', JSON.stringify(r));
  const keysJ = [...sw.store.keys()].filter(k => k.includes('Joseki.json'));
  check('SW json: la versión antigua de la misma ruta se poda (no se acumula)', keysJ.length === 1 && keysJ[0].endsWith('h=bbb'), keysJ.join(','));
  const other = BASE + 'otro.json?h=ccc';
  await sw.go(other);
  check('SW json: la poda no toca otros ficheros', [...sw.store.keys()].some(k => k.endsWith('Joseki.json?h=bbb')) && [...sw.store.keys()].some(k => k.endsWith('otro.json?h=ccc')));
  const before = sw.calls.length;
  const sgf = await sw.go('https://h/tsumevault/my_collections/a/b/c.sgf');
  check('SW: las ramas nuevas no capturan otras rutas (un .sgf sigue su rama)', sgf && sw.calls.length === before + 1 && sw.calls[sw.calls.length - 1].endsWith('.sgf'));

  // ── Parte 3: humo de UI — el módulo J3 real con DOM y WGo simulados ──
  {
    const els = {};
    function mkEl(id) {
      const el = {
        id, children: [], style: {}, className: '', disabled: false, checked: true, _text: '', listeners: {},
        classList: { _s: new Set(), add(...c) { c.forEach(x => this._s.add(x)); }, remove(...c) { c.forEach(x => this._s.delete(x)); }, contains(c) { return this._s.has(c); } },
        appendChild(c) { this.children.push(c); return c; },
        contains(t) { return t === this || this.children.includes(t); },
        offsetWidth: 150, offsetHeight: 70,
        addEventListener(t, f) { this.listeners[t] = f; },
        get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); },
        set textContent(v) { this._text = String(v); this.children = []; },
        set innerHTML(v) { this._text = ''; this.children = []; },
        get innerHTML() { return ''; },
      };
      return el;
    }
    const docListeners = {};
    const doc = {
      body: mkEl('body'),
      addEventListener: (t, f) => { docListeners[t] = f; },
      getElementById: id => (els[id] = els[id] || mkEl(id)),
      createElement: () => mkEl(null),
      createTextNode: t => ({ textContent: t }),
    };
    class Pos { constructor() { this.m = new Map(); } get(x, y) { return this.m.get(x + ',' + y) || 0; } }
    class Game { constructor() { this.p = new Pos(); } play(x, y, c) { this.p.m.set(x + ',' + y, c); } setStone(x, y, c) { this.p.m.set(x + ',' + y, c); } getPosition() { return this.p; } }
    const sounds = [], alerts = [];
    const board = { objs: [], addObject(o) { this.objs.push(o); },
      element: { getBoundingClientRect: () => ({ left: 100, top: 50 }) }, left: 20, top: 20, fieldWidth: 20, fieldHeight: 20, pixelRatio: 1 };
    const lsStore = new Map();
    const fixtureText = fs.readFileSync('test_joseki_fixture.json', 'utf8');
    const fixtureCtxText = fs.readFileSync('test_joseki_fixture_ctx.json', 'utf8');   // J3.2
    let uiOnline = true;
    const ui = {
      console, Object, JSON, String, Set, Map, encodeURIComponent,
      document: doc, window: { innerWidth: 500, innerHeight: 500 }, Math,
      localStorage: { getItem: k => (lsStore.has(k) ? lsStore.get(k) : null), setItem: (k, v) => lsStore.set(k, String(v)) },
      WGo: { Game, B: 1, W: -1, Board: { drawHandlers: { LB: 'LBh', TR: 'TRh', SQ: 'SQh', CR: 'CRh', MA: 'MAh' } } },
      SGF_BASE: '/tsumevault/', wgoBoard: board, boardSize: 19,
      clearBoard: () => { board.objs = []; }, initBoard: () => {}, switchToBoard: () => {},
      playSound: s => sounds.push(s), alert: m => alerts.push(m),
      fetch: async (u) => {
        if (!uiOnline) throw new Error('offline');
        if (u.endsWith('manifest.json')) return { ok: true, json: async () => ({ format: 1, files: [{ file: '4-4 Joseki', json: '4-4 Joseki.json', hash: 'abc', lines: 9 }] }) };
        if (u.includes('/joseki/4-4%20Joseki.json?h=abc')) return { ok: true, json: async () => JSON.parse(fixtureText) };
        if (u.includes('/joseki/4-4%20Real.json?h=ctx')) return { ok: true, json: async () => JSON.parse(fixtureCtxText) };
        return { ok: false, status: 404 };
      },
    };
    vm.createContext(ui);
    vm.runInContext(fs.readFileSync('joseki_ui_bundle.js', 'utf8') + '\n;this.__api = { jsLoadManifest, jsOpenFile, jsBack, jsRestart, jsRotate, jsInitControls, jsRender, get stack() { return jsStack; }, get sym() { return jsSym; }, setActive(v) { jsActive = v; }, setWhatif(v) { jsShowWhatif = v; }, get showAll() { return jsShowAll; }, get whatif() { return jsShowWhatif; } };', ui);
    const A = ui.__api;
    const hint = () => els['board-hint'].textContent;
    const ghosts = () => board.objs.filter(o => o.type === 'outline');
    const labels = () => board.objs.filter(o => o.type === 'LBh');
    const click = (m) => ui.window._boardClickHandler(m.charCodeAt(0) - 97, m.charCodeAt(1) - 97);
    const play = (...ms) => ms.forEach(click);
    A.setActive(true);
    A.jsInitControls();

    // Sin red y sin manifiesto previo: aviso claro, sin excepción
    uiOnline = false;
    await A.jsLoadManifest();
    check('UI: offline sin manifiesto → aviso en la lista', /No joseki files available/.test(els['js-list'].textContent), els['js-list'].textContent);
    uiOnline = true;
    await A.jsLoadManifest();
    check('UI: la lista muestra el fichero y su nº de líneas', els['js-list'].children.length === 1 && /4-4 Joseki/.test(els['js-list'].textContent) && /9 lines/.test(els['js-list'].textContent), els['js-list'].textContent);
    await A.jsOpenFile({ file: '4-4 Joseki', json: '4-4 Joseki.json', hash: 'abc', lines: 9 });
    check('UI: abrir fichero sin errores', alerts.length === 0, alerts.join('|'));
    check('UI: raíz → un fantasma en Q16 con ●', ghosts().length === 1 && ghosts()[0].x === 15 && ghosts()[0].y === 3 && labels()[0].text === '●');
    check('UI: cabecera con el nombre del fichero', /4-4 Joseki/.test(hint()), hint());
    click('aa');
    check('UI: clic fuera de un fantasma no hace nada', A.stack.length === 0);
    play('pd', 'nc');
    check('UI: dos clics → dos jugadas, piedra B y W en el tablero', A.stack.length === 2 && board.objs.filter(o => o.c === 1 && !o.type).length === 1 && board.objs.filter(o => o.c === -1 && !o.type).length === 1);
    check('UI: tras nc, dos fantasmas negros (bifurcación)', ghosts().length === 2 && ghosts().every(g => g.c === 1));
    check('UI: sonido de piedra al jugar', sounds.filter(s => s === 'stone').length === 2, sounds.join(','));
    play('qf', 'pb', 'qc', 'kc');
    check('UI: final de línea → borde verde + sonido right + texto', els['board-wrap'].classList.contains('board-ok') && sounds[sounds.length - 1] === 'right' && /End of line/.test(hint()), hint());
    check('UI: ruta de nombres en la cabecera', /Low Enclosure/.test(hint()), hint());
    check('UI: en kc, fantasmas ¿y si? en R18 (W y B comparten punto → uno) y R12', ghosts().length === 2 && labels().every(l => l.text === '?'));
    click('qb');
    const pop = els['js-pop'];
    check('J3.1 UI: punto con dos opciones → menú flotante con 2 botones, sin jugar aún',
      A.stack.length === 6 && pop.style.display === 'flex' && pop.children.length === 2, `${pop.style.display} ${pop.children.length}`);
    // R18 = (16,1): x = 100 + 20 + 16*20 = 440 → 440+10+150 > 500-4 → se recoloca a la izquierda
    check('J3.1 UI: el menú se ancla a la intersección y se recoloca en el borde', pop.style.left === (440 - 150 - 10) + 'px' && pop.style.top === (50 + 20 + 20 + 10) + 'px',
      `${pop.style.left} ${pop.style.top}`);
    docListeners.pointerdown({ target: pop.children[0] });
    check('J3.1 UI: pulsar dentro del menú no lo cierra', pop.style.display === 'flex');
    docListeners.pointerdown({ target: {} });
    check('J3.1 UI: pulsar fuera lo cierra', pop.style.display === 'none');
    click('qb');
    docListeners.keydown({ code: 'Escape' });
    check('J3.1 UI: Escape lo cierra', pop.style.display === 'none' && A.stack.length === 6);
    click('qb');
    const chipW = pop.children.find(c => /\(W\)/.test(c.textContent));
    chipW.listeners.click();
    check('J3.1 UI: elegir en el menú lo cierra (al repintar)', pop.style.display === 'none');
    check('UI: elegir la rama de W aplica el pase implícito + la piedra y avisa del tenuki', A.stack.length === 8 && A.stack[6].implicit && /tenuki by B/.test(hint()), hint());
    A.jsBack();
    check('UI: Back salta también el pase implícito (vuelve a kc)', A.stack.length === 6 && A.stack[5].m === 'kc');
    A.setWhatif(false); A.jsRender(null);
    check('UI: ocultar ¿y si? → sin fantasmas en kc', ghosts().length === 0);
    A.setWhatif(true);
    A.jsRestart();
    play('pd', 'nc', 'pf', 'pb', 'qc', 'kc');
    const passChip = els['js-choices'].children.find(c => /Pass/.test(c.textContent));
    check('UI: el pase malo aparece como chip ✕', !!passChip && /✕/.test(passChip.textContent), passChip && passChip.textContent);
    passChip.listeners.click();
    check('UI: elegir una jugada mala → borde rojo + sonido wrong', els['board-wrap'].classList.contains('board-bad') && sounds[sounds.length - 1] === 'wrong');
    check('UI: un pase no pone piedra ni marca de último movimiento', !board.objs.some(o => o.type === 'CR'));
    A.jsRestart();
    play('pd', 'nc', 'qf', 'pb', 'qc', 'kc', 'qb');
    els['js-pop'].children.find(c => /\(B\)/.test(c.textContent)).listeners.click();   // R18 compartido: elegir la de B
    click('oc');
    check('UI: las marcas TR del nodo se dibujan (W oc → TR en pb)', board.objs.some(o => o.type === 'TRh' && o.x === 15 && o.y === 1));
    const before = board.objs.filter(o => !o.type).length;
    A.jsRotate();
    const tr = board.objs.find(o => o.type === 'TRh');
    check('UI: rotar conserva las piedras y transforma las marcas', A.sym === 1 && board.objs.filter(o => !o.type).length === before && tr.x === 18 - 15 && tr.y === 1, JSON.stringify(tr));
    A.jsRotate(); A.jsRotate();
    const cnt = A.stack.length;
    A.jsBack();
    check('UI: Back funciona con el tablero rotado', A.stack.length === cnt - 1);
    // (los pasos anteriores dejaron el tablero rotado: se completa el ciclo de 8)
    while (A.sym !== 0) A.jsRotate();
    check('UI: tras completar el ciclo de rotaciones vuelve a la orientación del fichero', A.sym === 0);
    // J3.1: "all ghosts" desmarcado
    check('J3.1 UI: por defecto (sin preferencias) los dos checks marcados', A.showAll === true && A.whatif === true && els['js-allghosts'].checked === true);
    els['js-allghosts'].checked = false; els['js-allghosts'].listeners.change({ target: els['js-allghosts'] });
    check('J3.1 UI: desmarcar "all ghosts" se recuerda en localStorage', lsStore.get('joseki_show_all') === '0');
    A.jsRestart();
    check('J3.1 UI: una sola continuación → sin fantasmas ni símbolos', ghosts().length === 0 && labels().length === 0);
    const neutral = els['js-choices'].children[0];
    check('J3.1 UI: botón Pass neutro, sin símbolo', els['js-choices'].children.length === 1 && neutral.textContent === 'Pass', neutral && neutral.textContent);
    neutral.listeners.click();
    check('J3.1 UI: el Pass neutro no hace nada si pasar no es una opción', A.stack.length === 0);
    click('pd');
    check('J3.1 UI: con fantasmas ocultos se avanza pulsando el punto correcto', A.stack.length === 1);
    click('aa');
    check('J3.1 UI: un punto incorrecto no hace nada', A.stack.length === 1);
    click('nc');
    check('J3.1 UI: en una bifurcación (2 opciones) los fantasmas vuelven a verse', ghosts().length === 2);
    play('qf', 'pb', 'qc', 'kc', 'qb');
    els['js-pop'].children.find(c => /\(B\)/.test(c.textContent)).listeners.click();
    els['js-choices'].children.find(c => /Pass/.test(c.textContent)).listeners.click();   // B qb → W pass (2 opciones: chip visible)
    play('ob', 'oc', 'pc', 'nb', 'pa');
    const n2 = A.stack.length;
    check('J3.1 UI: tras B Q19 la única continuación es un pase → sin fantasmas, Pass neutro', ghosts().length === 0 && els['js-choices'].children[0].textContent === 'Pass');
    els['js-choices'].children[0].listeners.click();
    check('J3.1 UI: el Pass neutro juega el pase único y llega al final de línea', A.stack.length === n2 + 1 && A.stack[n2].m === 'pass' && /End of line/.test(hint()), hint());
    // Preferencias: un contexto nuevo lee lo guardado
    lsStore.set('joseki_show_whatif', '0');
    A.jsInitControls();
    check('J3.1 UI: al iniciar se aplican las preferencias guardadas a estado y checks',
      A.showAll === false && A.whatif === false && els['js-allghosts'].checked === false && els['js-whatif'].checked === false);
    A.setActive(false);
    const len = A.stack.length;
    ui.window._boardClickHandler(0, 0);
    check('UI: fuera de la pestaña los clics no actúan', A.stack.length === len);

    // ── J3.2: contexto y letras, con tu 4-4 real (contexto N17 = mc) ──
    A.setActive(true); A.setWhatif(true);
    els['js-allghosts'].checked = true; els['js-allghosts'].listeners.change({ target: els['js-allghosts'] });
    alerts.length = 0;
    await A.jsOpenFile({ file: '4-4 Real', json: '4-4 Real.json', hash: 'ctx', lines: 49 });
    check('J3.2 UI: abrir el fichero con contexto y letras sin errores', alerts.length === 0 && A.stack.length === 0 && A.sym === 0, alerts.join('|'));
    const at = (x, y) => board.objs.filter(o => o.x === x && o.y === y);
    const MC = [12, 2];   // N17
    play('pd', 'qc');
    check('J3.2 UI: la jugada con letra la dibuja (A en N17, aún sin piedra) — antes rompía el render',
      at(...MC).some(o => o.type === 'LBh' && o.text === 'A') && !at(...MC).some(o => !o.type), JSON.stringify(at(...MC)));
    check('J3.2 UI: con solo un contexto como continuación, ningún fantasma', ghosts().length === 0);
    const ctxChip = els['js-choices'].children.find(c => /Context/.test(c.textContent));
    check('J3.2 UI: chip «◆ Context · <nombre>»', !!ctxChip && /◆/.test(ctxChip.textContent) && /Context · SAN-SAN with O-Keima Extension/.test(ctxChip.textContent),
      els['js-choices'].children.map(c => c.textContent).join(' | '));
    const nStone = sounds.filter(x => x === 'stone').length;
    ctxChip.listeners.click();
    check('J3.2 UI: elegir el contexto lo apila y pone la piedra negra en N17', A.stack.length === 3 && A.stack[2].ctx && at(...MC).some(o => !o.type && o.c === 1));
    check('J3.2 UI: la piedra de contexto lleva cuadrado', at(...MC).some(o => o.type === 'SQh'), JSON.stringify(at(...MC)));
    check('J3.2 UI: sin marca de última jugada (no hay jugada) ni sonido de piedra',
      !board.objs.some(o => o.type === 'CR') && sounds.filter(x => x === 'stone').length === nStone);
    check('J3.2 UI: el nombre del contexto en la cabecera', /SAN-SAN with O-Keima Extension/.test(hint()), hint());
    check('J3.2 UI: el turno no cambia — siguen dos fantasmas NEGROS (Q16-bloqueo y Q17)', ghosts().length === 2 && ghosts().every(g => g.c === 1));
    click('qd');
    check('J3.2 UI: con letra en el punto, la letra manda y no hay cuadrado', at(...MC).some(o => o.type === 'LBh' && o.text === 'A')
      && !at(...MC).some(o => o.type === 'SQh') && at(...MC).some(o => !o.type && o.c === 1), JSON.stringify(at(...MC)));
    check('J3.2 UI: tras el contexto vuelve la marca de última jugada (R16)', board.objs.some(o => o.type === 'CR' && o.x === 16 && o.y === 3));
    A.jsRotate();
    const R = [18 - 12, 2];   // jsXform('mc', 1)
    check('J3.2 UI: rotar mueve la piedra de contexto y su letra', at(...R).some(o => !o.type && o.c === 1) && at(...R).some(o => o.type === 'LBh' && o.text === 'A')
      && !at(...MC).length, JSON.stringify({ r: at(...R), mc: at(...MC) }));
    A.jsBack();
    check('J3.2 UI: Back al contexto → vuelve el cuadrado (rotado)', A.stack.length === 3 && at(...R).some(o => o.type === 'SQh'));
    A.jsBack();
    check('J3.2 UI: Back otra vez → el contexto se va con su piedra', A.stack.length === 2 && !at(...R).some(o => !o.type), JSON.stringify(at(...R)));
    while (A.sym !== 0) A.jsRotate();
    els['js-allghosts'].checked = false; els['js-allghosts'].listeners.change({ target: els['js-allghosts'] });
    A.jsRender(null);
    const tx = els['js-choices'].children.map(c => c.textContent);
    check('J3.2 UI: con "all ghosts" desmarcado el chip de contexto sigue visible (junto al Pass neutro)',
      tx.length === 2 && tx[0] === 'Pass' && /Context · SAN-SAN/.test(tx[1]), tx.join(' | '));
    A.setWhatif(false); A.jsRender(null);
    check('J3.2 UI: y también con "what-if" desmarcado', els['js-choices'].children.some(c => /Context/.test(c.textContent)));
    A.setWhatif(true);
    click('mc');
    check('J3.2 UI: pulsar el tablero nunca elige el contexto', A.stack.length === 2);
  }

  console.log(`\nRESULTADO JOSEKI: ${fails.length ? `${fails.length} FALLOS: ${fails.join(' | ')}` : 'TODO OK'} (${n} checks)`);
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error('ERROR FATAL', e); process.exit(2); });
