#!/usr/bin/env node
/* T8A: verifica que la reescritura estándar (window function rn=1) de las
 * queries con bare columns (GROUP BY ... HAVING id=MAX(id)) devuelve
 * EXACTAMENTE las mismas filas que las originales, sobre una DB sintética con
 * casos límite. Los callers indexan por set_id/chapter_id (bucles for → map),
 * así que el orden de filas es irrelevante: se compara como conjuntos
 * ordenados por clave.
 */
'use strict';
const initSqlJs = require('sql.js');

const CASES = [
  { // cliente 1947 / servidor 446
    name: 'ultimo run cerrado por set (colRuns)',
    old: `SELECT set_id,id,started_at,closed_at,COALESCE(paused_ms,0) AS paused_ms FROM runs WHERE source=? AND status='closed' AND set_id IS NOT NULL AND chapter_id IS NULL GROUP BY set_id HAVING id=MAX(id)`,
    neu: `SELECT set_id,id,started_at,closed_at,paused_ms FROM (SELECT set_id,id,started_at,closed_at,COALESCE(paused_ms,0) AS paused_ms, ROW_NUMBER() OVER (PARTITION BY set_id ORDER BY id DESC) rn FROM runs WHERE source=? AND status='closed' AND set_id IS NOT NULL AND chapter_id IS NULL) WHERE rn=1`,
    params: ['tsumego_hero'], key: r => r.set_id,
  },
  { // cliente 1948 / servidor 456 (equivalente)
    name: 'ultimo run cerrado por capitulo (chapRuns global)',
    old: `SELECT chapter_id,set_id,id,started_at,closed_at,COALESCE(paused_ms,0) AS paused_ms FROM runs WHERE source=? AND status='closed' AND chapter_id IS NOT NULL GROUP BY chapter_id HAVING id=MAX(id)`,
    neu: `SELECT chapter_id,set_id,id,started_at,closed_at,paused_ms FROM (SELECT chapter_id,set_id,id,started_at,closed_at,COALESCE(paused_ms,0) AS paused_ms, ROW_NUMBER() OVER (PARTITION BY chapter_id ORDER BY id DESC) rn FROM runs WHERE source=? AND status='closed' AND chapter_id IS NOT NULL) WHERE rn=1`,
    params: ['tsumego_hero'], key: r => r.chapter_id,
  },
  { // cliente 1988 / servidor 396 (con set_id)
    name: 'ultimo run cerrado por capitulo dentro de un set',
    old: `SELECT chapter_id,id,started_at,closed_at,COALESCE(paused_ms,0) AS paused_ms FROM runs WHERE source=? AND set_id=? AND chapter_id IS NOT NULL AND status='closed' GROUP BY chapter_id HAVING id=MAX(id)`,
    neu: `SELECT chapter_id,id,started_at,closed_at,paused_ms FROM (SELECT chapter_id,id,started_at,closed_at,COALESCE(paused_ms,0) AS paused_ms, ROW_NUMBER() OVER (PARTITION BY chapter_id ORDER BY id DESC) rn FROM runs WHERE source=? AND set_id=? AND chapter_id IS NOT NULL AND status='closed') WHERE rn=1`,
    params: ['tsumego_hero', 1], key: r => r.chapter_id,
  },
  { // servidor 446: solo clave+id → MAX(id) directo (estandar)
    name: 'servidor: ultimo run por set (2 col)',
    old: `SELECT set_id, id FROM runs WHERE source=? AND status='closed' AND set_id IS NOT NULL AND chapter_id IS NULL GROUP BY set_id HAVING id = MAX(id)`,
    neu: `SELECT set_id, MAX(id) AS id FROM runs WHERE source=? AND status='closed' AND set_id IS NOT NULL AND chapter_id IS NULL GROUP BY set_id`,
    params: ['tsumego_hero'], key: r => r.set_id,
  },
  { // servidor 396: idem por capitulo dentro de set
    name: 'servidor: ultimo run por capitulo en set (2 col)',
    old: `SELECT chapter_id, id FROM runs WHERE source=? AND set_id=? AND chapter_id IS NOT NULL AND status='closed' GROUP BY chapter_id HAVING id = MAX(id)`,
    neu: `SELECT chapter_id, MAX(id) AS id FROM runs WHERE source=? AND set_id=? AND chapter_id IS NOT NULL AND status='closed' GROUP BY chapter_id`,
    params: ['tsumego_hero', 1], key: r => r.chapter_id,
  },
  { // servidor 456: set_id es bare column → rn=1
    name: 'servidor: ultimo run por capitulo global (3 col)',
    old: `SELECT chapter_id, set_id, id FROM runs WHERE source=? AND status='closed' AND chapter_id IS NOT NULL GROUP BY chapter_id HAVING id = MAX(id)`,
    neu: `SELECT chapter_id, set_id, id FROM (SELECT chapter_id, set_id, id, ROW_NUMBER() OVER (PARTITION BY chapter_id ORDER BY id DESC) rn FROM runs WHERE source=? AND status='closed' AND chapter_id IS NOT NULL) WHERE rn=1`,
    params: ['tsumego_hero'], key: r => r.chapter_id,
  },
];

