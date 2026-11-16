#!/usr/bin/env node
/* test_ai.js — IA3: funciones puras de la partida contra la IA (ai_bundle.js,
 * extraído de tsumevault.html con extract_ai.py). Uso:
 *     python extract_ai.py && node test_ai.js
 */
'use strict';
const fs = require('fs');
const vm = require('node:vm');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('ai_bundle.js', 'utf8'), ctx);
const fails = [];
function check(name, cond, extra = '') { console.log((cond ? 'PASS ' : 'FAIL ') + name + (cond ? '' : '  ' + extra)); if (!cond) fails.push(name); }
const J = JSON.stringify;
const f = (code) => vm.runInContext(code, ctx);

// Coordenadas GTP <-> WGo (x izquierda->derecha, y arriba->abajo)
check('coords: esquinas y la columna sin I', f("aiToGtp(0,0)") === 'A19' && f("aiToGtp(18,18)") === 'T1' && f("aiToGtp(8,9)") === 'J10' && f("aiToGtp(3,15)") === 'D4');
let roundtrip = true;
for (let x = 0; x < 19; x++) for (let y = 0; y < 19; y++) { const p = f(`aiFromGtp(aiToGtp(${x},${y}))`); if (!p || p.x !== x || p.y !== y) roundtrip = false; }
check('coords: ida y vuelta en las 361 intersecciones', roundtrip);
check('coords: inválidos -> null (I, fuera, pase, ceros a la izquierda)',
  ['I5', 'U3', 'A0', 'A20', 'pass', '', 'D04', 'd4'].every(v => f(`aiFromGtp(${J(v)})`) === null));
check('coords SGF: D4 = dp, Q16 = pd, pase vacío', f("aiSgfCoord('D4')") === 'dp' && f("aiSgfCoord('Q16')") === 'pd' && f("aiSgfCoord('pass')") === '');

// Handicap
let hcOk = true;
for (let n = 2; n <= 9; n++) { const s = f(`aiHandicapStones(${n})`); if (s.length !== n || new Set(s).size !== n || s.some(v => !f(`aiFromGtp(${J(v)})`))) hcOk = false; }
check('handicap: de 2 a 9 piedras, distintas y válidas', hcOk);
check('handicap: 0 y 1 sin piedras', f('aiHandicapStones(0)').length === 0 && f('aiHandicapStones(1)').length === 0);
check('handicap: devuelve copia (no comparte la tabla)', (() => { const a = f('aiHandicapStones(2)'); a.push('X'); return f('aiHandicapStones(2)').length === 2; })());

// Niveles
check('niveles: etiquetas', f("aiLevelLabel('katago:rank_15k')") === '15k' && f("aiLevelLabel('katago:rank_3d')") === '3d' && f("aiLevelLabel('katago:max')") === 'Máximo');
const lv = f('aiDefaultLevels()');
check('niveles: lista por defecto = la del servidor (20k..1k, 1d..9d, max)', lv.length === 30 && lv[0] === 'katago:rank_20k' && lv[19] === 'katago:rank_1k' && lv[20] === 'katago:rank_1d' && lv[29] === 'katago:max');

// Partida nueva
let g = f("aiNewGame({ level: 'katago:rank_12k', handicap: 0, holder: 'me', myColor: 'W', rules: 'japanese' })");
check('igualada japonesa: mi color elegido, komi 6.5, handicap 0', g.my_color === 'W' && g.komi === 6.5 && g.handicap === 0 && g.hc_stones.length === 0, J(g));
g = f("aiNewGame({ level: 'x', handicap: 0, myColor: 'B', rules: 'chinese' })");
check('igualada china: komi 7.5', g.komi === 7.5 && g.rules === 'chinese', J(g));
g = f("aiNewGame({ level: 'x', handicap: 3, holder: 'me', myColor: 'W', rules: 'japanese' })");
check('recibo 3: negras, +3, komi 0.5, 3 piedras (mi color elegido se ignora)', g.my_color === 'B' && g.handicap === 3 && g.komi === 0.5 && g.hc_stones.length === 3, J(g));
g = f("aiNewGame({ level: 'x', handicap: 6, holder: 'ai', myColor: 'B', rules: 'japanese' })");
check('doy 6: blancas, -6', g.my_color === 'W' && g.handicap === -6 && g.hc_stones.length === 6, J(g));
g = f("aiNewGame({ level: 'x', handicap: 1, holder: 'me', rules: 'japanese' })");
check('handicap 1: negras sin piedras y komi 0.5', g.my_color === 'B' && g.handicap === 1 && g.hc_stones.length === 0 && g.komi === 0.5, J(g));

