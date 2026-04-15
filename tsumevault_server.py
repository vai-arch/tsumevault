"""
tsumevault_server.py — Servidor API para TsumeVault.

Uso:
    python tsumevault_server.py [puerto]

Por defecto puerto: 3002
DB: tsumeVault.db (mismo directorio que este script)

Endpoints:
    GET  /db/collections
    GET  /db/chapters?set_id=X&source=X
    GET  /db/problems?chapter_id=X
    GET  /db/problem?source=X&problem_id=Y
    GET  /db/runs?source=X&status=X
    GET  /db/run/items?run_id=X
    GET  /db/last_run_stats?source=X&set_id=X
    GET  /db/last_run_stats_all?source=X
    GET  /db/struggling?source=X[&set_id=X][&chapter_id=X]
    POST /db/attempt   { source, problem_id, run_id?, result, time_ms? }
    POST /db/run       { source, set_id?, chapter_id?, vc_id?, type }
    PUT  /db/run       { id, status? }
"""

import sys
import os
import json
import random
import sqlite3
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORT       = int(sys.argv[1]) if len(sys.argv) > 1 else 3002
DB_PATH    = os.path.join(SCRIPT_DIR, 'tsumeVault.db')
# ─────────────────────────────────────────────────────────────────────────────

def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def rows_to_list(rows):
    return [dict(r) for r in rows]


# ── Migration ────────────────────────────────────────────────────────────────

def migrate_db():
     with db_connect() as con:
         cols = [r[1] for r in con.execute("PRAGMA table_info(runs)").fetchall()]
         if 'uuid' not in cols:
             con.execute("ALTER TABLE runs ADD COLUMN uuid TEXT")
             con.commit()
             print("[migrate] Columna uuid añadida a runs.")
         cols_a = [r[1] for r in con.execute("PRAGMA table_info(attempts)").fetchall()]
         if 'uuid' not in cols_a:
             con.execute("ALTER TABLE attempts ADD COLUMN uuid TEXT")
             con.commit()
             print("[migrate] Columna uuid añadida a attempts.")

# ── GET handlers ──────────────────────────────────────────────────────────────

def handle_get_collections(qs):
    source = qs.get('source', ['tsumego_hero'])[0]
    with db_connect() as con:
        rows = con.execute("""
            SELECT c.*,
                   COALESCE(s.total_attempts, 0) AS total_attempts,
                   COALESCE(s.total_correct,  0) AS total_correct
            FROM collections c
            LEFT JOIN (
                SELECT p.source, p.set_id,
                       SUM(a.total_attempts) AS total_attempts,
                       SUM(a.total_correct)  AS total_correct
                FROM problems p
                LEFT JOIN problem_stats a USING (source, problem_id)
                GROUP BY p.source, p.set_id
            ) s ON c.source = s.source AND c.set_id = s.set_id
            WHERE c.source = ?
            ORDER BY c.difficulty_num ASC NULLS LAST, c.name ASC
        """, (source,)).fetchall()
    return {'collections': rows_to_list(rows)}


def handle_get_chapters(qs):
    set_id = qs.get('set_id', [None])[0]
    source = qs.get('source', ['tsumego_hero'])[0]
    if not set_id:
        return {'error': 'set_id required'}, 400
    with db_connect() as con:
        rows = con.execute("""
            SELECT ch.*,
                   COALESCE(s.total_attempts, 0) AS total_attempts,
                   COALESCE(s.total_correct,  0) AS total_correct
            FROM chapters ch
            LEFT JOIN (
                SELECT p.chapter_id,
                       SUM(a.total_attempts) AS total_attempts,
                       SUM(a.total_correct)  AS total_correct
                FROM problems p
                LEFT JOIN problem_stats a USING (source, problem_id)
                GROUP BY p.chapter_id
            ) s ON ch.id = s.chapter_id
            WHERE ch.source = ? AND ch.set_id = ?
            ORDER BY ch.chapter_num ASC
        """, (source, int(set_id))).fetchall()
    return {'chapters': rows_to_list(rows)}


