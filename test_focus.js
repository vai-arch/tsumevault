#!/usr/bin/env node
/* FC2: valida el código REAL (extraído vía extract_focus.py) de la API local de
 * Focus contra un sql.js real: Focus, capítulos, estados calculados, archivado,
 * sesiones, % por primer intento y "pendiente hoy".
 * Uso: python3 extract_focus.py && node test_focus.js */
'use strict';
const fs = require('fs');
const vm = require('node:vm');
const nodeCrypto = require('crypto');
const initSqlJs = require('sql.js');
const BUNDLE = fs.readFileSync('focus_bundle.js', 'utf8');
const fails = [];
function check(name, cond, extra = '') { console.log((cond ? 'PASS ' : 'FAIL ') + name + (cond ? '' : `  ${extra}`)); if (!cond) fails.push(name); }
(async () => {
  const SQL = await initSqlJs();
  const ctx = { console, db: null, crypto: { getRandomValues: (a) => nodeCrypto.randomFillSync(a) } };
  vm.createContext(ctx);
  vm.runInContext(BUNDLE, ctx, { filename: 'focus_bundle.js' });
  ctx.db = new SQL.Database();
  ctx.createSchema();
  const run = (c) => vm.runInContext(c, ctx);
  const q1 = (sql, p = []) => ctx.dbQueryOne(sql, p);
  const J = (x) => JSON.stringify(x);
  run(`
    dbExec("INSERT INTO collections (source,set_id,name,folder) VALUES ('th',1,'Col A','a'),('gj',2,'Col B','b')", []);
    dbExec("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar,name) VALUES (1,'th',1,1,0,'Uno'),(2,'th',1,2,0,'Dos'),(3,'th',1,3,0,'Tres'),(4,'th',1,4,0,'Cuatro'),(5,'gj',2,1,0,'Cinco')", []);
    dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('th','p1',1,1,1,'a'),('th','p2',1,1,2,'b'),('th','p3',1,2,1,'c'),('th','p4',1,3,1,'d'),('th','p5',1,1,3,'e'),('gj','g1',2,5,1,'f')", []);
    dbExec("UPDATE problems SET hidden=1 WHERE problem_id='p5'", []);
  `);

  // ── nombre / crear / renombrar ──
  check('focusNorm recorta y colapsa espacios', ctx.focusNorm('  Corner   patterns ') === 'Corner patterns');
  check('focusNorm rechaza vacío y >60', ctx.focusNorm('   ') === null && ctx.focusNorm('x'.repeat(61)) === null && ctx.focusNorm('x'.repeat(60)) !== null);
  const cF = ctx.localFocusCreate(' Corner  patterns ');
  check('crear Focus: ok, nombre normalizado, synced=0', cF.ok && q1('SELECT name, synced, archived, deleted FROM focus WHERE uuid=?', [cF.uuid])?.name === 'Corner patterns'
    && q1('SELECT synced FROM focus WHERE uuid=?', [cF.uuid]).synced === 0);
  const F = cF.uuid;
  check('crear con nombre repetido (sin distinguir mayúsculas) → duplicate', ctx.localFocusCreate('corner PATTERNS').error === 'duplicate');
  check('crear con nombre inválido → invalid', ctx.localFocusCreate('  ').error === 'invalid');
  const G = ctx.localFocusCreate('Lateral').uuid;
  const H = ctx.localFocusCreate('Vacío').uuid;
  check('localFocusList ordena por nombre', J(ctx.localFocusList(false).map(f => f.name)) === J(['Corner patterns', 'Lateral', 'Vacío']));
  check('renombrar a un nombre ya usado → duplicate', ctx.localFocusRename(G, 'CORNER patterns').error === 'duplicate');
  run(`dbExec("UPDATE focus SET synced=1 WHERE uuid=?", ['${G}'])`);
  const gBefore = q1('SELECT updated_at FROM focus WHERE uuid=?', [G]).updated_at;
  check('renombrar: ok, synced=0 y updated_at estrictamente mayor', ctx.localFocusRename(G, 'Lateral patterns').ok
    && (() => { const r = q1('SELECT name, synced, updated_at FROM focus WHERE uuid=?', [G]); return r.name === 'Lateral patterns' && r.synced === 0 && r.updated_at > gBefore; })());
  run(`dbExec("UPDATE focus SET synced=1 WHERE uuid=?", ['${G}'])`);
  check('renombrar al mismo nombre no toca la fila (sigue synced=1)', ctx.localFocusRename(G, ' Lateral  patterns').ok && q1('SELECT synced FROM focus WHERE uuid=?', [G]).synced === 1);

  // ── capítulos ──
  check('añadir capítulo inexistente → no_chapter', ctx.localFocusAddChapter(F, 99).error === 'no_chapter');
  check('añadir capítulo: ok (en trabajo, synced=0)', ctx.localFocusAddChapter(F, 1).ok
    && J(q1('SELECT promoted, active, synced FROM focus_chapters WHERE focus_uuid=? AND chapter_id=1', [F])) === J({ promoted: 0, active: 1, synced: 0 }));
  ctx.localFocusAddChapter(F, 2);
  ctx.localFocusAddChapter(F, 5);   // otra source: válido
  check('un capítulo solo puede estar en un Focus (mismo u otro) → in_focus',
    ctx.localFocusAddChapter(F, 1).error === 'in_focus' && ctx.localFocusAddChapter(G, 1).error === 'in_focus');
  check('localFocusOfChapter devuelve el Focus del capítulo (y null si está libre)',
    ctx.localFocusOfChapter(1)?.uuid === F && ctx.localFocusOfChapter(3) === null);
  check('localFocusChapterMap cubre todos los capítulos en Focus', (() => { const m = ctx.localFocusChapterMap(); return m.size === 3 && m.get(5).name === 'Corner patterns'; })());
  check('sacar capítulo: ok y queda libre (active=0, no se borra la fila)', ctx.localFocusRemoveChapter(F, 5).ok
    && ctx.localFocusOfChapter(5) === null && q1('SELECT active FROM focus_chapters WHERE focus_uuid=? AND chapter_id=5', [F]).active === 0);
  check('sacar un capítulo que no es miembro → not_member', ctx.localFocusRemoveChapter(F, 5).error === 'not_member');
  check('un capítulo sacado puede entrar en otro Focus', ctx.localFocusAddChapter(G, 5).ok && ctx.localFocusOfChapter(5)?.uuid === G);
  const chF = ctx.localFocusChapters(F);
  check('localFocusChapters: estado work, nombres, cross-source y problemas visibles (oculto excluido)',
    J(chF.map(c => [c.chapter_id, c.state, c.chapter_name, c.collection_name, c.problems, c.missing])) === J([[2, 'work', 'Dos', 'Col A', 1, false], [1, 'work', 'Uno', 'Col A', 2, false]]),
    J(chF));

  // ── promoción (estados calculados) ──
  const pr = ctx.localFocusSetPromoted(F, 2, true);
  check('promocionar sin Run completo → ready', pr.ok && pr.state === 'ready');
  check('promocionar activa show y lo deja pendiente de sync', J(q1('SELECT mostrar, mostrar_synced FROM chapters WHERE id=2')) === J({ mostrar: 1, mostrar_synced: 0 }));
  run(`
    dbExec("INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,uuid) VALUES (10,'th',1,NULL,'collection','closed',1,1,'2026-11-01T10:00:00Z','r-col')", []);
    dbExec("INSERT INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (10,'th','p3',1,'correct')", []);
    dbExec("INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,uuid) VALUES (11,'th',1,2,'chapter','closed',2,1,'2026-11-01T10:00:00Z','r-half')", []);
    dbExec("INSERT INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (11,'th','p3',1,'correct'),(11,'th','p9',2,NULL)", []);
  `);
  check('un Run de colección o un Run de capítulo a medias NO lo promocionan (sigue ready)',
    ctx.localFocusChapters(F).find(c => c.chapter_id === 2).state === 'ready');
  const ac = ctx.localFocusArchiveCheck(F);
  check('archivar con capítulos ready → bloqueado (y nada cambia)', ctx.localFocusArchive(F).error === 'ready'
    && ac.ready.length === 1 && q1('SELECT archived FROM focus WHERE uuid=?', [F]).archived === 0);
  run(`
    dbExec("INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,uuid) VALUES (12,'th',1,2,'chapter','closed',1,1,'2026-11-02T10:00:00Z','r-full')", []);
    dbExec("INSERT INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (12,'th','p3',1,'wrong')", []);
  `);
  check('con un Run de capítulo completo (aunque con fallos) → promoted', ctx.localFocusChapters(F).find(c => c.chapter_id === 2).state === 'promoted');
  run(`dbExec("DELETE FROM run_items WHERE run_id=12", []); dbExec("DELETE FROM runs WHERE id=12", [])`);
  check('si se borra ese Run vuelve sola a ready', ctx.localFocusChapters(F).find(c => c.chapter_id === 2).state === 'ready');
  const dm = ctx.localFocusSetPromoted(F, 2, false);
  check('devolver a En trabajo: work, y show NO se toca', dm.ok && dm.state === 'work' && q1('SELECT mostrar FROM chapters WHERE id=2').mostrar === 1);
  run(`
    dbExec("INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,uuid) VALUES (13,'th',1,1,'chapter','closed',2,2,'2026-11-02T10:00:00Z','r-ch1')", []);
    dbExec("INSERT INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (13,'th','p1',1,'correct'),(13,'th','p2',2,'correct')", []);
  `);
  check('promocionar un capítulo que YA tiene Run completo → promoted directo', ctx.localFocusSetPromoted(F, 1, true).state === 'promoted');
  ctx.localFocusSetPromoted(F, 1, false);

  // ── sesiones y % (primer intento) ──
  run(`dbExec("INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path) VALUES ('th','p6',1,2,2,'g')", [])`);
  const sp = ctx.localFocusSessionProblems(F).map(p => p.problem_id).sort();
  check('problemas de sesión = visibles de los capítulos En trabajo', J(sp) === J(['p1', 'p2', 'p3', 'p6']), J(sp));
  const S1 = ctx.localFocusSessionStart(F);
  check('iniciar sesión crea la fila (no completada, synced=0)', J(q1('SELECT completed, ended_at, synced FROM focus_sessions WHERE uuid=?', [S1])) === J({ completed: 0, ended_at: null, synced: 0 }));
  run(`
    localInsertAttempt('th', 'p1', null, 'wrong', 100, '${S1}');
    localInsertAttempt('th', 'p1', null, 'correct', 100, '${S1}');
    localInsertAttempt('th', 'p2', null, 'correct', 100, '${S1}');
    localInsertAttempt('th', 'p3', null, 'correct', 100, '${S1}');
    localInsertAttempt('th', 'p6', null, 'wrong', 100, '${S1}');
    localInsertAttempt('th', 'p3', null, 'wrong', 100);
  `);
  const st1 = ctx.localFocusSessionStats(S1);
  check('% de sesión: cuenta el PRIMER intento de cada problema e ignora intentos fuera de la sesión',
    J(st1) === J({ total: 4, ok: 2, pct: 50 }), J(st1));
  check('una sesión no completada no cuenta para el progreso', ctx.localFocusProgress(F).last === null);
  check('completar sesión: true; repetir: false', ctx.localFocusSessionComplete(S1) === true && ctx.localFocusSessionComplete(S1) === false
    && q1('SELECT completed FROM focus_sessions WHERE uuid=?', [S1]).completed === 1);
  run(`dbExec("UPDATE focus_sessions SET ended_at='2026-11-01T10:00:00Z' WHERE uuid=?", ['${S1}'])`);   // S1 en el pasado: orden determinista
  ctx.localFocusSetPromoted(F, 2, true);          // ch2 sale de las próximas sesiones
  ctx.localFocusAddChapter(F, 3);                 // ch3 entra después de S1
  const S2 = ctx.localFocusSessionStart(F);
  run(`
    localInsertAttempt('th', 'p1', null, 'correct', 100, '${S2}');
    localInsertAttempt('th', 'p2', null, 'correct', 100, '${S2}');
    localInsertAttempt('th', 'p4', null, 'wrong', 100, '${S2}');
  `);
  ctx.localFocusSessionComplete(S2);
  const prog = ctx.localFocusProgress(F);
  check('progreso: % del Focus = última sesión completada', J(prog.last) === J({ ok: 2, total: 3, pct: 67 }), J(prog.last));
  check('progreso por capítulo = última sesión completada que lo incluyó',
    J(prog.byChapter) === J({ 1: { ok: 2, total: 2, pct: 100 }, 2: { ok: 1, total: 2, pct: 50 }, 3: { ok: 0, total: 1, pct: 0 } }), J(prog.byChapter));
  // FC9: % de la tarjeta = capítulos En trabajo ahora, con su última sesión; cada problema pesa igual
  {
    const wp = (u) => ctx.localFocusWorkPct(ctx.localFocusChapters(u), ctx.localFocusProgress(u));
    check('FC9: % de tarjeta = En trabajo actuales (ch1 2/2 + ch3 0/1 = 2/3); el promocionado ch2 no cuenta',
      J(wp(F)) === J({ ok: 2, total: 3, pct: 67 }), J(wp(F)));
    ctx.localFocusSetPromoted(F, 3, true);
    check('FC9: al promocionar un capítulo sale del % en el acto (solo ch1 → 100%)', J(wp(F)) === J({ ok: 2, total: 2, pct: 100 }), J(wp(F)));
    ctx.localFocusSetPromoted(F, 3, false);
    ctx.localFocusSetPromoted(F, 2, false);
    check('FC9: devolverlo a En trabajo lo vuelve a sumar con su última sesión (ch2 1/2) y pesa por problema',
      J(wp(F)) === J({ ok: 3, total: 5, pct: 60 }), J(wp(F)));
    ctx.localFocusSetPromoted(F, 2, true);
    check('FC9: un Focus sin sesiones → pct null', ctx.localFocusWorkPct(ctx.localFocusChapters(G), ctx.localFocusProgress(G)).pct === null);
  }
  check('capítulo sin sesiones completadas → sin entrada en byChapter', ctx.localFocusAddChapter(F, 4).ok && !(4 in ctx.localFocusProgress(F).byChapter));

  // ── pendiente hoy ──
  const t1 = ctx.localFocusTodayStatus();
  const byName = (n) => t1.find(x => x.name === n);
  check('Focus con sesión completada hoy → no pendiente', byName('Corner patterns').doneToday === true && byName('Corner patterns').pending === false);
  check('Focus con capítulos en trabajo y sin sesión hoy → pendiente', byName('Lateral patterns').pending === true && byName('Lateral patterns').work === 1);
  check('Focus sin capítulos en trabajo → no pendiente', byName('Vacío').work === 0 && byName('Vacío').pending === false);
  run(`dbExec("UPDATE focus_sessions SET ended_at=? WHERE uuid=?", [new Date(Date.now() - 36 * 3600 * 1000).toISOString().replace(/\\.\\d+Z$/, 'Z'), '${S2}'])`);
  check('sesión completada ayer → vuelve a estar pendiente hoy', ctx.localFocusTodayStatus().find(x => x.name === 'Corner patterns').pending === true);

  // ── capítulo desaparecido (reimportación) ──
  run(`dbExec("INSERT INTO focus_chapters (focus_uuid,chapter_id,promoted,active,updated_at,synced) VALUES (?,777,0,1,'2026-11-01T00:00:00Z',1)", ['${G}'])`);
  const gm = ctx.localFocusChapters(G).find(c => c.chapter_id === 777);
  check('capítulo que ya no existe → missing=true (se avisa, no falla)', gm && gm.missing === true && gm.state === 'work');
  check('un capítulo desaparecido no entra en la sesión ni cuenta como trabajo pendiente',
    ctx.localFocusSessionProblems(G).every(p => p.chapter_id === 5) && ctx.localFocusTodayStatus().find(x => x.name === 'Lateral patterns').work === 1);

  // ── archivar / reabrir ──
  ctx.localFocusSetPromoted(F, 3, true);
  run(`
    dbExec("INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,uuid) VALUES (14,'th',1,2,'chapter','closed',2,2,'2026-11-02T11:00:00Z','r-ch2'),(15,'th',1,3,'chapter','closed',1,1,'2026-11-02T11:00:00Z','r-ch3')", []);
    dbExec("INSERT INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (14,'th','p3',1,'correct'),(14,'th','p6',2,'correct'),(15,'th','p4',1,'correct')", []);
  `);
  const arch = ctx.localFocusArchive(F);
  check('archivar: libera los En trabajo (1 y 4) y conserva los Promocionados (2 y 3)', arch.ok
    && J(arch.freed.map(c => c.chapter_id).sort()) === J([1, 4])
    && ctx.localFocusOfChapter(1) === null && ctx.localFocusOfChapter(2)?.uuid === F && ctx.localFocusOfChapter(2)?.archived === 1, J(arch));
  check('archivado: fuera de la lista diaria, dentro con includeArchived', !ctx.localFocusList(false).some(f => f.uuid === F) && ctx.localFocusList(true).some(f => f.uuid === F));
  check('archivado: fuera de "pendiente hoy"', !ctx.localFocusTodayStatus().some(x => x.uuid === F));
  check('un Promocionado de un Focus archivado no puede entrar en otro', ctx.localFocusAddChapter(G, 2).error === 'in_focus');
  check('un En trabajo liberado sí puede entrar en otro', ctx.localFocusAddChapter(G, 1).ok);
  check('en un Focus archivado no se puede añadir, sacar ni promocionar',
    ctx.localFocusAddChapter(F, 3).error === 'not_active' && ctx.localFocusRemoveChapter(F, 2).error === 'not_active' && ctx.localFocusSetPromoted(F, 2, false).error === 'not_active');
  check('no se inicia sesión en un Focus archivado', ctx.localFocusSessionStart(F) === null);
  check('reabrir: vuelve a la lista con sus Promocionados', ctx.localFocusReopen(F).ok && ctx.localFocusList(false).some(f => f.uuid === F)
    && J(ctx.localFocusChapters(F).map(c => [c.chapter_id, c.state])) === J([[2, 'promoted'], [3, 'promoted']]));
  check('reabrir uno no archivado → not_archived', ctx.localFocusReopen(F).error === 'not_archived');

  // ── borrar ──
  check('borrar un Focus con sesiones → has_sessions', ctx.localFocusDelete(F).error === 'has_sessions');
  ctx.localFocusAddChapter(H, 4);
  check('borrar un Focus sin sesiones: ok, sale de la lista y libera sus capítulos', ctx.localFocusDelete(H).ok
    && !ctx.localFocusList(true).some(f => f.uuid === H) && ctx.localFocusOfChapter(4) === null
    && q1('SELECT deleted, synced FROM focus WHERE uuid=?', [H]).deleted === 1);
  check('el nombre de un Focus borrado se puede reutilizar', ctx.localFocusCreate('Vacío').ok);
  check('no se escriben filas sin updated_at (todas las escrituras dejan synced=0 con fecha)',
    q1('SELECT COUNT(*) c FROM focus_chapters WHERE updated_at IS NULL OR updated_at=\'\'').c === 0);

  console.log('\n' + (fails.length === 0 ? 'TODO OK' : `FALLOS: ${fails.length}`));
  process.exit(fails.length === 0 ? 0 : 1);
})();
