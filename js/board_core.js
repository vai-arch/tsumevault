// TsumeVault — núcleo del tablero compartido (AR3a, docs/WORKPLAN_ARCHIVO.md): tablero WGo, marcas,
// sonidos, ajustes en localStorage, servidor/token y aiPost. Movido TAL CUAL desde tsumevault.html: cada bloque
// empieza con "⇠ #N" y en la página queda "⇢ js/board_core.js #N" (tests/page_source.py reconstruye la página
// original byte a byte). Se carga con <script src> ANTES de ai_pure.js, game_viewer.js y el script principal.

// ⇠ #1 (antes en tsumevault.html, línea 1939)
const SYNC_SERVER_KEY = 'sync_server_url';
const BOARD_BG_KEY = 'board_background';
// ⇠ #2 (antes en tsumevault.html, línea 1943)
const SOUND_KEY = 'sound_enabled';
const SFX_VOLUME_KEY = 'sfx_volume';
// ⇠ #3 (antes en tsumevault.html, línea 1959)
let SYNC_SERVER = localStorage.getItem(SYNC_SERVER_KEY) || 'https://tsumevault.duckdns.org';
// ── Fase 1 (§4.1): token estático opcional. Si no hay token guardado, las
// peticiones van sin cabecera (compatible con servidores sin auth).
const SYNC_TOKEN_KEY = 'sync_token';
function syncFetch(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = localStorage.getItem(SYNC_TOKEN_KEY);
  if (token) headers['X-Auth-Token'] = token;
  return fetch(SYNC_SERVER + path, { ...opts, headers });
}
let currentBoardBg = localStorage.getItem(BOARD_BG_KEY) || '#c4943a';
let currentStoneSet = null; // {label, black:[], white:[]} or null = REALISTIC
// ⇠ #4 (antes en tsumevault.html, línea 1972)
let soundEnabled = localStorage.getItem(SOUND_KEY) !== 'false';
let sfxVolume = parseInt(localStorage.getItem(SFX_VOLUME_KEY));
// ⇠ #5 (antes en tsumevault.html, línea 1983)
let wgoBoard = null, boardSize = 19;
// ⇠ #6 (antes en tsumevault.html, línea 1998)
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { } }
// ⇠ #7 (antes en tsumevault.html, línea 2014)
const SGF_BASE = '/tsumevault/';
// FC12: URL de un SGF a partir de su sgf_path. Solo se codifican los caracteres que rompen una
// ruta (% # ?): una carpeta como "This Endgame appears 100%" daba HTTP 400. El resto queda igual
// que antes (el navegador ya codifica espacios y acentos), asi que las URLs que ya funcionaban y
// sus entradas en la cache offline no cambian.
function sgfUrl(path) { return SGF_BASE + path.replace(/\\/g, '/').replace(/%/g, '%25').replace(/#/g, '%23').replace(/\?/g, '%3F'); }
// ⇠ #8 (antes en tsumevault.html, línea 2041)
// ── SFX: funciones puras (extract_sfx.py las extrae para test_sfx.js; sin DOM ni estado global) ──
// Índice al azar en 0..n-1 distinto de `last` cuando n > 1 (con un solo sonido, siempre 0).
// rnd en [0,1); un `last` fuera de rango (p. ej. -1 al empezar) no excluye nada.
function sfxPickIndex(n, last, rnd) {
  if (n <= 1) return 0;
  if (!(last >= 0 && last < n)) return Math.min(n - 1, Math.floor(rnd * n));
  const i = Math.min(n - 2, Math.floor(rnd * (n - 1)));
  return i >= last ? i + 1 : i;
}
// ── fin SFX funciones puras ──
// Sonido de piedra variado: put01..05 al poner, cap01..05 si la jugada captura (solo la captura).
// Un <audio> por fichero, así dos jugadas seguidas pueden solaparse en vez de cortarse.
const STONE_SFX = {
  stone: [1, 2, 3, 4, 5].map(i => new Audio('audio/put0' + i + '.mp3')),
  capture: [1, 2, 3, 4, 5].map(i => new Audio('audio/cap0' + i + '.mp3')),
};
const stoneSfxLast = { stone: -1, capture: -1 };
function playStoneSound(captured) {
  if (!soundEnabled) return;
  const k = captured ? 'capture' : 'stone', pool = STONE_SFX[k];
  const i = sfxPickIndex(pool.length, stoneSfxLast[k], Math.random()); stoneSfxLast[k] = i;
  try { pool[i].currentTime = 0; pool[i].volume = sfxVolume / 100; pool[i].play(); } catch (e) { }
}
// WGo.Game.play devuelve el array de piedras capturadas si la jugada es legal (código numérico si no).
function capturedAny(r) { return Array.isArray(r) && r.length > 0; }
// ⇠ #9 (antes en tsumevault.html, línea 4037)
// ── Stone image cache ──
const imgCache = {};
function getImg(src) {
  if (!imgCache[src]) { const img = new Image(); img.src = src; imgCache[src] = img; }
  return imgCache[src];
}
function pickVariant(list, x, y) { return list[(x * 13 + y * 7) % list.length]; }
// ⇠ #10 (antes en tsumevault.html, línea 5076)
function buildStoneHandler(set) {
  if (!set) return WGo.Board.drawHandlers.REALISTIC;
  if (set.flat) return bsFlatHandler();   // E3: piedras planas (js/board_style.js)
  return {
    stone: {
      draw: function (a, board) {
        const ctx = this;
        // E3: con la descolocación fija si está activada; entonces, del tamaño de las planas para que las vecinas no se pisen
        const [x, y] = bsStonePos(a, board), r = board.stoneRadius * (currentJitter ? BS_FLAT_RADIUS : 1);
        const isBlack = a.c === WGo.B;
        const src = isBlack ? pickVariant(set.black, a.x, a.y) : pickVariant(set.white, a.x, a.y);
        const img = getImg(src);
        if (!img.complete || img.naturalWidth === 0) { img.onload = () => board.redraw(); return; }
        ctx.drawImage(img, x - r, y - r, r * 2, r * 2);
      }
    }
  };
}
// ⇠ #11 (antes en tsumevault.html, línea 6763)
function initBoard(size) {
  boardSize = size || 19;
  const margin = 24;
  // T38: antes se restaba board-wrap.offsetLeft, que en movil depende del ancho que tenia el tablero
  // antes del giro (esta centrado con margin:auto): al volver a vertical se medía con el board-wrap
  // aun a 240px y el tablero se quedaba mas pequeño en cada giro. Movil: innerWidth (#main puede estar
  // en display:none en la primera apertura); resto: ancho real de la columna central.
  const mainW = window.innerWidth < 768 ? window.innerWidth : (document.getElementById('main').clientWidth || window.innerWidth);
  const availW = mainW - margin;
  const availH = window.innerHeight - 140;
  const avail = Math.min(availW, availH);
  const sz = Math.max(240, Math.min(avail, 620));
  document.getElementById('board').innerHTML = '';
  wgoBoard = new WGo.Board(document.getElementById('board'), {
    size: boardSize, width: sz, background: currentBoardBg,
    stoneHandler: buildStoneHandler(currentStoneSet)
  });
  wgoBoard.setSection(-0.5, -0.5, -0.5, -0.5);
  bsStyleBoard(wgoBoard);   // E3: líneas y sombra del estilo plano (js/board_style.js); addCustomObject repinta
  wgoBoard.addCustomObject(WGo.Board.coordinates);
  wgoBoard.addEventListener('click', (x, y) => { if (window._boardClickHandler) window._boardClickHandler(x, y); });
  wgoBoard._globalListenerSet = true;
  // F11-fix: ancho explicito en el CONTENEDOR (no solo en el canvas de
  // dentro). Sin esto, #board-wrap (ancho "auto") intenta ajustarse a su
  // contenido, pero #board (bloque normal, ancho "auto" tambien) por
  // defecto quiere ocupar el 100% de #board-wrap -> referencia circular
  // que el navegador resuelve dando a #board-wrap todo el ancho
  // disponible en vez de los "sz" px reales del canvas. Resultado
  // medido en movil: board-wrap=384px pero canvas=360px, con el hueco
  // sobrante SIEMPRE a la derecha (el margin:auto de #board-wrap no
  // tiene nada que repartir si ya ocupa el 100%). Fijar el ancho aqui
  // rompe la ambiguedad: #board-wrap mide exactamente sz, y el
  // margin:auto (movil) / align-items:center (#main, desktop/tablet)
  // ya lo centran de verdad.
  document.getElementById('board-wrap').style.width = sz + 'px';
  document.getElementById('board-wrap').style.display = 'block';
  document.getElementById('welcome').style.display = 'none';
  document.getElementById('comment-box').style.maxWidth = sz + 'px';
}
function clearBoard() {
  if (!wgoBoard) return;
  for (let x = 0; x < wgoBoard.size; x++) { wgoBoard.obj_arr[x] = []; for (let y = 0; y < wgoBoard.size; y++)wgoBoard.obj_arr[x][y] = []; }
  wgoBoard.redraw();
}
// ⇠ #12 (antes en tsumevault.html, línea 6840)
// T33: simbolo de calidad de una jugada a partir de sus marcas SGF (IT/BM/DO/TE; el
// parser de WGo las deja tal cual en el nodo, p. ej. node.BM = '1', node.IT = '').
// Mismos simbolos, colores y prioridad que J3 (jsMarkInfo). null = sin marca.
function moveQualityMark(node) {
  if (!node) return null;
  const has = k => node[k] !== undefined;
  if (!has('IT') && !has('BM') && !has('DO') && !has('TE')) return null;
  const info = jsMarkInfo({ it: has('IT'), q: has('BM') ? 'bad' : has('DO') ? 'doubtful' : undefined, te: has('TE') });
  return { sym: info.sym, color: info.color };
}
// T33: marca de la ultima jugada: su simbolo de calidad si lo tiene; si no, el circulo de siempre.
function addLastMoveMark(x, y, q) {
  if (q) wgoBoard.addObject({ x, y, type: WGo.Board.drawHandlers['LB'], text: q.sym, c: q.color });
  else wgoBoard.addObject({ x, y, type: 'CR' });
}
// ⇠ #13 (antes en tsumevault.html, línea 7471)
// J3: símbolo + color de un fantasma (J-31: color Y forma, no solo tono).
function jsMarkInfo(n) {
  if (n.ctx) return { sym: '◆', color: '#a07cd8', kind: 'context' };   // J3.2: nodo de contexto (piedras añadidas)
  if (n.it && !n.implicit) return { sym: '?', color: '#4a8fe7', kind: 'whatif' };
  if (n.q === 'bad') return { sym: '✕', color: '#d45030', kind: 'bad' };
  if (n.q === 'doubtful') return { sym: '▲', color: '#e0a030', kind: 'doubtful' };
  if (n.te) return { sym: '★', color: '#5cb868', kind: 'tesuji' };
  return { sym: '●', color: '#5cb868', kind: 'good' };
}
// ⇠ #15 (antes en tsumevault.html, línea 8575)
// Cuadradito de territorio: negro o blanco según el dueño, más opaco cuanto más seguro.
const AI_OWN_HANDLER = {
  stone: {
    draw: function (a, board) {
      const ctx = this, x = board.getX(a.x), y = board.getY(a.y), h = board.stoneRadius * 0.55;
      ctx.save();
      ctx.globalAlpha = Math.min(1, Math.abs(a.own)) * 0.85;
      ctx.fillStyle = a.own > 0 ? '#ffffff' : '#000000';
      ctx.strokeStyle = a.own > 0 ? '#000000' : '#ffffff';
      ctx.lineWidth = 0.6;
      ctx.fillRect(x - h, y - h, h * 2, h * 2);
      ctx.strokeRect(x - h, y - h, h * 2, h * 2);
      ctx.restore();
    }
  }
};
// ⇠ #16 (antes en tsumevault.html, línea 8679)
async function aiPost(path, body, timeoutMs) {
  const r = await syncFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
}
// ⇠ #17 (antes en tsumevault.html, línea 9324)
function isMobilePortrait() { return window.innerWidth < 768; }
// ⇠ #18 (antes en tsumevault.html, línea 9326)
function switchToBoard() { if (isMobilePortrait()) document.getElementById('app').classList.add('mob-board'); }
