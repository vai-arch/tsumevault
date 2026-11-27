// TsumeVault — archivo de partidas (AR3b, docs/WORKPLAN_ARCHIVO.md). Lo usa archive.html, después de
// board_core.js, ai_pure.js y game_viewer.js (tablero, visor y análisis compartidos con tsumevault.html).
//
// Árbol torneo → edición → sección → fase (agrupado por país) + filtros por todo el archivo (jugador con
// alias y color, enfrentamientos, años, solo con SGF) + lista. Las partidas sin SGF salen en gris y no hacen
// nada al tocarlas (Victor las baja con los games_pendientes.txt). Datos: /archive/* del servidor, con el
// mismo token que la app; el árbol y las listas abiertas quedan en caché para usarlos sin conexión.

// ══ Funciones puras (tests/test_archive_page.js) ══
const AR_STATE_KEY = 'archive_state_v1';
const AR_CACHE = 'tsumevault-archive-data';
const AR_PAGE = 200;
const AR_COUNTRIES = [['japan', 'Japan'], ['korea', 'Korea'], ['china', 'China'], ['taiwan', 'Taiwan'], ['international', 'International'], ['other', 'Other']];

function arEmptyState() {
  return { t: null, e: null, s: null, ph: null, p1: null, color: 'any', p2: null, y1: '', y2: '', sgf: false };
}

// el estado guardado puede venir de otra versión o estar roto: solo se acepta lo que tiene la forma esperada
function arSanitizeState(o) {
  const s = arEmptyState();
  if (!o || typeof o !== 'object') return s;
  if (typeof o.t === 'string') s.t = o.t;
  if (Number.isInteger(o.e)) s.e = o.e;
  if (Number.isInteger(o.s)) s.s = o.s;
  if (typeof o.ph === 'string' && s.s !== null) s.ph = o.ph;
  for (const k of ['p1', 'p2']) if (o[k] && Number.isInteger(o[k].id) && typeof o[k].name === 'string') s[k] = { id: o[k].id, name: o[k].name };
  if (['any', 'b', 'w'].includes(o.color)) s.color = o.color;
  for (const k of ['y1', 'y2']) if (typeof o[k] === 'string' && /^\d{0,4}$/.test(o[k])) s[k] = o[k];
  s.sgf = o.sgf === true;
  if (!s.p1) { s.p2 = null; s.color = 'any'; }
  return s;
}

// hay algún filtro aparte de la selección del árbol
function arHasFilters(st) {
  return !!(st.p1 || st.p2 || /^\d{4}$/.test(st.y1) || /^\d{4}$/.test(st.y2) || st.sgf);
}

function arQuery(st, offset, limit) {
  const q = [];
  if (st.s !== null) q.push('section=' + st.s);
  else if (st.e !== null) q.push('edition=' + st.e);
  else if (st.t) q.push('tournament=' + encodeURIComponent(st.t));
  if (st.s !== null && st.ph !== null) q.push('phase=' + encodeURIComponent(st.ph));
  if (st.p1) {
    q.push('player=' + st.p1.id);
    if (st.p2) q.push('player2=' + st.p2.id);
    else if (st.color !== 'any') q.push('color=' + st.color);
  }
  if (/^\d{4}$/.test(st.y1)) q.push('year_from=' + st.y1);
  if (/^\d{4}$/.test(st.y2)) q.push('year_to=' + st.y2);
  if (st.sgf) q.push('has_sgf=1');
  q.push('offset=' + (offset || 0), 'limit=' + (limit || AR_PAGE));
  return '/archive/games?' + q.join('&');
}

// [[país, etiqueta, [torneos]]] en el orden de AR_COUNTRIES; dentro, el orden del servidor (nº de partidas)
function arGroupByCountry(tournaments) {
  const by = {};
  for (const t of tournaments || []) (by[t.country] = by[t.country] || []).push(t);
  const out = AR_COUNTRIES.filter(([c]) => by[c]).map(([c, label]) => [c, label, by[c]]);
  for (const c of Object.keys(by)) if (!AR_COUNTRIES.some(([k]) => k === c)) out.push([c, c, by[c]]);
  return out;
}

function arMatchTournament(t, text) {
  const q = (text || '').trim().toLowerCase();
  if (!q) return true;
  return [t.name, t.local, t.slug].some(x => x && String(x).toLowerCase().includes(q));
}

