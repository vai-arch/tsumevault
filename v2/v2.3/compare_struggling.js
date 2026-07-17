#!/usr/bin/env node
/* T12/R12-P3: verifica que la reescritura de localGetStruggling (una query con
 * window function) es equivalente a la implementación N+1 original, sobre una
 * DB sintética con casos límite. El caller envuelve el resultado en Set →
 * se compara como CONJUNTOS. Nota sobre empates de created_at: el orden entre
 * empatados ya era indefinido en la versión vieja (ORDER BY created_at DESC
 * con LIMIT); los casos de empate del fixture están diseñados para que el
 * veredicto sea invariante al orden elegido. */
'use strict';
const initSqlJs = require('sql.js');

(async () => {
  const SQL = await initSqlJs();
  const db = new SQL.Database();
  // soporte de window functions
  try { db.exec('SELECT ROW_NUMBER() OVER (ORDER BY 1)'); }
  catch (e) { console.error('FATAL: sql.js sin window functions'); process.exit(2); }

  db.run(`CREATE TABLE problems (source TEXT, problem_id TEXT, set_id INTEGER, chapter_id INTEGER);
          CREATE TABLE attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, problem_id TEXT,
            run_id INTEGER, result TEXT, time_ms INTEGER, created_at TEXT, uuid TEXT, synced INTEGER DEFAULT 0);`);

  const P = [ // [pid, set, chap]
    ['p_solo_ok', 1, 10], ['p_solo_ko', 1, 10], ['p_mix_reciente_ko', 1, 11],
    ['p_ko_antiguo_fuera_de_n', 1, 11], ['p_sin_intentos', 1, 10],
    ['p_pocos_intentos_ko', 2, 20], ['p_empate_mismo_resultado', 2, 20],
    ['p_empate_distinto_resultado_n_grande', 2, 21], ['p_otro_source', 1, 10],
  ];
  for (const [pid, s, c] of P) db.run('INSERT INTO problems VALUES (?,?,?,?)', [pid === 'p_otro_source' ? 'otro' : 'th', pid, s, c]);

  const A = [ // [pid, result, created_at]  (n=3 por defecto)
    ['p_solo_ok', 'correct', 't1'], ['p_solo_ok', 'correct', 't2'], ['p_solo_ok', 'correct', 't3'], ['p_solo_ok', 'wrong', 't0'], // wrong antiguo fuera de los 3 ultimos
    ['p_solo_ko', 'wrong', 't1'], ['p_solo_ko', 'wrong', 't2'],
    ['p_mix_reciente_ko', 'correct', 't1'], ['p_mix_reciente_ko', 'wrong', 't3'], ['p_mix_reciente_ko', 'correct', 't2'],
    ['p_ko_antiguo_fuera_de_n', 'wrong', 't0'], ['p_ko_antiguo_fuera_de_n', 'correct', 't1'], ['p_ko_antiguo_fuera_de_n', 'correct', 't2'], ['p_ko_antiguo_fuera_de_n', 'correct', 't3'],
    ['p_pocos_intentos_ko', 'wrong', 't1'],
    // empates: mismo created_at, MISMO resultado → veredicto invariante al orden
    ['p_empate_mismo_resultado', 'wrong', 'tX'], ['p_empate_mismo_resultado', 'wrong', 'tX'], ['p_empate_mismo_resultado', 'correct', 'tX'], ['p_empate_mismo_resultado', 'correct', 't9'],
    // empates con resultados distintos pero n >= total intentos → LIMIT no corta el grupo
    ['p_empate_distinto_resultado_n_grande', 'wrong', 'tY'], ['p_empate_distinto_resultado_n_grande', 'correct', 'tY'],
    ['p_otro_source', 'wrong', 't1'],
  ];
  for (const [pid, r, t] of A) db.run('INSERT INTO attempts (source,problem_id,result,created_at) VALUES (?,?,?,?)',
    [pid === 'p_otro_source' ? 'otro' : 'th', pid, r, t]);

  function q(sql, params) { const st = db.prepare(sql); st.bind(params); const out = []; while (st.step()) out.push(st.getAsObject()); st.free(); return out; }

  // ── implementación VIEJA (copiada literal de localGetStruggling) ──
  function oldImpl(source, { set_id, chapter_id } = {}, n = 3) {
    let sql = 'SELECT problem_id FROM problems WHERE source=?';
    const params = [source];
    if (chapter_id) { sql += ' AND chapter_id=?'; params.push(chapter_id); }
    else if (set_id) { sql += ' AND set_id=?'; params.push(set_id); }
    const probs = q(sql, params).map(r => r.problem_id);
    const struggling = [];
    for (const pid of probs) {
      const rows = q('SELECT result FROM attempts WHERE source=? AND problem_id=? ORDER BY created_at DESC LIMIT ?', [source, pid, n]);
      if (rows.length && rows.some(r => r.result === 'wrong')) struggling.push(pid);
    }
    return struggling;
  }

  // ── implementación NUEVA (la query que se instalará en el cliente) ──
  function newImpl(source, { set_id, chapter_id } = {}, n = 3) {
    let scope = '';
    const params = [source];
    if (chapter_id) { scope = ' AND p.chapter_id=?'; params.push(chapter_id); }
    else if (set_id) { scope = ' AND p.set_id=?'; params.push(set_id); }
    params.push(n);
    return q(`
      WITH ranked AS (
        SELECT a.problem_id, a.result,
               ROW_NUMBER() OVER (PARTITION BY a.problem_id ORDER BY a.created_at DESC, a.id DESC) rn
        FROM attempts a
        JOIN problems p ON p.source = a.source AND p.problem_id = a.problem_id
        WHERE a.source = ?${scope}
      )
      SELECT problem_id FROM ranked WHERE rn <= ?
      GROUP BY problem_id
      HAVING SUM(result = 'wrong') > 0`, params).map(r => r.problem_id);
  }

  const CASES = [
    ['sin filtro n=3', 'th', {}, 3],
    // n=1 solo sobre scope SIN problemas de empate: con LIMIT cortando un grupo
    // de created_at empatados con resultados mixtos, la implementacion VIEJA ya
    // era no determinista (elige filas arbitrarias entre empatadas); asertar ahi
    // seria asertar sobre comportamiento indefinido. La nueva es determinista
    // (desempata por id DESC), lo cual es una mejora, no una regresion.
    ['set_id=1 n=1 (sin empates)', 'th', { set_id: 1 }, 1],
    ['sin filtro n=10 (mas que intentos)', 'th', {}, 10],
    ['set_id=1', 'th', { set_id: 1 }, 3],
    ['set_id=2', 'th', { set_id: 2 }, 3],
    ['chapter_id=11 (prioridad sobre set)', 'th', { set_id: 999, chapter_id: 11 }, 3],
    ['otro source', 'otro', {}, 3],
    ['source sin datos', 'nada', {}, 3],
  ];
  let fails = 0;
  for (const [name, src, f, n] of CASES) {
    const a = new Set(oldImpl(src, f, n));
    const b = new Set(newImpl(src, f, n));
    const same = a.size === b.size && [...a].every(x => b.has(x));
    console.log((same ? 'PASS ' : 'FAIL ') + name + (same ? '' : `  vieja={${[...a]}} nueva={${[...b]}}`));
    if (!same) fails++;
  }
  console.log(fails ? `\n${fails} FALLOS` : '\nCOMPARACION OK: struggling equivalente');
  process.exit(fails ? 1 : 0);
})();
