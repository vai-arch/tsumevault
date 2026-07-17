#!/usr/bin/env node
/* Compatibilidad Fase 1: el cliente ANTIGUO (sin modificar) debe seguir
 * funcionando contra el servidor NUEVO (sin token definido), y su push del
 * historial completo no debe duplicar nada. Después, un cliente NUEVO debe
 * poder convivir con los datos que dejó el antiguo.
 */
'use strict';
const fs = require('fs');
const vm = require('node:vm');
const nodeCrypto = require('crypto');
const initSqlJs = require('sql.js');

const OLD = fs.readFileSync('harness_bundle_old.js', 'utf8');
const NEW = fs.readFileSync('harness_bundle.js', 'utf8');
const SERVER = 'http://127.0.0.1:3489';

const fails = [];
function check(n, c, x = '') { console.log((c ? 'PASS ' : 'FAIL ') + n + (c ? '' : '  ' + x)); if (!c) fails.push(n); }

function makeDevice(name, bundle) {
  const store = new Map(), idb = new Map(), netlog = [];
  const ctx = {
    console, setTimeout, clearTimeout, AbortSignal,
    crypto: { getRandomValues: (a) => nodeCrypto.randomFillSync(a) },
    alert: () => {}, setSyncStatus: () => {},
    document: { addEventListener: () => {}, getElementById: () => null, visibilityState: 'visible' },
    window: { addEventListener: () => {} },
    localStorage: { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) },
    fetch: async (u, o) => { netlog.push({ url: String(u), method: (o && o.method) || 'GET' }); return fetch(u, o); },
    idbGet: async k => idb.has(k) ? idb.get(k) : undefined,
    idbSet: async (k, v) => { idb.set(k, v); },
    DB_KEY: 'tsumeVault_db', SYNC_SERVER: SERVER,
    SQL: null, db: null, activeRunId: null, filterMostrar: false, lightMode: true, syncInProgress: false,
  };
  vm.createContext(ctx, { name });
  vm.runInContext(bundle, ctx, { filename: name + '_bundle.js' });
  return {
    name, ctx, store, netlog,
    run: c => vm.runInContext(c, ctx),
    runAsync: async c => await vm.runInContext(`(async()=>{ ${c} })()`, ctx),
    q1: sql => vm.runInContext(`dbQueryOne(${JSON.stringify(sql)}, [])`, ctx),
  };
}

(async () => {
  const SQL = await initSqlJs();

  // ── Cliente ANTIGUO ──
  const O = makeDevice('OLD', OLD);
  O.ctx.SQL = SQL;
  O.run('db = new SQL.Database(); createSchema();');
  O.run(`
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar) VALUES (1,'tsumego_hero',1,1,1)", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('tsumego_hero','p1',1,1,1,'x.sgf')", []);
    localStorage.setItem('static_version','0');
    const r = localInsertRun('tsumego_hero','chapter',{chapter_id:1});
    activeRunId = r.run_id;
    localInsertAttempt('tsumego_hero','p1',activeRunId,'correct',450);
  `);
  let ok = await O.runAsync('return (async () => { try { await doSync(true); return true; } catch(e){ console.log(e.message); return false; } })()');
  check('C1: cliente antiguo sincroniza contra servidor nuevo', ok === true);
  ok = await O.runAsync('return (async () => { try { await doSync(true); return true; } catch(e){ return false; } })()');
  check('C1: segundo sync del cliente antiguo (re-push historial) ok', ok === true);
  const pushes = O.netlog.filter(c => c.url.endsWith('/sync/push')).length;
  check('C1: el cliente antiguo sí re-pushea (comportamiento previo intacto)', pushes === 2, `pushes=${pushes}`);
  const pull = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('C1: servidor deduplicó (1 attempt, 1 run)', pull.attempts.length === 1 && pull.runs.length === 1, JSON.stringify([pull.attempts.length, pull.runs.length]));

  // syncDeletedRuns del cliente antiguo (sin columna synced)
  await O.runAsync('await syncDeletedRuns()');
  check('C1: syncDeletedRuns antiguo no borra el run existente', O.q1('SELECT COUNT(*) c FROM runs').c === 1);

  // ── Cliente NUEVO conviviendo con los datos del antiguo ──
  const N = makeDevice('NEW', NEW);
  N.ctx.SQL = SQL;
  N.run('db = new SQL.Database(); createSchema();');
  N.run(`
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar) VALUES (1,'tsumego_hero',1,1,1)", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('tsumego_hero','p1',1,1,1,'x.sgf')", []);
    localStorage.setItem('static_version','0');
  `);
  ok = await N.runAsync('return await tryAutoSync(true)');
  check('C2: cliente nuevo pullea datos del antiguo', ok === true && N.q1('SELECT COUNT(*) c FROM attempts').c === 1);
  N.run(`
    const r = localInsertRun('tsumego_hero','chapter',{chapter_id:1});
    activeRunId = r.run_id;
    localInsertAttempt('tsumego_hero','p1',activeRunId,'wrong',900);
  `);
  await N.runAsync('await tryAutoSync(true)');
  // el antiguo vuelve a sincronizar y recibe lo del nuevo sin duplicar lo suyo
  ok = await O.runAsync('return (async () => { try { await doSync(true); return true; } catch(e){ return false; } })()');
  check('C3: cliente antiguo recibe datos del nuevo', ok === true && O.q1('SELECT COUNT(*) c FROM attempts').c === 2, `c=${O.q1('SELECT COUNT(*) c FROM attempts').c}`);
  const pull2 = await (await fetch(`${SERVER}/sync/pull?since_attempt_id=0&since_run_id=0`)).json();
  check('C3: servidor sigue sin duplicados (2 attempts, 2 runs)', pull2.attempts.length === 2 && pull2.runs.length === 2, JSON.stringify([pull2.attempts.length, pull2.runs.length]));

  console.log('\nRESULTADO COMPAT:', fails.length ? `${fails.length} FALLOS: ${fails.join(' | ')}` : 'TODO OK');
  process.exit(fails.length ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