// nombre corto de una sección dentro de su edición: "52nd Meijin Title Match" → "Title Match"; "52nd Meijin" → ""
function arSectionShort(event, edition, tournament) {
  let s = ' ' + (event || '') + ' ';
  for (const w of [edition && edition.label, tournament && tournament.name]) if (w) s = s.split(' ' + w + ' ').join(' ');
  return s.trim();
}

// fases de una sección como filas del árbol: la tabla principal ('') y después las de t, con su recuento
function arPhaseRows(section) {
  if (!section.phases || !section.phases.length) return [];
  const named = section.phases.reduce((a, [, n]) => a + Number(n), 0);
  const rows = [{ ph: '', label: 'Main', n: Math.max(0, section.games - named) }];
  for (const [name, n] of section.phases) rows.push({ ph: name, label: name, n: Number(n) });
  return rows.filter(r => r.n > 0);
}

function arAbbrevPhase(p) {
  return (p || '').replace(/^Preliminary\b/, 'Prel.').replace(/^Qualifying\b/, 'Qual.').replace(/^Round\b/, 'R.');
}

function arFind(tree, st) {
  const t = st.t ? (tree.tournaments || []).find(x => x.slug === st.t) : null;
  const e = t && st.e !== null ? t.editions.find(x => x.id === st.e) : null;
  const s = e && st.s !== null ? e.sections.find(x => x.id === st.s) : null;
  return { t, e, s };
}

// "Meijin › 52nd › Preliminary B" y cuántas partidas tiene la selección (los recuentos del árbol)
function arCrumb(tree, st) {
  const { t, e, s } = arFind(tree, st);
  const parts = [];
  let total = null;
  if (t) { parts.push(t.name); total = t.games; }
  if (e) { parts.push(e.label || e.slug); total = e.games; }
  if (s) {
    const short = arSectionShort(s.event, e, t);
    if (short) parts.push(short);
    total = s.games;
    if (st.ph !== null) {
      const r = arPhaseRows(s).find(x => x.ph === st.ph);
      parts.push(st.ph === '' ? 'Main' : st.ph);
      total = r ? r.n : null;
    }
  }
  return { parts, total };
}

// ficha del torneo (datos de kifumaster): null si no hay torneo elegido; con edición elegida añade su línea
function arTournamentCard(tree, st) {
  const { t, e } = arFind(tree, st);
  if (!t) return null;
  const fmt = n => Number(n || 0).toLocaleString('en-US');
  const games = n => `${fmt(n)} game${n === 1 ? '' : 's'}`;
  const nEd = (t.editions || []).length;
  const facts = [t.years || '', `${games(t.games)} · ${fmt(t.sgf)} with SGF`, `${nEd} edition${nEd === 1 ? '' : 's'}`].filter(Boolean);
  let edition = null;
  if (e) {
    const span = [e.from, e.to].filter(Boolean);
    const dates = span.length === 2 && span[0] !== span[1] ? `${span[0]} – ${span[1]}` : (span[0] || '');
    edition = [`${e.label || e.slug}: ${games(e.games)} · ${fmt(e.sgf)} with SGF`, dates].filter(Boolean).join(' · ');
  }
  const history = (Array.isArray(t.history) ? t.history : []).filter(x => typeof x === 'string' && x.trim());
  return { title: t.name, local: t.local && t.local !== t.name ? t.local : '', facts, edition, history };
}

// texto de una fila de la lista; global = búsqueda por todo el archivo (se añade torneo y edición)
function arRowParts(g, ctx) {
  const extra = [];
  if (ctx.global && g.tournament_name) extra.push(`${g.tournament_name} ${g.edition || ''}`.trim());
  if (!ctx.phaseChosen && g.phase) extra.push(arAbbrevPhase(g.phase));
  const title = [g.event_name, g.phase ? 'Phase: ' + g.phase : '', g.result_text || '', g.id, g.has_sgf ? '' : 'Not downloaded yet'].filter(Boolean).join('\n');
  return { date: g.date || '—', players: `${g.black || '?'} – ${g.white || '?'}`, result: g.result || '', extra: extra.join(' · '), title };
}

