// AR3b: funciones puras de js/archive.js (la página del archivo de partidas).
//     node tests/test_archive_page.js
const fs = require('fs'), path = require('path'), vm = require('vm');
let FAILS = 0, N = 0;
function check(name, cond, extra) { N++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (!cond && extra ? '  ' + extra : '')); if (!cond) FAILS++; }
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const ctx = { console, JSON, Math, Number, String, Object, Array, Set, AR_NO_INIT: true };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'js', 'archive.js'), 'utf8'), ctx, { filename: 'archive.js' });
const R = (code) => vm.runInContext(code, ctx);
const S = (o) => R(`Object.assign(arEmptyState(), ${JSON.stringify(o)})`);

// ── estado guardado ──
check('estado roto o de otra versión → vacío', eq(R('arSanitizeState("x")'), R('arEmptyState()')) && eq(R('arSanitizeState(null)'), R('arEmptyState()')));
const dirty = R(`arSanitizeState({ t: 'meijin', e: 3, s: 7, ph: 'Preliminary B', p1: { id: 5, name: 'Iyama Yuta' }, p2: { id: 'x' }, color: 'rojo', y1: '20x', y2: '2026', sgf: 'si', extra: 1 })`);
check('estado: se queda solo lo válido', eq(dirty, { t: 'meijin', e: 3, s: 7, ph: 'Preliminary B', p1: { id: 5, name: 'Iyama Yuta' }, color: 'any', p2: null, y1: '', y2: '2026', sgf: false }), JSON.stringify(dirty));
check('estado: sin jugador 1 no hay jugador 2 ni color', eq(R(`arSanitizeState({ p2: { id: 2, name: 'B' }, color: 'b' })`), R('arEmptyState()')));
check('estado: fase sin sección se descarta', R(`arSanitizeState({ e: 3, ph: '' }).ph`) === null);

// ── query ──
check('query: sin nada, todo el archivo paginado', R(`arQuery(arEmptyState(), 0)`) === '/archive/games?offset=0&limit=200');
check('query: torneo', R(`arQuery(${JSON.stringify(S({ t: 'meijin' }))}, 0)`) === '/archive/games?tournament=meijin&offset=0&limit=200');
check('query: la edición manda sobre el torneo', R(`arQuery(${JSON.stringify(S({ t: 'meijin', e: 3 }))}, 0)`) === '/archive/games?edition=3&offset=0&limit=200');
check('query: sección + tabla principal (phase vacío)', R(`arQuery(${JSON.stringify(S({ t: 'meijin', e: 3, s: 7, ph: '' }))}, 0)`) === '/archive/games?section=7&phase=&offset=0&limit=200');
check('query: fase con espacio codificada', R(`arQuery(${JSON.stringify(S({ t: 'meijin', e: 3, s: 7, ph: 'Preliminary B' }))}, 200)`) === '/archive/games?section=7&phase=Preliminary%20B&offset=200&limit=200');
check('query: jugador con color', R(`arQuery(${JSON.stringify(S({ p1: { id: 5, name: 'A' }, color: 'b' }))}, 0)`) === '/archive/games?player=5&color=b&offset=0&limit=200');
check('query: enfrentamientos (el color no se manda)', R(`arQuery(${JSON.stringify(S({ p1: { id: 5, name: 'A' }, p2: { id: 9, name: 'B' }, color: 'b' }))}, 0)`) === '/archive/games?player=5&player2=9&offset=0&limit=200');
check('query: años y solo con SGF; año incompleto se ignora', R(`arQuery(${JSON.stringify(S({ y1: '2020', y2: '20', sgf: true }))}, 0)`) === '/archive/games?year_from=2020&has_sgf=1&offset=0&limit=200');
check('query: slug de torneo codificado', R(`arQuery(${JSON.stringify(S({ t: 'a&b' }))}, 0)`).startsWith('/archive/games?tournament=a%26b&'));
check('hay filtros: no con solo selección del árbol; sí con jugador, años o SGF',
  !R(`arHasFilters(${JSON.stringify(S({ t: 'meijin', e: 3 }))})`) && R(`arHasFilters(${JSON.stringify(S({ y2: '2001' }))})`) && R(`arHasFilters(${JSON.stringify(S({ sgf: true }))})`) && !R(`arHasFilters(${JSON.stringify(S({ y1: '19' }))})`));

