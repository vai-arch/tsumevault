// TsumeVault — estilo del tablero (docs/WORKPLAN_ESTILOS.md). Se carga con <script src> DESPUÉS de js/board_core.js
// (usa currentBoardBg, currentStoneSet, wgoBoard, lsGet/lsSet y BOARD_BG_KEY) en tsumevault.html y en archive.html.
//
// E1: la lista de fondos (img/boards/boards.json) y de piedras (img/stones/stones.json) y la restauración de lo
//     elegido viven aquí, no en la página: el archivo aplica las mismas piedras y ya no hace falta abrir ⚙.
// E2: un estilo por defecto y excepciones opcionales por sección (problems, games, joseki, play, archive),
//     guardado en localStorage['board_style_v1']. Un estilo = { bg, stones, jitter }:
//       bg     — color '#rrggbb' o ruta de imagen (como board_background)
//       stones — '' = realistas (WGo), 'Flat' = planas, o el label de un juego de stones.json
//       jitter — descolocación fija de las piedras (planas y de imagen), apagada por defecto
//     Al cambiar de sección se repinta el MISMO tablero (WGo lee fondo y piedras en cada repintado): no se pierde
//     la posición. Las claves antiguas (board_background, stone_set_label) se siguen escribiendo con el estilo por
//     defecto, por compatibilidad.
// E3: piedras planas (estilo kifumaster, código propio): color plano, algo más pequeñas que la casilla, sombra propia
//     y sombra bajo el tablero; líneas más oscuras.

const BOARD_STYLE_KEY = 'board_style_v1';
const STONE_SET_KEY = 'stone_set_label';
const BS_SECTIONS = [['problems', 'Problems'], ['games', 'Games'], ['joseki', 'Joseki'], ['play', 'Play'], ['archive', 'Archive']];
const BS_FLAT = 'Flat';                 // valor de stones para las piedras planas
const BS_DEFAULT_BG = '#c4943a';
const BS_JITTER_MAX = 0.06;             // descolocación máxima, en fracción de casilla
const BS_FLAT_RADIUS = 0.92;            // radio de la piedra plana respecto al de WGo (deja una rendija entre vecinas)

// ── funciones puras ──
function bsCleanStyle(s) {
  s = s && typeof s === 'object' ? s : {};
  return { bg: typeof s.bg === 'string' && s.bg ? s.bg : BS_DEFAULT_BG, stones: typeof s.stones === 'string' ? s.stones : '', jitter: s.jitter === true };
}
// modelo guardado → modelo limpio; sin modelo, se crea el de por defecto con las claves antiguas (nadie ve cambio)
function bsParseModel(raw, legacyBg, legacyStones) {
  let m = null;
  try { m = JSON.parse(raw || 'null'); } catch (e) { m = null; }
  const out = { default: m && typeof m === 'object' && m.default ? bsCleanStyle(m.default) : bsCleanStyle({ bg: legacyBg, stones: legacyStones || '' }) };
  for (const [k] of BS_SECTIONS) out[k] = m && typeof m === 'object' && m[k] ? bsCleanStyle(m[k]) : null;
  return out;
}
function bsStyleFor(model, section) { return (section && model[section]) || model.default; }
// pestaña de tsumevault.html → sección de estilo
function bsSectionOfTab(tab) { return { games: 'games', josekis: 'joseki', play: 'play' }[tab] || 'problems'; }
// cambia el estilo de 'default' o de una sección (si la sección no tenía excepción, parte del de por defecto)
function bsWithStyle(model, target, patch) {
  const out = { ...model };
  const base = target === 'default' ? model.default : (model[target] || model.default);
  out[target] = bsCleanStyle({ ...base, ...patch });
  return out;
}
function bsWithoutOverride(model, section) { return section === 'default' ? model : { ...model, [section]: null }; }
// descolocación fija de la piedra en (x, y): siempre la misma, en [-BS_JITTER_MAX, BS_JITTER_MAX] por eje
function bsJitter(x, y) {
  let h = (Math.imul(x + 1, 73856093) ^ Math.imul(y + 1, 19349663)) >>> 0;
  const next = () => { h ^= h << 13; h >>>= 0; h ^= h >>> 17; h ^= h << 5; h >>>= 0; return h / 4294967296; };
  next();
  return [(next() * 2 - 1) * BS_JITTER_MAX, (next() * 2 - 1) * BS_JITTER_MAX];
}

// ── estado ──
let bsModel = bsParseModel(lsGet(BOARD_STYLE_KEY), lsGet(BOARD_BG_KEY), lsGet(STONE_SET_KEY));
let bsSection = 'problems';
let currentJitter = false;
let boardImages = [], stoneSets = [];
let bsVisualPromise = null;