function arCountText(shown, total, filtered) {
  if (total === null || total === undefined || !filtered) return `${shown} game${shown === 1 ? '' : 's'}`;
  return `${shown} of ${total}`;
}

// ══ Página ══
let arTree = null, arState = arEmptyState(), arOpen = {}, arGames = [], arTotal = 0, arSeq = 0, arSelected = null, arInfoVisible = false;

function arLoadState() {
  try { arState = arSanitizeState(JSON.parse(lsGet(AR_STATE_KEY) || 'null')); } catch (e) { arState = arEmptyState(); }
  try { arOpen = JSON.parse(lsGet('archive_open_v1') || '{}') || {}; } catch (e) { arOpen = {}; }
}
function arSaveState() {
  lsSet(AR_STATE_KEY, JSON.stringify(arState));
  lsSet('archive_open_v1', JSON.stringify(arOpen));
}

// red primero; si falla, la copia en caché (Cache API). Devuelve {data, offline} o lanza el error
async function arFetchJson(path) {
  let cache = null;
  try { cache = await caches.open(AR_CACHE); } catch (e) { cache = null; }
  try {
    const r = await syncFetch(path, { signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined });
    if (r.status === 401) throw Object.assign(new Error('token'), { code: 401 });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    if (cache) { try { await cache.put(path, r.clone()); } catch (e) { /* sin sitio: da igual */ } }
    return { data: await r.json(), offline: false };
  } catch (err) {
    if (err.code === 401) throw err;
    const hit = cache ? await cache.match(path) : null;
    if (hit) return { data: await hit.json(), offline: true };
    throw err;
  }
}

function arEl(tag, cls, text) {
  const d = document.createElement(tag);
  if (cls) d.className = cls;
  if (text !== undefined) d.textContent = text;
  return d;
}

function arCount(n, sgf) {
  const c = arEl('span', 'ct');
  c.textContent = n + (sgf ? ' · ' : '');
  if (sgf) { const b = arEl('b', '', String(sgf)); c.appendChild(b); }
  c.title = `${n} games${sgf ? `, ${sgf} with SGF` : ''}`;
  return c;
}

function arRenderTree() {
  const box = document.getElementById('tree');
  box.innerHTML = '';
  if (!arTree) { box.appendChild(arEl('div', 'msg', 'Loading…')); return; }
  const text = document.getElementById('tree-filter').value;
  let any = false;
  for (const [, label, list] of arGroupByCountry(arTree.tournaments)) {
    const shown = list.filter(t => arMatchTournament(t, text));
    if (!shown.length) continue;
    any = true;
    box.appendChild(arEl('div', 'tr-country', label));
    for (const t of shown) {
      const row = arEl('div', 'tr-row' + (arState.t === t.slug && arState.e === null ? ' sel' : ''));
      row.appendChild(arEl('span', 'nm', (arOpen[t.slug] ? '▾ ' : '▸ ') + t.name));
      if (t.local) row.appendChild(arEl('span', 'lc', t.local));
      row.appendChild(arCount(t.games, t.sgf));
      row.title = `${t.name}${t.local ? ' · ' + t.local : ''}${t.years ? ' · ' + t.years : ''}`;
      row.onclick = () => { arOpen[t.slug] = !arOpen[t.slug] || arState.t !== t.slug; arSelect({ t: t.slug, e: null, s: null, ph: null }); };
      box.appendChild(row);
      if (!arOpen[t.slug]) continue;
      for (const e of t.editions) {
        const er = arEl('div', 'tr-row tr-l1' + (arState.e === e.id && arState.s === null ? ' sel' : ''));
        er.appendChild(arEl('span', 'nm', e.label || e.slug));
        if (e.from) er.appendChild(arEl('span', 'lc', (e.from || '').slice(0, 4) + (e.to && e.to.slice(0, 4) !== e.from.slice(0, 4) ? '–' + e.to.slice(0, 4) : '')));
        er.appendChild(arCount(e.games, e.sgf));
        er.onclick = () => arSelect({ t: t.slug, e: e.id, s: null, ph: null });
        box.appendChild(er);
        if (arState.e !== e.id) continue;
        const many = e.sections.length > 1;
        for (const s of e.sections) {
          const phases = arPhaseRows(s);
          if (many) {
            const sr = arEl('div', 'tr-row tr-l2' + (arState.s === s.id && arState.ph === null ? ' sel' : ''));
            sr.appendChild(arEl('span', 'nm', arSectionShort(s.event, e, t) || s.event));   // la principal, con su nombre de evento: "Main" es la fase
            sr.appendChild(arCount(s.games, s.sgf));
            sr.title = s.event;
            sr.onclick = () => arSelect({ t: t.slug, e: e.id, s: s.id, ph: null });
            box.appendChild(sr);
          }
          for (const p of phases) {
            const pr = arEl('div', 'tr-row ' + (many ? 'tr-l3' : 'tr-l2') + (arState.s === s.id && arState.ph === p.ph ? ' sel' : ''));
            pr.appendChild(arEl('span', 'nm', p.label));
            pr.appendChild(arCount(p.n));
            pr.title = `${s.event} · ${p.label}`;
            pr.onclick = () => arSelect({ t: t.slug, e: e.id, s: s.id, ph: p.ph });
            box.appendChild(pr);
          }
        }
      }
    }
  }
  if (!any) box.appendChild(arEl('div', 'msg', 'No tournament matches'));
}