// Turnos y pases
check('turno: sin handicap empiezan negras', f("aiToPlay({ moves: [], hc_stones: [] })") === 'B');
check('turno: handicap 1 empiezan negras', f("aiToPlay(aiNewGame({ level:'x', handicap:1, holder:'ai', rules:'japanese' }))") === 'B');
check('turno: handicap >=2 empiezan blancas', f("aiToPlay({ moves: [], hc_stones: ['D4','Q16'] })") === 'W');
check('turno: alterna tras cada jugada (pases incluidos)', f("aiToPlay({ moves: [['W','pass']], hc_stones: ['D4','Q16'] })") === 'B' && f("aiToPlay({ moves: [['B','D4'],['W','pass']], hc_stones: [] })") === 'B');
check('dos pases seguidos terminan; uno solo o separados, no',
  f("aiTwoPasses({ moves: [['B','D4'],['W','pass'],['B','pass']] })") === true
  && f("aiTwoPasses({ moves: [['B','pass']] })") === false
  && f("aiTwoPasses({ moves: [['B','pass'],['W','D4'],['B','pass']] })") === false);

// Score con signo y regla del abandono
check('score: negras ganan con W-3.5 -> +3.5 para mí con negras', f("aiMyScore('passes', -3.5, 'B')") === 3.5 && f("aiMyScore('passes', -3.5, 'W')") === -3.5);
check('score: estimación redondeada a 1 decimal', f("aiMyScore('passes', 2.37, 'W')") === 2.4);
check('abandono mío con estimación a favor -> derrota mínima -0.5', f("aiMyScore('resign_me', -8, 'B')") === -0.5 && f("aiMyScore('resign_me', 0, 'B')") === -0.5);
check('abandono mío con estimación en contra -> se respeta', f("aiMyScore('resign_me', 20, 'B')") === -20);
check('abandono de la IA con estimación en contra -> victoria mínima +0.5', f("aiMyScore('resign_ai', 5, 'B')") === 0.5);
check('sin -0 (empate exacto)', Object.is(f("aiMyScore('passes', 0, 'B')"), 0));

// Resultado y SGF
check('RE: abandonos y puntos', f("aiResultString('resign_me', -0.5, 'B')") === 'W+R' && f("aiResultString('resign_ai', 3, 'W')") === 'W+R'
  && f("aiResultString('passes', 12.5, 'W')") === 'W+12.5' && f("aiResultString('passes', -3.5, 'W')") === 'B+3.5' && f("aiResultString('passes', 0, 'B')") === '0');
g = f(`(() => { const g = aiNewGame({ level: 'katago:rank_15k', handicap: 2, holder: 'me', rules: 'chinese' }); g.moves = [['W','Q4'],['B','pass'],['W','C3']]; return g; })()`);
ctx.__g = g;
const sgf = f("aiBuildSgf(__g, { endType: 'passes', score: 12.5, date: '2026-11-13', myName: 'Jugador', aiName: 'KataGo 15k' })");
check('SGF: cabecera, handicap, reglas, jugadores y resultado',
  sgf.startsWith('(;GM[1]FF[4]CA[UTF-8]') && sgf.includes('SZ[19]KM[0.5]RU[Chinese]HA[2]AB[dp][pd]') && sgf.includes('PB[Jugador]PW[KataGo 15k]RE[B+12.5]'), sgf);
check('SGF: jugadas en orden, pase como []', sgf.endsWith(';W[pp];B[];W[cq])'), sgf);
check('SGF: escapa ] y \\ en textos', f("aiBuildSgf(__g, { endType: 'resign_me', score: -0.5, date: 'd', myName: 'a]b\\\\c', aiName: 'x' })").includes('PB[a\\]b\\\\c]'));

