    function makeUUID() {
      return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, c =>
        (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }

    function dbExec(sql, params) { db.run(sql, params); }

    function dbQuery(sql, params) {
      const stmt = db.prepare(sql);
      if (params) stmt.bind(params);
      const rows = [];
      while (stmt.step()) rows.push(stmt.getAsObject());
      stmt.free();
      return rows;
    }

    function dbQueryOne(sql, params) { const rows = dbQuery(sql, params); return rows.length ? rows[0] : null; }

    async function saveDB() { const data = db.export(); await idbSet(DB_KEY, data); }

    function createSchema() {
      db.run(`
    CREATE TABLE IF NOT EXISTS collections (
      source TEXT NOT NULL, set_id INTEGER NOT NULL, name TEXT NOT NULL,
      folder TEXT NOT NULL, difficulty_raw TEXT, difficulty_num INTEGER,
      num_problems INTEGER, on_disk INTEGER NOT NULL DEFAULT 0,
      chapter_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (source, set_id)
    );
    CREATE TABLE IF NOT EXISTS chapters (
      id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
      set_id INTEGER NOT NULL, chapter_num INTEGER NOT NULL,
      diff_min INTEGER, diff_max INTEGER, diff_avg INTEGER, name TEXT,
      problem_count INTEGER NOT NULL DEFAULT 0, mostrar INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS problems (
      source TEXT NOT NULL, problem_id TEXT NOT NULL, set_id INTEGER NOT NULL,
      chapter_id INTEGER, order_in_chapter INTEGER, sgf_path TEXT NOT NULL,
      sgf_exists INTEGER NOT NULL DEFAULT 0, difficulty_raw TEXT,
      difficulty_num INTEGER, color_to_play TEXT, PRIMARY KEY (source, problem_id)
    );
    CREATE TABLE IF NOT EXISTS attempts (
      id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
      problem_id TEXT NOT NULL, run_id INTEGER, result TEXT NOT NULL,
      time_ms INTEGER, created_at TEXT NOT NULL, uuid TEXT
    );
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
      set_id INTEGER, chapter_id INTEGER, vc_id INTEGER,
      type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
      total INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL, closed_at TEXT, uuid TEXT, paused_ms INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS run_items (
      run_id INTEGER NOT NULL, source TEXT NOT NULL,
      problem_id TEXT NOT NULL, order_in_run INTEGER NOT NULL, result TEXT,
      PRIMARY KEY (run_id, problem_id)
    );
    CREATE INDEX IF NOT EXISTS idx_problems_set  ON problems(source, set_id);
    CREATE INDEX IF NOT EXISTS idx_problems_diff ON problems(source, difficulty_num);
    CREATE INDEX IF NOT EXISTS idx_problems_chap ON problems(chapter_id);
    CREATE INDEX IF NOT EXISTS idx_attempts_prob ON attempts(source, problem_id);
    CREATE INDEX IF NOT EXISTS idx_attempts_run  ON attempts(run_id);
    CREATE INDEX IF NOT EXISTS idx_run_items_run ON run_items(run_id);
    CREATE TABLE IF NOT EXISTS game_collections (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      folder TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS games (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      game_collection_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      sgf_path TEXT NOT NULL,
      FOREIGN KEY (game_collection_id) REFERENCES game_collections(id)
    );
    CREATE INDEX IF NOT EXISTS idx_games_collection ON games(game_collection_id);
    CREATE TABLE IF NOT EXISTS sm2_state (
      source      TEXT NOT NULL,
      problem_id  TEXT NOT NULL,
      due_date    TEXT NOT NULL,
      interval    REAL NOT NULL DEFAULT 6,
      easiness    REAL NOT NULL DEFAULT 2.5,
      repetitions INTEGER NOT NULL DEFAULT 0,
      updated_at  TEXT NOT NULL,
      PRIMARY KEY (source, problem_id)
    );
    CREATE INDEX IF NOT EXISTS idx_sm2_updated ON sm2_state(updated_at);
  `);
    }

    function localInsertAttempt(source, problem_id, run_id, result, time_ms) {
      const created_at = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
      const uuid = makeUUID();
      dbExec(`INSERT INTO attempts (source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (?,?,?,?,?,?,?)`,
        [source, problem_id, run_id ?? null, result, time_ms ?? null, created_at, uuid]);
      if (run_id) {
        dbExec(`UPDATE runs SET done=done+1 WHERE id=?`, [run_id]);
        dbExec(`UPDATE runs SET status='closed', closed_at=? WHERE id=? AND done>=total AND status='open'`, [created_at, run_id]);
        dbExec(`UPDATE run_items SET result=? WHERE run_id=? AND problem_id=?`, [result, run_id, problem_id]);
        // SM-2: actualizar estado solo si el intento pertenece a un run (no Free Practice)
        updateSm2(source, problem_id, result);
      }
    }

    function updateSm2(source, problem_id, result) {
      const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
      const today = now.slice(0, 10); // YYYY-MM-DD

      // Leer estado actual o usar valores iniciales
      const row = dbQueryOne(
        'SELECT interval, easiness, repetitions FROM sm2_state WHERE source=? AND problem_id=?',
        [source, problem_id]
      );
      let interval    = row ? row.interval    : 6;
      let easiness    = row ? row.easiness    : 2.5;
      let repetitions = row ? row.repetitions : 0;

      if (result === 'correct') {
        repetitions += 1;
        // Calcular siguiente intervalo con jitter entre intervalo_actual y intervalo_siguiente
        const nextBase = repetitions === 1 ? 6 : Math.round(interval * easiness);
        const nextNext = Math.round(nextBase * easiness);
        // jitter: aleatorio entre nextBase y nextNext (excluido)
        const jitter = nextBase + Math.floor(Math.random() * Math.max(1, nextNext - nextBase));
        interval = jitter;
        // easiness no cambia en acierto (SM-2 estándar la sube levemente, pero lo omitimos para simplicidad)
      } else {
        // Fallo: reinicio completo
        repetitions = 0;
        interval = 1;
        easiness = Math.max(1.3, easiness - 0.2);
      }

      // Calcular due_date
      const due = new Date(today);
      due.setDate(due.getDate() + Math.round(interval));
      const due_date = due.toISOString().slice(0, 10);

      dbExec(`
        INSERT INTO sm2_state (source, problem_id, due_date, interval, easiness, repetitions, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, problem_id) DO UPDATE SET
          due_date    = excluded.due_date,
          interval    = excluded.interval,
          easiness    = excluded.easiness,
          repetitions = excluded.repetitions,
          updated_at  = excluded.updated_at
      `, [source, problem_id, due_date, interval, easiness, repetitions, now]);
    }

   function localInsertRun(source, type, { set_id, chapter_id } = {}) {
	  if (chapter_id && !set_id) { const ch = dbQueryOne('SELECT set_id FROM chapters WHERE id=?', [chapter_id]); if (ch) set_id = ch.set_id; }
	  let rows;
	  if (type === 'chapter' && chapter_id) rows = dbQuery(`SELECT source,problem_id FROM problems WHERE chapter_id=? ORDER BY order_in_chapter`, [chapter_id]);
	  else if (type === 'collection' && set_id) {
		if (filterMostrar) {
		  rows = dbQuery(`SELECT p.source,p.problem_id FROM problems p JOIN chapters ch ON ch.id=p.chapter_id WHERE p.source=? AND p.set_id=? AND ch.mostrar=1 ORDER BY p.order_in_chapter`, [source, set_id]);
		} else {
		  rows = dbQuery(`SELECT source,problem_id FROM problems WHERE source=? AND set_id=? ORDER BY order_in_chapter`, [source, set_id]);
		}
	  } else return null;
	  for (let i = rows.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1));[rows[i], rows[j]] = [rows[j], rows[i]]; }
	  const total = rows.length, uuid = makeUUID();
	  const started_at = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
	  dbExec(`INSERT INTO runs (source,set_id,chapter_id,type,status,total,done,started_at,uuid) VALUES (?,?,?,?,?,?,0,?,?)`,
		[source, set_id ?? null, chapter_id ?? null, type, 'open', total, started_at, uuid]);
	  const run_id = dbQueryOne('SELECT id FROM runs WHERE uuid=?', [uuid])?.id;
	  if (!run_id) { alert('[localInsertRun] INSERT falló: uuid=' + uuid); return null; }
	  for (let order = 0; order < rows.length; order++) {
		dbExec(`INSERT INTO run_items (run_id,source,problem_id,order_in_run) VALUES (?,?,?,?)`, [run_id, rows[order].source, rows[order].problem_id, order + 1]);
	  }
	  return { run_id, total };
	}

	function localUpdateRunStatus(run_id, status) {
      const closed_at = status === 'closed' ? new Date().toISOString().replace(/\.\d+Z$/, 'Z') : null;
      dbExec(`UPDATE runs SET status=?, closed_at=? WHERE id=?`, [status, closed_at, run_id]);
    }

	async function purgeEmptyRuns() {
      const cutoff = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
      const stale = dbQuery(
        `SELECT id FROM runs WHERE started_at < ? AND
         (SELECT COUNT(*) FROM run_items WHERE run_id=runs.id AND result IS NOT NULL) = 0`,
        [cutoff]
      );
      if (!stale.length) return;
      const ids = stale.map(r => r.id);
      const ph = ids.map(() => '?').join(',');
      dbExec(`DELETE FROM run_items WHERE run_id IN (${ph})`, ids);
      dbExec(`DELETE FROM runs WHERE id IN (${ph})`, ids);
      await saveDB();
      try {
        await fetch(`${SYNC_SERVER}/db/runs/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids }),
          signal: AbortSignal.timeout(5000)
        });
      } catch (e) { console.warn('[purgeEmptyRuns] server delete failed', e); }
    }

    async function tryAutoSync(silent = false) {
      if (syncInProgress) return;
      syncInProgress = true;
      if (!silent) setSyncStatus('syncing');
      try { await doSync(silent); setSyncStatus('ok'); }
      catch (e) { setSyncStatus('idle'); }
      finally { syncInProgress = false; }
    }

    async function doSync(lightMode = false) {
      const maxServerAttemptId = dbQueryOne('SELECT MAX(id) AS m FROM attempts WHERE uuid IS NULL', [])?.m || 0;
      const maxServerRunId = dbQueryOne('SELECT MAX(id) AS m FROM runs WHERE uuid IS NULL', [])?.m || 0;
      const pullR = await fetch(`${SYNC_SERVER}/sync/pull?since_attempt_id=${maxServerAttemptId}&since_run_id=${maxServerRunId}`, { signal: AbortSignal.timeout(90000) });
      if (!pullR.ok) throw new Error('pull failed');
      const pulled = await pullR.json();
      const stmtA = db.prepare(`INSERT OR IGNORE INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (?,?,?,?,?,?,?,?)`);
      for (const a of pulled.attempts) stmtA.run([a.id, a.source, a.problem_id, a.run_id, a.result, a.time_ms, a.created_at, a.uuid ?? null]);
      stmtA.free();
      for (const r of pulled.runs) {
        const exists = r.uuid ? dbQueryOne('SELECT id FROM runs WHERE uuid=?', [r.uuid]) : dbQueryOne('SELECT id FROM runs WHERE id=?', [r.id]);
        if (!exists) {
          dbExec(`INSERT OR IGNORE INTO runs (id,source,set_id,chapter_id,vc_id,type,status,total,done,started_at,closed_at,uuid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`,
            [r.id, r.source, r.set_id, r.chapter_id, r.vc_id, r.type, r.status, r.total, r.done, r.started_at, r.closed_at, r.uuid ?? null]);
          for (const ri of (pulled.run_items || []).filter(i => i.run_id === r.id))
            dbExec(`INSERT OR IGNORE INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (?,?,?,?,?)`, [ri.run_id, ri.source, ri.problem_id, ri.order_in_run, ri.result]);
        }
      }
      const newAttempts = dbQuery('SELECT * FROM attempts WHERE uuid IS NOT NULL', []).map(a => ({ ...a, client_id: a.id }));
      const newRuns = dbQuery('SELECT * FROM runs WHERE uuid IS NOT NULL', []).map(r => ({ ...r, run_items: dbQuery('SELECT * FROM run_items WHERE run_id=?', [r.id]) }));
      if (newAttempts.length || newRuns.length) {
        const pushR = await fetch(`${SYNC_SERVER}/sync/push`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ attempts: newAttempts, runs: newRuns }), signal: AbortSignal.timeout(90000) });
        if (!pushR.ok) throw new Error('push failed');
      }
      if (!lightMode) {
        try {
          const vR = await fetch(`${SYNC_SERVER}/sync/static_version`, { signal: AbortSignal.timeout(5000) });
          if (vR.ok) {
            const { version } = await vR.json();
            const localVersion = parseInt(localStorage.getItem('static_version') || '0');
            if (version !== localVersion) {
              const snapR = await fetch(`${SYNC_SERVER}/sync/snapshot`, { signal: AbortSignal.timeout(120000) });
              if (snapR.ok) { importSnapshot(await snapR.json()); localStorage.setItem('static_version', String(version)); }
            }
          }
        } catch (e) { console.warn('[sync] static_version check failed', e); }
        // ── Sync games ──
        try {
          const gR = await fetch(`${SYNC_SERVER}/sync/games`, { signal: AbortSignal.timeout(10000) });
          if (gR.ok) {
            const { game_collections, games } = await gR.json();
            for (const col of game_collections) {
              try { dbExec('INSERT OR IGNORE INTO game_collections (id, name, folder) VALUES (?,?,?)', [col.id, col.name, col.folder]); } catch(e) {}
            }
            for (const g of games) {
              try { dbExec('INSERT OR IGNORE INTO games (id, game_collection_id, name, sgf_path) VALUES (?,?,?,?)', [g.id, g.game_collection_id, g.name, g.sgf_path]); } catch(e) {}
            }
          }
        } catch (e) { console.warn('[sync] games sync failed', e); }
      }
	  // ── Sync mostrar ──
      const chapMostrar = dbQuery('SELECT id, mostrar FROM chapters', []);
      try {
        await fetch(`${SYNC_SERVER}/sync/chapters_mostrar`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chapters: chapMostrar }),
          signal: AbortSignal.timeout(8000)
        });
      } catch (_) { }
      // ── Sync SM-2 ──
      try {
        const lastSm2Sync = localStorage.getItem('last_sm2_sync') || '1970-01-01T00:00:00Z';
        // Pull: recibir estados del servidor más recientes que nuestro cursor
        const sm2PullR = await fetch(`${SYNC_SERVER}/sync/sm2/pull?since=${encodeURIComponent(lastSm2Sync)}`, {
          signal: AbortSignal.timeout(8000)
        });
        if (sm2PullR.ok) {
          const { sm2_state: pulled } = await sm2PullR.json();
          for (const r of pulled) {
            const existing = dbQueryOne(
              'SELECT updated_at FROM sm2_state WHERE source=? AND problem_id=?',
              [r.source, r.problem_id]
            );
            // Solo aplicar si el servidor tiene un estado más reciente
            if (!existing || r.updated_at > existing.updated_at) {
              dbExec(`
                INSERT INTO sm2_state (source, problem_id, due_date, interval, easiness, repetitions, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, problem_id) DO UPDATE SET
                  due_date    = excluded.due_date,
                  interval    = excluded.interval,
                  easiness    = excluded.easiness,
                  repetitions = excluded.repetitions,
                  updated_at  = excluded.updated_at
              `, [r.source, r.problem_id, r.due_date, r.interval, r.easiness, r.repetitions, r.updated_at]);
            }
          }
        }
        // Push: enviar estados modificados desde el último sync
        const pendingSm2 = dbQuery(
          'SELECT * FROM sm2_state WHERE updated_at > ?',
          [lastSm2Sync]
        );
        if (pendingSm2.length > 0) {
          const sm2PushR = await fetch(`${SYNC_SERVER}/sync/sm2/push`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sm2_state: pendingSm2 }),
            signal: AbortSignal.timeout(8000)
          });
          if (sm2PushR.ok) {
            localStorage.setItem('last_sm2_sync', new Date().toISOString().replace(/\.\d+Z$/, 'Z'));
          }
        } else {
          localStorage.setItem('last_sm2_sync', new Date().toISOString().replace(/\.\d+Z$/, 'Z'));
        }
      } catch (e) { console.warn('[sync] sm2 sync failed', e); }
      await saveDB();
    }

	async function syncDeletedRuns() {
      const localRuns = dbQuery(`SELECT id, uuid FROM runs WHERE uuid IS NOT NULL`, []);
      if (!localRuns.length) return;
      const uuids = localRuns.map(r => r.uuid);
      try {
        const r = await fetch(`${SYNC_SERVER}/sync/check_runs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uuids }),
          signal: AbortSignal.timeout(8000)
        });
        if (!r.ok) return;
        const { missing } = await r.json();
        if (!missing.length) return;
        console.log('[syncDeletedRuns] borrando localmente:', missing);
        for (const uuid of missing) {
          const run = dbQueryOne(`SELECT id FROM runs WHERE uuid=?`, [uuid]);
          if (!run) continue;
          dbExec(`DELETE FROM run_items WHERE run_id=?`, [run.id]);
          dbExec(`DELETE FROM runs WHERE id=?`, [run.id]);
        }
        await saveDB();
        console.log('[syncDeletedRuns] borrado completado:', missing.length, 'runs');
      } catch (e) { console.warn('[syncDeletedRuns] failed', e); }
    }