function arSelect(sel) {
  Object.assign(arState, sel);
  arSaveState();
  arRenderTree();
  arReloadList();
  if (!gmActive || arInfoVisible) arShowInfo(false);   // sin partida abierta, la ficha ocupa el sitio del tablero
}

// muestra la ficha del torneo elegido en #main (en móvil, jump=true pasa a esa pantalla); sin torneo, la quita
function arShowInfo(jump) {
  const card = arTree ? arTournamentCard(arTree, arState) : null;
  if (!card) { arHideInfo(); return false; }
  const box = document.getElementById('t-info');
  box.innerHTML = '';
  if (gmActive) {
    const back = arEl('button', 'ctrl-btn back', '← Back to the game');
    back.onclick = () => arHideInfo();
    box.appendChild(back);
  }
  box.appendChild(arEl('h2', '', card.title));
  if (card.local) box.appendChild(arEl('div', 'loc', card.local));
  box.appendChild(arEl('div', 'facts', card.facts.join(' · ')));
  if (card.edition) box.appendChild(arEl('div', 'facts ed', card.edition));
  if (card.history.length) for (const para of card.history) box.appendChild(arEl('p', '', para));
  else box.appendChild(arEl('p', 'none', 'No description on kifumaster.'));
  if (typeof gmStopTimer === 'function') gmStopTimer();
  for (const id of ['welcome', 'board-wrap', 'gm-controls', 'comment-box']) document.getElementById(id).style.display = 'none';
  box.style.display = 'block';
  box.scrollTop = 0;
  arInfoVisible = true;
  if (jump) switchToBoard();
  return true;
}

// quita la ficha: vuelve la partida abierta o, si no hay, el "Select a game"
function arHideInfo() {
  document.getElementById('t-info').style.display = 'none';
  const was = arInfoVisible;
  arInfoVisible = false;
  if (gmActive) {
    if (was) {
      document.getElementById('gm-controls').style.display = 'flex';
      document.getElementById('comment-box').style.display = 'block';
      initBoard(boardSize); gmRenderCurrentNode();   // vuelve a mostrar #board-wrap con el tamaño actual
    }
  } else document.getElementById('welcome').style.display = '';
}

function arRenderCrumb() {
  const box = document.getElementById('crumb');
  box.innerHTML = '';
  const { parts, total } = arTree ? arCrumb(arTree, arState) : { parts: [], total: null };
  if (parts.length) {
    box.appendChild(arEl('span', '', parts.join(' › ')));
    const x = arEl('span', 'x', '✕');
    x.title = 'Search the whole archive';
    x.onclick = () => arSelect({ t: null, e: null, s: null, ph: null });
    const i = arEl('span', 'i', 'ⓘ');
    i.title = 'About this tournament';
    i.onclick = () => arShowInfo(true);
    box.appendChild(i);
    box.appendChild(x);
  } else box.appendChild(arEl('span', '', 'Whole archive'));
  const n = arEl('span', 'n', arCountText(arTotal, total, arHasFilters(arState)));
  box.appendChild(n);
}

