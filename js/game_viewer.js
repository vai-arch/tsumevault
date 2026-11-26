// TsumeVault — visor de partidas compartido (AR0, WORKPLAN_ARCHIVO.md).
// Visor de Games (navegación, reproducción, variantes, comentarios) + AN2 (análisis con KataGo).
// Movido tal cual desde tsumevault.html: se carga con <script src> ANTES del script principal y
// comparte con él el ámbito global (let/const/function de nivel superior).
// La página anfitriona debe definir: ver "Contrato con la página" al final de este fichero.

let gmCurrentGame = null;   // { id, name, sgf_path }
let gmRootNode = null;      // raíz del árbol WGo
let gmNodeStack = [];       // stack de nodos visitados (para prev)
let gmCurrentNode = null;   // nodo actual
let gmGame = null;          // WGo.Game para tracking de posición
let gmTimer = null;         // setInterval handle
let gmTimerRunning = false;
let gmTimerDelay = 3000;    // ms entre movimientos en auto-play
let gmActive = false;       // true cuando el viewer está activo

// ══ GAMES VIEWER (visor) ══

async function gmOpenGame(gameRow) {
  gmStopTimer();
  gmActive = true;
  gmCurrentGame = gameRow;
  try {
    let sgf = gameRow.sgf;   // IA: partidas contra la IA traen el SGF como texto (ai_games.sgf)
    if (sgf == null) {
      const res = await fetch(sgfUrl(gameRow.sgf_path)); // FC12
      if (!res.ok) throw new Error('SGF not found');
      sgf = await res.text();
    }
    const kifu = WGo.Kifu.fromSgf(sgf);
    gmRootNode = kifu.root;
    const size = parseInt((sgf.match(/SZ\[(\d+)\]/) || [, '19'])[1]);
    gmNodeStack = [];
    gmCurrentNode = gmRootNode;
    gmSgfText = sgf; anReset(); // AN2: tras cargar la partida (la ficha usa gmRootNode)
    if (!wgoBoard || boardSize !== size) initBoard(size);
    gmGame = new WGo.Game(boardSize);
    gmGame.allow_rewrite = true;
    gmRenderCurrentNode();
    gmUpdateControls();
    switchToBoard();
    document.getElementById('board-hint').textContent = gameRow.name.replace(/\.sgf$/i, '');
    document.getElementById('board-hint').className = '';
  } catch (e) { console.warn('gmOpenGame', e); alert('Error loading game: ' + e.message); }
}

function gmApplyNodeToGame(node) {
  // Aplica setup stones del nodo raíz
  if (node === gmRootNode) {
    gmGame.allow_rewrite = true;
    for (let x = 0; x < boardSize; x++) for (let y = 0; y < boardSize; y++) gmGame.setStone(x, y, 0);
    if (node.setup) for (const s of node.setup) gmGame.setStone(s.x, s.y, s.c === 1 ? WGo.B : WGo.W);
    if (node.properties) {
      const toCoord = v => ({ x: v.charCodeAt(0) - 97, y: v.charCodeAt(1) - 97 });
      if (node.properties.AB) { const ab = Array.isArray(node.properties.AB) ? node.properties.AB : [node.properties.AB]; ab.forEach(v => { const c = toCoord(v); gmGame.setStone(c.x, c.y, WGo.B); }); }
      if (node.properties.AW) { const aw = Array.isArray(node.properties.AW) ? node.properties.AW : [node.properties.AW]; aw.forEach(v => { const c = toCoord(v); gmGame.setStone(c.x, c.y, WGo.W); }); }
    }
  }
  gmLastCaptured = false;
  if (node.move && node.move.x !== undefined) {
    gmLastCaptured = capturedAny(gmGame.play(node.move.x, node.move.y, node.move.c === 1 ? WGo.B : WGo.W));
  }
}
let gmLastCaptured = false;   // la última jugada aplicada por gmApplyNodeToGame capturó

function gmRebuildGameFromStack() {
  // Reconstruye WGo.Game desde cero siguiendo el stack + nodo actual
  gmGame = new WGo.Game(boardSize);
  gmGame.allow_rewrite = true;
  const path = [...gmNodeStack, gmCurrentNode];
  for (const n of path) gmApplyNodeToGame(n);
}