// Atrás
const U = (my, moves) => { ctx.__u = { my_color: my, moves }; return f('aiUndoLength(__u)'); };
check('atrás: quita mi última jugada y la respuesta de la IA', U('B', [['B','D4'],['W','Q16'],['B','C3'],['W','pass']]) === 2);
check('atrás: si la IA no respondió (error), quita solo la mía', U('B', [['B','D4'],['W','Q16'],['B','C3']]) === 2);
check('atrás: con la IA empezando (yo blancas) conserva su primera jugada', U('W', [['B','Q16'],['W','D4'],['B','Q4']]) === 1);
check('atrás: sin jugadas propias -> null (botón deshabilitado)', U('W', [['B','Q16']]) === null && U('B', []) === null);

// ── IA4: estadísticas ──
check('rango: 20k=0, 1k=19, 1d=20, 9d=28; max y otros motores fuera',
  f("aiRankIdx('katago:rank_20k')") === 0 && f("aiRankIdx('katago:rank_1k')") === 19 && f("aiRankIdx('katago:rank_1d')") === 20
  && f("aiRankIdx('katago:rank_9d')") === 28 && f("aiRankIdx('katago:max')") === null && f("aiRankIdx('gnugo:10')") === null && f("aiRankIdx('katago:rank_21k')") === null);
let rt = true; for (let i = 0; i <= 28; i++) if (f(`aiRankIdx(aiRankLevel(${i}))`) !== i) rt = false;
check('rango: ida y vuelta índice <-> nivel', rt);
const G = (lvl, h, score, extra = {}) => Object.assign({ ai_level: `katago:rank_${lvl}`, handicap: h, score, played_at: '2026-11-01T10:00:00Z', deleted: 0 }, extra);
ctx.__games = [G('15k', -6, 75), G('15k', -6, -20), G('9k', 5, 36), G('9k', 3, -10), G('3k', 9, 94), G('12k', 0, 65),
  G('14k', -2, 50, { deleted: 1 }), Object.assign(G('15k', 0, 500), { ai_level: 'katago:max' })];
const cells = f('aiGrid(__games)');
check('rejilla: media por casilla (15k dando 6: +75 y -20 -> 27.5, 2 partidas)', cells['5|-6'].n === 2 && cells['5|-6'].avg === 27.5, J(cells));
check('rejilla: ignora borradas y Máximo', !('6|-2' in cells) && Object.keys(cells).length === 5, J(Object.keys(cells)));
ctx.__cells = cells;
const st = f('aiHandicapStatus(__cells, 8)');   // objetivo 12k
const row = (lvl) => st.find(r => r.i === f(`aiRankIdx('katago:rank_${lvl}')`));
check('handicap requerido: 9k recibe 3, 15k da 3, 3k recibe 9 (objetivo 12k)', row('9k').hReq === 3 && row('15k').hReq === -3 && row('3k').hReq === 9);
check('diagonal: 15k superado (ganó dando 6 ≥ 3 requeridas)', row('15k').done === true);
check('diagonal: 9k NO superado (solo verde recibiendo 5 > 3; recibiendo 3 en rojo)', row('9k').done === false);
check('diagonal: 3k superado recibiendo 9', row('3k').done === true);
check('diagonal: sin el propio nivel objetivo y solo |h| ≤ 9', !st.some(r => r.i === 8) && st.every(r => Math.abs(r.hReq) <= 9) && st.length === 8 + 9, `n=${st.length}`);
check('casilla implícita: 15k dando 3 sin jugar se da por superada; 9k recibiendo 6 también; 9k recibiendo 4 no',
  f("aiCellImplied(__cells, 5, -3)") === true && f("aiCellImplied(__cells, 11, 6)") === true && f("aiCellImplied(__cells, 11, 4)") === false);