function arRenderList(append) {
  const box = document.getElementById('list');
  if (!append) box.innerHTML = '';
  const old = document.getElementById('more');
  if (old) old.remove();
  const ctx = { global: !arState.t, phaseChosen: arState.ph !== null };
  for (const g of arGames.slice(append ? box.querySelectorAll('.g-row').length : 0)) {
    const p = arRowParts(g, ctx);
    const row = arEl('div', 'g-row ' + (g.has_sgf ? 'has' : 'no') + (arSelected === g.id ? ' sel' : ''));
    row.dataset.id = g.id;
    row.appendChild(arEl('span', 'd', p.date));
    row.appendChild(arEl('span', 'p', p.players));
    row.appendChild(arEl('span', 'r', p.result));
    if (p.extra) row.appendChild(arEl('span', 'x', p.extra));
    row.title = p.title;
    if (g.has_sgf) row.onclick = () => arOpenGame(g, row);
    box.appendChild(row);
  }
  if (!arGames.length) box.appendChild(arEl('div', 'msg', 'No games'));
  if (arGames.length < arTotal) {
    const m = arEl('button', 'ctrl-btn', `More (${arTotal - arGames.length})`);
    m.id = 'more';
    m.onclick = () => arLoadMore();
    box.appendChild(m);
  }
  arRenderCrumb();
}

async function arReloadList() {
  const seq = ++arSeq;
  arGames = []; arTotal = 0;
  const box = document.getElementById('list');
  box.innerHTML = '';
  box.appendChild(arEl('div', 'msg', 'Loading…'));
  try {
    const { data, offline } = await arFetchJson(arQuery(arState, 0, AR_PAGE));
    if (seq !== arSeq) return;
    arGames = data.games || []; arTotal = data.total || 0;
    arRenderList(false);
    if (offline) box.prepend(arEl('div', 'msg', 'Offline: saved copy'));
  } catch (err) {
    if (seq !== arSeq) return;
    box.innerHTML = '';
    box.appendChild(arEl('div', 'msg', err.code === 401 ? 'Server token missing: set it in TsumeVault ⚙' : 'Not available offline (open it once with connection)'));
    arRenderCrumb();
    document.querySelector('#crumb .n').textContent = '';
  }
}

async function arLoadMore() {
  const seq = arSeq;
  try {
    const { data } = await arFetchJson(arQuery(arState, arGames.length, AR_PAGE));
    if (seq !== arSeq) return;
    arGames = arGames.concat(data.games || []);
    arRenderList(true);
  } catch (err) { /* el botón se queda para reintentar */ }
}

async function arOpenGame(g, row) {
  try {
    const { data } = await arFetchJson('/archive/sgf?id=' + g.id);
    arSelected = g.id;
    document.querySelectorAll('.g-row.sel').forEach(r => r.classList.remove('sel'));
    if (row) row.classList.add('sel');
    document.getElementById('t-info').style.display = 'none';
    arInfoVisible = false;
    await gmOpenGame({ name: `${g.black || '?'} – ${g.white || '?'}`, sgf: data.sgf });
    document.getElementById('gm-controls').style.display = 'flex';   // en tsumevault.html lo hace switchTab('games')
    document.getElementById('comment-box').style.display = 'block';
    switchToBoard();
  } catch (err) {
    const cb = document.getElementById('comment-box');
    cb.style.display = 'block';
    cb.textContent = 'Could not load the SGF' + (err.code === 401 ? ' (server token missing)' : ' (offline and not saved yet)');
  }
}

// autocompletado de jugador: /archive/players?q= (nombre o alias); al elegir, pasa a "chip" con ✕
function arPlayerInput(inputId, boxId, key) {
  const input = document.getElementById(inputId), box = document.getElementById(boxId);
  let timer = null, list = null;
  const close = () => { if (list) { list.remove(); list = null; } };
  const render = () => {
    const p = arState[key];
    input.style.display = p ? 'none' : '';
    const old = box.querySelector('.chip');
    if (old) old.remove();
    if (p) {
      const c = arEl('span', 'chip', p.name + ' ✕');
      c.title = 'Remove this player';
      c.onclick = () => { arState[key] = null; if (key === 'p1') { arState.p2 = null; arState.color = 'any'; } arSyncFilters(); arSaveState(); arReloadList(); };
      box.appendChild(c);
    }
  };
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { close(); return; }
    timer = setTimeout(async () => {
      try {
        const { data } = await arFetchJson('/archive/players?q=' + encodeURIComponent(q));
        close();
        if (!data.players || !data.players.length) return;
        list = arEl('div', 'sugg');
        for (const p of data.players) {
          const d = arEl('div', '', `${p.name} (${p.games})`);
          d.onmousedown = (ev) => { ev.preventDefault(); arState[key] = { id: p.id, name: p.name }; input.value = ''; close(); arSyncFilters(); arSaveState(); arReloadList(); };
          list.appendChild(d);
        }
        box.appendChild(list);
      } catch (e) { close(); }
    }, 250);
  });
  input.addEventListener('blur', () => setTimeout(close, 150));
  return render;
}