def handle_get_problems(qs):
    chapter_id = qs.get('chapter_id', [None])[0]
    set_id     = qs.get('set_id', [None])[0]
    source     = qs.get('source', ['tsumego_hero'])[0]
    with db_connect() as con:
        if chapter_id:
            rows = con.execute("""
                SELECT p.*,
                       COALESCE(s.total_attempts, 0) AS total_attempts,
                       COALESCE(s.total_correct,  0) AS total_correct,
                       COALESCE(s.pct_correct,    0) AS pct_correct,
                       s.last_seen
                FROM problems p
                LEFT JOIN problem_stats s USING (source, problem_id)
                WHERE p.chapter_id = ?
                ORDER BY p.order_in_chapter ASC
            """, (int(chapter_id),)).fetchall()
        elif set_id:
            rows = con.execute("""
                SELECT p.*,
                       COALESCE(s.total_attempts, 0) AS total_attempts,
                       COALESCE(s.total_correct,  0) AS total_correct,
                       COALESCE(s.pct_correct,    0) AS pct_correct,
                       s.last_seen
                FROM problems p
                LEFT JOIN problem_stats s USING (source, problem_id)
                WHERE p.source = ? AND p.set_id = ?
                ORDER BY p.order_in_chapter ASC
            """, (source, int(set_id))).fetchall()
        else:
            rows = con.execute("""
                SELECT p.*,
                       COALESCE(s.total_attempts, 0) AS total_attempts,
                       COALESCE(s.total_correct,  0) AS total_correct,
                       COALESCE(s.pct_correct,    0) AS pct_correct,
                       s.last_seen
                FROM problems p
                LEFT JOIN problem_stats s USING (source, problem_id)
                WHERE p.source = ?
                ORDER BY p.order_in_chapter ASC
            """, (source,)).fetchall()
    return {'problems': rows_to_list(rows)}
    
def handle_get_problem(qs):
    source     = qs.get('source', ['tsumego_hero'])[0]
    problem_id = qs.get('problem_id', [None])[0]
    if not problem_id:
        return {'error': 'problem_id required'}, 400
    with db_connect() as con:
        row = con.execute("""
            SELECT p.*,
                   c.name   AS collection_name,
                   ch.chapter_num,
                   COALESCE(s.total_attempts, 0) AS total_attempts,
                   COALESCE(s.total_correct,  0) AS total_correct,
                   COALESCE(s.pct_correct,    0) AS pct_correct,
                   COALESCE(s.avg_time_ms,    0) AS avg_time_ms,
                   s.last_seen
            FROM problems p
            LEFT JOIN collections c  ON c.source=p.source AND c.set_id=p.set_id
            LEFT JOIN chapters    ch ON ch.id=p.chapter_id
            LEFT JOIN problem_stats s USING (source, problem_id)
            WHERE p.source = ? AND p.problem_id = ?
        """, (source, problem_id)).fetchone()
    if not row:
        return {'error': 'not found'}, 404
    return {'problem': dict(row)}


def handle_get_runs(qs):
    source = qs.get('source', ['tsumego_hero'])[0]
    status = qs.get('status', [None])[0]
    with db_connect() as con:
        base_sql = """
            SELECT r.*,
                   CASE
                     WHEN r.chapter_id IS NOT NULL
                       THEN c.name || ' · Ch ' || ch.chapter_num
                     WHEN r.set_id IS NOT NULL
                       THEN c.name
                     ELSE 'Run #' || r.id
                   END AS label
            FROM runs r
            LEFT JOIN collections c  ON c.source=r.source AND c.set_id=r.set_id
            LEFT JOIN chapters    ch ON ch.id=r.chapter_id
            WHERE r.source=?
        """
        if status:
            rows = con.execute(base_sql + " AND r.status=? ORDER BY r.started_at DESC",
                               (source, status)).fetchall()
        else:
            rows = con.execute(base_sql + " ORDER BY r.started_at DESC",
                               (source,)).fetchall()
    return {'runs': rows_to_list(rows)}