function gmRenderCurrentNode() {
  const node = gmCurrentNode;
  clearBoard();
  // Dibujar posición actual desde WGo.Game
  gmRebuildGameFromStack();
  const pos = gmGame.getPosition();
  for (let x = 0; x < boardSize; x++) for (let y = 0; y < boardSize; y++) {
    const v = pos.get(x, y);
    if (v === WGo.B) wgoBoard.addObject({ x, y, c: 1 });
    else if (v === WGo.W) wgoBoard.addObject({ x, y, c: -1 });
  }
  // Marcar último movimiento (solo si no hay LB en esa posición)
  if (node.move && node.move.x !== undefined) {
    const hasLB = node.markup && node.markup.some(m => m.type === 'LB' && m.x === node.move.x && m.y === node.move.y);
    if (!hasLB) addLastMoveMark(node.move.x, node.move.y, moveQualityMark(node)); // T33
  }
  // Markup del nodo (LB, TR, SQ, etc.)
  if (node.markup) {
    const pos2 = gmGame.getPosition();
    for (const mk of node.markup) {
      const v = pos2.get(mk.x, mk.y);
      const stoneC = v === WGo.B ? 1 : v === WGo.W ? -1 : 0;
      const obj = { x: mk.x, y: mk.y };
      if (mk.type === 'LB') {
        obj.type = WGo.Board.drawHandlers['LB']; obj.text = mk.text || '';
        obj.c = stoneC === 1 ? 'white' : stoneC === -1 ? 'black' : '#333';
      } else if (WGo.Board.drawHandlers[mk.type]) {
        obj.type = WGo.Board.drawHandlers[mk.type];
        obj.c = stoneC === 1 ? 'white' : stoneC === -1 ? 'black' : '#333';
      } else continue;
      wgoBoard.addObject(obj);
    }
  }
  // Variaciones: mostrar números en el tablero
  const children = node.children || [];
  if (children.length > 1) {
    children.forEach((child, idx) => {
      if (child.move && child.move.x !== undefined) {
        wgoBoard.addObject({ x: child.move.x, y: child.move.y, type: WGo.Board.drawHandlers['LB'], text: String(idx + 1), c: '#1a1aff' });
      }
    });
  }
  // Comentario
  const cb = document.getElementById('comment-box');
  cb.textContent = node.comment || '';
  // Handler de click
  gmSetupBoardClick();
  anAfterRender(); // AN2
}

function gmSetupBoardClick() {
  if (!wgoBoard) return;
  window._boardClickHandler = (x, y) => {
    if (!gmActive) return;
    const node = gmCurrentNode;
    const children = node.children || [];
    if (children.length === 0) return; // fin de partida
    // Buscar si (x,y) coincide con algún hijo
    const matchIdx = children.findIndex(c => c.move && c.move.x === x && c.move.y === y);
    if (matchIdx === -1) return; // no coincide con ninguna variante
    gmAdvanceTo(matchIdx);
  };
}

function gmAdvanceTo(childIdx) {
  const children = gmCurrentNode.children || [];
  if (!children.length) return;
  const idx = Math.max(0, Math.min(childIdx, children.length - 1));
  gmNodeStack.push(gmCurrentNode);
  gmCurrentNode = children[idx];
  gmRenderCurrentNode();
  gmUpdateControls();
  if (gmCurrentNode.move && gmCurrentNode.move.x !== undefined) playStoneSound(gmLastCaptured);   // solo al avanzar de una en una; los saltos no suenan
  // Parar timer si hay comentario o variaciones
  if (gmTimerRunning && gmShouldPauseTimer()) gmStopTimer();
}

function gmPrev() {
  if (!gmNodeStack.length) return;
  gmCurrentNode = gmNodeStack.pop();
  gmRenderCurrentNode();
  gmUpdateControls();
}

function gmNext() {
  const children = gmCurrentNode.children || [];
  if (!children.length) return;
  gmAdvanceTo(0); // avanza por la variante principal
}

function gmShouldPauseTimer() {
  const node = gmCurrentNode;
  const children = node.children || [];
  return !!(node.comment) || children.length > 1 || children.length === 0;
}

function gmStartTimer() {
  if (gmTimer) clearInterval(gmTimer);
  gmTimerRunning = true;
  document.getElementById('gm-btn-play').textContent = '⏸';  // ▷ parado / ⏸ reproduciendo
  gmTimer = setInterval(() => {
    const children = (gmCurrentNode.children || []);
    if (children.length === 0) { gmStopTimer(); return; }  // fin de partida
    if (children.length > 1) { gmStopTimer(); return; }    // variación: parar antes de avanzar
    gmNext();
    // Parar si el nodo al que llegamos tiene comentario o variaciones
    if (gmShouldPauseTimer()) gmStopTimer();
  }, gmTimerDelay);
}

function gmStopTimer() {
  if (gmTimer) { clearInterval(gmTimer); gmTimer = null; }
  gmTimerRunning = false;
  const btn = document.getElementById('gm-btn-play');
  if (btn) btn.textContent = '▷';
}

function gmToggleTimer() {
  if (gmTimerRunning) gmStopTimer(); else gmStartTimer();
}

function gmUpdateControls() {
  const hasPrev = gmNodeStack.length > 0;
  const hasNext = (gmCurrentNode.children || []).length > 0;
  document.getElementById('gm-btn-prev').disabled = !hasPrev;
  document.getElementById('gm-btn-next').disabled = !hasNext;
  if (!hasNext && gmTimerRunning) gmStopTimer();
}

function gmGoToBranchStart() {
  // Retrocede hasta el primer ancestro con más de un hijo
  while (gmNodeStack.length > 0) {
    const parent = gmNodeStack[gmNodeStack.length - 1];
    if ((parent.children || []).length > 1) {
      // Estamos en el nodo de decisión
      gmCurrentNode = gmNodeStack.pop();
      gmRenderCurrentNode();
      gmUpdateControls();
      return;
    }
    gmCurrentNode = gmNodeStack.pop();
  }
  // Si no hay bifurcación, va al principio
  gmCurrentNode = gmRootNode;
  gmNodeStack = [];
  gmRenderCurrentNode();
  gmUpdateControls();
}