const day = (d) => `2026-11-${String(d).padStart(2, '0')}T10:00:00Z`;
const series = (lvl, scores) => scores.map((s, k) => G(lvl, 0, s, { played_at: day(k + 1) }));
ctx.__R = f('AI_CLOSE_RULES');
const lad = (games) => { ctx.__lg = games; return f('aiLadder(__lg, __R)'); };
let L = lad(series('15k', [120, 150, 101]));
check('escalera: 3/3 con media > 100 cierra en la regla 1 a las 3', L[0].closed && L[0].closed.rule === 0 && L[0].closed.at === 3 && L[0].winrate === 100, J(L));
L = lad(series('13k', [60, 120, 54, 82, 91]));
check('escalera: 5/5 con media > 15 (pero ≤ 100 a las 3) cierra en la regla 2 a las 5', L[0].closed && L[0].closed.rule === 1 && L[0].closed.at === 5, J(L));
L = lad(series('12k', [10, 20, -5, 30, -40, 5, 5, 5, 5, 5, 5]));
check('escalera: entre 6 y 11 partidas no cierra aunque vaya bien', L[0].closed === null && L[0].n === 11, J(L));
L = lad(series('12k', [10, 20, -5, 30, -40, 5, 5, 5, 5, 5, -5, -3, 4, 2, 2, 2]));
check('escalera: desde 12 cierra en cuanto llega a ≥75 % y media > 0,5 (falla 12-15, cierra a las 16)', L[0].closed && L[0].closed.rule === 2 && L[0].closed.at === 16, J(L));
L = lad(series('12k', [120, 150, 101, -50, -50, -50]));
check('escalera: un nivel cerrado no se reabre aunque bajen las cifras', L[0].closed && L[0].closed.at === 3 && L[0].winrate === 50, J(L));
L = lad([...series('10k', [5, 5]), G('10k', 2, 30), G('10k', 0, 9, { deleted: 1 })]);
check('escalera: solo igualadas no borradas', L[0].n === 2, J(L));
L = lad(series('11k', [30, 30, 30, 30]).reverse());
check('escalera: orden cronológico por played_at, no por orden de llegada', L[0].n === 4 && L[0].closed === null, J(L));

// ── AN2: análisis en el visor ──
ctx.__st = [{ x: 3, y: 15, c: 1 }, { x: 15, y: 3, c: 1 }];
ctx.__mv = [{ c: -1, x: 15, y: 15 }, { c: 1 }, { c: -1, x: 2, y: 16 }];
let P = f("anPosition(19, __st, __mv, '(;GM[1]SZ[19]KM[0.5]RU[Japanese]HA[2])')");
check('posición: handicap 2 y jugadas en GTP, pase incluido, komi y reglas del SGF', P.ok && J(P.body.handicap_stones) === '["D4","Q16"]'
  && J(P.body.moves) === '[["W","Q4"],["B","pass"],["W","C3"]]' && P.body.komi === 0.5 && P.body.rules === 'japanese', J(P));
P = f("anPosition(19, [], [], '(;KM[7.5]RU[Chinese])')");
check('posición: reglas chinas reconocidas', P.ok && P.body.rules === 'chinese' && P.body.komi === 7.5, J(P));
P = f("anPosition(19, [], [], '(;GM[1])')");
check('posición: sin KM -> 6.5 en igualada', P.ok && P.body.komi === 6.5, J(P));
P = f("anPosition(19, __st, [], '(;GM[1])')");
check('posición: sin KM y con handicap -> 0.5', P.ok && P.body.komi === 0.5, J(P));
check('posición: no soportadas (13×13, piedras blancas, una sola piedra)',
  !f("anPosition(13, [], [], '')").ok && !f("anPosition(19, [{x:3,y:3,c:-1}], [], '')").ok && !f("anPosition(19, [{x:3,y:3,c:1}], [], '')").ok);
ctx.__wl = [0, 0.5, -7, 3.5, 4];   // ventaja de blancas antes de cada jugada (y tras la última)
ctx.__mm = [['B','D4'], ['W','Q16'], ['B','Q4'], ['W','C3']];
const M = f('anMistakes(__wl, __mm, 5)');
check('errores: el de blancas (pierde 7.5) y el de negras (pierde 10.5), no los pequeños',
  M.length === 2 && M[0].i === 2 && M[0].color === 'W' && M[0].loss === 7.5 && M[1].i === 3 && M[1].color === 'B' && M[1].loss === 10.5, J(M));
