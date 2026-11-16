#!/usr/bin/env node
/* test_clock.js — RL1: funciones puras del reloj de entrenamiento (tc*, en el bloque de
 * funciones puras de tsumevault.html que extract_ai.py extrae a ai_bundle.js). Uso:
 *     python extract_ai.py && node test_clock.js
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
const sys = (main, periods, period) => f(`tcNormalize({ type: 'byoyomi', main: ${main}, periods: ${periods}, period: ${period} })`);
const at = (s, st, e) => ctx.tcAt(s, st, e);

// Normalización (lo que se recuerda del panel)
check('sin reloj: null, basura o tipo desconocido -> none',
  [null, undefined, {}, { type: 'canadian' }, 'x'].every(v => ctx.tcNormalize(v).type === 'none'));
check('byoyomi: valores tal cual', J(sys(600, 5, 30)) === J({ type: 'byoyomi', main: 600, periods: 5, period: 30 }));
check('byoyomi: tiempo principal 0 permitido', sys(0, 3, 10).main === 0);
check('byoyomi: recorta a los límites y redondea',
  J(f("tcNormalize({ type: 'byoyomi', main: -5, periods: 99, period: 0 })")) === J({ type: 'byoyomi', main: 0, periods: 30, period: 1 })
  && sys(12.6, 2.4, 29.5).main === 13 && sys(12.6, 2.4, 29.5).periods === 2);
check('byoyomi: no numéricos -> valores por defecto',
  J(f("tcNormalize({ type: 'byoyomi', main: 'x', periods: null, period: undefined })")) === J({ type: 'byoyomi', main: 0, periods: 5, period: 30 }));
check('inicio: none -> null; byoyomi -> principal en ms y periodos llenos',
  ctx.tcStart({ type: 'none' }) === null && J(ctx.tcStart(sys(300, 3, 30))) === J({ mainMs: 300000, periods: 3, overMs: 0, expired: false }));

// tcAt: consumo dentro de un turno
const S = sys(60, 3, 10), st0 = ctx.tcStart(S);
let a = at(S, st0, 0);
check('tiempo principal: al empezar', a.phase === 'main' && a.mainMs === 60000 && a.periods === 3);
a = at(S, st0, 59999);
check('tiempo principal: 1 ms antes de acabarse', a.phase === 'main' && a.mainMs === 1);
a = at(S, st0, 60000);
check('fin del principal: byoyomi con 3 periodos llenos', a.phase === 'byo' && a.periods === 3 && a.periodMs === 10000, J(a));
a = at(S, st0, 64000);
check('byoyomi: 4 s dentro del primer periodo', a.phase === 'byo' && a.periods === 3 && a.periodMs === 6000);
a = at(S, st0, 70000);
check('byoyomi: agotar un periodo exacto consume uno y el siguiente empieza lleno', a.phase === 'byo' && a.periods === 2 && a.periodMs === 10000, J(a));
a = at(S, st0, 89999);
check('byoyomi: último periodo, 1 ms', a.phase === 'byo' && a.periods === 1 && a.periodMs === 1, J(a));
a = at(S, st0, 90000);
check('fin del último periodo: fuera de tiempo, 0 ms de exceso', a.phase === 'over' && a.overMs === 0 && a.periods === 0, J(a));
a = at(S, st0, 102500);
check('fuera de tiempo: el exceso sigue contando', a.phase === 'over' && a.overMs === 12500);
const S0 = sys(0, 2, 5), z = ctx.tcStart(S0);
a = at(S0, z, 0);
check('principal 0: desde la primera jugada en byoyomi', a.phase === 'byo' && a.periods === 2 && a.periodMs === 5000, J(a));

// tcPress: estado del turno siguiente
let st = ctx.tcPress(S, st0, 20000);
check('pulsar en el principal: descuenta lo pensado', J(st) === J({ mainMs: 40000, periods: 3, overMs: 0, expired: false }));
st = ctx.tcPress(S, st0, 64000);
check('pulsar dentro de un periodo: no lo consume (el siguiente turno lo tiene lleno)', st.mainMs === 0 && st.periods === 3 && !st.expired);
a = at(S, st, 0);
check('turno siguiente en byoyomi: periodo lleno', a.phase === 'byo' && a.periodMs === 10000 && a.periods === 3);
st = ctx.tcPress(S, st0, 75000);
check('pulsar tras agotar un periodo: quedan 2', st.periods === 2 && st.mainMs === 0);
st = ctx.tcPress(S, st0, 95000);
check('pulsar fuera de tiempo: expirado con el exceso', J(st) === J({ mainMs: 0, periods: 0, overMs: 5000, expired: true }));
a = at(S, st, 3000);
check('expirado: el turno siguiente sigue en negativo acumulando', a.phase === 'over' && a.overMs === 8000);
st = ctx.tcPress(S, st, 3000);
check('expirado: no vuelve atrás', st.expired && st.overMs === 8000);
// Secuencia de turnos: lo pensado se acumula solo en el principal
let s2 = ctx.tcStart(S);
for (const e of [15000, 15000, 15000]) s2 = ctx.tcPress(S, s2, e);
check('tres turnos de 15 s: quedan 15 s de principal', s2.mainMs === 15000 && s2.periods === 3);
s2 = ctx.tcPress(S, s2, 20000);
check('turno que cruza a byoyomi (15 s principal + 5 s): periodos intactos', s2.mainMs === 0 && s2.periods === 3);
s2 = ctx.tcPress(S, s2, 25000);
check('turno de 25 s en byoyomi 3×10: consume 2, queda 1', s2.periods === 1 && !s2.expired);

// Avisos
const ev = (s, st, e0, e1) => ctx.tcEvents(s, st, e0, e1).map(x => x.kind + (x.n != null ? x.n : '') + (x.left != null ? ':' + x.left : '') + (x.periods != null ? '/' + x.periods : '')).join(' ');
check('sin reloj o expirado: sin avisos', ctx.tcEventTimes({ type: 'none' }, null).length === 0 && ctx.tcEventTimes(S, { mainMs: 0, periods: 0, overMs: 1, expired: true }).length === 0);
check('dentro del principal: nada', ev(S, st0, 0, 59999) === '');
check('entrada en byoyomi al acabar el principal', ev(S, st0, 59000, 60000) === 'byo_start/3');
check('cuenta atrás 9..1 del primer periodo (10 s) y periodo consumido',
  ev(S, st0, 60000, 70000) === 'count9 count8 count7 count6 count5 count4 count3 count2 count1 period_used:2', ev(S, st0, 60000, 70000));
check('el último periodo termina con timeout, sin period_used', ev(S, st0, 88999, 90000) === 'count1 timeout');
check('después del timeout no hay más avisos', ev(S, st0, 90000, 200000) === '');
check('instantes: cuenta 9 a 1 s del inicio del periodo de 10 s', ctx.tcEventTimes(S, st0).find(x => x.kind === 'count' && x.n === 9).t === 61000);
check('intervalo (e0, e1]: abierto por la izquierda', ev(S, st0, 60000, 60000) === '' && ev(S, st0, 60999, 61000) === 'count9');
const S5 = sys(0, 3, 5);
check('periodo de 5 s: cuenta desde 4; principal 0 sin aviso de entrada',
  ev(S5, ctx.tcStart(S5), -1, 5000) === 'count4 count3 count2 count1 period_used:2', ev(S5, ctx.tcStart(S5), -1, 5000));
const S30 = sys(0, 1, 30);
check('periodo de 30 s: la cuenta empieza a los 21 s', ctx.tcEventTimes(S30, ctx.tcStart(S30))[0].t === 21000);
const S1 = sys(10, 1, 1);
check('periodo de 1 s: sin cuenta, solo entrada y timeout', ev(S1, ctx.tcStart(S1), 0, 99999) === 'byo_start/1 timeout');
check('turno que empieza ya en byoyomi: sin byo_start', !ev(S, ctx.tcPress(S, st0, 65000), 0, 99999).includes('byo_start'));
check('nº de avisos con 30 periodos (límite): acotado', ctx.tcEventTimes(sys(0, 30, 600), ctx.tcStart(sys(0, 30, 600))).length === 30 * 10);

// Etiquetas
check('etiqueta principal: redondea hacia arriba (4:32)', ctx.tcLabel(at(S, { mainMs: 272000, periods: 3 }, 0.5)) === '4:32' && ctx.tcLabel(at(S, { mainMs: 271001, periods: 3 }, 0)) === '4:32');
check('etiqueta con horas', ctx.tcLabel(at(sys(5400, 1, 30), { mainMs: 5400000, periods: 1 }, 0)) === '1:30:00');
check('etiqueta byoyomi: "3 × 0:06"', ctx.tcLabel(at(S, st0, 64000)) === '3 × 0:06');
check('etiqueta fuera de tiempo: negativo hacia abajo', ctx.tcLabel(at(S, st0, 102500)) === '−0:12');
check('OT SGF', ctx.tcSgfOT(sys(600, 5, 30)) === '5x30 byo-yomi');

// SGF
check('propiedades de jugada sin reloj: solo TT', ctx.tcMoveProps('B', { t: 12345, a: null }) === 'TT[12.3]');
check('propiedades en principal: BL', ctx.tcMoveProps('B', { t: 2000, a: at(S, st0, 2000) }) === 'TT[2]BL[58]');
check('propiedades en byoyomi: WL del periodo y OW', ctx.tcMoveProps('W', { t: 64000, a: at(S, st0, 64000) }) === 'TT[64]WL[6]OW[3]');
check('propiedades fuera de tiempo: OB[0]', ctx.tcMoveProps('B', { t: 95000, a: at(S, st0, 95000) }) === 'TT[95]BL[0]OB[0]');

const g = f("aiNewGame({ level: 'katago:rank_15k', handicap: 0, myColor: 'B', rules: 'japanese' })");
g.moves = [['B', 'D4'], ['W', 'Q16'], ['B', 'pass'], ['W', 'Q4'], ['B', 'C3']];
const sgfPlain = ctx.aiBuildSgf(g, { endType: 'score', score: 1.5, date: '2026-11-15', myName: 'J', aiName: 'K' });
check('SGF sin tlog ni tc: igual que antes (sin TM/OT/TT)', !/TM\[|OT\[|TT\[/.test(sgfPlain) && sgfPlain.includes(';B[dp];W[pd];B[];W[pp];B[cq])'), sgfPlain);
g.tc = sys(60, 3, 10);
g.tlog = [{ t: 20000, a: at(g.tc, st0, 20000) }, { t: 5000, a: null }, { t: 50000, a: at(g.tc, ctx.tcPress(g.tc, st0, 20000), 50000) }, null, { t: 30000, a: at(g.tc, { mainMs: 0, periods: 1, overMs: 0, expired: false }, 30000) }];
const sgf = ctx.aiBuildSgf(g, { endType: 'score', score: 1.5, date: '2026-11-15', myName: 'J', aiName: 'K' });
check('SGF con reloj: TM/OT en la raíz', sgf.includes('TM[60]OT[3x10 byo-yomi]'), sgf);
check('SGF: tiempos solo en mis jugadas (la de la IA no lleva aunque haya registro)',
  sgf.includes(';B[dp]TT[20]BL[40];W[pd];B[]TT[50]BL[10]OB[2];W[pp];B[cq]TT[30]BL[0]OB[0])'), sgf);
check('SGF: tlog más corto que las jugadas no rompe', (() => { const h = Object.assign({}, g, { tlog: [g.tlog[0]] }); return ctx.aiBuildSgf(h, { endType: 'score', score: 1, date: 'd', myName: 'a', aiName: 'b' }).endsWith(';B[cq])'); })());

// Resumen para el histórico
const sm = ctx.tcSgfSummary(sgf, 'B');
check('resumen: media de mis jugadas (20+50+30)/3', sm.avgMs === 33333 && sm.timed === 3, J(sm));
check('resumen: entré en byoyomi en la jugada 3 y me pasé en la 5', sm.byoMove === 3 && sm.timeoutMove === 5 && sm.clock && sm.ot === '3x10 byo-yomi', J(sm));
const sp = ctx.tcSgfSummary(sgfPlain, 'B');
check('resumen de partida antigua: sin datos', sp.avgMs === null && sp.byoMove === null && sp.timeoutMove === null && !sp.clock && sp.ot === null, J(sp));
check('resumen desde el otro color: nada mío', ctx.tcSgfSummary(sgf, 'W').avgMs === null);
check('resumen: vacío o basura', ctx.tcSgfSummary('', 'B').avgMs === null && ctx.tcSgfSummary(null, 'B').timed === 0);
const hc = f("aiNewGame({ level: 'x', handicap: 3, holder: 'ai', rules: 'japanese' })");
hc.moves = [['W', 'C3'], ['B', 'R3']]; hc.tlog = [{ t: 7000, a: null }];
const shc = ctx.tcSgfSummary(ctx.aiBuildSgf(hc, { endType: 'score', score: 1, date: 'd', myName: 'a', aiName: 'b' }), 'W');
check('resumen con handicap (AB en la raíz no cuenta como jugada) y sin reloj', shc.avgMs === 7000 && !shc.clock && shc.byoMove === null, J(shc));
check('resumen: no confunde OB de otra jugada ni BL[0] en principal con timeout',
  ctx.tcSgfSummary('(;GM[1];B[aa]TT[1]BL[0];W[bb]OW[0];B[cc]TT[3]BL[5]OB[1])', 'B').timeoutMove === null
  && ctx.tcSgfSummary('(;GM[1];B[aa]TT[1]BL[0];W[bb]OW[0];B[cc]TT[3]BL[5]OB[1])', 'B').byoMove === 3);

// RL4: histórico
const ht = (sm) => ctx.tcHistoryText(sm);
check('histórico: partida antigua sin tiempos -> nada', ht(ctx.tcSgfSummary(sgfPlain, 'B')) === null && ht(null) === null);
const h1 = ht(ctx.tcSgfSummary(sgf, 'B'));
check('histórico corto: media, byoyomi y ⏰', h1.short === '⏱ 33 s/jug · byo 3 · ⏰ 5', h1.short);
check('histórico largo: reloj y explicación', h1.long === 'Media pensada por jugada: 33 s (3 jugadas) · reloj 1 min + 3 × 10 s · entraste en byoyomi en la jugada 3 · se te acabó el tiempo en la jugada 5', h1.long);
check('histórico sin reloj: solo la media (con decimal si < 10 s)', ht(shc).short === '⏱ 7.0 s/jug' && !ht(shc).long.includes('reloj'), J(ht(shc)));
check('histórico: media de minutos', ht({ avgMs: 95000, timed: 4, byoMove: null, timeoutMove: null, ot: null }).short === '⏱ 1:35/jug');
check('histórico: principal en segundos y OT desconocido tal cual',
  ht({ avgMs: 5000, timed: 1, ot: '5x30 byo-yomi', tm: 90, byoMove: null, timeoutMove: null }).long.includes('reloj 90 s + 5 × 30 s')
  && ht({ avgMs: 5000, timed: 1, ot: '25/300 Canadian', tm: 600, byoMove: null, timeoutMove: null }).long.includes('reloj 25/300 Canadian'));
check('resumen: lee TM', ctx.tcSgfSummary(sgf, 'B').tm === 60 && ctx.tcSgfSummary(sgfPlain, 'B').tm === null);

// RL3: avisos
const cue = (ev) => ctx.tcEventCue(ev);
check('aviso entrada en byoyomi', J(cue({ kind: 'byo_start', periods: 5 })) === J({ key: 'byoyomi', text: 'Byoyomi', vib: [300] }));
check('entrada con un solo periodo: último periodo', cue({ kind: 'byo_start', periods: 1 }).key === 'ultimo_periodo' && cue({ kind: 'byo_start', periods: 1 }).text.includes('Último'));
check('cuenta atrás en palabras (nueve … uno)', cue({ kind: 'count', n: 9 }).text === 'nueve' && cue({ kind: 'count', n: 1 }).text === 'uno' && cue({ kind: 'count', n: 3 }).key === '3');
check('periodo consumido: "Quedan 3"', J(cue({ kind: 'period_used', left: 3 })) === J({ key: 'quedan_3', text: 'Quedan 3', vib: [400] }));
check('periodo consumido con uno restante: "Último periodo"', cue({ kind: 'period_used', left: 1 }).key === 'ultimo_periodo');
check('fin del último periodo: "Fuera de tiempo"', cue({ kind: 'timeout' }).key === 'fuera_de_tiempo');
check('aviso desconocido: null', cue({ kind: 'x' }) === null);
check('todos los avisos posibles tienen texto y vibración',
  ctx.tcEventTimes(sys(5, 4, 10), ctx.tcStart(sys(5, 4, 10))).every(ev => { const c = cue(ev); return c && c.text && c.vib.length; }));
check('grabaciones a precargar: 3 fijas + cuenta + quedan_2..periodos-1',
  J(ctx.tcCueKeys(sys(0, 4, 5))) === J(['byoyomi', 'ultimo_periodo', 'fuera_de_tiempo', '1', '2', '3', '4', 'quedan_2', 'quedan_3']));
check('grabaciones: sin reloj ninguna', ctx.tcCueKeys({ type: 'none' }).length === 0);
check('grabaciones: cubren todos los avisos de la partida', (() => {
  const S = sys(5, 4, 10), keys = new Set(ctx.tcCueKeys(S));
  return ctx.tcEventTimes(S, ctx.tcStart(S)).every(ev => keys.has(cue(ev).key));
})());

console.log(fails.length ? `\n${fails.length} FAIL` : '\nTODO OK');
process.exit(fails.length ? 1 : 0);
