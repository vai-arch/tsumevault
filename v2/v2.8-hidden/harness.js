#!/usr/bin/env node
/* Arnés de validación Fase 1: ejecuta el código REAL del cliente modificado
 * (harness_bundle.js, extraído de tsumevault.html) en contextos vm aislados
 * ("dispositivos") contra el servidor real tsumevault_server.py.
 */
'use strict';
const fs = require('fs');
const vm = require('node:vm');
const nodeCrypto = require('crypto');
const initSqlJs = require('sql.js');

const BUNDLE = fs.readFileSync('harness_bundle.js', 'utf8');
const SERVER = process.env.TEST_SERVER || 'http://127.0.0.1:3488';
const OFFLINE = 'http://127.0.0.1:9';   // puerto cerrado: simula sin conexión

let SQLHost = null;
const fails = [];
function check(name, cond, extra = '') {
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (cond ? '' : `  ${extra}`));
  if (!cond) fails.push(name);
}

function makeDevice(name, opts = {}) {
  const store = opts.store || new Map();   // localStorage persistente entre "reinicios"
  const idb = opts.idb || new Map();       // IndexedDB simulada
  const netlog = [];
  const ctx = {
    console,
    setTimeout, clearTimeout,
    AbortSignal,
    crypto: { getRandomValues: (a) => nodeCrypto.randomFillSync(a) },
    alert: () => {},
    loadRuns: () => {},
    setSyncStatus: () => {},
    document: { addEventListener: () => {}, getElementById: () => null, visibilityState: 'visible' },
    window: { addEventListener: () => {} },
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    },
    fetch: async (url, o) => {
      netlog.push({ url: String(url), method: (o && o.method) || 'GET', body: (o && o.body) || null });
      return fetch(url, o);
    },
    idbGet: async (k) => (idb.has(k) ? idb.get(k) : undefined),
    idbSet: async (k, v) => { idb.set(k, v); },
    DB_KEY: 'tsumeVault_db',
    SYNC_SERVER: opts.server || SERVER,
    currentSource: 'tsumego_hero',
    SQL: SQLHost,
    db: null,
    activeRunId: null,
    filterMostrar: false,
    lightMode: true,
    syncInProgress: false,
  };
  vm.createContext(ctx, { name });
  vm.runInContext(BUNDLE, ctx, { filename: 'bundle.js' });
  const dev = {
    name, ctx, store, idb, netlog,
    run: (code) => vm.runInContext(code, ctx, { filename: `${name}.js` }),
    async runAsync(code) { return await vm.runInContext(`(async()=>{ ${code} })()`, ctx, { filename: `${name}.js` }); },
    q: (sql) => vm.runInContext(`dbQuery(${JSON.stringify(sql)}, [])`, ctx),
    q1: (sql) => vm.runInContext(`dbQueryOne(${JSON.stringify(sql)}, [])`, ctx),
    pushCount: () => netlog.filter(c => c.url.endsWith('/sync/push')).length,
  };
  return dev;
}

// "Reinicio" de un dispositivo: nuevo contexto, misma localStorage e IndexedDB;
// la DB se recarga desde IndexedDB como hace initDB(), aplicando migraciones.
function reloadDevice(dev, opts = {}) {
  const nd = makeDevice(dev.name, { store: dev.store, idb: dev.idb, server: opts.server || dev.ctx.SYNC_SERVER });
  const saved = dev.idb.get('tsumeVault_db');
  if (saved) {
    nd.ctx.db = new SQLHost.Database(saved);
    nd.run('migrateSyncColumns()');
  } else {
    nd.run('db = new SQL.Database(); createSchema();');
  }
  return nd;
}

function freshDevice(name, opts = {}) {
  const d = makeDevice(name, opts);
  d.run('db = new SQL.Database(); createSchema();');
  // datos estáticos mínimos para poder crear runs (localInsertRun consulta problems/chapters)
  d.run(`
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar) VALUES (1,'tsumego_hero',1,1,1)", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('tsumego_hero','p1',1,1,1,'x.sgf')", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('tsumego_hero','p2',1,1,2,'y.sgf')", []);
    localStorage.setItem('static_version','0');
  `);
  return d;
}

async function serverQuery(sql) {
  // consulta directa a la DB del servidor (mismo host) vía sqlite3 CLI no está
  // garantizada; usamos python inline desde el runner bash. Aquí: endpoint pull.
  throw new Error('no usado');
}

