#!/usr/bin/env node
/* T23: valida el código REAL (extraído vía extract_tags.py) de la API local de
 * etiquetas y del filtro por tags de localGetProblems contra un sql.js real.
 * Uso: python3 extract_tags.py && node test_tags.js */
'use strict';
const fs = require('fs');
const vm = require('node:vm');
const initSqlJs = require('sql.js');
const BUNDLE = fs.readFileSync('tags_bundle.js', 'utf8');
const fails = [];
function check(name, cond, extra = '') { console.log((cond ? 'PASS ' : 'FAIL ') + name + (cond ? '' : `  ${extra}`)); if (!cond) fails.push(name); }
(async () => {
  const SQL = await initSqlJs();
  const ctx = { console, db: null };
  vm.createContext(ctx);
  vm.runInContext(BUNDLE, ctx, { filename: 'tags_bundle.js' });
  ctx.db = new SQL.Database();
  ctx.createSchema();
  const run = (c) => vm.runInContext(c, ctx);
  run(`
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar,name) VALUES (1,'th',1,1,1,'A')", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('th','p1',1,1,1,'a')", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('th','p2',1,1,2,'b')", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('th','p3',1,1,3,'c')", []);
  `);
  // ── dominio ──
  check('normTag recorta y colapsa espacios', ctx.normTag('  vida  y   muerte ') === 'vida y muerte');
  check('normTag rechaza vacio y >40 chars', ctx.normTag('   ') === null && ctx.normTag('x'.repeat(41)) === null);
  check('localAddTag crea con synced=0', ctx.localAddTag('ko') === 'ko' && run("dbQueryOne('SELECT synced FROM tags WHERE tag=?',['ko'])").synced === 0);
  check('localAddTag es case-insensitive (devuelve el existente, no duplica)', ctx.localAddTag('KO') === 'ko' && run("dbQueryOne('SELECT COUNT(*) c FROM tags',[])").c === 1);
  ctx.localAddTag('seki'); ctx.localAddTag('Tesuji');
  check('localGetTags ordena sin distinguir mayusculas', JSON.stringify(ctx.localGetTags()) === JSON.stringify(['ko', 'seki', 'Tesuji']), JSON.stringify(ctx.localGetTags()));
  check('localAddTag con nombre invalido devuelve null', ctx.localAddTag('') === null);
  // ── asignaciones ──
  check('problema sin tags -> []', ctx.localGetProblemTags('th', 'p1').length === 0);
  check('asignar devuelve true y crea fila active=1 synced=0', ctx.localSetProblemTag('th', 'p1', 'ko', true) === true
    && JSON.stringify(run("dbQueryOne('SELECT active,synced FROM problem_tags WHERE problem_id=? AND tag=?',['p1','ko'])")) === JSON.stringify({ active: 1, synced: 0 }));
  check('re-asignar lo mismo es no-op (false, no toca updated_at)', ctx.localSetProblemTag('th', 'p1', 'ko', true) === false);
  run("dbExec('UPDATE problem_tags SET synced=1 WHERE problem_id=? AND tag=?',['p1','ko'])");
  const before = run("dbQueryOne('SELECT updated_at FROM problem_tags WHERE problem_id=? AND tag=?',['p1','ko'])").updated_at;
  check('retirar crea tombstone (active=0), vuelve a synced=0 y updated_at estrictamente mayor',
    ctx.localSetProblemTag('th', 'p1', 'ko', false) === true
    && (() => { const r = run("dbQueryOne('SELECT active,synced,updated_at FROM problem_tags WHERE problem_id=? AND tag=?',['p1','ko'])"); return r.active === 0 && r.synced === 0 && r.updated_at > before; })());
  check('tombstone no aparece en localGetProblemTags', ctx.localGetProblemTags('th', 'p1').length === 0);
  ctx.localSetProblemTag('th', 'p1', 'ko', true);
  ctx.localSetProblemTag('th', 'p1', 'seki', true);
  ctx.localSetProblemTag('th', 'p2', 'seki', true);
  check('varias etiquetas por problema, ordenadas', JSON.stringify(ctx.localGetProblemTags('th', 'p1')) === JSON.stringify(['ko', 'seki']));
  check('asignar con tag inexistente lo crea en el dominio (sin huerfanos)', ctx.localSetProblemTag('th', 'p3', 'nuevo', true) === true && ctx.localGetTags().includes('nuevo'));
  check('problem_id numerico se guarda como texto', ctx.localSetProblemTag('th', 42, 'ko', true) === true && run("dbQueryOne('SELECT typeof(problem_id) t FROM problem_tags WHERE problem_id=?',['42'])").t === 'text');
  check('localTagInUse cuenta solo activas', ctx.localTagInUse('seki') === 2 && ctx.localTagInUse('Tesuji') === 0);
  // ── filtro en localGetProblems ──
  const ids = (o) => ctx.localGetProblems('th', o).map(p => p.problem_id);
  check('sin filtro de tags: todos (guardia anti-test-vacuo)', JSON.stringify(ids({})) === JSON.stringify(['p1', 'p2', 'p3']));
  check('tags=[] equivale a sin filtro', JSON.stringify(ids({ tags: [] })) === JSON.stringify(['p1', 'p2', 'p3']));
  check('filtro por un tag', JSON.stringify(ids({ tags: ['ko'] })) === JSON.stringify(['p1']), JSON.stringify(ids({ tags: ['ko'] })));
  check('filtro por varios tags = OR', JSON.stringify(ids({ tags: ['ko', 'nuevo'] })) === JSON.stringify(['p1', 'p3']));
  check('filtro es case-insensitive', JSON.stringify(ids({ tags: ['SEKI'] })) === JSON.stringify(['p1', 'p2']));
  check('filtro AND con el resto (chapter_ids)', JSON.stringify(ids({ tags: ['seki'], chapter_ids: [1] })) === JSON.stringify(['p1', 'p2']) && ids({ tags: ['seki'], chapter_ids: [99] }).length === 0);
  ctx.localSetProblemTag('th', 'p2', 'seki', false);
  check('un tombstone saca al problema del filtro', JSON.stringify(ids({ tags: ['seki'] })) === JSON.stringify(['p1']));
  run("dbExec('UPDATE problems SET hidden=1 WHERE problem_id=?',['p1'])");
  check('problema oculto (T13) no aparece aunque tenga el tag', ids({ tags: ['seki'] }).length === 0);
  console.log('\n' + (fails.length === 0 ? 'TODO OK' : `FALLOS: ${fails.length}`));
  process.exit(fails.length === 0 ? 0 : 1);
})();