// ── árbol ──
const tree = {
  tournaments: [
    { slug: 'samsung-cup', name: 'Samsung Cup', local: '삼성화재배', country: 'international', games: 2407, sgf: 0, editions: [] },
    { slug: 'lanke-cup', name: 'Lanke Cup', local: null, country: 'other', games: 2, sgf: 0, editions: [] },
    { slug: 'meijin', name: 'Meijin', local: '名人戦', country: 'japan', games: 6, sgf: 1, editions: [
      { id: 3, slug: '52', label: '52nd', games: 6, sgf: 1, sections: [
        { id: 6, event: '52nd Meijin Title Match', phases: null, games: 1, sgf: 0 },
        { id: 7, event: '52nd Meijin', phases: [['Preliminary B', 2], ['Preliminary C', 1]], games: 5, sgf: 1 }] }] },
    { slug: 'kbs-cup', name: 'KBS Cup', local: 'KBS바둑왕전', country: 'korea', games: 1651, sgf: 0, editions: [] },
    { slug: 'honinbo', name: 'Honinbo', local: '本因坊戦', country: 'japan', games: 6190, sgf: 0, editions: [] },
    { slug: 'raro', name: 'Raro', country: 'marte', games: 1, sgf: 0, editions: [] }],
};
ctx.TREE = tree;
const groups = R('arGroupByCountry(TREE.tournaments)').map(([c, l, ts]) => [c, l, ts.map(t => t.slug)]);
check('por país en orden fijo (Japón, Corea, internacionales, otros) y país desconocido al final',
  eq(groups, [['japan', 'Japan', ['meijin', 'honinbo']], ['korea', 'Korea', ['kbs-cup']], ['international', 'International', ['samsung-cup']], ['other', 'Other', ['lanke-cup']], ['marte', 'marte', ['raro']]]), JSON.stringify(groups));
check('filtro de torneos por nombre, nombre local o slug, sin mayúsculas',
  R(`arMatchTournament(TREE.tournaments[2], 'mei')`) && R(`arMatchTournament(TREE.tournaments[2], '名人')`) && R(`arMatchTournament(TREE.tournaments[0], 'SAMSUNG')`) && !R(`arMatchTournament(TREE.tournaments[0], 'meijin')`) && R(`arMatchTournament(TREE.tournaments[0], '  ')`));
check('nombre corto de sección', R(`arSectionShort('52nd Meijin Title Match', { label: '52nd' }, { name: 'Meijin' })`) === 'Title Match' && R(`arSectionShort('52nd Meijin', { label: '52nd' }, { name: 'Meijin' })`) === '');
const ph = R('arPhaseRows(TREE.tournaments[2].editions[0].sections[1])');
check('fases: principal primero (5 − 3 = 2) y luego las de t', eq(ph, [{ ph: '', label: 'Main', n: 2 }, { ph: 'Preliminary B', label: 'Preliminary B', n: 2 }, { ph: 'Preliminary C', label: 'Preliminary C', n: 1 }]), JSON.stringify(ph));
check('fases: sección sin t no tiene filas; principal vacía no sale',
  eq(R('arPhaseRows(TREE.tournaments[2].editions[0].sections[0])'), []) && eq(R(`arPhaseRows({ games: 2, phases: [['Final', 2]] })`).map(r => r.ph), ['Final']));
check('abreviatura de fase', R(`arAbbrevPhase('Preliminary B')`) === 'Prel. B' && R(`arAbbrevPhase('')`) === '' && R(`arAbbrevPhase('Final')`) === 'Final');
check('miga: torneo › edición › fase con su recuento', eq(R(`arCrumb(TREE, ${JSON.stringify(S({ t: 'meijin', e: 3, s: 7, ph: 'Preliminary B' }))})`), { parts: ['Meijin', '52nd', 'Preliminary B'], total: 2 }));
check('miga: sección con nombre corto (Title Match) y la principal como Main',
  eq(R(`arCrumb(TREE, ${JSON.stringify(S({ t: 'meijin', e: 3, s: 6 }))})`), { parts: ['Meijin', '52nd', 'Title Match'], total: 1 }) &&
  eq(R(`arCrumb(TREE, ${JSON.stringify(S({ t: 'meijin', e: 3, s: 7, ph: '' }))})`), { parts: ['Meijin', '52nd', 'Main'], total: 2 }));