def handle_get_last_run_stats(qs):
    source = qs.get('source', ['tsumego_hero'])[0]
    set_id = qs.get('set_id', [None])[0]
    if not set_id:
        return {'error': 'set_id required'}, 400
    with db_connect() as con:
        # Último run cerrado de colección completa (sin chapter_id)
        col_run = con.execute("""
            SELECT id FROM runs
            WHERE source=? AND set_id=? AND chapter_id IS NULL AND status='closed'
            ORDER BY closed_at DESC LIMIT 1
        """, (source, int(set_id))).fetchone()

        # Último run cerrado por capítulo
        chap_runs = con.execute("""
            SELECT chapter_id, id FROM runs
            WHERE source=? AND set_id=? AND chapter_id IS NOT NULL AND status='closed'
            GROUP BY chapter_id HAVING id = MAX(id)
        """, (source, int(set_id))).fetchall()

        by_chapter = {}
        for row in chap_runs:
            chapter_id, run_id = row[0], row[1]
            items = con.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """, (run_id,)).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            pct = round(ok / total * 100) if total > 0 else None
            by_chapter[chapter_id] = {'ok': ok, 'total': total, 'pct': pct}

        # Stats de colección completa
        col_stats = {'ok': 0, 'total': 0, 'pct': None}
        if col_run:
            run_id = col_run[0]
            items = con.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """, (run_id,)).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            col_stats = {'ok': ok, 'total': total, 'pct': round(ok / total * 100) if total > 0 else None}

    return {'stats': {'by_chapter': by_chapter, 'collection': col_stats}}

def handle_get_last_run_stats_all(qs):
    source = qs.get('source', ['tsumego_hero'])[0]
    with db_connect() as con:
        # Último run cerrado por set_id (runs de colección completa)
        col_runs = con.execute("""
            SELECT set_id, id FROM runs
            WHERE source=? AND status='closed' AND set_id IS NOT NULL AND chapter_id IS NULL
            GROUP BY set_id HAVING id = MAX(id)
        """, (source,)).fetchall()

        # Último run cerrado por chapter_id
        chap_runs = con.execute("""
            SELECT chapter_id, set_id, id FROM runs
            WHERE source=? AND status='closed' AND chapter_id IS NOT NULL
            GROUP BY chapter_id HAVING id = MAX(id)
        """, (source,)).fetchall()

        result = {}  # set_id → {collection: {pct}, by_chapter: {chapter_id: {pct}}}

        for row in col_runs:
            set_id, run_id = row[0], row[1]
            items = con.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """, (run_id,)).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            pct = round(ok / total * 100) if total > 0 else None
            if set_id not in result:
                result[set_id] = {'collection': None, 'by_chapter': {}}
            result[set_id]['collection'] = {'ok': ok, 'total': total, 'pct': pct}

        for row in chap_runs:
            chapter_id, set_id, run_id = row[0], row[1], row[2]
            items = con.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """, (run_id,)).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            pct = round(ok / total * 100) if total > 0 else None
            if set_id not in result:
                result[set_id] = {'collection': None, 'by_chapter': {}}
            result[set_id]['by_chapter'][chapter_id] = {'ok': ok, 'total': total, 'pct': pct}

    return {'stats': result}

def handle_get_struggling(qs):
    source     = qs.get('source', ['tsumego_hero'])[0]
    set_id     = qs.get('set_id', [None])[0]
    chapter_id = qs.get('chapter_id', [None])[0]
    n          = int(qs.get('n', ['3'])[0])

    with db_connect() as con:
        if chapter_id:
            scope_rows = con.execute(
                "SELECT problem_id FROM problems WHERE source=? AND chapter_id=?",
                (source, int(chapter_id))).fetchall()
        elif set_id:
            scope_rows = con.execute(
                "SELECT problem_id FROM problems WHERE source=? AND set_id=?",
                (source, int(set_id))).fetchall()
        else:
            scope_rows = con.execute(
                "SELECT problem_id FROM problems WHERE source=?",
                (source,)).fetchall()
        scope_ids = [r[0] for r in scope_rows]
        if not scope_ids:
            return {'problem_ids': []}
        struggling = []
        for problem_id in scope_ids:
            rows = con.execute("""
                SELECT result FROM attempts
                WHERE source=? AND problem_id=?
                ORDER BY created_at DESC
                LIMIT ?
            """, (source, problem_id, n)).fetchall()
            if not rows:
                continue
            results = [r[0] for r in rows]
            if any(r == 'wrong' for r in results):
                struggling.append(problem_id)
    return {'problem_ids': struggling}
    