function gmInitControls() {
  document.getElementById('gm-btn-prev').addEventListener('click', () => { gmStopTimer(); gmPrev(); });
  document.getElementById('gm-btn-branch').addEventListener('click', () => { gmStopTimer(); gmGoToBranchStart(); });
  document.getElementById('gm-btn-next').addEventListener('click', () => { gmStopTimer(); gmNext(); });
  document.getElementById('gm-btn-play').addEventListener('click', gmToggleTimer);
  anInitControls(); // AN2
  document.getElementById('gm-timer-sel').addEventListener('change', e => {
    gmTimerDelay = parseInt(e.target.value);
    if (gmTimerRunning) { gmStopTimer(); gmStartTimer(); }
  });
}

// ══ AN2: ANÁLISIS EN EL VISOR DE GAMES (gráfica de ventaja + mejores jugadas a petición) ══
// Usa /ai/graph y /ai/analyze (ai_engines.py, AN1). Solo con conexión; solo 19×19 normal o con handicap.
const AN_MISTAKE = 6, AN_BLUNDER = 12;   // puntos perdidos para marcar error / error grave (umbrales de KaTrain)
let gmSgfText = '';
let anState = { graph: null, graphOn: false, resByNode: new Map(), pvOn: false, busy: false, errColor: 'all' };

function anReset() {
  // filtro de errores: en tus partidas contra la IA, solo los tuyos; en las demás, todos
  anState = { graph: null, graphOn: false, graphLoading: false, resByNode: new Map(), pvOn: false, busy: false, errColor: (gmCurrentGame && gmCurrentGame.persp) || 'all',
    est: null, times: undefined };   // PA4: estimación de la posición vista · PA5: tiempos pensados (se leen al dibujar)
  anRenderInfo();
  { const s = document.getElementById('gm-an-status'); if (s) { s.style.display = 'none'; s.textContent = ''; } }
  if (gmCurrentGame && gmCurrentGame.uuid) anStatusPoll(anState);   // PA6
  const gw = document.getElementById('gm-graph'); if (gw) { gw.style.display = 'none'; gw.textContent = ''; }
  const at = document.getElementById('gm-an-text'); if (at) at.style.display = 'none';
  anUpdateButtons();
}
function anPersp() { return (gmCurrentGame && gmCurrentGame.persp) || 'B'; }
function anRootStones() {
  const g = new WGo.Game(boardSize); g.allow_rewrite = true;
  const save = gmGame; gmGame = g; gmApplyNodeToGame(gmRootNode); gmGame = save;
  const pos = g.getPosition(), out = [];
  for (let x = 0; x < boardSize; x++) for (let y = 0; y < boardSize; y++) {
    const v = pos.get(x, y); if (v === WGo.B) out.push({ x, y, c: 1 }); else if (v === WGo.W) out.push({ x, y, c: -1 });
  }
  return out;
}
const anMoveOf = (n) => (n && n.move && (n.move.c === 1 || n.move.c === -1)) ? { c: n.move.c, x: n.move.x, y: n.move.y } : null;
function anMainLine() {
  const out = []; let n = gmRootNode;
  while (n && n.children && n.children.length) { n = n.children[0]; const m = anMoveOf(n); if (m) out.push(m); }
  return out;
}
function anCurrentMoves() { return [...gmNodeStack, gmCurrentNode].filter(n => n !== gmRootNode).map(anMoveOf).filter(Boolean); }
function anOnMainLine() {
  let n = gmRootNode; const path = [...gmNodeStack, gmCurrentNode];
  if (path[0] !== gmRootNode) return false;
  for (let i = 1; i < path.length; i++) { if (!n.children || n.children[0] !== path[i]) return false; n = path[i]; }
  return true;
}
function anBody(moves) {
  const p = anPosition(boardSize, anRootStones(), moves, gmSgfText);
  if (!p.ok) { anMsg('Análisis no disponible: ' + p.reason); return null; }
  return p.body;
}
function anMsg(t) { const h = document.getElementById('board-hint'); if (h) { h.textContent = t; h.className = ''; } }
function anUpdateButtons() {
  const g = document.getElementById('gm-btn-graph'), a = document.getElementById('gm-btn-an'), pv = document.getElementById('gm-btn-pv');
  if (!g) return;
  g.disabled = a.disabled = anState.busy || !gmRootNode;
  const tb = document.getElementById('gm-btn-times');   // PB2: solo con la gráfica a la vista y si la partida tiene tiempos
  tb.style.display = anState.graphOn && gmRootNode && anTimes() ? '' : 'none';
  tb.classList.toggle('active', anTimesOn());
  const es = document.getElementById('gm-btn-est');   // PA4
  es.disabled = anState.busy || !gmRootNode;
  es.classList.toggle('active', !!(anState.est && anState.est.node === gmCurrentNode));
  g.classList.toggle('active', anState.graphOn);
  const cr0 = anState.resByNode.get(gmCurrentNode), cr = cr0 && anState.anHidden !== gmCurrentNode ? cr0 : null;   // PB3
  a.classList.toggle('active', !!cr);
  const showPv = !!(cr && cr.data.candidates[0].pv.length);
  pv.style.display = showPv ? '' : 'none';
  pv.classList.toggle('active', anState.pvOn);
  const ep = document.getElementById('gm-btn-err-prev'), en = document.getElementById('gm-btn-err-next'), ef = document.getElementById('gm-btn-err-filter');
  const has = !!anState.graph;
  ep.style.display = en.style.display = ef.style.display = has ? '' : 'none';
  ef.textContent = { all: '●○', B: '●', W: '○' }[anState.errColor];
  ef.title = { all: 'Errores de los dos colores (toca para ver solo negras)', B: 'Solo errores de negras (toca para ver solo blancas)', W: 'Solo errores de blancas (toca para ver los dos)' }[anState.errColor];
  if (has) {
    ep.disabled = anState.busy || anMistakeTarget(-1) == null;
    en.disabled = anState.busy || anMistakeTarget(1) == null;
  }
}
// Errores (modelo 1): posición CON la jugada mala ya puesta y marcada (jugada i -> posición i);
// 🔍 Analizar dice cuánto costó y cuál era la alternativa.
function anMistakeTarget(dir) {
  if (!anState.graph) return null;
  const cur = anOnMainLine() ? anCurrentMoves().length : -1;
  const ts = anMistakes(anState.graph.leads, anState.graph.moves, AN_MISTAKE)
    .filter(m => anState.errColor === 'all' || m.color === anState.errColor).map(m => m.i);
  if (dir > 0) return ts.find(t => t > cur) ?? null;
  const prev = ts.filter(t => t < cur);
  return prev.length ? prev[prev.length - 1] : null;
}
function anJumpMistake(dir) { const t = anMistakeTarget(dir); if (t != null) anGoToMove(t); }
function anCycleErrColor() {
  anState.errColor = { all: 'B', B: 'W', W: 'all' }[anState.errColor];
  anDrawGraph(); anUpdateButtons();
}
// Ficha de la partida en el panel lateral (en Games)
function anRenderInfo() {
  const box = document.getElementById('gm-info-rows'); if (!box) return;
  box.textContent = '';
  const rows = gmRootNode ? anGameInfoRows(anSgfRootProps(gmSgfText), anMainLine().length) : [];
  if (!rows.length) { const d = document.createElement('div'); d.className = 'sb-row'; d.textContent = gmRootNode ? 'El SGF no trae datos de la partida' : '—'; box.appendChild(d); return; }
  for (const [k, v] of rows) {
    const d = document.createElement('div'); d.className = 'sb-row';
    const a = document.createElement('span'); a.className = 'k'; a.textContent = k;
    const b = document.createElement('span'); b.className = 'v'; b.textContent = v;
    d.appendChild(a); d.appendChild(b); box.appendChild(d);
  }
}