check('miga: sin selección, vacía; selección que ya no existe, vacía', eq(R(`arCrumb(TREE, arEmptyState())`), { parts: [], total: null }) && eq(R(`arCrumb(TREE, ${JSON.stringify(S({ t: 'nada' }))})`), { parts: [], total: null }));

// ── filas ──
const g = { id: 'ab'.repeat(16), date: '2026-09-17', black: 'Hane Naoki', white: 'Kōno Rin', result: 'B+R', result_text: 'Black wins by resignation', event_name: '52nd Meijin', phase: 'Preliminary B', tournament_name: 'Meijin', edition: '52nd', has_sgf: false };
ctx.G = g;
const inEd = R(`arRowParts(G, { global: false, phaseChosen: false })`);
check('fila en una edición: fecha, negras – blancas, resultado y fase abreviada', inEd.date === '2026-09-17' && inEd.players === 'Hane Naoki – Kōno Rin' && inEd.result === 'B+R' && inEd.extra === 'Prel. B', JSON.stringify(inEd));
check('fila con la fase ya elegida: no la repite', R(`arRowParts(G, { global: false, phaseChosen: true }).extra`) === '');
check('fila en búsqueda global: añade torneo y edición', R(`arRowParts(G, { global: true, phaseChosen: false }).extra`) === 'Meijin 52nd · Prel. B');
check('tooltip: evento, fase, resultado largo, id y aviso si no está descargada', ['52nd Meijin', 'Phase: Preliminary B', 'Black wins by resignation', g.id, 'Not downloaded yet'].every(x => inEd.title.includes(x)));
check('fila con datos que faltan', eq(R(`(({ date, players, result }) => [date, players, result])(arRowParts({}, { global: true, phaseChosen: false }))`), ['—', '? – ?', '']));
check('recuento: "12 of 85" con filtro; "85 games" sin filtro o sin total', R('arCountText(12, 85, true)') === '12 of 85' && R('arCountText(85, 85, false)') === '85 games' && R('arCountText(1, null, true)') === '1 game');

// ficha del torneo
ctx.TREE.tournaments[2].years = '1976-2026';
ctx.TREE.tournaments[2].history = ['The Meijin is one of the big three.', '  ', 7, 'Second paragraph.'];
ctx.TREE.tournaments[2].editions[0].from = '2025-09-01'; ctx.TREE.tournaments[2].editions[0].to = '2026-10-20';
const card = R(`arTournamentCard(TREE, ${JSON.stringify(S({ t: 'meijin' }))})`);
check('ficha: nombre, nombre local, años, partidas con SGF y ediciones', eq(card, { title: 'Meijin', local: '名人戦',
  facts: ['1976-2026', '6 games · 1 with SGF', '1 edition'], edition: null, history: ['The Meijin is one of the big three.', 'Second paragraph.'] }), JSON.stringify(card));
check('ficha: con edición elegida añade su línea con fechas', R(`arTournamentCard(TREE, ${JSON.stringify(S({ t: 'meijin', e: 3, s: 7 }))}).edition`) === '52nd: 6 games · 1 with SGF · 2025-09-01 – 2026-10-20');
const bare = R(`arTournamentCard(TREE, ${JSON.stringify(S({ t: 'samsung-cup' }))})`);
check('ficha: sin historia ni años; miles con separador', eq(bare.facts, ['2,407 games · 0 with SGF', '0 editions']) && eq(bare.history, []) && bare.local === '삼성화재배', JSON.stringify(bare));
check('ficha: sin torneo (o que ya no existe) no hay ficha', R('arTournamentCard(TREE, arEmptyState())') === null && R(`arTournamentCard(TREE, ${JSON.stringify(S({ t: 'nada' }))})`) === null);
check('ficha: nombre local igual al nombre no se repite', R(`arTournamentCard({ tournaments: [{ slug: 'x', name: 'X', local: 'X', games: 1, sgf: 0, editions: [] }] }, ${JSON.stringify(S({ t: 'x' }))}).local`) === '');

console.log(`\n${N - FAILS}/${N} PASS`);
process.exit(FAILS ? 1 : 0);