def handle_get_difficulty_range(qs):
    source = qs.get('source', ['tsumego_hero'])[0]
    with db_connect() as con:
        row = con.execute("""
            SELECT MIN(difficulty_num), MAX(difficulty_num)
            FROM problems
            WHERE source=? AND difficulty_num IS NOT NULL
        """, (source,)).fetchone()
    if not row or row[0] is None:
        return {'min': None, 'max': None}
    return {'min': row[0], 'max': row[1]}
    
def handle_get_run_items(qs):
    run_id = qs.get('run_id', [None])[0]
    if not run_id:
        return {'error': 'run_id required'}, 400
    with db_connect() as con:
        rows = con.execute("""
            SELECT ri.*, p.sgf_path, p.difficulty_raw, p.difficulty_num, p.color_to_play
            FROM run_items ri
            JOIN problems p USING (source, problem_id)
            WHERE ri.run_id = ?
            ORDER BY ri.order_in_run ASC
        """, (int(run_id),)).fetchall()
    return {'items': rows_to_list(rows)}


# ── POST/PUT handlers ─────────────────────────────────────────────────────────

def handle_post_attempt(body):
    for f in ('source', 'problem_id', 'result'):
        if f not in body:
            return {'error': f'missing: {f}'}, 400
    with db_connect() as con:
        result = body['result']
        con.execute("""
            INSERT INTO attempts (source, problem_id, run_id, result, time_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (body['source'], int(body['problem_id']), body.get('run_id'),
              result, body.get('time_ms'), now_iso()))
        run_id = body.get('run_id')
        if run_id:
            con.execute("UPDATE runs SET done=done+1 WHERE id=?", (int(run_id),))
            con.execute("""
                UPDATE runs SET status='closed', closed_at=?
                WHERE id=? AND done>=total AND status='open'
            """, (now_iso(), int(run_id)))
            con.execute("""
                UPDATE run_items SET result=? WHERE run_id=? AND problem_id=?
            """, (result, int(run_id), int(body['problem_id'])))
        con.commit()
    return {'ok': True}


def handle_post_run(body):
    for f in ('source', 'type'):
        if f not in body:
            return {'error': f'missing: {f}'}, 400
    run_type   = body['type']
    source     = body['source']
    set_id     = body.get('set_id')
    chapter_id = body.get('chapter_id')
    vc_id      = body.get('vc_id')

    with db_connect() as con:
        if chapter_id and not set_id:
            row = con.execute("SELECT set_id FROM chapters WHERE id=?", (int(chapter_id),)).fetchone()
            if row:
                set_id = row[0]
        if run_type == 'chapter' and chapter_id:
            rows = con.execute(
                "SELECT source, problem_id FROM problems WHERE chapter_id=? ORDER BY order_in_chapter",
                (int(chapter_id),)).fetchall()
        elif run_type == 'collection' and set_id:
            rows = con.execute(
                "SELECT source, problem_id FROM problems WHERE source=? AND set_id=? ORDER BY order_in_chapter",
                (source, int(set_id))).fetchall()
        elif run_type == 'virtual' and vc_id:
            rows = con.execute(
                "SELECT source, problem_id FROM virtual_items WHERE vc_id=?",
                (int(vc_id),)).fetchall()
        else:
            return {'error': 'invalid type or missing id'}, 400

        items = list(rows)
        random.shuffle(items)
        total = len(items)

        cur = con.execute("""
            INSERT INTO runs (source, set_id, chapter_id, vc_id, type, status, total, done, started_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, 0, ?)
        """, (source, set_id, chapter_id, vc_id, run_type, total, now_iso()))
        run_id = cur.lastrowid

        for order, row in enumerate(items, 1):
            con.execute("""
                INSERT INTO run_items (run_id, source, problem_id, order_in_run, result)
                VALUES (?, ?, ?, ?, NULL)
            """, (run_id, row[0], row[1], order))
        con.commit()

    return {'ok': True, 'run_id': run_id, 'total': total}


def handle_put_run(body):
    if 'id' not in body:
        return {'error': 'id required'}, 400
    with db_connect() as con:
        if 'status' in body:
            closed_at = now_iso() if body['status'] == 'closed' else None
            con.execute("UPDATE runs SET status=?, closed_at=? WHERE id=?",
                        (body['status'], closed_at, int(body['id'])))
        con.commit()
    return {'ok': True}


# ── HTTP Handler ──────────────────────────────────────────────────────────────

# ── SYNC handlers ────────────────────────────────────────────────────────────

def handle_sync_snapshot(qs):
    """Devuelve todas las tablas estáticas para inicializar el móvil."""
    with db_connect() as con:
        collections = rows_to_list(con.execute("SELECT * FROM collections").fetchall())
        chapters    = rows_to_list(con.execute("SELECT * FROM chapters").fetchall())
        problems    = rows_to_list(con.execute("SELECT * FROM problems").fetchall())
    return {'collections': collections, 'chapters': chapters, 'problems': problems}


def handle_sync_pull(qs):
    """Devuelve attempts y runs nuevos desde los IDs indicados."""
    since_attempt_id = int(qs.get('since_attempt_id', ['0'])[0])
    since_run_id     = int(qs.get('since_run_id',     ['0'])[0])
    with db_connect() as con:
        attempts = rows_to_list(con.execute(
            "SELECT * FROM attempts WHERE id > ? ORDER BY id ASC",
            (since_attempt_id,)
        ).fetchall())
        runs = rows_to_list(con.execute(
            "SELECT * FROM runs WHERE id > ? ORDER BY id ASC",
            (since_run_id,)
        ).fetchall())
        # run_items de los runs devueltos
        run_ids = [r['id'] for r in runs]
        run_items = []
        if run_ids:
            placeholders = ','.join('?' * len(run_ids))
            run_items = rows_to_list(con.execute(
                f"SELECT * FROM run_items WHERE run_id IN ({placeholders})",
                run_ids
            ).fetchall())
    return {'attempts': attempts, 'runs': runs, 'run_items': run_items}


def handle_sync_push(body):
    """
    Recibe attempts y runs del móvil e inserta los que no existen.
    - attempts: deduplicados por uuid (si existe) o por (source, problem_id, created_at)
    - runs: deduplicados por uuid
    Devuelve IDs asignados por el servidor para que el móvil actualice su DB.
    """
    attempts_in  = body.get('attempts', [])
    runs_in      = body.get('runs', [])

    inserted_attempts = []  # {client_id, server_id}
    inserted_runs     = []  # {client_uuid, server_id}

    with db_connect() as con:
        # ── Attempts ──
        for a in attempts_in:
            uuid = a.get('uuid')
            if uuid:
                existing = con.execute(
                    "SELECT id FROM attempts WHERE uuid=?", (uuid,)
                ).fetchone()
            else:
                existing = con.execute(
                    "SELECT id FROM attempts WHERE source=? AND problem_id=? AND created_at=?",
                    (a['source'], a['problem_id'], a['created_at'])
                ).fetchone()
            if existing:
                inserted_attempts.append({'client_id': a.get('client_id'), 'server_id': existing[0]})
                continue
            cur = con.execute(
                "INSERT INTO attempts (source, problem_id, run_id, result, time_ms, created_at, uuid) VALUES (?,?,?,?,?,?,?)",
                (a['source'], a['problem_id'], None,
                 a['result'], a.get('time_ms'), a['created_at'], uuid)
            )
            inserted_attempts.append({'client_id': a.get('client_id'), 'server_id': cur.lastrowid})

        # ── Runs ──
        for r in runs_in:
            uuid = r.get('uuid')
            if not uuid:
                continue
            existing = con.execute("SELECT id FROM runs WHERE uuid=?", (uuid,)).fetchone()
            if existing:
                inserted_runs.append({'client_uuid': uuid, 'server_id': existing[0]})
                continue
            cur = con.execute("""
                INSERT INTO runs (source, set_id, chapter_id, vc_id, type, status,
                                  total, done, started_at, closed_at, uuid)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (r['source'], r.get('set_id'), r.get('chapter_id'), r.get('vc_id'),
                  r['type'], r['status'], r['total'], r['done'],
                  r['started_at'], r.get('closed_at'), uuid))
            server_run_id = cur.lastrowid
            inserted_runs.append({'client_uuid': uuid, 'server_id': server_run_id})

            # run_items
            for item in r.get('run_items', []):
                con.execute("""
                    INSERT OR IGNORE INTO run_items (run_id, source, problem_id, order_in_run, result)
                    VALUES (?,?,?,?,?)
                """, (server_run_id, item['source'], item['problem_id'],
                      item['order_in_run'], item.get('result')))

        con.commit()

    return {'ok': True, 'attempts': inserted_attempts, 'runs': inserted_runs}
    