// fondos de imagen y juegos de piedras del servidor (una sola vez por página)
function bsLoadVisual() {
  if (!bsVisualPromise) bsVisualPromise = (async () => {
    try {
      const r = await fetch('img/boards/boards.json', { signal: AbortSignal.timeout(3000) });
      if (r.ok) boardImages = (await r.json()).map(item => ({ label: item.label || item.file.replace(/\.[^.]+$/, ''), value: 'img/boards/' + item.file }));
    } catch (e) { }
    try {
      const r = await fetch('img/stones/stones.json', { signal: AbortSignal.timeout(3000) });
      if (r.ok) stoneSets = (await r.json()).map(item => ({ label: item.label, black: item.black.map(f => 'img/stones/' + f), white: item.white.map(f => 'img/stones/' + f) }));
    } catch (e) { }
  })();
  return bsVisualPromise;
}
function bsResolveStones(label) {
  if (label === BS_FLAT) return { label: BS_FLAT, flat: true };
  return (label && stoneSets.find(s => s.label === label)) || null;   // null = realistas (o juego aún sin cargar)
}
function bsSave() {
  lsSet(BOARD_STYLE_KEY, JSON.stringify(bsModel));
  lsSet(BOARD_BG_KEY, bsModel.default.bg);                              // compatibilidad con versiones anteriores
  lsSet(STONE_SET_KEY, bsModel.default.stones);
}
// aplica el estilo de la sección (o de la actual) y repinta el tablero que haya, sin recrearlo
function bsApply(section) {
  if (section) bsSection = section;
  const st = bsStyleFor(bsModel, bsSection);
  currentBoardBg = st.bg;
  currentStoneSet = bsResolveStones(st.stones);
  currentJitter = st.jitter;
  if (wgoBoard) bsRestyle(wgoBoard);
}
function bsRestyle(board) {
  board.background = currentBoardBg;
  const img = currentBoardBg && currentBoardBg[0] !== '#';
  board.element.style.backgroundColor = img ? '' : currentBoardBg;
  board.element.style.backgroundImage = img ? `url('${currentBoardBg}')` : 'none';
  board.stoneHandler = buildStoneHandler(currentStoneSet);
  bsStyleBoard(board);
  board.redraw();
}
// lo que el estilo plano cambia además de las piedras: líneas más oscuras y sombra bajo el tablero
function bsStyleBoard(board) {
  const flat = !!(currentStoneSet && currentStoneSet.flat);
  if (!board._bsTheme) board._bsTheme = { ...board.theme };
  board.theme = flat ? { ...board._bsTheme, gridLinesColor: 'rgba(26,31,26,0.9)', starColor: '#1a1f1a' } : { ...board._bsTheme };
  board.element.style.boxShadow = flat ? '0 1px 3px rgba(0,0,0,.3), 0 4px 12px rgba(0,0,0,.14)' : '';
}
// centro de la piedra, con la descolocación si está activada
function bsStonePos(a, board) {
  let x = board.getX(a.x), y = board.getY(a.y);
  if (currentJitter) { const [dx, dy] = bsJitter(a.x, a.y); x += dx * board.fieldWidth; y += dy * board.fieldHeight; }
  return [x, y];
}
// piedras planas: sombra propia (en la capa de sombras de WGo, que ya va desplazada abajo a la derecha) y piedra
function bsFlatHandler() {
  return {
    shadow: {
      draw: function (a, board) {
        const [x, y] = bsStonePos(a, board), r = board.stoneRadius * BS_FLAT_RADIUS * 1.12;
        const g = this.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, 'rgba(0,0,0,0.32)'); g.addColorStop(0.78, 'rgba(0,0,0,0.32)'); g.addColorStop(1, 'rgba(0,0,0,0)');
        this.fillStyle = g; this.beginPath(); this.arc(x, y, r, 0, 2 * Math.PI); this.fill();
      }
    },
    stone: {
      draw: function (a, board) {
        const [x, y] = bsStonePos(a, board), r = board.stoneRadius * BS_FLAT_RADIUS;
        this.beginPath(); this.arc(x, y, r, 0, 2 * Math.PI);
        if (a.c === WGo.W) {
          this.fillStyle = '#ffffff'; this.fill();
          this.lineWidth = Math.max(1, board.stoneRadius / 14); this.strokeStyle = '#1a1a1a'; this.stroke();
        } else { this.fillStyle = '#0d0d0d'; this.fill(); }
      }
    }
  };
}

bsApply();                                  // fondo ya, piedras de imagen en cuanto llegue stones.json
bsLoadVisual().then(() => bsApply());