// ── gráfica ──
async function anToggleGraph() {
  if (anState.graphOn) { anState.graphOn = false; document.getElementById('gm-graph').style.display = 'none'; anUpdateButtons(); return; }
  anState.graphOn = true;
  document.getElementById('gm-graph').style.display = '';
  if (!anState.graph || !anState.graph.complete) { anLoadGraph(); return; }
  anDrawGraph(); anUpdateButtons();
}
// AN3: la gráfica se pide por tramos (búsqueda corta por posición, ~1 s cada una; el servidor
// guarda lo calculado y lo ya visto sale al instante) y se dibuja según llega. Si se abre otra
// partida, el bucle se detiene. Ocultar la gráfica no lo detiene: termina y queda guardada.
// AN4: lo calcula el servidor en segundo plano (sigue aunque la app se cierre o el móvil apague
// la pantalla); la app pinta lo que ya hay y consulta el progreso cada pocos segundos. Si el
// servidor no tiene análisis automático (antiguo o apagado), se calcula por tramos desde aquí.
async function anLoadGraph() {
  const st = anState;
  if (st.graphLoading) { anDrawGraph(); return; }
  const moves = anMainLine();
  const body = anBody(moves); if (!body) { st.graphOn = false; document.getElementById('gm-graph').style.display = 'none'; anUpdateButtons(); return; }
  if (moves.length > 600) { anMsg('Partida demasiado larga para la gráfica'); st.graphOn = false; document.getElementById('gm-graph').style.display = 'none'; anUpdateButtons(); return; }
  const n = moves.length;
  if (!st.graph) st.graph = { leads: new Array(n + 1).fill(null), moves: body.moves, complete: false };
  st.graphLoading = true; anUpdateButtons();
  const fill = (d) => { d.white_leads.forEach((v, k) => { if (v != null) st.graph.leads[k] = v; }); st.graph.complete = st.graph.leads.indexOf(null) < 0; };
  const cachedOnly = () => aiPost('/ai/graph', Object.assign({}, body, { from: 0, to: n, cached_only: true }), 20000);
  const done = () => { anMsg((gmCurrentGame && gmCurrentGame.name || '').replace(/\.sgf$/i, '')); };
  try {
    anMsg('Consultando la gráfica…');
    fill(await cachedOnly());
    if (anState !== st) return;
    anDrawGraph(); anUpdateButtons();
    if (st.graph.complete) { done(); return; }
    let job = null;
    try { job = await aiPost('/ai/graph_job', Object.assign({}, body, { label: (gmCurrentGame && gmCurrentGame.name || '').replace(/\.sgf$/i, '').slice(0, 80) }, gmCurrentGame && gmCurrentGame.persp ? { mine: gmCurrentGame.persp } : {}), 15000); /* partidas contra la IA: mine = el servidor prepara solo mis errores */ } catch (e) { job = null; }
    if (anState !== st) return;
    if (job && job.enabled) {
      let fails = 0;
      while (anState === st && !st.graph.complete && st.graphOn) {
        const k = st.graph.leads.filter(v => v != null).length;
        anMsg(`Analizando en el servidor… ${k}/${n + 1}` + (fails ? ' · reintentando' : ' · sigue aunque cierres la app'));
        await new Promise(r => setTimeout(r, 2500));
        if (anState !== st) return;
        try { fill(await cachedOnly()); fails = 0; } catch (e) { fails++; }
        if (anState !== st) return;
        anDrawGraph(); anUpdateButtons();
      }
      if (st.graph.complete) done();
      return;   // oculta: el servidor sigue; al volver a mostrarla se retoma la consulta
    }
    await anLoadGraphChunks(st, body, n);
  } catch (e) {
    if (anState === st) anMsg('No se pudo consultar la gráfica: ' + e.message + ' — pulsa 📈 dos veces para reintentar');
  } finally {
    st.graphLoading = false;
    if (anState === st) { anDrawGraph(); anUpdateButtons(); }
  }
}
// AN3: cálculo por tramos desde la app (servidor sin análisis automático).
async function anLoadGraphChunks(st, body, n) {
  const CHUNK = 20;
  for (let from = st.graph.leads.indexOf(null); from >= 0 && from <= n; from = st.graph.leads.indexOf(null)) {
    const to = Math.min(n, from + CHUNK - 1);
    anMsg(`Calculando la gráfica… ${from}/${n}`);
    const data = await aiPost('/ai/graph', Object.assign({}, body, { from, to }), 120000);
    if (anState !== st) return;   // se abrió otra partida
    data.white_leads.forEach((v, k) => { st.graph.leads[from + k] = v; });
    anDrawGraph(); anUpdateButtons();
  }
  st.graph.complete = true;
  anMsg((gmCurrentGame && gmCurrentGame.name || '').replace(/\.sgf$/i, ''));
}
function anDrawGraph() {
  const wrap = document.getElementById('gm-graph');
  if (!wrap || !anState.graphOn || !anState.graph) return;
  const { leads, moves } = anState.graph, persp = anPersp(), sg = persp === 'B' ? -1 : 1;
  const vals = leads.map(v => v == null ? null : sg * v), n = vals.length - 1;
  const done = vals.indexOf(null) < 0 ? n : vals.indexOf(null) - 1;   // AN3: último punto ya calculado
  // Ancho fijo por jugada (se desplaza en horizontal si no cabe) y centrado en la jugada actual
  const AN_PX_PER_MOVE = 6, pad = 8, H = 170;
  const tmsAll = anTimes(), tms = tmsAll && anTimesOn() ? tmsAll : null, TB = tms ? 44 : 0;   // PA5: franja de tiempos pensados bajo la gráfica (PB2: a petición)
  const W = Math.max((wrap.clientWidth || 300) - 2, n * AN_PX_PER_MOVE + 2 * pad), maxAbs = Math.max(10, ...vals.filter(v => v != null).map(Math.abs));
  const X = (i) => pad + (W - 2 * pad) * (n ? i / n : 0), Y = (v) => H / 2 - (H / 2 - pad) * (v / maxAbs);
  const ns = 'http://www.w3.org/2000/svg', mk = (t, a) => { const e = document.createElementNS(ns, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
  wrap.textContent = '';
  const scroller = document.createElement('div');
  // width:0 + min-width:100%: el ancho de la gráfica no ensancha los contenedores (#board-wrap es flexible)
  scroller.style.cssText = 'width:0;min-width:100%;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;border:1px solid var(--border);background:var(--panel);scrollbar-width:thin;scrollbar-color:var(--border2) transparent;';
  const svg = mk('svg', { viewBox: `0 0 ${W} ${H + TB}`, width: W, height: H + TB, style: `display:block;cursor:pointer;width:${W}px;height:${H + TB}px;` });
  // marcas cada 50 jugadas para orientarse al desplazar
  for (let k = 50; k < n; k += 50) {
    svg.appendChild(mk('line', { x1: X(k), x2: X(k), y1: 0, y2: H, stroke: 'var(--border)', 'stroke-width': 1 }));
    const tl = mk('text', { x: X(k) + 3, y: 12, fill: 'var(--dim2)', 'font-size': 10, 'font-family': 'monospace' }); tl.textContent = String(k); svg.appendChild(tl);
  }
  svg.appendChild(mk('line', { x1: pad, x2: W - pad, y1: H / 2, y2: H / 2, stroke: 'var(--border2)', 'stroke-width': 1 }));
  if (done >= 0) {
    const pts = vals.slice(0, done + 1).map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
    svg.appendChild(mk('polygon', { points: `${X(0)},${H / 2} ${pts} ${X(done)},${H / 2}`, fill: 'rgba(212,168,74,.18)' }));
    svg.appendChild(mk('polyline', { points: pts, fill: 'none', stroke: 'var(--gold)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }));
  }
  for (const m of anMistakes(leads, moves, AN_MISTAKE)) {
    const c = mk('circle', { cx: X(m.i), cy: Y(vals[m.i]), r: m.loss >= AN_BLUNDER ? 4 : 3, fill: m.loss >= AN_BLUNDER ? 'var(--accent)' : '#e0a030',
      opacity: anState.errColor === 'all' || m.color === anState.errColor ? 1 : 0.25 });
    const t = mk('title', {}); t.textContent = `Jugada ${m.i} (${m.color === 'B' ? 'negras' : 'blancas'}): −${m.loss}`; c.appendChild(t);
    svg.appendChild(c);
  }
  if (tms) {   // PA5: una barra por jugada con tiempo (las mías); naranja/rojo si fue error
    const loss = new Map(anMistakes(leads, moves, AN_MISTAKE).map(m => [m.i, m.loss]));
    const CAP = 120, top = H + 6, hMax = TB - 10;
    const maxT = Math.max(10, Math.min(CAP, ...tms.filter(v => v != null)));
    const bw = Math.max(1.5, Math.min(5, (W - 2 * pad) / Math.max(1, n) * 0.7));
    svg.appendChild(mk('line', { x1: pad, x2: W - pad, y1: H + 1, y2: H + 1, stroke: 'var(--border)', 'stroke-width': 1 }));
    const lt = mk('text', { x: pad, y: top + 6, fill: 'var(--dim2)', 'font-size': 9, 'font-family': 'monospace' }); lt.textContent = '⏱'; svg.appendChild(lt);
    for (let i = 1; i <= n; i++) {
      const t = tms[i]; if (t == null) continue;
      const h = Math.max(1, Math.min(t, maxT) / maxT * hMax), l = loss.get(i);
      const col = l >= AN_BLUNDER ? 'var(--accent)' : l >= AN_MISTAKE ? '#e0a030' : 'rgba(212,168,74,.55)';
      const b = mk('rect', { x: X(i) - bw / 2, y: top + hMax - h, width: bw, height: h, fill: col });
      const bt = mk('title', {}); bt.textContent = `Jugada ${i}: pensaste ${anThinkTxt(t)}` + (l >= AN_MISTAKE ? ` · −${l}` : ''); b.appendChild(bt);
      svg.appendChild(b);
      if (t > maxT) svg.appendChild(mk('line', { x1: X(i) - bw, x2: X(i) + bw, y1: top, y2: top, stroke: col, 'stroke-width': 1.5 }));   // pasa del tope
    }
  }
  if (anOnMainLine()) {
    const cur = anCurrentMoves().length;
    svg.appendChild(mk('line', { x1: X(cur), x2: X(cur), y1: 0, y2: H + TB, stroke: 'var(--text)', 'stroke-width': 1, 'stroke-dasharray': '3,3', 'vector-effect': 'non-scaling-stroke' }));
  }
  let down = null;   // si el dedo se ha movido (desplazamiento), no es un toque
  svg.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, sl: scroller.scrollLeft }; });
  svg.addEventListener('click', (e) => {
    if (down && (Math.abs(e.clientX - down.x) > 8 || Math.abs(e.clientY - down.y) > 8 || Math.abs(scroller.scrollLeft - down.sl) > 2)) { down = null; return; }
    down = null;
    const r = svg.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left) - pad) / (W - 2 * pad) * n);
    anGoToMove(Math.max(0, Math.min(n, i)));
  });
  scroller.appendChild(svg);
  wrap.appendChild(scroller);
  const curX = anOnMainLine() ? X(anCurrentMoves().length) : null;
  if (curX != null) scroller.scrollLeft = Math.max(0, curX - scroller.clientWidth / 2);
  wrap.appendChild(Object.assign(document.createElement('div'), {
    className: 'gm-an-box', style: 'margin-top:3px;',
    textContent: anGraphCaption(leads, moves, persp, anOnMainLine() ? anCurrentMoves().length : null)
      + (tmsAll && anOnMainLine() && tmsAll[anCurrentMoves().length] != null ? ` · pensaste ${anThinkTxt(tmsAll[anCurrentMoves().length])}` : ''),   // PA5 (con la franja oculta también)
  }));
}
function anGoToMove(i) {
  gmStopTimer();
  gmNodeStack = []; gmCurrentNode = gmRootNode;
  let k = 0;
  while (k < i && gmCurrentNode.children && gmCurrentNode.children.length) {
    gmNodeStack.push(gmCurrentNode); gmCurrentNode = gmCurrentNode.children[0];
    if (anMoveOf(gmCurrentNode)) k++;
  }
  gmRenderCurrentNode(); gmUpdateControls();
}