ctx.__wl2 = [0, -12];
check('errores: una jugada de negras que empeora a negras', f("anMistakes([0, 8], [['B','D4']], 5)")[0].loss === 8 && f("anMistakes(__wl2, [['B','D4']], 5)").length === 0);

ctx.__cl = [0, 0.5, -7, 3.5]; ctx.__cm = [['B','D4'], ['W','Q16'], ['B','Q4']];
check('texto gráfica: jugada de blancas que pierde 7.5, ventaja desde negras',
  f("anGraphCaption(__cl, __cm, 'B', 2)") === 'Jugada 2 · blancas: −7.5 (error) · Ventaja negras: +7', f("anGraphCaption(__cl, __cm, 'B', 2)"));
check('texto gráfica: error grave de negras visto desde blancas (tú)',
  f("anGraphCaption(__cl, __cm, 'W', 3)") === 'Jugada 3 · negras: −10.5 (error grave) · Ventaja tú: +3.5', f("anGraphCaption(__cl, __cm, 'W', 3)"));
check('texto gráfica: ganancia, inicio y fuera de la línea principal',
  f("anGraphCaption([0, -2], [['B','D4']], 'B', 1)") === 'Jugada 1 · negras: +2 · Ventaja negras: +2'
  && f("anGraphCaption(__cl, __cm, 'B', 0)") === 'Inicio · Ventaja negras: ±0' && f("anGraphCaption(__cl, __cm, 'B', null)") === 'Fuera de la línea principal');

// ── Ficha de la partida ──
const P1 = f(`anSgfRootProps('(;GM[1]FF[4]SZ[19]PB[Lee Sedol]BR[9p]PW[AlphaGo]KM[7.5]RE[W+R]DT[2016-03-09]EV[Google DeepMind Challenge]RO[1]C[comentario con \\\\] escapado]AB[dd][pp];B[qd];W[dc])')`);
check('ficha: propiedades del nodo raíz, sin las de las jugadas', P1.PB === 'Lee Sedol' && P1.BR === '9p' && P1.KM === '7.5' && P1.RE === 'W+R' && P1.B === undefined && P1.W === undefined, J(P1));
check('ficha: ] escapado dentro de un valor y valores múltiples', P1.C === 'comentario con ] escapado' && P1.AB === 'dd, pp', J(P1));
ctx.__p1 = P1;
const R1 = f('anGameInfoRows(__p1, 211)');
check('ficha: filas legibles en orden, solo con lo que hay', J(R1) === J([['Negras','Lee Sedol · 9p'],['Blancas','AlphaGo'],['Resultado','Blancas por abandono'],['Komi','7.5'],['Jugadas','211'],['Fecha','2016-03-09'],['Evento','Google DeepMind Challenge · 1']]), J(R1));
const RE = (re) => { ctx.__re = { RE: re }; return f('anGameInfoRows(__re, null)')[0][1]; };
check('ficha: resultados', RE('B+3.5') === 'Negras por 3.5' && RE('W+T') === 'Blancas por tiempo' && RE('0') === 'Empate' && RE('Void') === 'Void');
check('ficha: SGF vacío o sin raíz', J(f("anSgfRootProps('')")) === '{}' && J(f("anGameInfoRows({}, null)")) === '[]');

// ── Texto del análisis (modelo 1) ──
ctx.__d = { to_play: 'B', candidates: [{ move: 'S6', scoreLead: 14.9 }, { move: 'F2', scoreLead: 13.4 }], played: { move: 'P1', scoreLead: 0.6, loss: 14.3 } };
check('análisis: habla de la jugada vista, alternativas como diferencia y ventaja desde negras',
  f("anAnalysisText(__d, 83, 'B', false)") === 'Jugada 83 (negras): P1 · −14.3 respecto a la mejor\nMejor: ★ S6 · 2 F2 (−1.5)\nVentaja negras con la mejor: +14.9', f("anAnalysisText(__d, 83, 'B', false)"));