(async () => {
  const SQL = await initSqlJs();
  const db = new SQL.Database();
  db.run(`CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT,
    set_id INTEGER, chapter_id INTEGER, vc_id INTEGER, type TEXT, status TEXT,
    total INTEGER, done INTEGER, started_at TEXT, closed_at TEXT, uuid TEXT,
    paused_ms INTEGER, synced INTEGER DEFAULT 0)`);
  // DB sintética con casos límite: varios runs por grupo, open intercalados,
  // paused_ms NULL, otro source, runs de set sin chapter y viceversa,
  // capítulos repartidos entre sets, grupos con un solo run.
  const rows = [
    // [source, set_id, chapter_id, status, started, closed, paused]
    ['tsumego_hero', 1, null, 'closed', 't1', 't2', null],
    ['tsumego_hero', 1, null, 'closed', 't3', 't4', 500],   // gana (id mayor) set 1
    ['tsumego_hero', 1, null, 'open',   't5', null, 0],     // open: fuera
    ['tsumego_hero', 2, null, 'closed', 't6', 't7', 100],   // unico set 2
    ['otro_source',  1, null, 'closed', 't8', 't9', 0],     // otro source: fuera
    ['tsumego_hero', null, 10, 'closed', 'u1', 'u2', null],
    ['tsumego_hero', 1,    10, 'closed', 'u3', 'u4', 42],   // gana chapter 10
    ['tsumego_hero', 1,    11, 'closed', 'u5', 'u6', 0],    // unico chapter 11 (set 1)
    ['tsumego_hero', 2,    12, 'closed', 'u7', 'u8', 7],    // chapter 12 (set 2)
    ['tsumego_hero', 1,    11, 'open',   'u9', null, 0],    // open: fuera
    ['tsumego_hero', null, null, 'closed', 'z1', 'z2', 0],  // sin set ni chapter: fuera de ambas
  ];
  const ins = db.prepare('INSERT INTO runs (source,set_id,chapter_id,status,started_at,closed_at,paused_ms) VALUES (?,?,?,?,?,?,?)');
  for (const r of rows) ins.run(r);
  ins.free();

  function q(sql, params) {
    const st = db.prepare(sql); st.bind(params);
    const out = [];
    while (st.step()) out.push(st.getAsObject());
    st.free(); return out;
  }
  let fails = 0;
  for (const c of CASES) {
    const a = q(c.old, c.params).sort((x, y) => c.key(x) - c.key(y));
    const b = q(c.neu, c.params).sort((x, y) => c.key(x) - c.key(y));
    const same = JSON.stringify(a) === JSON.stringify(b);
    console.log((same ? 'PASS ' : 'FAIL ') + c.name);
    if (!same) { fails++; console.log('  vieja:', JSON.stringify(a)); console.log('  nueva:', JSON.stringify(b)); }
    if (!a.length) { fails++; console.log('FAIL ' + c.name + ' — la query vieja no devolvio filas (fixture inutil)'); }
  }
  console.log(fails ? `\n${fails} FALLOS` : '\nCOMPARACION OK: reescritura equivalente');
  process.exit(fails ? 1 : 0);
})();