// ── análisis de la posición actual ──
// Modelo 1: se analiza la ÚLTIMA jugada del tablero (la que se ve marcada): la posición de
// antes, con esa jugada como "played". En el inicio (sin jugadas) se analiza la primera jugada.
async function anAnalyze() {
  const node = gmCurrentNode, moves = anCurrentMoves(), st = anState;
  if (st.resByNode.has(node)) {   // PB3: ya analizada: el 🔍 la oculta o la vuelve a mostrar (sin recalcular)
    st.anHidden = st.anHidden === node ? null : node;
    gmRenderCurrentNode(); return;
  }
  const last = moves[moves.length - 1];
  const body = anBody(last ? moves.slice(0, -1) : moves); if (!body) return;
  if (last) {
    body.to_play = last.c === 1 ? 'B' : 'W';
    body.played = last.x === undefined ? 'pass' : aiToGtp(last.x, last.y);
  } else {
    body.to_play = body.handicap_stones.length ? 'W' : 'B';
  }
  anState.busy = true; anUpdateButtons(); anMsg('Analizando… (unos segundos)');
  try {
    const data = await aiPost('/ai/analyze', body, 120000);
    if (anState !== st) return;   // se abrió otra partida
    // Se guarda aunque se haya cambiado de jugada mientras tanto: se verá al volver a ella.
    st.resByNode.set(node, { node, data, moveNo: last ? moves.length : null });
    if (gmCurrentNode === node) {
      st.pvOn = false;
      anMsg((gmCurrentGame && gmCurrentGame.name || '').replace(/\.sgf$/i, ''));
      gmRenderCurrentNode();
    } else {
      anMsg(`Análisis de la jugada ${last ? moves.length : 0} listo: vuelve a ella para verlo`);
    }
  } catch (e) {
    if (anState === st) anMsg('No se pudo analizar (' + e.message + ')');
  } finally { st.busy = false; if (anState === st) anUpdateButtons(); }
}
// PA4: estimación (número + territorio) de la posición que se ve. Al cambiar de jugada desaparece.
async function anEstimate() {
  const st = anState, node = gmCurrentNode;
  if (st.est && st.est.node === node) { st.est = null; gmRenderCurrentNode(); return; }   // segundo toque: ocultar
  const body = anBody(anCurrentMoves()); if (!body) return;
  st.busy = true; anUpdateButtons(); anMsg('Estimando…');
  try {
    const d = await aiPost('/ai/score', Object.assign({}, body, { mode: 'estimate' }), 30000);
    if (anState !== st) return;
    if (gmCurrentNode !== node) { anMsg('Estimación lista, pero has cambiado de jugada: vuelve a pulsar 📊'); return; }
    st.est = { node, sw: d.score_white, own: d.ownership || null };
    anMsg((gmCurrentGame && gmCurrentGame.name || '').replace(/\.sgf$/i, ''));
    gmRenderCurrentNode();
  } catch (e) {
    if (anState === st) anMsg('No se pudo estimar (' + e.message + ')');
  } finally { st.busy = false; if (anState === st) anUpdateButtons(); }
}
// PA6: estado del análisis automático de esta partida contra la IA, junto al 📈. Mientras no
// esté hecha, se vuelve a consultar cada 5 s; se detiene al abrir otra partida.
async function anStatusPoll(st) {
  const uuid = gmCurrentGame && gmCurrentGame.uuid, box = document.getElementById('gm-an-status');
  if (!uuid || !box) return;
  let s = null;
  try { const d = await aiPost('/ai/analysis_status', { uuids: [uuid] }, 10000); s = d && d.status ? d.status[uuid] : null; }
  catch (e) { s = null; }
  if (anState !== st) return;
  const t = anStatusText(s);
  box.textContent = t.text; box.title = t.title; box.style.display = t.text ? '' : 'none';
  if (s && (s.state === 'queued' || s.state === 'running')) setTimeout(() => { if (anState === st) anStatusPoll(st); }, 5000);
}
// PA5: tiempos pensados de la partida (TT del SGF), solo si cuadran con la línea principal.
// PB2: la franja de tiempos bajo la gráfica se muestra a petición (oculta por defecto; se recuerda en el dispositivo)
const AN_TIMES_KEY = 'an_times_on';
function anTimesOn() { return lsGet(AN_TIMES_KEY) === '1'; }
function anToggleTimes() { lsSet(AN_TIMES_KEY, anTimesOn() ? '0' : '1'); anDrawGraph(); anUpdateButtons(); }
function anTimes() {
  if (anState.times === undefined) {
    const t = anMoveTimes(gmSgfText);
    anState.times = t.length - 1 === anMainLine().length && t.some(v => v != null) ? t : null;
  }
  return anState.times;
}
function anTogglePv() { if (!anState.resByNode.get(gmCurrentNode)) return; anState.pvOn = !anState.pvOn; gmRenderCurrentNode(); }
// Llamada al final de gmRenderCurrentNode: repinta lo que corresponde al nodo actual.
function anAfterRender() {
  if (anState.anHidden && anState.anHidden !== gmCurrentNode) anState.anHidden = null;   // PB3: al cambiar de jugada se vuelve a ver
  const r0 = anState.resByNode.get(gmCurrentNode), r = r0 && anState.anHidden !== gmCurrentNode ? r0 : null;
  if (r) {
    const d = r.data, cs = d.candidates, best = cs[0];
    const pos = gmGame.getPosition();
    // Las candidatas y la secuencia son de la posición ANTERIOR: el punto de la jugada hecha
    // está ocupado por ella; si coincide con una candidata, la etiqueta va sobre la piedra.
    const playedPt = d.played ? aiFromGtp(d.played.move) : null;
    const freeOrPlayed = (p) => pos.get(p.x, p.y) === 0 || (playedPt && p.x === playedPt.x && p.y === playedPt.y);
    if (anState.pvOn) {
      best.pv.forEach((v, k) => {
        const p = aiFromGtp(v); if (!p || pos.get(p.x, p.y) !== 0) return;
        const col = ((k % 2 === 0) === (d.to_play === 'B')) ? 1 : -1;
        wgoBoard.addObject({ x: p.x, y: p.y, c: col, type: 'outline' });
        wgoBoard.addObject({ x: p.x, y: p.y, type: WGo.Board.drawHandlers['LB'], text: String(k + 1), c: col === 1 ? '#000' : '#fff' });
      });
    } else {
      cs.forEach((c, k) => {
        const p = aiFromGtp(c.move); if (!p || !freeOrPlayed(p)) return;
        const onStone = pos.get(p.x, p.y) !== 0;
        wgoBoard.addObject({ x: p.x, y: p.y, type: WGo.Board.drawHandlers['LB'], text: k === 0 ? '★' : String(k + 1),
          c: onStone ? (pos.get(p.x, p.y) === WGo.B ? '#fff' : '#000') : (k === 0 ? '#1a7a2a' : '#1a1aff') });
      });
    }
    const tms = anTimes();   // PA5
    const txt = anAnalysisText(d, r.moveNo, anPersp(), !!(gmCurrentGame && gmCurrentGame.persp), tms && r.moveNo != null ? tms[r.moveNo] : null);
    const at = document.getElementById('gm-an-text');
    at.textContent = txt + (anState.pvOn ? `\nSecuencia: ${best.pv.join(' ')}` : '');
    at.style.display = '';
  } else {
    document.getElementById('gm-an-text').style.display = 'none';
  }
  // PA4: estimación de esta posición (cuadraditos de territorio y su texto encima del análisis)
  if (anState.est && anState.est.node !== gmCurrentNode) anState.est = null;
  if (anState.est) {
    const e = anState.est, pos = gmGame.getPosition();
    if (e.own) for (let y = 0; y < 19; y++) for (let x = 0; x < 19; x++) {
      const o = e.own[x + 19 * y], s = pos.get(x, y);
      const show = s === 0 ? Math.abs(o) >= 0.15 : (s === WGo.B ? o >= 0.5 : o <= -0.5);
      if (show) wgoBoard.addObject({ x, y, type: AI_OWN_HANDLER, own: o });
    }
    const at = document.getElementById('gm-an-text'), line = anEstText(e.sw, anPersp(), !!(gmCurrentGame && gmCurrentGame.persp));
    at.textContent = r ? line + '\n' + at.textContent : line;
    at.style.display = '';
  }
  anDrawGraph();
  anUpdateButtons();
}
function anInitControls() {
  document.getElementById('gm-btn-graph').addEventListener('click', anToggleGraph);
  document.getElementById('gm-btn-an').addEventListener('click', anAnalyze);
  document.getElementById('gm-btn-est').addEventListener('click', anEstimate);   // PA4
  document.getElementById('gm-btn-times').addEventListener('click', anToggleTimes);   // PB2
  document.getElementById('gm-btn-pv').addEventListener('click', anTogglePv);
  document.getElementById('gm-btn-err-filter').addEventListener('click', anCycleErrColor);
  document.getElementById('gm-btn-err-prev').addEventListener('click', () => anJumpMistake(-1));
  document.getElementById('gm-btn-err-next').addEventListener('click', () => anJumpMistake(1));
}

// ══ Contrato con la página anfitriona (AR0) ══
// Este fichero no se basta solo: usa, del script principal de la página, estos nombres globales
// (comprobado con tests/test_game_viewer.js; si añades uno, añádelo también allí):
//   tablero:   wgoBoard, boardSize, initBoard(size), clearBoard(), addLastMoveMark(x, y, q),
//              moveQualityMark(node), switchToBoard()
//   sonido:    playStoneSound(captured), capturedAny(r)
//   ficheros:  sgfUrl(path), lsGet(k), lsSet(k, v)
//   servidor:  aiPost(path, body), aiToGtp(x, y), aiFromGtp(v), AI_OWN_HANDLER
//   análisis (funciones puras del bloque IA3): anAnalysisText, anEstText, anGameInfoRows,
//              anGraphCaption, anMistakes, anMoveTimes, anPosition, anSgfRootProps,
//              anStatusText, anThinkTxt
//   DOM:       los controles #gm-controls (gm-btn-*, gm-timer-sel, gm-an-*), #board-hint, #comment-box
// Y la página usa de aquí: gmOpenGame, gmInitControls, gmStopTimer, gmRenderCurrentNode,
// gmRootNode, gmActive.