check('análisis: en mi partida con blancas, la ventaja es la mía (de signo contrario)',
  f("anAnalysisText(__d, 83, 'W', true)").endsWith('Tu ventaja con la mejor: −14.9'), f("anAnalysisText(__d, 83, 'W', true)"));
ctx.__d2 = { to_play: 'W', candidates: [{ move: 'Q4', scoreLead: -2 }], played: { move: 'Q4', scoreLead: -2, loss: 0 } };
check('análisis: buena jugada y una sola candidata', f("anAnalysisText(__d2, 84, 'B', false)") === 'Jugada 84 (blancas): Q4 · buena jugada\nMejor: ★ Q4\nVentaja negras con la mejor: +2', f("anAnalysisText(__d2, 84, 'B', false)"));
ctx.__d3 = { to_play: 'B', candidates: [{ move: 'Q16', scoreLead: 6.5 }], played: null };
check('análisis: inicio sin jugadas', f("anAnalysisText(__d3, null, 'B', false)").startsWith('Inicio · juegan negras\nMejor: ★ Q16'));

// ── AN3: gráfica a medio calcular ──
ctx.__wn = [0, 0.5, -7, null, null]; ctx.__mn = [['B','D4'], ['W','Q16'], ['B','Q4'], ['W','C3']];
check('gráfica parcial: errores solo donde hay los dos valores', J(f('anMistakes(__wn, __mn, 5)')) === J([{ i: 2, color: 'W', loss: 7.5 }]), J(f('anMistakes(__wn, __mn, 5)')));
check('gráfica parcial: texto de una jugada aún sin calcular', f("anGraphCaption(__wn, __mn, 'B', 3)") === 'Jugada 3 · calculando…' && f("anGraphCaption(__wn, __mn, 'B', 2)").startsWith('Jugada 2 · blancas: −7.5'));

// ── ST1: estado del servidor ──
const ST = { ok: true, time: '2026-11-15T12:00:00Z', uptime_s: 93784, schema_version: 7, disk: { total: 40e9, free: 18e9 }, mem: { total: 3.9e9, available: 2.5e9 },
  load: [0.4, 0.3, 0.2], cpus: 2, cache: { rows: 12345, bytes: 4300000 },
  ai: { available: true, engine_running: false, move_ms_avg: 1400, worker: { enabled: true, queue: 2, current: { label: '2026-11-14 · rank_20k', done: 120, total: 251 }, done_today: 5, last_error: null } } };
ctx.__st1 = ST;
let SS = f("srvStatusSummary(__st1, 120)");
check('estado: todo bien -> verde, con las cuatro líneas', SS.level === 'ok' && SS.warn.length === 0 && SS.lines.length === 4
  && SS.lines[0][1] === 'responde en 120 ms · BD v7 · en marcha 1 d 2 h' && SS.lines[1][1] === 'disponible · dormido · jugada media 1.4 s'
  && SS.lines[2][1] === 'activado · en cola 2 · analizando 2026-11-14 · rank_20k (120/251) · hoy 5', J(SS));
check('estado: sin respuesta -> rojo', f("srvStatusSummary(null, 0)").level === 'bad');
ctx.__st2 = JSON.parse(J(ST)); ctx.__st2.disk.free = 2e9; ctx.__st2.ai.worker.last_error = { msg: 'x: fallo', at: '2026-11-15T11:00:00Z' };
SS = f("srvStatusSummary(__st2, 90)");
check('estado: poco disco y error reciente -> ámbar con avisos', SS.level === 'warn' && SS.warn.includes('Poco disco libre') && SS.warn.includes('Error reciente en el análisis automático'), J(SS.warn));
ctx.__st3 = JSON.parse(J(ST)); ctx.__st3.ai = { available: false, engine_reason: 'ai_engines.py no cargado' };
SS = f("srvStatusSummary(__st3, 90)");
check('estado: KataGo no disponible -> ámbar (el sync sigue funcionando)', SS.level === 'warn' && SS.lines[1][1].startsWith('no disponible') && SS.lines.length === 3, J(SS));

console.log('\nRESULTADO AI:', fails.length ? `${fails.length} FALLOS: ${fails.join(' | ')}` : 'TODO OK');
process.exit(fails.length ? 1 : 0);
