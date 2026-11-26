// TsumeVault — funciones puras de la IA (bloque «IA3: funciones puras», sin DOM ni estado global; AR3a).
// Movido TAL CUAL desde tsumevault.html (ver board_core.js). Se carga después de board_core.js.

// ⇠ #14 (antes en tsumevault.html, línea 7785)
// ── IA3: funciones puras (extract_ai.py las extrae para test_ai.js; sin DOM ni estado global) ──
const AI_COLS = 'ABCDEFGHJKLMNOPQRST';   // GTP: columnas sin la I
// Piedras de handicap (vista de negras): 2 = esquinas opuestas, 3 añade abajo-derecha, etc.
const AI_HC_STONES = {
  2: ['D4', 'Q16'], 3: ['D4', 'Q16', 'Q4'], 4: ['D4', 'Q16', 'Q4', 'D16'],
  5: ['D4', 'Q16', 'Q4', 'D16', 'K10'], 6: ['D4', 'Q16', 'Q4', 'D16', 'D10', 'Q10'],
  7: ['D4', 'Q16', 'Q4', 'D16', 'D10', 'Q10', 'K10'], 8: ['D4', 'Q16', 'Q4', 'D16', 'D10', 'Q10', 'K4', 'K16'],
  9: ['D4', 'Q16', 'Q4', 'D16', 'D10', 'Q10', 'K4', 'K16', 'K10'],
};
function aiToGtp(x, y) { return AI_COLS[x] + (19 - y); }
function aiFromGtp(v) {
  if (typeof v !== 'string' || !v || v === 'pass') return null;
  const x = AI_COLS.indexOf(v[0]), n = parseInt(v.slice(1), 10);
  return (x < 0 || !(n >= 1 && n <= 19) || String(n) !== v.slice(1)) ? null : { x, y: 19 - n };
}
function aiSgfCoord(v) { const p = aiFromGtp(v); return p ? String.fromCharCode(97 + p.x) + String.fromCharCode(97 + p.y) : ''; }
function aiHandicapStones(n) { return (AI_HC_STONES[n] || []).slice(); }
// Etiqueta de un nivel. labels = etiquetas que publica el servidor para los motores extra
// ({'gnugo:10': 'GNU Go 10'}); sin ella, un motor extra se ve como 'gnugo 10'.
function aiLevelName(level, labels) {
  const s = String(level || '');
  if (labels && Object.prototype.hasOwnProperty.call(labels, s) && labels[s]) return String(labels[s]);
  if (aiIsExtraLevel(s)) return s.replace(':', ' ');
  const lv = s.split(':').pop();
  if (lv === 'max') return 'Máximo';
  const m = /^rank_(\d+)([kd])$/.exec(lv);
  return m ? m[1] + m[2] : lv;
}
// Fuerza aproximada de un motor extra que publica el servidor ({'gnugo:10': '~7k'}), o null.
function aiLevelStrength(level, strengths) {
  const s = String(level || '');
  return strengths && Object.prototype.hasOwnProperty.call(strengths, s) && strengths[s] ? String(strengths[s]) : null;
}
function aiStrengthText(strength) { return strength ? '≈ ' + String(strength).replace(/^~\s*/, '') : ''; }   // '~7k' -> '≈ 7k'
// Motores rivales extra (GNU Go, Fuego…; ai_engines.json en el servidor): todo nivel
// 'motor:nivel' que no sea de KataGo. Un solo nivel cada uno; no cuentan para superar niveles.
function aiIsExtraLevel(level) {
  const s = String(level || '');
  return /^[a-z0-9]+:[a-z0-9_]+$/.test(s) && !s.startsWith('katago:');
}
// Filas extra de la rejilla: los motores que publica el servidor (en su orden) y después,
// ordenados, los que solo aparecen en partidas guardadas (motor ya retirado o sin conexión).
function aiExtraLevels(games, serverLevels) {
  const out = [], old = [];
  for (const lv of serverLevels || []) if (aiIsExtraLevel(lv) && !out.includes(lv)) out.push(lv);
  for (const g of games || []) {
    if (!g.deleted && aiIsExtraLevel(g.ai_level) && !out.includes(g.ai_level) && !old.includes(g.ai_level)) old.push(g.ai_level);
  }
  return out.concat(old.sort());
}
function aiDefaultLevels() {
  const out = [];
  for (let k = 20; k >= 1; k--) out.push(`katago:rank_${k}k`);
  for (let d = 1; d <= 9; d++) out.push(`katago:rank_${d}d`);
  out.push('katago:max');
  return out;
}
// Configuración de una partida nueva. handicap 0..9; holder 'me'|'ai' (quien lleva el
// handicap juega con negras); myColor solo cuenta en igualadas. Handicap 1 = negras sin
// piedras y komi 0,5. Igualada: komi 6,5 japonesas / 7,5 chinas. game.handicap queda con
// signo desde el jugador: +N recibe, -N da.
function aiNewGame({ level, handicap, holder, myColor, rules }) {
  const h = Math.max(0, Math.min(9, handicap | 0));
  const r = rules === 'chinese' ? 'chinese' : 'japanese';
  const g = { level, rules: r, moves: [], status: 'playing' };
  if (h >= 1) {
    g.my_color = holder === 'ai' ? 'W' : 'B';
    g.handicap = holder === 'ai' ? -h : h;
    g.komi = 0.5;
    g.hc_stones = h >= 2 ? aiHandicapStones(h) : [];
  } else {
    g.my_color = myColor === 'W' ? 'W' : 'B';
    g.handicap = 0;
    g.komi = r === 'chinese' ? 7.5 : 6.5;
    g.hc_stones = [];
  }
  return g;
}
function aiToPlay(game) {
  const m = game.moves;
  if (!m.length) return game.hc_stones.length >= 2 ? 'W' : 'B';
  return m[m.length - 1][0] === 'B' ? 'W' : 'B';
}
// Atrás: nº de jugadas que quedan tras deshacer la última jugada propia y todo lo posterior
// (la respuesta de la IA). null si no hay ninguna jugada propia que deshacer.
function aiUndoLength(game) {
  for (let i = game.moves.length - 1; i >= 0; i--) if (game.moves[i][0] === game.my_color) return i;
  return null;
}
function aiTwoPasses(game) {
  const m = game.moves;
  return m.length >= 2 && m[m.length - 1][1] === 'pass' && m[m.length - 2][1] === 'pass';
}
// Score con signo desde el jugador a partir del score de blancas del motor. Quien abandona
// pierde siempre: si la estimación dice lo contrario, derrota mínima (±0,5).
function aiMyScore(endType, scoreWhite, myColor) {
  let s = myColor === 'W' ? scoreWhite : -scoreWhite;
  s = Math.round(s * 10) / 10 || 0;
  if (endType === 'resign_me' && !(s < 0)) s = -0.5;
  if (endType === 'resign_ai' && !(s > 0)) s = 0.5;
  return s;
}
function aiResultString(endType, score, myColor) {
  const other = myColor === 'B' ? 'W' : 'B';
  if (endType === 'resign_me') return other + '+R';
  if (endType === 'resign_ai') return myColor + '+R';
  if (score === 0) return '0';
  return (score > 0 ? myColor : other) + '+' + Math.abs(score);
}
function aiSgfText(s) { return String(s).replace(/\\/g, '\\\\').replace(/]/g, '\\]'); }
function aiBuildSgf(game, { endType, score, date, myName, aiName }) {
  const pb = game.my_color === 'B' ? myName : aiName, pw = game.my_color === 'B' ? aiName : myName;
  let s = `(;GM[1]FF[4]CA[UTF-8]AP[TsumeVault]SZ[19]KM[${game.komi}]RU[${game.rules === 'chinese' ? 'Chinese' : 'Japanese'}]`;
  if (game.hc_stones.length) s += `HA[${game.hc_stones.length}]AB` + game.hc_stones.map(v => `[${aiSgfCoord(v)}]`).join('');
  s += `DT[${aiSgfText(date)}]PB[${aiSgfText(pb)}]PW[${aiSgfText(pw)}]RE[${aiResultString(endType, score, game.my_color)}]`;
  const tc = game.tc && game.tc.type === 'byoyomi' ? game.tc : null;   // RL1: sistema de tiempo y tiempos por jugada
  if (tc) s += `TM[${tc.main}]OT[${tcSgfOT(tc)}]`;
  game.moves.forEach(([c, v], i) => {
    s += `;${c}[${v === 'pass' ? '' : aiSgfCoord(v)}]`;
    const rec = game.tlog && game.tlog[i];
    if (rec && c === game.my_color) s += tcMoveProps(c, rec);
  });
  return s + ')';
}
// IA4: estadísticas (Excel de Victor). Para superar niveles solo cuentan partidas con nivel
// humano de KataGo ('katago:rank_*'); 'max' queda fuera y los motores extra solo tienen su fila
// en la rejilla. Índice de rango: 20k=0 … 1k=19, 1d=20 … 9d=28.
function aiRankIdx(level) {
  const m = /^katago:rank_(\d+)([kd])$/.exec(String(level || ''));
  if (!m) return null;
  const n = parseInt(m[1], 10);
  if (m[2] === 'k') return n >= 1 && n <= 20 ? 20 - n : null;
  return n >= 1 && n <= 9 ? 19 + n : null;
}
function aiRankLevel(i) { return i < 20 ? `katago:rank_${20 - i}k` : `katago:rank_${i - 19}d`; }
// Rejilla nivel × handicap: celdas "i|h" (i = índice de rango) o "motor:nivel|h" (motores extra)
// con nº de partidas y media de score (h con signo: + recibo).
function aiGrid(games) {
  const cells = {};
  for (const g of games) {
    if (g.deleted) continue;
    const i = aiRankIdx(g.ai_level);
    const row = i != null ? i : aiIsExtraLevel(g.ai_level) ? g.ai_level : null;
    if (row == null) continue;
    const k = row + '|' + g.handicap, c = cells[k] || (cells[k] = { n: 0, sum: 0, avg: 0 });
    c.n++; c.sum += g.score; c.avg = Math.round(c.sum / c.n * 10) / 10;
  }
  return cells;
}
function aiCellGreen(cells, i, h) { const c = cells[i + '|' + h]; return !!(c && c.avg > 0); }
// Casilla sin jugar "dada por superada": hay una más difícil de la misma fila en verde
// (más difícil = recibir menos / dar más = h menor).
function aiCellImplied(cells, i, h) { for (let x = -9; x < h; x++) if (aiCellGreen(cells, i, x)) return true; return false; }
// Filas de KataGo que se ocultan en la rejilla por no interesar: las que ya se ganan dando 9
// (casilla −9 en verde) y las que están a más de 3 rangos por encima del rango más fuerte con
// alguna casilla en verde, si no tienen partidas. Nunca el nivel objetivo t ni las de keep
// (las de borde dorado). Los motores extra no son filas de rango: no entran aquí.
function aiHiddenRows(cells, t, keep) {
  let best = -1;
  const played = new Set();
  for (const k of Object.keys(cells)) {
    const r = k.slice(0, k.lastIndexOf('|'));
    if (!/^\d+$/.test(r)) continue;
    const i = Number(r);
    played.add(i);
    if (cells[k].avg > 0 && i > best) best = i;
  }
  const out = [];
  for (let i = 0; i <= 28; i++) {
    if (i === t || (keep && keep.has(i))) continue;
    if (aiCellGreen(cells, i, -9) || (best >= 0 && i > best + 3 && !played.has(i))) out.push(i);
  }
  return out;
}
// Handicap que corresponde contra el rival i para superar el nivel objetivo t (+ recibo).
function aiHcRequired(i, t) { return i - t; }
// Diagonal de handicaps para superar el nivel t: cada rival i ≠ t con |h| ≤ 9 está superado
// si alguna casilla de su fila con h ≤ h requerido está en verde.
function aiHandicapStatus(cells, t) {
  const out = [];
  for (let i = 0; i <= 28; i++) {
    if (i === t) continue;
    const hReq = aiHcRequired(i, t);
    if (Math.abs(hReq) > 9) continue;
    let done = false;
    for (let h = -9; h <= hReq && !done; h++) if (aiCellGreen(cells, i, h)) done = true;
    out.push({ i, hReq, done });
  }
  return out;
}
// Reglas de cierre por defecto: puntos de control sobre TODAS las partidas igualadas del nivel,
// en orden. Las primeras se evalúan solo al llegar exactamente a n partidas; la última, de n en
// adelante. Cierra si % victorias ≥ pct y media > avg. Un nivel cerrado no se reabre.
const AI_CLOSE_RULES = [{ n: 3, pct: 100, avg: 100 }, { n: 5, pct: 80, avg: 15 }, { n: 12, pct: 75, avg: 0.5 }];
function aiLadder(games, rules) {
  const byLvl = {};
  for (const g of games) {
    if (g.deleted || g.handicap !== 0) continue;
    const i = aiRankIdx(g.ai_level);
    if (i != null) (byLvl[i] = byLvl[i] || []).push(g);
  }
  const out = [];
  for (const i of Object.keys(byLvl).map(Number).sort((a, b) => a - b)) {
    const seq = byLvl[i].slice().sort((a, b) => (a.played_at < b.played_at ? -1 : a.played_at > b.played_at ? 1 : 0));
    let wins = 0, sum = 0, closed = null;
    seq.forEach((g, k) => {
      wins += g.score > 0 ? 1 : 0; sum += g.score;
      const n = k + 1, pct = wins / n * 100, avg = sum / n;
      if (closed) return;
      rules.forEach((r, ri) => {
        if (closed) return;
        const at = ri < rules.length - 1 ? n === r.n : n >= r.n;
        if (at && pct >= r.pct && avg > r.avg) closed = { rule: ri, at: n };
      });
    });
    out.push({ i, n: seq.length, wins, winrate: Math.round(wins / seq.length * 100), avg: Math.round(sum / seq.length * 10) / 10, closed });
  }
  return out;
}
// AN2: análisis de partidas en el visor de Games. Solo 19×19 con piedras iniciales negras
// (partidas normales o con handicap 2..9). stones: piedras iniciales {x,y,c} (c 1 negras, -1
// blancas); moves: [{c, x, y}] con x undefined = pase. Devuelve {ok, body} o {ok:false, reason}.
function anPosition(size, stones, moves, sgfText) {
  if (size !== 19) return { ok: false, reason: 'solo tableros de 19×19' };
  if (stones.some(s => s.c !== 1)) return { ok: false, reason: 'posición con piedras blancas iniciales' };
  if (stones.length === 1 || stones.length > 9) return { ok: false, reason: 'posición inicial no soportada' };
  const km = /KM\[([^\]]*)\]/.exec(sgfText || ''), ru = /RU\[([^\]]*)\]/.exec(sgfText || '');
  let komi = km ? parseFloat(km[1]) : NaN;
  if (!Number.isFinite(komi)) komi = stones.length ? 0.5 : 6.5;
  komi = Math.max(-50, Math.min(50, Math.round(komi * 2) / 2));
  const rules = ru && /chin|aga|nz|tromp/i.test(ru[1]) ? 'chinese' : 'japanese';
  return { ok: true, body: {
    rules, komi,
    handicap_stones: stones.map(s => aiToGtp(s.x, s.y)),
    moves: moves.map(m => [m.c === 1 ? 'B' : 'W', m.x === undefined ? 'pass' : aiToGtp(m.x, m.y)]),
  } };
}
// Errores a partir de la gráfica: whiteLeads[i] = ventaja de blancas antes de la jugada i
// (i = 0..n). Pérdida de la jugada i = cuánto empeora la ventaja de quien la hizo.
function anMistakes(whiteLeads, moves, minLoss) {
  const out = [];
  for (let i = 0; i < moves.length && i + 1 < whiteLeads.length; i++) {
    if (whiteLeads[i] == null || whiteLeads[i + 1] == null) continue;   // AN3: tramo aún sin calcular
    const sign = moves[i][0] === 'B' ? -1 : 1;
    const loss = Math.round((sign * whiteLeads[i] - sign * whiteLeads[i + 1]) * 10) / 10;
    if (loss >= minLoss) out.push({ i: i + 1, color: moves[i][0], loss });
  }
  return out;
}
// Texto bajo la gráfica para la jugada actual cur (null = fuera de la línea principal):
// lo que ganó o perdió quien la hizo y la ventaja tras ella, desde persp ('B' negras o el jugador).
function anGraphCaption(whiteLeads, moves, persp, cur) {
  const fmt = (v) => (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(v);
  const sg = persp === 'B' ? -1 : 1, who = persp === 'B' ? 'negras' : 'tú';
  if (cur == null) return 'Fuera de la línea principal';
  if (whiteLeads[cur] == null || (cur > 0 && whiteLeads[cur - 1] == null)) return `Jugada ${cur} · calculando…`;   // AN3
  const adv = `Ventaja ${who}: ${fmt(Math.round(sg * whiteLeads[cur] * 10) / 10)}`;
  if (cur === 0 || cur > moves.length) return 'Inicio · ' + adv;
  const mc = moves[cur - 1][0], ms = mc === 'B' ? -1 : 1;
  const d = Math.round((ms * whiteLeads[cur] - ms * whiteLeads[cur - 1]) * 10) / 10;
  const tag = d <= -10 ? ' (error grave)' : d <= -5 ? ' (error)' : '';
  return `Jugada ${cur} · ${mc === 'B' ? 'negras' : 'blancas'}: ${fmt(d)}${tag} · ${adv}`;
}
// Ficha de la partida: propiedades del nodo raíz del SGF ({PB: 'Lee', KM: '6.5', ...}).
// Respeta los ']' escapados (\]); solo lee hasta el primer ';' fuera de corchetes tras la raíz.
function anSgfRootProps(sgf) {
  const out = {}, t = String(sgf || '');
  let i = t.indexOf(';');
  if (i < 0) return out;
  i++;
  let key = '';
  while (i < t.length) {
    const ch = t[i];
    if (ch === ';' || ch === '(' || ch === ')') break;
    if (/[A-Za-z]/.test(ch)) { key += ch; i++; continue; }
    if (ch === '[') {
      let v = ''; i++;
      while (i < t.length && t[i] !== ']') { if (t[i] === '\\' && i + 1 < t.length) i++; v += t[i]; i++; }
      i++;
      const k = key.replace(/[a-z]/g, '');
      if (k) { if (out[k] == null) out[k] = v.trim(); else out[k] += ', ' + v.trim(); }
      // varios valores seguidos ([a][b]) comparten la clave
      if (t[i] !== '[') key = '';
      continue;
    }
    i++;
  }
  return out;
}
// Filas legibles de la ficha: [[etiqueta, valor], ...] solo con lo que el SGF trae.
function anGameInfoRows(p, nMoves) {
  const rows = [], who = (n, r) => [n, r].filter(Boolean).join(' · ');
  const res = (re) => {
    const m = /^([BW])\+(.*)$/i.exec(re || '');
    if (!m) return re === '0' || /^(draw|jigo)$/i.test(re || '') ? 'Empate' : re;
    const side = m[1].toUpperCase() === 'B' ? 'Negras' : 'Blancas', how = m[2];
    if (/^r(esign)?$/i.test(how)) return `${side} por abandono`;
    if (/^t(ime)?$/i.test(how)) return `${side} por tiempo`;
    if (/^f(orfeit)?$/i.test(how)) return `${side} por incomparecencia`;
    return how ? `${side} por ${how}` : `${side} ganan`;
  };
  if (p.PB || p.BR) rows.push(['Negras', who(p.PB, p.BR)]);
  if (p.PW || p.WR) rows.push(['Blancas', who(p.PW, p.WR)]);
  if (p.RE) rows.push(['Resultado', res(p.RE)]);
  if (p.HA && p.HA !== '0') rows.push(['Handicap', p.HA]);
  if (p.KM) rows.push(['Komi', p.KM]);
  if (p.RU) rows.push(['Reglas', p.RU]);
  if (nMoves != null) rows.push(['Jugadas', String(nMoves)]);
  if (p.DT) rows.push(['Fecha', p.DT]);
  if (p.EV || p.RO) rows.push(['Evento', [p.EV, p.RO].filter(Boolean).join(' · ')]);
  if (p.GN) rows.push(['Partida', p.GN]);
  if (p.PC) rows.push(['Lugar', p.PC]);
  if (p.TM || p.OT) rows.push(['Tiempo', [p.TM && `${p.TM} s`, p.OT].filter(Boolean).join(' + ')]);
  if (p.SO) rows.push(['Fuente', p.SO]);
  return rows;
}
// Texto del análisis (modelo 1: habla de la jugada que se ve en el tablero).
// d: respuesta de /ai/analyze sobre la posición ANTERIOR a esa jugada (to_play = quien la hizo);
// moveNo: nº de esa jugada (null = inicio, sin jugada todavía); persp: 'B' o 'W' para la ventaja;
// mine: true si persp es el jugador (partidas contra la IA) -> "tu ventaja".
function anAnalysisText(d, moveNo, persp, mine, thinkS) {
  const fmt = (v) => (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(Math.round(v * 10) / 10);
  const cs = d.candidates, best = cs[0], side = d.to_play === 'B' ? 'negras' : 'blancas';
  const lines = [];
  if (moveNo == null) lines.push(`Inicio · juegan ${side}`);
  else if (d.played) lines.push(`Jugada ${moveNo} (${side}): ${d.played.move} · ` +
    (d.played.loss <= 0.5 ? 'buena jugada' : `${fmt(-d.played.loss)} respecto a la mejor`) +
    (thinkS != null && Number.isFinite(+thinkS) ? ` · pensaste ${anThinkTxt(thinkS)}` : ''));   // PA5
  lines.push(`Mejor: ★ ${best.move}` + cs.slice(1).map((c, k) => ` · ${k + 2} ${c.move} (${fmt(c.scoreLead - best.scoreLead)})`).join(''));
  const adv = (d.to_play === persp ? 1 : -1) * best.scoreLead;
  lines.push(`${mine ? 'Tu ventaja' : 'Ventaja ' + (persp === 'B' ? 'negras' : 'blancas')} con la mejor: ${fmt(adv)}`);
  return lines.join('\n');
}
// ST1: resumen del estado del servidor para ⚙. s = respuesta de /server/status (null si no
// respondió), ms = tiempo de respuesta. Devuelve {level: 'ok'|'warn'|'bad', warn: [...], lines: [[título, texto]]}.
function srvStatusSummary(s, ms, nowIso) {
  if (!s) return { level: 'bad', warn: ['El servidor no responde'], lines: [] };
  const GB = (b) => b == null ? '?' : (b / 1073741824).toFixed(1) + ' GB';
  const MB = (b) => b == null ? '?' : (b / 1048576).toFixed(1) + ' MB';
  const up = (t) => t >= 86400 ? `${Math.floor(t / 86400)} d ${Math.floor(t % 86400 / 3600)} h` : t >= 3600 ? `${Math.floor(t / 3600)} h ${Math.floor(t % 3600 / 60)} min` : `${Math.floor(t / 60)} min`;
  const warn = [], ai = s.ai || {}, w = ai.worker || null;
  if (!ai.available) warn.push('KataGo no disponible' + (ai.engine_reason ? ` (${ai.engine_reason})` : ''));
  if (s.disk && s.disk.free / s.disk.total < 0.1) warn.push('Poco disco libre');
  if (s.mem && s.mem.available != null && s.mem.available / s.mem.total < 0.1) warn.push('Poca memoria libre');
  if (w && w.queue > 20) warn.push(`Cola de análisis larga (${w.queue})`);
  const errAt = w && w.last_error && Date.parse(w.last_error.at), now = Date.parse(nowIso || s.time);
  if (errAt && now - errAt < 86400000) warn.push('Error reciente en el análisis automático');
  const lines = [
    ['Conexión', `responde en ${ms} ms · BD v${s.schema_version} · en marcha ${up(s.uptime_s || 0)}`],
    ['KataGo', !ai.available ? `no disponible${ai.engine_reason ? ' · ' + ai.engine_reason : ''}`
      : `disponible · ${ai.engine_running ? 'cargado' : 'dormido'}` + (ai.move_ms_avg != null ? ` · jugada media ${(ai.move_ms_avg / 1000).toFixed(1)} s` : '')],
  ];
  if (w) {
    let t = w.enabled ? `activado · en cola ${w.queue}` : 'desactivado';
    if (w.current) t += ` · analizando ${w.current.label || 'partida'} (${w.current.done}/${w.current.total})`;
    if (w.enabled) t += ` · hoy ${w.done_today}`;
    if (w.last_error) t += ` · último error: ${w.last_error.msg} (${w.last_error.at.slice(0, 16).replace('T', ' ')})`;
    lines.push(['Análisis', t]);
  }
  lines.push(['Máquina', [s.disk && `disco ${GB(s.disk.free)} libres de ${GB(s.disk.total)}`,
    s.mem && s.mem.available != null && `memoria ${GB(s.mem.available)} libres de ${GB(s.mem.total)}`,
    s.load && `carga ${s.load.join(' ')}${s.cpus ? ` (${s.cpus} CPU)` : ''}`,
    s.cache && s.cache.rows != null && `caché ${s.cache.rows} posiciones (${MB(s.cache.bytes)})`].filter(Boolean).join(' · ')]);
  return { level: warn.length ? 'warn' : 'ok', warn, lines };
}
// RL1: reloj de entrenamiento (solo del jugador; WORKPLAN_IA.md, sección RL). Tiempos en ms.
// Sistema: {type:'none'} | {type:'byoyomi', main (s), periods, period (s)}. El tipo deja sitio
// a otros sistemas (canadiense) sin tocar el resto. Estado entre turnos: {mainMs, periods,
// overMs, expired}; dentro del turno todo se deriva de e = ms pensados en este turno (sin pausas).
const TC_LIMITS = { main: [0, 10800], periods: [1, 30], period: [1, 600] };
function tcNormalize(c) {
  if (!c || c.type !== 'byoyomi') return { type: 'none' };
  const cl = (v, [lo, hi], def) => { const n = v == null || v === '' ? NaN : Math.round(Number(v)); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : def; };
  return { type: 'byoyomi', main: cl(c.main, TC_LIMITS.main, 0), periods: cl(c.periods, TC_LIMITS.periods, 5), period: cl(c.period, TC_LIMITS.period, 30) };
}
function tcStart(sys) {
  return sys && sys.type === 'byoyomi' ? { mainMs: sys.main * 1000, periods: sys.periods, overMs: 0, expired: false } : null;
}
// Reloj tras pensar e ms en el turno que empezó en st. phase: 'main' | 'byo' | 'over'.
// En byoyomi un periodo se consume entero solo si se agota; al pulsar, el siguiente vuelve lleno.
function tcAt(sys, st, e) {
  const P = sys.period * 1000;
  if (st.expired) return { phase: 'over', mainMs: 0, periods: 0, periodMs: 0, overMs: st.overMs + e };
  if (e < st.mainMs) return { phase: 'main', mainMs: st.mainMs - e, periods: st.periods, periodMs: P, overMs: 0 };
  const rest = e - st.mainMs, used = Math.floor(rest / P);
  if (used < st.periods) return { phase: 'byo', mainMs: 0, periods: st.periods - used, periodMs: P - rest % P, overMs: 0 };
  return { phase: 'over', mainMs: 0, periods: 0, periodMs: 0, overMs: rest - st.periods * P };
}
// Estado para el turno siguiente al pulsar el reloj tras e ms. Pasado el último periodo, el
// reloj se queda en negativo y sigue acumulando (solo aviso: la partida no termina).
function tcPress(sys, st, e) {
  const a = tcAt(sys, st, e);
  if (a.phase === 'over') return { mainMs: 0, periods: 0, overMs: a.overMs, expired: true };
  return { mainMs: a.mainMs, periods: a.periods, overMs: 0, expired: false };
}
// Avisos del turno (instantes desde el inicio del turno): entrada en byoyomi, cuenta atrás de
// cada periodo (desde min(9, periodo-1) hasta 1), periodo consumido (left = los que quedan)
// y fin del último periodo. tcEvents devuelve los de (e0, e1], en orden.
function tcEventTimes(sys, st) {
  if (!sys || sys.type !== 'byoyomi' || st.expired) return [];
  const P = sys.period * 1000, out = [], t0 = st.mainMs;
  if (t0 > 0) out.push({ t: t0, kind: 'byo_start', periods: st.periods });
  for (let k = 0; k < st.periods; k++) {
    const ts = t0 + k * P, left = st.periods - k;
    for (let n = Math.min(9, sys.period - 1); n >= 1; n--) out.push({ t: ts + P - n * 1000, kind: 'count', n });
    out.push(left > 1 ? { t: ts + P, kind: 'period_used', left: left - 1 } : { t: ts + P, kind: 'timeout' });
  }
  return out;
}
function tcEvents(sys, st, e0, e1) { return tcEventTimes(sys, st).filter(ev => ev.t > e0 && ev.t <= e1); }
function tcFmt(ms, up) {
  const s = up ? Math.floor(ms / 1000) : Math.ceil(ms / 1000), h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}
function tcLabel(a) {
  if (a.phase === 'main') return tcFmt(a.mainMs);
  if (a.phase === 'byo') return `${a.periods} × ${tcFmt(a.periodMs)}`;
  return '−' + tcFmt(a.overMs, true);
}
function tcSgfOT(sys) { return `${sys.periods}x${sys.period} byo-yomi`; }
// Propiedades SGF de una jugada mía: TT = segundos pensados (propiedad propia de TsumeVault,
// se mide también sin reloj); TS[1] = me salté el tiempo mínimo de reflexión (propia también);
// con reloj, BL/WL = tiempo restante (del periodo en byoyomi) y OB/OW = periodos restantes;
// OB[0] = me pasé del último periodo.
function tcMoveProps(color, rec) {
  const s1 = (ms) => String(Math.round(ms / 100) / 10);
  let s = `TT[${s1(rec.t)}]` + (rec.s ? 'TS[1]' : '');
  const a = rec.a;
  if (a) {
    if (a.phase === 'main') s += `${color}L[${s1(a.mainMs)}]`;
    else if (a.phase === 'byo') s += `${color}L[${s1(a.periodMs)}]O${color}[${a.periods}]`;
    else s += `${color}L[0]O${color}[0]`;
  }
  return s;
}
// Resumen de tiempos de una partida guardada (histórico): media pensada por jugada mía, jugada
// en la que entré en byoyomi y en la que se me acabó el tiempo (null si no hay datos), y cuántas
// veces me salté el tiempo mínimo de reflexión (TS[1]).
function tcSgfSummary(sgf, myColor) {
  const re = /;([BW])\[([a-s]{0,2})\]((?:[A-Z]+\[[^\]]*\])*)/g;
  let m, n = 0, sum = 0, cnt = 0, byoMove = null, timeoutMove = null, hasClock = false, skips = 0;
  while ((m = re.exec(String(sgf || '')))) {
    n++;
    if (m[1] !== myColor) continue;
    const prop = (k) => { const r = new RegExp('(?:^|\\])' + k + '\\[([^\\]]*)\\]').exec(m[3]); return r ? r[1] : null; };
    const tt = prop('TT'), ob = prop('O' + myColor);
    if (tt != null && Number.isFinite(parseFloat(tt))) { sum += parseFloat(tt); cnt++; }
    if (prop('TS') === '1') skips++;
    if (prop(myColor + 'L') != null) hasClock = true;
    if (ob != null && byoMove == null) byoMove = n;
    if (ob === '0' && timeoutMove == null) timeoutMove = n;
  }
  const ot = /\bOT\[([^\]]*)\]/.exec(String(sgf || '')), tm = /\bTM\[([\d.]+)\]/.exec(String(sgf || ''));
  return { avgMs: cnt ? Math.round(sum / cnt * 1000) : null, timed: cnt, byoMove, timeoutMove, clock: hasClock, ot: ot ? ot[1] : null, tm: tm ? parseFloat(tm[1]) : null, skips };
}
// RL4: texto del histórico a partir de tcSgfSummary: corto para la fila y largo para el título.
// null si la partida no tiene tiempos (anteriores al reloj).
function tcHistoryText(sm) {
  if (!sm || sm.avgMs == null) return null;
  const sec = sm.avgMs / 1000, avg = sec < 60 ? `${sec < 10 ? sec.toFixed(1) : Math.round(sec)} s` : tcFmt(sm.avgMs);
  let short = `⏱ ${avg}/jug`, long = `Media pensada por jugada: ${avg} (${sm.timed} jugadas)`;
  if (sm.ot) {
    const m = /^(\d+)x(\d+) byo-yomi$/.exec(sm.ot), main = sm.tm || 0;
    const mainTxt = main % 60 ? `${main} s` : `${main / 60} min`;
    long += ` · reloj ${m ? `${mainTxt} + ${m[1]} × ${m[2]} s` : sm.ot}`;
  }
  if (sm.byoMove != null) { short += ` · byo ${sm.byoMove}`; long += ` · entraste en byoyomi en la jugada ${sm.byoMove}`; }
  if (sm.timeoutMove != null) { short += ` · ⏰ ${sm.timeoutMove}`; long += ` · se te acabó el tiempo en la jugada ${sm.timeoutMove}`; }
  if (sm.skips) { short += ` · ⏭ ${sm.skips}`; long += ` · te saltaste la espera ${sm.skips} ${sm.skips === 1 ? 'vez' : 'veces'}`; }
  return { short, long };
}
// RL3: qué decir y cómo vibrar en cada aviso del reloj. key = nombre de la grabación propia
// (audio/clock/<key>.mp3); si no existe, se dice text con la voz del navegador.
function tcEventCue(ev) {
  const W = ['cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve'];
  switch (ev.kind) {
    case 'byo_start': return ev.periods === 1 ? { key: 'ultimo_periodo', text: 'Byoyomi. Último periodo', vib: [300, 100, 300] }
      : { key: 'byoyomi', text: 'Byoyomi', vib: [300] };
    case 'count': return { key: String(ev.n), text: W[ev.n] || String(ev.n), vib: [60] };
    case 'period_used': return ev.left === 1 ? { key: 'ultimo_periodo', text: 'Último periodo', vib: [300, 100, 300] }
      : { key: 'quedan_' + ev.left, text: 'Quedan ' + ev.left, vib: [400] };
    case 'timeout': return { key: 'fuera_de_tiempo', text: 'Fuera de tiempo', vib: [500, 150, 500, 150, 500] };
    default: return null;
  }
}
// Grabaciones que puede usar una partida con este sistema (para precargarlas).
function tcCueKeys(sys) {
  if (!sys || sys.type !== 'byoyomi') return [];
  const k = ['byoyomi', 'ultimo_periodo', 'fuera_de_tiempo'];
  for (let n = 1; n <= Math.min(9, sys.period - 1); n++) k.push(String(n));
  for (let n = 2; n < sys.periods; n++) k.push('quedan_' + n);
  return k;
}
// PA2: partida pedida desde una casilla de la rejilla (i = índice de rango, h = handicap con
// signo: + recibo, − doy). En igualadas, el color contrario al de la última igualada no borrada
// contra ese nivel (por played_at); si no hay ninguna, negras. Con handicap el color lo fija aiNewGame.
function aiCellGameParams(games, level, h) {
  if (h !== 0) return { level, hc: Math.abs(h), holder: h > 0 ? 'me' : 'ai', color: 'B' };
  let last = null;
  for (const g of games || []) {
    if (g.deleted || g.ai_level !== level || g.handicap !== 0) continue;
    if (!last || String(g.played_at) > String(last.played_at)) last = g;
  }
  return { level, hc: 0, holder: 'me', color: last ? (last.my_color === 'B' ? 'W' : 'B') : 'B' };
}
// PA3: ms que faltan para poder jugar con un mínimo de minS segundos pensados (0 = ya se puede).
// skipped: la espera de este turno se saltó con doble toque (jugada obvia).
function aiThinkLeft(minS, spentMs, skipped) {
  if (skipped) return 0;
  const m = Math.max(0, Math.round(+minS || 0)) * 1000;
  return Math.max(0, Math.ceil(m - (+spentMs || 0)));
}
// PA5: segundos pensados (TT) por jugada de la línea principal; out[i] = jugada i (1..n), null sin dato.
function anMoveTimes(sgf) {
  const re = /;([BW])\[([a-s]{0,2})\]((?:[A-Z]+\[[^\]]*\])*)/g, out = [null];
  let m;
  while ((m = re.exec(String(sgf || '')))) {
    const r = /(?:^|\])TT\[([^\]]*)\]/.exec(m[3]), v = r ? parseFloat(r[1]) : NaN;
    out.push(Number.isFinite(v) ? v : null);
  }
  return out;
}
function anThinkTxt(s) {
  if (s == null || !Number.isFinite(+s)) return '';
  s = +s;
  if (s >= 60) { const t = Math.round(s); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`; }
  return (s < 10 ? String(Math.round(s * 10) / 10) : String(Math.round(s))) + ' s';
}
// PA4: texto de la estimación del visor (score_white con signo: + ganan blancas).
function anEstText(scoreWhite, persp, mine) {
  const v = Math.round((persp === 'B' ? -1 : 1) * scoreWhite * 10) / 10;
  const fmt = (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(v);
  return `Estimación: ${mine ? 'tu ventaja' : 'ventaja ' + (persp === 'B' ? 'negras' : 'blancas')} ${fmt}`;
}
// PA6: estado del análisis automático de una partida (respuesta de /ai/analysis_status).
// icon para el histórico; text para junto al 📈 del visor; title al pasar el ratón.
function anStatusText(s) {
  const st = s && s.state;
  if (st === 'done') return { icon: '✓', text: '✓', title: 'Analizada: gráfica y errores listos' };
  if (st === 'queued') return { icon: '⏳', text: '⏳ en cola', title: 'En la cola de análisis del servidor' };
  if (st === 'running') {
    const what = s.phase === 'errores' ? 'errores' : 'gráfica';
    const prog = Number.isFinite(s.done) && Number.isFinite(s.total) ? ` ${s.done}/${s.total}` : '';
    return { icon: '⏳', text: `⏳ ${what}${prog}`, title: `Analizándose en el servidor: ${what}${prog}` };
  }
  return { icon: '', text: '', title: '' };
}
// ── fin IA3 funciones puras ──