(async () => {
  SQLHost = await initSqlJs();

  // ════ Escenario 1: instalación desde cero + crear run + resolver + sync ════
  let A = freshDevice('A');
  A.run(`
    const r = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    activeRunId = r.run_id;
    localInsertAttempt('tsumego_hero', 'p1', activeRunId, 'correct', 1200);
    localInsertAttempt('tsumego_hero', 'p2', activeRunId, 'wrong', 800);
  `);
  check('E1: run local creado con synced=0', A.q1("SELECT synced,done,status FROM runs").synced === 0);
  let ok = await A.runAsync('return await tryAutoSync(true)');
  check('E1: primer sync ok', ok === true);
  check('E1: attempts marcados synced=1 tras push', A.q1("SELECT COUNT(*) c FROM attempts WHERE synced=0").c === 0);
  check('E1: run marcado synced=1 tras push', A.q1("SELECT synced FROM runs").synced === 1);
  const runUuidA = A.q1('SELECT uuid FROM runs').uuid;

  // Verificación en servidor vía pull limpio
  const pull0 = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('E1: servidor tiene el run', pull0.runs.some(r => r.uuid === runUuidA));
  check('E1: servidor tiene 2 attempts', pull0.attempts.length === 2);
  check('E1: run cerrado y done=2 en servidor', pull0.runs.find(r => r.uuid === runUuidA).status === 'closed' && pull0.runs.find(r => r.uuid === runUuidA).done === 2, JSON.stringify(pull0.runs));

  // ════ Escenario 2: sincronizar dos veces seguidas → sin re-push ════
  const pushesBefore = A.pushCount();
  ok = await A.runAsync('return await tryAutoSync(true)');
  check('E2: segundo sync ok', ok === true);
  check('E2: segundo sync NO envía push (nada pendiente)', A.pushCount() === pushesBefore, `pushes=${A.pushCount() - pushesBefore}`);

  // ════ Escenario 3: segundo dispositivo hace pull sin duplicar ════
  let B = freshDevice('B');
  ok = await B.runAsync('return await tryAutoSync(true)');
  check('E3: sync B ok', ok === true);
  check('E3: B tiene el run de A exactamente 1 vez', B.q1(`SELECT COUNT(*) c FROM runs WHERE uuid='${runUuidA}'`).c === 1);
  check('E3: B tiene 2 attempts (sin duplicados)', B.q1('SELECT COUNT(*) c FROM attempts').c === 2);
  check('E3: attempts en B llegan como synced=1', B.q1('SELECT COUNT(*) c FROM attempts WHERE synced=1').c === 2);
  check('E3: B no pushea nada', B.pushCount() === 0);
  check('E3: run_items de A visibles en B', B.q1('SELECT COUNT(*) c FROM run_items').c === 2);

  // ════ Escenario 4 (bug 3.1): pull duplicado no duplica estadísticas ════
  A.run(`setSyncMeta('last_pull_attempt_id', '0'); setSyncMeta('last_pull_run_id', '0');`);   // T9: cursores en sync_meta
  ok = await A.runAsync('return await tryAutoSync(true)');
  check('E4: re-pull completo ok', ok === true);
  check('E4: sin attempts duplicados tras re-pull (índice único uuid)', A.q1('SELECT COUNT(*) c FROM attempts').c === 2, `c=${A.q1('SELECT COUNT(*) c FROM attempts').c}`);
  check('E4: sin runs duplicados tras re-pull', A.q1('SELECT COUNT(*) c FROM runs').c === 1);
  check('E4: cursor de pull avanzó', parseInt(A.run(`getSyncMeta('last_pull_attempt_id')`)) >= 2);

  // ════ Escenario 5 (bug 3.2): run creado offline sobrevive a syncDeletedRuns ════
  let C = freshDevice('C', { server: OFFLINE });
  C.run(`
    const r = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    activeRunId = r.run_id;
    localInsertAttempt('tsumego_hero', 'p1', activeRunId, 'correct', 900);
  `);
  const cUuid = C.q1('SELECT uuid FROM runs').uuid;   // capturado ANTES del sync
  ok = await C.runAsync('return await tryAutoSync(true)');
  check('E5: sync offline falla silenciosamente', ok === false);
  await C.runAsync('await saveDB()');   // persistir como haría la app antes del reinicio
  // reinicio del dispositivo aún offline: syncDeletedRuns directo (peor caso)
  C = reloadDevice(C, { server: SERVER });
  const runsBefore = C.q1('SELECT COUNT(*) c FROM runs').c;
  await C.runAsync('await syncDeletedRuns()');
  check('E5: syncDeletedRuns NO borra el run offline no pusheado', C.q1('SELECT COUNT(*) c FROM runs').c === runsBefore);
  ok = await C.runAsync('return await tryAutoSync(true)');
  check('E5: al recuperar conexión el run se pushea', ok === true && C.q1('SELECT synced FROM runs WHERE synced<>1') === null);
  const pull1 = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('E5: servidor recibió el run creado offline', pull1.runs.some(r => r.uuid === cUuid));

  // ════ Escenario 6 (bug 3.3): purga por uuid; review runs con done>0 intactos ════
  let D = freshDevice('D');
  await D.runAsync('await tryAutoSync(true)');   // trae estado actual
  D.run(`
    // run vacío antiguo (purgable) — no pusheado
    dbExec("INSERT INTO runs (source,type,status,total,done,started_at,uuid,synced) VALUES ('tsumego_hero','chapter','open',2,0,'2026-07-10T09:00:00Z','empty-old-uuid',0)", []);
    // run estilo review: sin run_items pero con done>0 (historial VÁLIDO)
    dbExec("INSERT INTO runs (source,type,status,total,done,started_at,uuid,synced) VALUES ('tsumego_hero','review','closed',0,5,'2026-07-09T09:00:00Z','review-old-uuid',0)", []);
  `);
  await D.runAsync('await purgeEmptyRuns()');
  check('E6: run vacío antiguo purgado localmente', D.q1("SELECT COUNT(*) c FROM runs WHERE uuid='empty-old-uuid'").c === 0);
  check('E6: run de review con done>0 NO purgado', D.q1("SELECT COUNT(*) c FROM runs WHERE uuid='review-old-uuid'").c === 1);
  const delCalls = D.netlog.filter(c => c.url.endsWith('/db/runs/delete'));
  check('E6: la purga contactó al servidor por uuid', delCalls.length === 1);
  // el run de A (válido, en servidor) no debe haber sido tocado
  const pull2 = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('E6: el run válido de A sigue en el servidor', pull2.runs.some(r => r.uuid === runUuidA));

  // ════ Escenario 7: eliminar un run se propaga con check_runs ════
  await A.runAsync(`await deleteRun(dbQueryOne("SELECT id FROM runs WHERE uuid='${runUuidA}'", []).id)`);
  const pull3 = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('E7: run eliminado en servidor', !pull3.runs.some(r => r.uuid === runUuidA));
  ok = await B.runAsync('return await tryAutoSync(true)');
  await B.runAsync('await syncDeletedRuns()');
  check('E7: B elimina localmente el run borrado (estaba synced)', B.q1(`SELECT COUNT(*) c FROM runs WHERE uuid='${runUuidA}'`).c === 0);

  // ════ Escenario 8: SM-2 cursor sin reloj de cliente ════
  const cur = C.run(`getSyncMeta('last_sm2_sync')`);
  const maxUpd = C.q1('SELECT MAX(updated_at) m FROM sm2_state');
  check('E8: cursor SM-2 = max(updated_at) visto, no reloj', cur === (maxUpd && maxUpd.m), `cursor=${cur} max=${maxUpd && maxUpd.m}`);
  // B recibe el estado SM-2 de C
  await B.runAsync('await tryAutoSync(true)');
  check('E8: SM-2 replicado a B', B.q1("SELECT COUNT(*) c FROM sm2_state WHERE source='tsumego_hero' AND problem_id='p1'").c === 1);

  // ════ Escenario 9: run modificado tras push se re-pushea (dirty=2) ════
  let E = freshDevice('E');
  E.run(`
    const r = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    activeRunId = r.run_id;
  `);
  await E.runAsync('await tryAutoSync(true)');   // push del run abierto done=0
  check('E9: run abierto pusheado synced=1', E.q1('SELECT synced FROM runs').synced === 1);
  E.run(`
    localInsertAttempt('tsumego_hero', 'p1', activeRunId, 'correct', 500);
    localInsertAttempt('tsumego_hero', 'p2', activeRunId, 'correct', 500);
  `);
  check('E9: run pasa a synced=2 al cambiar', E.q1('SELECT synced FROM runs').synced === 2);
  await E.runAsync('await tryAutoSync(true)');
  const eUuid = E.q1('SELECT uuid FROM runs').uuid;
  const pull4 = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  const srvRun = pull4.runs.find(r => r.uuid === eUuid);
  check('E9: servidor refleja el cierre (done=2, closed)', srvRun && srvRun.done === 2 && srvRun.status === 'closed', JSON.stringify(srvRun));
  const srvItems = pull4.run_items.filter(i => i.run_id === srvRun.id && i.result === 'correct');
  check('E9: resultados de run_items actualizados en servidor', srvItems.length === 2, JSON.stringify(pull4.run_items.filter(i => i.run_id === srvRun.id)));
  check('E9: run vuelve a synced=1', E.q1('SELECT synced FROM runs').synced === 1);

  // ════ Escenario 10: migración de instalación existente (schema viejo) ════
  const oldDb = new SQLHost.Database();
  oldDb.run(`
    CREATE TABLE attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
      problem_id TEXT NOT NULL, run_id INTEGER, result TEXT NOT NULL,
      time_ms INTEGER, created_at TEXT NOT NULL, uuid TEXT);
    CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
      set_id INTEGER, chapter_id INTEGER, vc_id INTEGER, type TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open', total INTEGER NOT NULL DEFAULT 0,
      done INTEGER NOT NULL DEFAULT 0, started_at TEXT NOT NULL, closed_at TEXT,
      uuid TEXT, paused_ms INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE run_items (run_id INTEGER NOT NULL, source TEXT NOT NULL,
      problem_id TEXT NOT NULL, order_in_run INTEGER NOT NULL, result TEXT,
      PRIMARY KEY (run_id, problem_id));
    INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES
      (1,'tsumego_hero','chapter','closed',1,1,'2026-07-01T10:00:00Z','dup-run'),
      (2,'tsumego_hero','chapter','closed',1,1,'2026-07-01T10:00:00Z','dup-run');
    INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES
      (1,'tsumego_hero','p1',1,'correct',700,'2026-07-01T10:00:01Z','dup-att'),
      (2,'tsumego_hero','p1',2,'correct',700,'2026-07-01T10:00:01Z','dup-att');
  `);
  let F = makeDevice('F');
  F.ctx.db = oldDb;
  F.run('migrateSyncColumns()');
  check('E10: migración dedup attempts (queda 1)', F.q1("SELECT COUNT(*) c FROM attempts WHERE uuid='dup-att'").c === 1);
  check('E10: migración dedup runs (queda 1)', F.q1("SELECT COUNT(*) c FROM runs WHERE uuid='dup-run'").c === 1);
  check('E10: attempt repuntado al run conservado', F.q1("SELECT run_id FROM attempts WHERE uuid='dup-att'").run_id === 1);
  check('E10: columnas synced añadidas con backfill 0', F.q1('SELECT COUNT(*) c FROM attempts WHERE synced=0').c === 1);
  const idx = F.q("SELECT name FROM sqlite_master WHERE type='index'").map(r => r.name);
  check('E10: índices únicos uuid creados', idx.includes('idx_attempts_uuid') && idx.includes('idx_runs_uuid'), idx.join(','));

  // ════ Escenario 11: debounce de saveDB persiste sin sync ════
  let G = freshDevice('G', { server: OFFLINE });
  G.run(`
    localInsertAttempt('tsumego_hero', 'p1', null, 'correct', 300);
    scheduleSaveDB(50);
  `);
  await new Promise(r => setTimeout(r, 250));
  check('E11: intento persistido en IndexedDB por el debounce', (() => {
    const bytes = G.idb.get('tsumeVault_db');
    if (!bytes) return false;
    const d2 = new SQLHost.Database(bytes);
    const st = d2.prepare('SELECT COUNT(*) c FROM attempts'); st.step();
    const c = st.getAsObject().c; st.free(); d2.close();
    return c === 1;
  })());
  // reinicio simulado: el intento sigue y se sincroniza al volver la conexión
  G = reloadDevice(G, { server: SERVER });
  ok = await G.runAsync('return await tryAutoSync(true)');
  check('E11: tras reinicio y reconexión, el intento pendiente se pushea', ok === true && G.q1('SELECT synced FROM attempts').synced === 1);

  // ════ Escenario 12: token de cliente ════
  let H = freshDevice('H');
  H.store.set('sync_token', 'tok-cliente');
  let captured = null;
  const origFetch = H.ctx.fetch;
  H.ctx.fetch = async (url, o) => { captured = o && o.headers; return origFetch(url, o); };
  await H.runAsync("await syncFetch('/sync/static_version', {})");
  check('E12: syncFetch añade X-Auth-Token si hay token guardado', captured && captured['X-Auth-Token'] === 'tok-cliente', JSON.stringify(captured));
  H.store.delete('sync_token');
  captured = null;
  await H.runAsync("await syncFetch('/sync/static_version', {})");
  check('E12: sin token guardado no se envía cabecera', captured && !('X-Auth-Token' in captured), JSON.stringify(captured));

  // ════ Escenario 13 (fix cursores huérfanos): reset de DB con localStorage vivo ════
  // B tiene datos y cursores avanzados. Simulamos que el usuario borra la DB
  // del navegador (IndexedDB) pero localStorage sobrevive: la DB renace vacía
  // con los cursores antiguos apuntando por delante de los datos del servidor.
  check('E13: precondición — B tiene cursores avanzados (en sync_meta)',
    parseInt(B.run(`getSyncMeta('last_pull_attempt_id')`)) > 0 && parseInt(B.run(`getSyncMeta('last_pull_run_id')`)) > 0 && !!B.run(`getSyncMeta('last_sm2_sync')`));
  const srvSnapshot = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  B.idb.delete('tsumeVault_db');                       // reset de la DB
  B = makeDevice('B', { store: B.store, idb: B.idb }); // recarga con localStorage intacto
  B.run('db = new SQL.Database(); createSchema();');
  B.run(`
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar) VALUES (1,'tsumego_hero',1,1,1)", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('tsumego_hero','p1',1,1,1,'x.sgf')", []);
    localStorage.setItem('static_version','0');
  `);
  ok = await B.runAsync('return await tryAutoSync(true)');
  check('E13: sync tras reset ok', ok === true);
  check('E13: recupera TODOS los attempts del servidor pese al cursor huérfano',
    B.q1('SELECT COUNT(*) c FROM attempts').c === srvSnapshot.attempts.length,
    `local=${B.q1('SELECT COUNT(*) c FROM attempts').c} servidor=${srvSnapshot.attempts.length}`);
  check('E13: recupera TODOS los runs del servidor',
    B.q1('SELECT COUNT(*) c FROM runs').c === srvSnapshot.runs.length,
    `local=${B.q1('SELECT COUNT(*) c FROM runs').c} servidor=${srvSnapshot.runs.length}`);
  check('E13: recupera el estado SM-2', B.q1('SELECT COUNT(*) c FROM sm2_state').c >= 1);
  const maxSrvAtt = Math.max(0, ...srvSnapshot.attempts.map(a => a.id));
  check('E13: el cursor se reescribe al valor correcto tras la recuperación',
    parseInt(B.run(`getSyncMeta('last_pull_attempt_id')`)) === maxSrvAtt,
    `cursor=${B.run(`getSyncMeta('last_pull_attempt_id')`)} max=${maxSrvAtt}`);
  ok = await B.runAsync('return await tryAutoSync(true)');
  check('E13: segundo sync tras recuperación sin duplicados',
    ok === true && B.q1('SELECT COUNT(*) c FROM attempts').c === srvSnapshot.attempts.length);

  // ════ Escenario 14 (remapeo de ids): datos locales previos al primer sync ════
  // K crea DOS runs con un attempt cada uno ANTES de su primer sync: sus ids
  // locales (runs 1-2, attempts 1-2) colisionan con ids ya usados en el
  // servidor. Antes, las filas del servidor con id ocupado se descartaban en
  // silencio y no volvían (el cursor avanza igual); ahora todo entra con ids
  // locales nuevos y cada attempt cuelga de su run correcto vía run_uuid.
  let K = freshDevice('K');
  K.run(`
    const r1 = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    localInsertAttempt('tsumego_hero', 'p1', r1.run_id, 'correct', 600);
    const r2 = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    localInsertAttempt('tsumego_hero', 'p2', r2.run_id, 'wrong', 700);
  `);
  const kUuids = K.q('SELECT uuid FROM runs').map(r => r.uuid);
  const srvPre = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('E14: precondición — colisión real de ids run y attempt',
    srvPre.runs.some(r => r.id === 2) && srvPre.attempts.some(a => a.id <= 2),
    JSON.stringify({ runs: srvPre.runs.map(x => x.id), atts: srvPre.attempts.map(x => x.id) }));
  ok = await K.runAsync('return await tryAutoSync(true)');
  check('E14: sync ok', ok === true);
  const kRuns = K.q1('SELECT COUNT(*) c FROM runs').c;
  const kAtts = K.q1('SELECT COUNT(*) c FROM attempts').c;
  check('E14: K recibe TODOS los runs del servidor pese a la colisión',
    kRuns === srvPre.runs.length + 2, `local=${kRuns} esperado=${srvPre.runs.length + 2}`);
  check('E14: K recibe TODOS los attempts del servidor pese a la colisión',
    kAtts === srvPre.attempts.length + 2, `local=${kAtts} esperado=${srvPre.attempts.length + 2}`);
  let attached = 0, wrong = 0;
  for (const a of srvPre.attempts) {
    if (!a.uuid || !a.run_uuid) continue;
    const row = K.q1(`SELECT r.uuid u FROM attempts x JOIN runs r ON r.id = x.run_id WHERE x.uuid = '${a.uuid}'`);
    if (row && row.u === a.run_uuid) attached++; else wrong++;
  }
  check('E14: cada attempt recibido cuelga de su run correcto (por uuid)', wrong === 0 && attached > 0, `ok=${attached} mal=${wrong}`);
  check('E14: los attempts propios de K siguen en sus runs locales 1 y 2',
    K.q1('SELECT COUNT(*) c FROM attempts WHERE run_id IN (1,2)').c === 2);
  ok = await K.runAsync('return await tryAutoSync(true)');
  check('E14: doble sync sin duplicados',
    ok === true && K.q1('SELECT COUNT(*) c FROM attempts').c === kAtts && K.q1('SELECT COUNT(*) c FROM runs').c === kRuns);
  const srvPost = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('E14: los runs propios de K llegaron al servidor',
    kUuids.every(u => srvPost.runs.some(r => r.uuid === u)));

  // ════ Escenario T2 (bug 3.6): fechas de review en base LOCAL, no UTC ════
  let M = freshDevice('M', { server: OFFLINE });
  M.run(`updateSm2('tsumego_hero', 'p1', 'wrong');`);   // fallo → interval=1, determinista
  const sm2row = M.q1("SELECT due_date, interval FROM sm2_state WHERE problem_id='p1'");
  const dexp = new Date(); dexp.setDate(dexp.getDate() + sm2row.interval);
  const expDue = `${dexp.getFullYear()}-${String(dexp.getMonth() + 1).padStart(2, '0')}-${String(dexp.getDate()).padStart(2, '0')}`;
  check('T2: due_date = hoy LOCAL + interval', sm2row.due_date === expDue, `due=${sm2row.due_date} esperado=${expDue}`);
  M.run(`dbExec("UPDATE sm2_state SET due_date=?", [localDateStr()])`);   // vence hoy local
  const pend = M.run(`localCountReviewPending('tsumego_hero', {})`);
  check('T2: localCountReviewPending cuenta lo que vence hoy local', pend === 1, `pend=${pend}`);

  // ════ Escenario T4 (bug 3.8): runs de review coherentes ════
  // startReview arrastra demasiado DOM para extraerlo al bundle; se simula su
  // efecto post-fix (INSERT type='review' con total=N) y se valida la semantica
  // de DB: cierre exacto al completar y sin incrementos tras soltar activeRunId.
  let R = freshDevice('R', { server: OFFLINE });
  R.run(`
    dbExec("INSERT INTO runs (source,set_id,chapter_id,type,status,total,done,started_at,uuid) VALUES ('tsumego_hero',NULL,NULL,'review','open',3,0,'2026-07-13T10:00:00Z','rv-t4-uuid')", []);
    activeRunId = dbQueryOne("SELECT id FROM runs WHERE uuid='rv-t4-uuid'", []).id;
    localInsertAttempt('tsumego_hero', 'p1', activeRunId, 'correct', 500);
    localInsertAttempt('tsumego_hero', 'p2', activeRunId, 'wrong', 500);
  `);
  let rvRun = R.q1("SELECT status, done, total FROM runs WHERE uuid='rv-t4-uuid'");
  check('T4: la review NO se cierra antes de completarse', rvRun.status === 'open' && rvRun.done === 2, JSON.stringify(rvRun));
  R.run(`localInsertAttempt('tsumego_hero', 'p1', activeRunId, 'correct', 500); activeRunId = null;`);
  rvRun = R.q1("SELECT status, done, total FROM runs WHERE uuid='rv-t4-uuid'");
  check('T4: cierre exacto al completar (done=total=3, closed)', rvRun.status === 'closed' && rvRun.done === 3 && rvRun.total === 3, JSON.stringify(rvRun));
  R.run(`localInsertAttempt('tsumego_hero', 'p2', null, 'correct', 500);`);   // intento posterior sin run activo
  rvRun = R.q1("SELECT status, done FROM runs WHERE uuid='rv-t4-uuid'");
  check('T4: intentos posteriores no incrementan el run de review', rvRun.done === 3, JSON.stringify(rvRun));

  // ════ Escenario T7 (3.12a): resumeRun de un run ya completado ════
  let T = freshDevice('T', { server: OFFLINE });
  T.run(`
    const r = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    localInsertAttempt('tsumego_hero', 'p1', r.run_id, 'correct', 400);
    localInsertAttempt('tsumego_hero', 'p2', r.run_id, 'wrong', 400);
    dbExec("UPDATE runs SET status='open', closed_at=NULL WHERE id=?", [r.run_id]);  // simular run completo que quedo open
    activeRunId = null; runMode = false;
  `);
  const attsBefore = T.q1('SELECT COUNT(*) c FROM attempts').c;
  await T.runAsync(`await resumeRun(dbQueryOne("SELECT id FROM runs", []).id)`);
  const t7run = T.q1('SELECT status FROM runs');
  check('T7: run completado NO se rejuega (runMode false, sin activeRunId)', T.run('runMode') === false && T.run('activeRunId') === null);
  check('T7: el run queda cerrado', t7run.status === 'closed', JSON.stringify(t7run));
  check('T7: cero attempts nuevos', T.q1('SELECT COUNT(*) c FROM attempts').c === attsBefore);
  T.run(`dbExec("INSERT INTO runs (source,type,status,total,done,started_at,uuid) VALUES ('tsumego_hero','review','open',3,3,'2026-07-13T09:00:00Z','rv-t7')", [])`);
  await T.runAsync(`await resumeRun(dbQueryOne("SELECT id FROM runs WHERE uuid='rv-t7'", []).id)`);
  check('T7: run de review (sin run_items) tampoco es reanudable y se cierra', T.q1("SELECT status FROM runs WHERE uuid='rv-t7'").status === 'closed' && T.run('runMode') === false);

  // ════ Escenario E15 (T9): migración de cursores desde localStorage ════
  // Simula un cliente anterior a sync_meta: DB con datos pero SIN la tabla, y
  // cursores solo en localStorage. Tras "actualizar" (reload → migración), los
  // cursores deben estar en sync_meta y el sync NO debe re-descargar el
  // historial completo (el pull sale con since > 0).
  let P = freshDevice('P');
  ok = await P.runAsync('return await tryAutoSync(true)');
  check('E15: precondición — P sincronizado', ok === true);
  const p15cur = P.run(`getSyncMeta('last_pull_attempt_id')`);
  check('E15: precondición — cursor > 0 en sync_meta', parseInt(p15cur) > 0, `cur=${p15cur}`);
  // degradar a estado pre-sync_meta: cursores a localStorage, tabla fuera
  P.run(`
    localStorage.setItem('last_pull_attempt_id', getSyncMeta('last_pull_attempt_id'));
    localStorage.setItem('last_pull_run_id', getSyncMeta('last_pull_run_id'));
    if (getSyncMeta('last_sm2_sync')) localStorage.setItem('last_sm2_sync', getSyncMeta('last_sm2_sync'));
    dbExec('DROP TABLE sync_meta', []);
  `);
  await P.runAsync('await saveDB()');
  P = reloadDevice(P);   // reload ejecuta migrateSyncColumns → migrateSyncMeta (import)
  check('E15: migración importa los cursores de localStorage a sync_meta',
    P.run(`getSyncMeta('last_pull_attempt_id')`) === p15cur,
    `sync_meta=${P.run(`getSyncMeta('last_pull_attempt_id')`)} esperado=${p15cur}`);
  const pullsBefore15 = P.netlog.filter(c => c.url.includes('/sync/pull?')).length;
  ok = await P.runAsync('return await tryAutoSync(true)');
  const lastPull15 = P.netlog.filter(c => c.url.includes('/sync/pull?')).pop();
  check('E15: el sync tras migrar NO re-descarga el historial (since > 0)',
    ok === true && lastPull15 && !lastPull15.url.includes('since_attempt_id=0'),
    lastPull15 && lastPull15.url);

  // ════ Escenario F1 (§12.1): contador de pendientes de sync ════
  let FP = freshDevice('F1', { server: OFFLINE });
  FP.run(`
    const r = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    localInsertAttempt('tsumego_hero', 'p1', r.run_id, 'correct', 300);
  `);
  let pcnt = FP.run('countPendingSync()');
  check('F1: offline cuenta pendientes (1 attempt + 1 run)', pcnt.attempts === 1 && pcnt.runs === 1 && pcnt.total === 2, JSON.stringify(pcnt));
  FP.ctx.SYNC_SERVER = SERVER;
  ok = await FP.runAsync('return await tryAutoSync(true)');
  pcnt = FP.run('countPendingSync()');
  check('F1: tras sync exitoso, cero pendientes', ok === true && pcnt.total === 0, JSON.stringify(pcnt));

  // ════ Escenario F5 (§12.5): snapshot diario de madurez ════
  let DS = freshDevice('DS', { server: OFFLINE });
  DS.run(`
    const r = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    localInsertAttempt('tsumego_hero', 'p1', r.run_id, 'correct', 300);
    localInsertAttempt('tsumego_hero', 'p2', r.run_id, 'correct', 300);
    snapshotDailyStats();
    snapshotDailyStats();   // idempotente: mismo día → REPLACE, no duplicado
  `);
  const ds = DS.q("SELECT date, source, dominated, seen, total FROM daily_stats");
  check('F5: un único snapshot por (día, source)', ds.length === 1, JSON.stringify(ds));
  const dloc = new Date();
  const dstr = `${dloc.getFullYear()}-${String(dloc.getMonth() + 1).padStart(2, '0')}-${String(dloc.getDate()).padStart(2, '0')}`;
  check('F5: snapshot con fecha LOCAL y agregados coherentes',
    ds[0].date === dstr && ds[0].total === 2 && ds[0].seen === 2 && ds[0].dominated >= 0 && ds[0].dominated <= 2,
    JSON.stringify(ds[0]));

  // ════ Escenario Q3: la cadena de re-sync no deja pendientes "pegados" ════
  // Un intento registrado MIENTRAS un sync está en vuelo rebota en
  // syncInProgress; sin la cadena, quedaba pendiente (badge pegado) hasta el
  // siguiente intento o sync manual.
  let Q = freshDevice('Q3');
  Q.run(`
    const r = localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 });
    localInsertAttempt('tsumego_hero', 'p1', r.run_id, 'correct', 200);
  `);
  // Interceptar el fetch del push: el cuerpo del push ya está construido cuando
  // se emite la petición; insertar en ese instante deja el intento fuera del
  // lote en vuelo de forma DETERMINISTA (un insert durante el pull sí entraría
  // en el push del mismo sync, como demostró la primera versión de este test).
  {
    const orig = Q.ctx.fetch; let injected = false;
    Q.ctx.fetch = async (url, o) => {
      if (!injected && String(url).endsWith('/sync/push')) {
        injected = true;
        Q.run(`localInsertAttempt('tsumego_hero', 'p2', null, 'correct', 200);`);
      }
      return orig(url, o);
    };
  }
  const q3ok = await Q.runAsync('return await tryAutoSync(true)');
  check('Q3: el sync en vuelo termina ok', q3ok === true);
  check('Q3: el intento llegado durante el vuelo queda pendiente al terminar',
    Q.run('countPendingSync()').total >= 1, JSON.stringify(Q.run('countPendingSync()')));
  await new Promise(r => setTimeout(r, 2600));                 // la cadena dispara a +1,5 s
  check('Q3: la cadena de re-sync lo deja todo sincronizado sin intervención',
    Q.run('countPendingSync()').total === 0, JSON.stringify(Q.run('countPendingSync()')));

  // ════ Escenario R1: visibilidad masiva por nivel (núcleo SQL) ════
  let V = freshDevice('R1', { server: OFFLINE });
  V.run(`
    dbExec("UPDATE chapters SET diff_avg = 600 WHERE id = 1", []);                     // 15k (fácil)
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar,diff_avg) VALUES (2,'tsumego_hero',1,2,0,1500)", []);  // 6k
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar,diff_avg) VALUES (3,'tsumego_hero',1,3,1,2100)", []);  // 1d (difícil)
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar,diff_avg) VALUES (4,'tsumego_hero',1,4,0,NULL)", []);  // sin dificultad
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar,diff_avg) VALUES (5,'otro',9,1,1,2100)", []);          // otra fuente: intacta
  `);
  const r1res = V.run(`applyMostrarUpTo('tsumego_hero', 1500)`);   // hasta 6k inclusive
  const vis = V.q("SELECT id, mostrar FROM chapters ORDER BY id");
  check('R1: visibles los ≤ nivel y los sin dificultad; ocultos los más difíciles',
    JSON.stringify(vis) === JSON.stringify([{id:1,mostrar:1},{id:2,mostrar:1},{id:3,mostrar:0},{id:4,mostrar:1},{id:5,mostrar:1}]),
    JSON.stringify(vis));
  check('R1: recuento devuelto correcto (3 visibles / 1 oculto en la fuente)',
    r1res.shown === 3 && r1res.hidden === 1, JSON.stringify(r1res));

  // ════ Escenario T13: borrado lógico de problemas (merge /sync/problems_hidden) ════
  // El fixture del servidor no trae catálogo en problems: se siembra p1/p2 con
  // una conexión sqlite3 propia (WAL-safe; el servidor abre conexiones por
  // petición, no las retiene).
  const cp = require('child_process');
  const srvSql = (sql) => cp.execFileSync('python3', ['-c',
    "import sqlite3,sys\ncon=sqlite3.connect('h_run/tsumeVault.db')\ncon.execute(sys.argv[1])\ncon.commit()\ncon.close()", sql]);
  const srvQ = (sql) => JSON.parse(cp.execFileSync('python3', ['-c',
    "import sqlite3,sys,json\ncon=sqlite3.connect('h_run/tsumeVault.db')\ncon.row_factory=sqlite3.Row\nprint(json.dumps([dict(r) for r in con.execute(sys.argv[1]).fetchall()]))", sql]).toString());
  srvSql("INSERT OR IGNORE INTO problems (source,problem_id,set_id,sgf_path) VALUES ('tsumego_hero','p1',1,'x.sgf')");
  srvSql("INSERT OR IGNORE INTO problems (source,problem_id,set_id,sgf_path) VALUES ('tsumego_hero','p2',1,'y.sgf')");
  let H1 = freshDevice('H1');
  // la UI marca los ocultos como PENDIENTES (hidden=2); el sync los confirma (2->1)
  H1.run(`dbExec("UPDATE problems SET hidden=2 WHERE source='tsumego_hero' AND problem_id='p1'", [])`);
  ok = await H1.runAsync('return await tryAutoSync(true)');
  check('T13: sync con oculto local ok', ok === true);
  check('T13: el pendiente queda confirmado tras el sync (2->1)', H1.q1("SELECT hidden FROM problems WHERE problem_id='p1'").hidden === 1,
    `hidden=${H1.q1("SELECT hidden FROM problems WHERE problem_id='p1'").hidden}`);
  check('T13: el servidor registra el oculto', srvQ("SELECT hidden FROM problems WHERE problem_id='p1'")[0].hidden === 1,
    JSON.stringify(srvQ("SELECT problem_id,hidden FROM problems")));
  check('T13: p2 sigue visible en servidor', srvQ("SELECT hidden FROM problems WHERE problem_id='p2'")[0].hidden === 0);
  let H2 = freshDevice('H2');
  check('T13: H2 parte con p1 visible (guardia anti-test-vacuo)', H2.q1("SELECT hidden FROM problems WHERE problem_id='p1'").hidden === 0);
  ok = await H2.runAsync('return await tryAutoSync(true)');
  check('T13: sync de H2 ok', ok === true);
  check('T13: el oculto de H1 llega a H2 (pull implícito en la respuesta)', H2.q1("SELECT hidden FROM problems WHERE problem_id='p1'").hidden === 1);
  check('T13: p2 sigue visible en H2', H2.q1("SELECT hidden FROM problems WHERE problem_id='p2'").hidden === 0);
  srvSql("UPDATE problems SET hidden=0 WHERE problem_id='p1'");   // unhide manual: procedimiento real acordado
  ok = await H1.runAsync('return await tryAutoSync(true)');
  check('T13: unhide manual en la BD del servidor se propaga al cliente',
    ok === true && H1.q1("SELECT hidden FROM problems WHERE problem_id='p1'").hidden === 0,
    `hidden=${H1.q1("SELECT hidden FROM problems WHERE problem_id='p1'").hidden}`);

  // ── T13b: filtrado local — runs nuevos y contador de repaso excluyen ocultos ──
  // Dispositivo offline: localInsertRun/localCountReviewPending son 100% locales.
  let VH = freshDevice('T13b', { server: OFFLINE });
  VH.run(`localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 })`);
  check('T13b: run baseline con los 2 problemas visibles (guardia anti-test-vacuo)',
    VH.q1('SELECT total FROM runs ORDER BY id DESC LIMIT 1').total === 2);
  VH.run(`dbExec("UPDATE problems SET hidden=1 WHERE problem_id='p2'", [])`);
  VH.run(`localInsertRun('tsumego_hero', 'chapter', { chapter_id: 1 })`);
  check('T13b: run nuevo excluye el problema oculto (total=1)',
    VH.q1('SELECT total FROM runs ORDER BY id DESC LIMIT 1').total === 1,
    `total=${VH.q1('SELECT total FROM runs ORDER BY id DESC LIMIT 1').total}`);
  check('T13b: run_items del run nuevo no contienen el oculto',
    VH.q1(`SELECT COUNT(*) c FROM run_items WHERE run_id=(SELECT MAX(id) FROM runs) AND problem_id='p2'`).c === 0);
  VH.run(`
    dbExec("DELETE FROM sm2_state", []);
    dbExec("INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at) VALUES ('tsumego_hero','p1','2000-01-01',1,2.5,1,'2000-01-01T00:00:00Z')", []);
    dbExec("INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at) VALUES ('tsumego_hero','p2','2000-01-01',1,2.5,1,'2000-01-01T00:00:00Z')", []);
  `);
  check('T13b: pendientes de repaso excluyen el oculto (1 de 2 vencidos)',
    VH.run(`localCountReviewPending('tsumego_hero', {})`) === 1,
    `n=${VH.run(`localCountReviewPending('tsumego_hero', {})`)}`);
  VH.run(`dbExec("UPDATE problems SET hidden=0 WHERE problem_id='p2'", [])`);
  check('T13b: al des-ocultar, el contador de repaso vuelve a 2 (guardia anti-test-vacuo)',
    VH.run(`localCountReviewPending('tsumego_hero', {})`) === 2);

  console.log('\nRESULTADO CLIENTE:', fails.length ? `${fails.length} FALLOS: ${fails.join(' | ')}` : 'TODO OK');
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error('ERROR FATAL', e); process.exit(2); });
