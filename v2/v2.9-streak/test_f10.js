#!/usr/bin/env node
/* F10: valida el código REAL (extraído vía extract_f10.py) de
 * localGetStreak / predictNextInterval contra un sql.js real. */
'use strict';
const fs = require('fs');
const vm = require('node:vm');
const initSqlJs = require('sql.js');

const BUNDLE = fs.readFileSync('f10_bundle.js', 'utf8');
const fails = [];
function check(name, cond, extra = '') {
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (cond ? '' : `  ${extra}`));
  if (!cond) fails.push(name);
}

(async () => {
  const SQL = await initSqlJs();
  const db = new SQL.Database();
  db.run(`CREATE TABLE attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, problem_id TEXT NOT NULL,
    run_id INTEGER, result TEXT NOT NULL, time_ms INTEGER, created_at TEXT NOT NULL, uuid TEXT)`);
  db.run(`CREATE TABLE sm2_state (
    source TEXT NOT NULL, problem_id TEXT NOT NULL, due_date TEXT NOT NULL,
    interval REAL NOT NULL DEFAULT 6, easiness REAL NOT NULL DEFAULT 2.5,
    repetitions INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
    PRIMARY KEY (source, problem_id))`);

  function insertAttempt(pid, result, runId, ts) {
    db.run(`INSERT INTO attempts (source,problem_id,run_id,result,time_ms,created_at) VALUES (?,?,?,?,?,?)`,
      ['tsumego_hero', pid, runId, result, 1000, ts]);
  }

  const ctx = { db, console };
  vm.createContext(ctx);
  vm.runInContext(BUNDLE, ctx, { filename: 'f10_bundle.js' });

  // ── localGetStreak ──

  // p1: correct, correct, correct (mas reciente al final) -> streak=3
  insertAttempt('p1', 'wrong', 1, '2026-08-01T10:00:00Z');
  insertAttempt('p1', 'correct', 1, '2026-08-02T10:00:00Z');
  insertAttempt('p1', 'correct', 2, '2026-08-03T10:00:00Z');
  insertAttempt('p1', 'correct', null, '2026-08-04T10:00:00Z'); // Free Practice: SI cuenta para el streak
  check('streak cuenta 3 aciertos seguidos (incluye uno de Free Practice)',
    ctx.localGetStreak('tsumego_hero', 'p1') === 3);

  // p2: el ultimo intento es wrong -> streak=0, aunque antes haya aciertos
  insertAttempt('p2', 'correct', 1, '2026-08-01T10:00:00Z');
  insertAttempt('p2', 'correct', 1, '2026-08-02T10:00:00Z');
  insertAttempt('p2', 'wrong', 1, '2026-08-03T10:00:00Z');
  check('streak=0 si el ultimo intento fue wrong (aunque antes hubiera aciertos)',
    ctx.localGetStreak('tsumego_hero', 'p2') === 0);

  // p3: nunca intentado -> streak=0
  check('streak=0 para problema sin intentos', ctx.localGetStreak('tsumego_hero', 'p3') === 0);

  // p4: un solo acierto -> streak=1
  insertAttempt('p4', 'correct', 1, '2026-08-01T10:00:00Z');
  check('streak=1 con un unico acierto', ctx.localGetStreak('tsumego_hero', 'p4') === 1);

  // otro source no se mezcla
  insertAttempt('p1', 'correct', 1, '2026-08-01T09:00:00Z');
  check('streak no mezcla sources distintos con el mismo problem_id',
    ctx.localGetStreak('other_source', 'p1') === 0);

  // ── predictNextInterval ──

  // Sin fila en sm2_state: usa defaults (interval=6, easiness=2.5, repetitions=0)
  // -> repetitions_next=1 -> nextBase=6 (fijo), nextNext=round(6*2.5)=15 -> rango 6-14
  const predNew = ctx.predictNextInterval('tsumego_hero', 'never_tracked');
  check('prediccion sin sm2_state previo usa defaults (6-14d, primera repeticion)',
    predNew.min === 6 && predNew.max === 14, JSON.stringify(predNew));

  // Con fila existente: repetitions=2, interval=10, easiness=2.5
  // -> repetitions_next=3 (!=1) -> nextBase=round(10*2.5)=25, nextNext=round(25*2.5)=63 -> rango 25-62
  db.run(`INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at)
          VALUES ('tsumego_hero','p10','2026-08-05',10,2.5,2,'2026-07-01T00:00:00Z')`);
  const predExisting = ctx.predictNextInterval('tsumego_hero', 'p10');
  check('prediccion con historial replica nextBase/nextNext de updateSm2 (25-62d)',
    predExisting.min === 25 && predExisting.max === 62, JSON.stringify(predExisting));

  // Caso limite: interval y easiness bajos con repetitions_next != 1 (para no
  // caer en la rama fija de 6) hacen que round(nextBase*easiness) <= nextBase
  // -> el rango colapsa a un unico valor en vez de min>max.
  db.run(`INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at)
          VALUES ('tsumego_hero','p11','2026-08-05',1,1.3,1,'2026-07-01T00:00:00Z')`);
  const predLowEase = ctx.predictNextInterval('tsumego_hero', 'p11');
  check('con easiness baja el rango colapsa a min===max (no min>max)',
    predLowEase.min === predLowEase.max, JSON.stringify(predLowEase));
  check('el valor colapsado sigue siendo positivo', predLowEase.min > 0);

  console.log('\n' + (fails.length === 0 ? 'TODO OK' : `FALLOS: ${fails.length}`));
  process.exit(fails.length === 0 ? 0 : 1);
})();