let arRenderP1 = () => { }, arRenderP2 = () => { };
function arSyncFilters() {
  arRenderP1(); arRenderP2();
  document.getElementById('f-color').style.display = arState.p1 && !arState.p2 ? '' : 'none';
  document.getElementById('f-p2-box').style.display = arState.p1 ? '' : 'none';
  document.getElementById('f-color').value = arState.color;
  document.getElementById('f-y1').value = arState.y1;
  document.getElementById('f-y2').value = arState.y2;
  document.getElementById('f-sgf').checked = arState.sgf;
}

async function arLoadTree() {
  try {
    const { data } = await arFetchJson('/archive/tree');
    arTree = data;
    // la selección guardada puede ya no existir (torneo despromocionado, edición renombrada…)
    const { t, e, s } = arFind(arTree, arState);
    if (arState.t && !t) Object.assign(arState, { t: null, e: null, s: null, ph: null });
    else if (arState.e !== null && !e) Object.assign(arState, { e: null, s: null, ph: null });
    else if (arState.s !== null && !s) Object.assign(arState, { s: null, ph: null });
    arRenderTree();
    arRenderCrumb();
  } catch (err) {
    const box = document.getElementById('tree');
    box.innerHTML = '';
    box.appendChild(arEl('div', 'msg', err.code === 401 ? 'Server token missing: set it in TsumeVault ⚙' : 'Archive not available (no connection and no saved copy)'));
  }
}

function arInit() {
  bsApply('archive');   // estilo del tablero del archivo (⚙ de la app, «Apply to: Archive»); js/board_style.js
  arLoadState();
  gmInitControls();
  arRenderP1 = arPlayerInput('f-p1', 'f-p1-box', 'p1');
  arRenderP2 = arPlayerInput('f-p2', 'f-p2-box', 'p2');
  arSyncFilters();
  document.getElementById('tree-filter').addEventListener('input', arRenderTree);
  document.getElementById('f-color').addEventListener('change', (e) => { arState.color = e.target.value; arSaveState(); arReloadList(); });
  for (const id of ['f-y1', 'f-y2']) {
    document.getElementById(id).addEventListener('change', (e) => {
      const v = e.target.value.trim();
      arState[id === 'f-y1' ? 'y1' : 'y2'] = /^\d{4}$/.test(v) ? v : '';
      e.target.value = arState[id === 'f-y1' ? 'y1' : 'y2'];
      arSaveState(); arReloadList();
    });
  }
  document.getElementById('f-sgf').addEventListener('change', (e) => { arState.sgf = e.target.checked; arSaveState(); arReloadList(); });
  document.getElementById('to-app').onclick = () => { window.location.href = 'tsumevault.html'; };
  document.getElementById('mob-back').onclick = () => document.getElementById('app').classList.remove('mob-board');
  let rt = null;
  window.addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(() => { if (gmActive && wgoBoard && !arInfoVisible) { initBoard(boardSize); gmRenderCurrentNode(); } }, 200);
  });
  arLoadTree().then(() => { arReloadList(); arShowInfo(false); });
  // sin conexión: el service worker de TsumeVault (ámbito /tsumevault/) ya sirve esta página; solo se registra
  // aquí si aún no hay ninguno, con la misma URL que usa tsumevault.html, para no pelearse con el suyo
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistration('/tsumevault/').then(reg => { if (!reg) navigator.serviceWorker.register('/tsumevault/sw.js'); }).catch(() => { });
  }
}

// los tests cargan el fichero con globalThis.AR_NO_INIT = true para probar solo las funciones puras
if (!globalThis.AR_NO_INIT) {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arInit); else arInit();
}