GET_ROUTES = {
    '/db/collections':        handle_get_collections,
    '/db/chapters':           handle_get_chapters,
    '/db/problems':           handle_get_problems,
    '/db/problem':            handle_get_problem,
    '/db/runs':               handle_get_runs,
    '/db/last_run_stats':     handle_get_last_run_stats,
    '/db/last_run_stats_all': handle_get_last_run_stats_all,
    '/db/struggling':         handle_get_struggling,
    '/db/run/items':          handle_get_run_items,
    '/db/difficulty_range':   handle_get_difficulty_range,
    '/sync/snapshot':         handle_sync_snapshot,
    '/sync/pull':             handle_sync_pull,
}

class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        parsed  = urlparse(self.path)
        handler = GET_ROUTES.get(parsed.path)
        if not handler:
            self._respond(404, {'error': 'not found'})
            return
        try:
            result = handler(parse_qs(parsed.query))
            if isinstance(result, tuple):
                self._respond(result[1], result[0])
            else:
                self._respond(200, result)
        except Exception as e:
            print(f'[ERROR GET {parsed.path}] {e}')
            self._respond(500, {'error': str(e)})

    def do_POST(self):
        parsed = urlparse(self.path)
        body   = self._read_body()
        routes = {
            '/db/attempt':  handle_post_attempt,
            '/db/run':      handle_post_run,
            '/sync/push':   handle_sync_push,
        }
        handler = routes.get(parsed.path)
        if not handler:
            self._respond(404, {'error': 'not found'})
            return
        try:
            result = handler(body)
            if isinstance(result, tuple):
                self._respond(result[1], result[0])
            else:
                self._respond(200, result)
        except Exception as e:
            print(f'[ERROR POST {parsed.path}] {e}')
            self._respond(500, {'error': str(e)})

    def do_PUT(self):
        parsed = urlparse(self.path)
        body   = self._read_body()
        if parsed.path == '/db/run':
            try:
                result = handle_put_run(body)
                if isinstance(result, tuple):
                    self._respond(result[1], result[0])
                else:
                    self._respond(200, result)
            except Exception as e:
                print(f'[ERROR PUT /db/run] {e}')
                self._respond(500, {'error': str(e)})
        else:
            self._respond(404, {'error': 'not found'})

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _respond(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)



if __name__ == '__main__':
    if not os.path.isfile(DB_PATH):
        print(f'[WARN] DB no encontrada: {DB_PATH}')
        print('       Ejecuta tsumevault_init.py primero.')

    print(f'TsumeVault API → http://localhost:{PORT}')
    print(f'DB             → {DB_PATH}')
    print('Ctrl+C para detener\n')

    migrate_db()

    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
