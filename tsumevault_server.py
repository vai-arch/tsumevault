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

import gzip
import json
import logging
import os
import random
import signal
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3002
DB_PATH = os.path.join(SCRIPT_DIR, "tsumeVault.db")

# Token estático de autenticación (Fase 1, §4.1). Si la variable de entorno
# TSUMEVAULT_TOKEN no está definida, la autenticación queda DESACTIVADA
# (modo compatibilidad: clientes antiguos siguen funcionando).
AUTH_TOKEN = os.environ.get("TSUMEVAULT_TOKEN", "").strip()

# Orígenes permitidos para CORS y para la verificación de Origin en escrituras.
# Sobreescribible con TSUMEVAULT_ORIGINS (lista separada por comas).
ALLOWED_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "TSUMEVAULT_ORIGINS",
        "https://vai-arch.github.io,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
}

# Límite de tamaño del body (Fase 1, §4.2): rechaza payloads absurdos con 413.
MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB

# El servidor pasa a ThreadingHTTPServer (una conexión lenta ya no bloquea el
# servicio). Este lock serializa TODO el acceso a SQLite, preservando
# exactamente la semántica single-thread previa: cero carreras SQL nuevas.
DB_LOCK = threading.Lock()

log = logging.getLogger("tsumevault")


class _BodyError(Exception):
    """Body HTTP inválido (demasiado grande o JSON malformado)."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


# ─────────────────────────────────────────────────────────────────────────────


def handle_delete_runs(body):
    ids = body.get("ids", [])
    uuids = body.get("uuids", [])
    if not isinstance(ids, list) or not isinstance(uuids, list):
        return {"error": "ids/uuids must be lists"}, 400
    if not ids and not uuids:
        return {"error": "ids or uuids required"}, 400
    with db_connect() as con:
        if ids:
            # TODO(Fase 2): retirar la ruta por ids locales cuando todos los
            # clientes usen uuids (bug 3.3 de la auditoría: los ids del cliente
            # no se corresponden con los del servidor). Se mantiene solo por
            # compatibilidad con clientes antiguos durante la transición.
            try:
                ids = [int(i) for i in ids]
            except (TypeError, ValueError):
                return {"error": "invalid ids"}, 400
            placeholders = ",".join("?" * len(ids))
            # T18: los attempts de un run borrado NO se eliminan (perderian
            # historial real de seen/correct/streak); se desvinculan a NULL y
            # pasan a contar como Free Practice. Decision de producto: T18.
            con.execute(
                f"UPDATE attempts SET run_id=NULL WHERE run_id IN (SELECT id FROM runs WHERE id IN ({placeholders}))",
                ids,
            )
            con.execute(
                f"DELETE FROM run_items WHERE run_id IN (SELECT id FROM runs WHERE id IN ({placeholders}))",
                ids,
            )
            con.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", ids)
        if uuids:
            placeholders = ",".join("?" * len(uuids))
            # T18: mismo tratamiento que arriba para la rama por uuids.
            con.execute(
                f"UPDATE attempts SET run_id=NULL WHERE run_id IN (SELECT id FROM runs WHERE uuid IN ({placeholders}))",
                uuids,
            )
            con.execute(
                f"DELETE FROM run_items WHERE run_id IN (SELECT id FROM runs WHERE uuid IN ({placeholders}))",
                uuids,
            )
            con.execute(f"DELETE FROM runs WHERE uuid IN ({placeholders})", uuids)
        con.commit()
    log.info("delete_runs: %d ids, %d uuids", len(ids), len(uuids))
    return {"ok": True}


def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ── Migration ────────────────────────────────────────────────────────────────


def _migrate_v2_hidden(con):
    """T13: schema v2 — borrado lógico de problemas (columna problems.hidden).

    hidden=0 (default) => visible; hidden=1 => oculto en toda la app sin
    borrar attempts/sm2_state/run_items. Idempotente (PRAGMA table_info).
    """
    cols_p = [r[1] for r in con.execute("PRAGMA table_info(problems)").fetchall()]
    if "hidden" not in cols_p:
        con.execute(
            "ALTER TABLE problems ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0"
        )
        log.info("[migrate] Columna hidden añadida a problems.")
    con.execute("PRAGMA user_version = 2")  # T13: sellar la version
    con.commit()
    log.info("[migrate] Migraciones completadas (schema_version=2).")


def migrate_db():
    with db_connect() as con:
        # T11: schema_version formal via PRAGMA user_version. Las migraciones
        # historicas (todas idempotentes: comprobaciones de PRAGMA table_info,
        # CREATE ... IF NOT EXISTS y dedup re-ejecutable) quedan bajo la
        # version 1. Migraciones futuras: "if version < N: ...; sellar N".
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version >= 2:
            log.info("[migrate] schema_version=%d — nada que migrar.", version)
            return
        if version >= 1:
            # T13: v1 ya aplicada — solo falta v2 (problems.hidden).
            _migrate_v2_hidden(con)
            return
        cols = [r[1] for r in con.execute("PRAGMA table_info(runs)").fetchall()]
        if "uuid" not in cols:
            con.execute("ALTER TABLE runs ADD COLUMN uuid TEXT")
            con.commit()
            log.info("[migrate] Columna uuid añadida a runs.")
        cols_a = [r[1] for r in con.execute("PRAGMA table_info(attempts)").fetchall()]
        if "uuid" not in cols_a:
            con.execute("ALTER TABLE attempts ADD COLUMN uuid TEXT")
            con.commit()
            log.info("[migrate] Columna uuid añadida a attempts.")

        cols_ch = [r[1] for r in con.execute("PRAGMA table_info(chapters)").fetchall()]
        if "mostrar" not in cols_ch:
            con.execute(
                "ALTER TABLE chapters ADD COLUMN mostrar INTEGER NOT NULL DEFAULT 0"
            )
            con.commit()
            log.info("[migrate] Columna mostrar añadida a chapters.")

        # ── Fase 1 (3.1/§6): dedup por uuid + índices ÚNICOS sobre uuid ──
        # Attempts duplicados con el mismo uuid son copias del mismo intento:
        # se conserva el más antiguo (MIN(id)).
        cur = con.execute(
            """
            DELETE FROM attempts WHERE uuid IS NOT NULL AND id NOT IN (
                SELECT MIN(id) FROM attempts WHERE uuid IS NOT NULL GROUP BY uuid)
            """
        )
        if cur.rowcount:
            log.info(
                "[migrate] %d attempts duplicados por uuid eliminados.", cur.rowcount
            )
        # Runs duplicados por uuid: repuntar attempts al run conservado,
        # eliminar run_items redundantes y borrar los duplicados.
        dup_runs = con.execute(
            """
            SELECT uuid, MIN(id) AS keep_id FROM runs
            WHERE uuid IS NOT NULL GROUP BY uuid HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in dup_runs:
            keep_id, run_uuid = row["keep_id"], row["uuid"]
            extra = [
                r[0]
                for r in con.execute(
                    "SELECT id FROM runs WHERE uuid=? AND id<>?", (run_uuid, keep_id)
                ).fetchall()
            ]
            if not extra:
                continue
            ph = ",".join("?" * len(extra))
            con.execute(
                f"UPDATE attempts SET run_id=? WHERE run_id IN ({ph})",
                [keep_id] + extra,
            )
            con.execute(f"DELETE FROM run_items WHERE run_id IN ({ph})", extra)
            con.execute(f"DELETE FROM runs WHERE id IN ({ph})", extra)
            log.info(
                "[migrate] run uuid=%s: %d duplicados fusionados en id=%d.",
                run_uuid,
                len(extra),
                keep_id,
            )
        # Índices únicos parciales: garantizan dedup por uuid y aceleran los
        # lookups de handle_sync_push (antes eran full scans, §5.2).
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_attempts_uuid ON attempts(uuid) WHERE uuid IS NOT NULL"
        )
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_uuid ON runs(uuid) WHERE uuid IS NOT NULL"
        )
        con.commit()

        # sm2_state
        con.execute("""
            CREATE TABLE IF NOT EXISTS sm2_state (
                source      TEXT NOT NULL,
                problem_id  TEXT NOT NULL,
                due_date    TEXT NOT NULL,
                interval    REAL NOT NULL DEFAULT 6,
                easiness    REAL NOT NULL DEFAULT 2.5,
                repetitions INTEGER NOT NULL DEFAULT 0,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (source, problem_id)
            )
        """)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sm2_updated ON sm2_state(updated_at)"
        )
        con.commit()
        # T13: aplicar también v2 y sellar directamente en schema_version=2.
        _migrate_v2_hidden(con)


# ── GET handlers ──────────────────────────────────────────────────────────────


def handle_get_collections(qs):
    source = qs.get("source", ["tsumego_hero"])[0]
    with db_connect() as con:
        rows = con.execute(
            """
            SELECT c.*,
                   COALESCE(s.total_attempts, 0) AS total_attempts,
                   COALESCE(s.total_correct,  0) AS total_correct,
                   COALESCE(v.visible_problems, 0) AS visible_problems
            FROM collections c
            LEFT JOIN (
                SELECT source, set_id, COUNT(*) AS visible_problems
                FROM problems WHERE hidden = 0
                GROUP BY source, set_id
            ) v ON c.source = v.source AND c.set_id = v.set_id
            LEFT JOIN (
                SELECT p.source, p.set_id,
                       SUM(a.total_attempts) AS total_attempts,
                       SUM(a.total_correct)  AS total_correct
                FROM problems p
                LEFT JOIN problem_stats a USING (source, problem_id)
                WHERE p.hidden = 0
                GROUP BY p.source, p.set_id
            ) s ON c.source = s.source AND c.set_id = s.set_id
            WHERE c.source = ?
            ORDER BY c.difficulty_num ASC NULLS LAST, c.name ASC
        """,
            (source,),
        ).fetchall()
    return {"collections": rows_to_list(rows)}


def handle_get_chapters(qs):
    set_id = qs.get("set_id", [None])[0]
    source = qs.get("source", ["tsumego_hero"])[0]
    if not set_id:
        return {"error": "set_id required"}, 400
    with db_connect() as con:
        rows = con.execute(
            """
            SELECT ch.*,
                   COALESCE(s.total_attempts, 0) AS total_attempts,
                   COALESCE(s.total_correct,  0) AS total_correct,
                   COALESCE(v.visible_problems, 0) AS visible_problems
            FROM chapters ch
            LEFT JOIN (
                SELECT chapter_id, COUNT(*) AS visible_problems
                FROM problems WHERE hidden = 0
                GROUP BY chapter_id
            ) v ON ch.id = v.chapter_id
            LEFT JOIN (
                SELECT p.chapter_id,
                       SUM(a.total_attempts) AS total_attempts,
                       SUM(a.total_correct)  AS total_correct
                FROM problems p
                LEFT JOIN problem_stats a USING (source, problem_id)
                WHERE p.hidden = 0
                GROUP BY p.chapter_id
            ) s ON ch.id = s.chapter_id
            WHERE ch.source = ? AND ch.set_id = ?
            ORDER BY ch.chapter_num ASC
        """,
            (source, int(set_id)),
        ).fetchall()
    return {"chapters": rows_to_list(rows)}


def handle_get_problems(qs):
    chapter_id = qs.get("chapter_id", [None])[0]
    set_id = qs.get("set_id", [None])[0]
    source = qs.get("source", ["tsumego_hero"])[0]
    with db_connect() as con:
        if chapter_id:
            rows = con.execute(
                """
                SELECT p.*,
                       COALESCE(s.total_attempts, 0) AS total_attempts,
                       COALESCE(s.total_correct,  0) AS total_correct,
                       COALESCE(s.pct_correct,    0) AS pct_correct,
                       s.last_seen
                FROM problems p
                LEFT JOIN problem_stats s USING (source, problem_id)
                WHERE p.chapter_id = ? AND p.hidden = 0
                ORDER BY p.order_in_chapter ASC
            """,
                (int(chapter_id),),
            ).fetchall()
        elif set_id:
            rows = con.execute(
                """
                SELECT p.*,
                       COALESCE(s.total_attempts, 0) AS total_attempts,
                       COALESCE(s.total_correct,  0) AS total_correct,
                       COALESCE(s.pct_correct,    0) AS pct_correct,
                       s.last_seen
                FROM problems p
                LEFT JOIN problem_stats s USING (source, problem_id)
                WHERE p.source = ? AND p.set_id = ? AND p.hidden = 0
                ORDER BY p.order_in_chapter ASC
            """,
                (source, int(set_id)),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT p.*,
                       COALESCE(s.total_attempts, 0) AS total_attempts,
                       COALESCE(s.total_correct,  0) AS total_correct,
                       COALESCE(s.pct_correct,    0) AS pct_correct,
                       s.last_seen
                FROM problems p
                LEFT JOIN problem_stats s USING (source, problem_id)
                WHERE p.source = ? AND p.hidden = 0
                ORDER BY p.order_in_chapter ASC
            """,
                (source,),
            ).fetchall()
    return {"problems": rows_to_list(rows)}


def handle_get_problem(qs):
    source = qs.get("source", ["tsumego_hero"])[0]
    problem_id = qs.get("problem_id", [None])[0]
    if not problem_id:
        return {"error": "problem_id required"}, 400
    with db_connect() as con:
        row = con.execute(
            """
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
        """,
            (source, problem_id),
        ).fetchone()
    if not row:
        return {"error": "not found"}, 404
    return {"problem": dict(row)}


def handle_get_runs(qs):
    source = qs.get("source", ["tsumego_hero"])[0]
    status = qs.get("status", [None])[0]
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
            rows = con.execute(
                base_sql + " AND r.status=? ORDER BY r.started_at DESC",
                (source, status),
            ).fetchall()
        else:
            rows = con.execute(
                base_sql + " ORDER BY r.started_at DESC", (source,)
            ).fetchall()
    return {"runs": rows_to_list(rows)}


def handle_get_last_run_stats(qs):
    source = qs.get("source", ["tsumego_hero"])[0]
    set_id = qs.get("set_id", [None])[0]
    if not set_id:
        return {"error": "set_id required"}, 400
    with db_connect() as con:
        # Último run cerrado de colección completa (sin chapter_id)
        col_run = con.execute(
            """
            SELECT id FROM runs
            WHERE source=? AND set_id=? AND chapter_id IS NULL AND status='closed'
            ORDER BY closed_at DESC LIMIT 1
        """,
            (source, int(set_id)),
        ).fetchone()

        # Último run cerrado por capítulo (T8/3.12: SQL estándar, sin bare columns)
        chap_runs = con.execute(
            """
            SELECT chapter_id, MAX(id) AS id FROM runs
            WHERE source=? AND set_id=? AND chapter_id IS NOT NULL AND status='closed'
            GROUP BY chapter_id
        """,
            (source, int(set_id)),
        ).fetchall()

        by_chapter = {}
        for row in chap_runs:
            chapter_id, run_id = row[0], row[1]
            items = con.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """,
                (run_id,),
            ).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            pct = round(ok / total * 100) if total > 0 else None
            by_chapter[chapter_id] = {"ok": ok, "total": total, "pct": pct}

        # Stats de colección completa
        col_stats = {"ok": 0, "total": 0, "pct": None}
        if col_run:
            run_id = col_run[0]
            items = con.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """,
                (run_id,),
            ).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            col_stats = {
                "ok": ok,
                "total": total,
                "pct": round(ok / total * 100) if total > 0 else None,
            }

    return {"stats": {"by_chapter": by_chapter, "collection": col_stats}}


def handle_get_last_run_stats_all(qs):
    source = qs.get("source", ["tsumego_hero"])[0]
    with db_connect() as con:
        # Último run cerrado por set_id (runs de colección completa)
        col_runs = con.execute(
            """
            SELECT set_id, MAX(id) AS id FROM runs
            WHERE source=? AND status='closed' AND set_id IS NOT NULL AND chapter_id IS NULL
            GROUP BY set_id
        """,
            (source,),
        ).fetchall()

        # Último run cerrado por chapter_id
        chap_runs = con.execute(
            """
            SELECT chapter_id, set_id, id FROM (
              SELECT chapter_id, set_id, id,
                     ROW_NUMBER() OVER (PARTITION BY chapter_id ORDER BY id DESC) rn
              FROM runs
              WHERE source=? AND status='closed' AND chapter_id IS NOT NULL
            ) WHERE rn=1
        """,
            (source,),
        ).fetchall()

        result = {}  # set_id → {collection: {pct}, by_chapter: {chapter_id: {pct}}}

        for row in col_runs:
            set_id, run_id = row[0], row[1]
            items = con.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """,
                (run_id,),
            ).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            pct = round(ok / total * 100) if total > 0 else None
            if set_id not in result:
                result[set_id] = {"collection": None, "by_chapter": {}}
            result[set_id]["collection"] = {"ok": ok, "total": total, "pct": pct}

        for row in chap_runs:
            chapter_id, set_id, run_id = row[0], row[1], row[2]
            items = con.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) AS ok
                FROM run_items WHERE run_id=?
            """,
                (run_id,),
            ).fetchone()
            total, ok = items[0] or 0, items[1] or 0
            pct = round(ok / total * 100) if total > 0 else None
            if set_id not in result:
                result[set_id] = {"collection": None, "by_chapter": {}}
            result[set_id]["by_chapter"][chapter_id] = {
                "ok": ok,
                "total": total,
                "pct": pct,
            }

    return {"stats": result}


def handle_get_struggling(qs):
    source = qs.get("source", ["tsumego_hero"])[0]
    set_id = qs.get("set_id", [None])[0]
    chapter_id = qs.get("chapter_id", [None])[0]
    n = int(qs.get("n", ["3"])[0])

    with db_connect() as con:
        # T12/P3: una sola query con window function en lugar de una query por
        # problema del scope (mismo cambio y misma equivalencia verificada que
        # en el cliente: compare_struggling.js).
        scope = ""
        params = [source]
        if chapter_id:
            scope = " AND p.chapter_id=?"
            params.append(int(chapter_id))
        elif set_id:
            scope = " AND p.set_id=?"
            params.append(int(set_id))
        params.append(n)
        rows = con.execute(
            f"""
            WITH ranked AS (
              SELECT a.problem_id, a.result,
                     ROW_NUMBER() OVER (PARTITION BY a.problem_id ORDER BY a.created_at DESC, a.id DESC) rn
              FROM attempts a
              JOIN problems p ON p.source = a.source AND p.problem_id = a.problem_id
              WHERE a.source = ?{scope} AND p.hidden = 0
            )
            SELECT problem_id FROM ranked WHERE rn <= ?
            GROUP BY problem_id
            HAVING SUM(result = 'wrong') > 0
        """,
            params,
        ).fetchall()
        struggling = [r[0] for r in rows]
    return {"problem_ids": struggling}


def handle_get_difficulty_range(qs):
    source = qs.get("source", ["tsumego_hero"])[0]
    with db_connect() as con:
        row = con.execute(
            """
            SELECT MIN(difficulty_num), MAX(difficulty_num)
            FROM problems
            WHERE source=? AND difficulty_num IS NOT NULL AND hidden=0
        """,
            (source,),
        ).fetchone()
    if not row or row[0] is None:
        return {"min": None, "max": None}
    return {"min": row[0], "max": row[1]}


def handle_get_run_items(qs):
    run_id = qs.get("run_id", [None])[0]
    if not run_id:
        return {"error": "run_id required"}, 400
    with db_connect() as con:
        rows = con.execute(
            """
            SELECT ri.*, p.sgf_path, p.difficulty_raw, p.difficulty_num, p.color_to_play
            FROM run_items ri
            JOIN problems p USING (source, problem_id)
            WHERE ri.run_id = ?
            ORDER BY ri.order_in_run ASC
        """,
            (int(run_id),),
        ).fetchall()
    return {"items": rows_to_list(rows)}


# ── POST/PUT handlers ─────────────────────────────────────────────────────────


def handle_post_attempt(body):
    for f in ("source", "problem_id", "result"):
        if f not in body:
            return {"error": f"missing: {f}"}, 400
    if body["result"] not in ("correct", "wrong"):
        # Fase 1 (3.11): antes se insertaba cualquier valor sin validar.
        return {"error": "result must be correct|wrong"}, 400
    with db_connect() as con:
        result = body["result"]
        con.execute(
            """
            INSERT INTO attempts (source, problem_id, run_id, result, time_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                body["source"],
                int(body["problem_id"]),
                body.get("run_id"),
                result,
                body.get("time_ms"),
                now_iso(),
            ),
        )
        run_id = body.get("run_id")
        if run_id:
            con.execute("UPDATE runs SET done=done+1 WHERE id=?", (int(run_id),))
            con.execute(
                """
                UPDATE runs SET status='closed', closed_at=?
                WHERE id=? AND done>=total AND status='open'
            """,
                (now_iso(), int(run_id)),
            )
            con.execute(
                """
                UPDATE run_items SET result=? WHERE run_id=? AND problem_id=?
            """,
                (result, int(run_id), int(body["problem_id"])),
            )
        con.commit()
    return {"ok": True}


def handle_post_run(body):
    for f in ("source", "type"):
        if f not in body:
            return {"error": f"missing: {f}"}, 400
    run_type = body["type"]
    source = body["source"]
    set_id = body.get("set_id")
    chapter_id = body.get("chapter_id")
    vc_id = body.get("vc_id")

    with db_connect() as con:
        if chapter_id and not set_id:
            row = con.execute(
                "SELECT set_id FROM chapters WHERE id=?", (int(chapter_id),)
            ).fetchone()
            if row:
                set_id = row[0]
        if run_type == "chapter" and chapter_id:
            rows = con.execute(
                "SELECT source, problem_id FROM problems WHERE chapter_id=? AND hidden=0 ORDER BY order_in_chapter",
                (int(chapter_id),),
            ).fetchall()
        elif run_type == "collection" and set_id:
            rows = con.execute(
                "SELECT source, problem_id FROM problems WHERE source=? AND set_id=? AND hidden=0 ORDER BY order_in_chapter",
                (source, int(set_id)),
            ).fetchall()
        elif run_type == "virtual" and vc_id:
            rows = con.execute(
                "SELECT source, problem_id FROM virtual_items WHERE vc_id=?",
                (int(vc_id),),
            ).fetchall()
        else:
            return {"error": "invalid type or missing id"}, 400

        items = list(rows)
        random.shuffle(items)
        total = len(items)

        cur = con.execute(
            """
            INSERT INTO runs (source, set_id, chapter_id, vc_id, type, status, total, done, started_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, 0, ?)
        """,
            (source, set_id, chapter_id, vc_id, run_type, total, now_iso()),
        )
        run_id = cur.lastrowid

        for order, row in enumerate(items, 1):
            con.execute(
                """
                INSERT INTO run_items (run_id, source, problem_id, order_in_run, result)
                VALUES (?, ?, ?, ?, NULL)
            """,
                (run_id, row[0], row[1], order),
            )
        con.commit()

    return {"ok": True, "run_id": run_id, "total": total}


def handle_put_run(body):
    if "id" not in body:
        return {"error": "id required"}, 400
    if "status" not in body:
        # Fase 1 (3.11): antes respondía {ok:true} sin hacer nada.
        return {"error": "status required"}, 400
    with db_connect() as con:
        closed_at = now_iso() if body["status"] == "closed" else None
        con.execute(
            "UPDATE runs SET status=?, closed_at=? WHERE id=?",
            (body["status"], closed_at, int(body["id"])),
        )
        con.commit()
    return {"ok": True}


# ── HTTP Handler ──────────────────────────────────────────────────────────────

# ── SYNC handlers ────────────────────────────────────────────────────────────


def handle_sync_snapshot(qs):
    """Devuelve todas las tablas estáticas para inicializar el móvil."""
    with db_connect() as con:
        collections = rows_to_list(con.execute("SELECT * FROM collections").fetchall())
        chapters = rows_to_list(con.execute("SELECT * FROM chapters").fetchall())
        problems = rows_to_list(con.execute("SELECT * FROM problems").fetchall())
        game_collections = rows_to_list(
            con.execute("SELECT * FROM game_collections").fetchall()
        )
        games = rows_to_list(con.execute("SELECT * FROM games").fetchall())
        sm2_state = rows_to_list(con.execute("SELECT * FROM sm2_state").fetchall())
    return {
        "collections": collections,
        "chapters": chapters,
        "problems": problems,
        "game_collections": game_collections,
        "games": games,
        "sm2_state": sm2_state,
    }


def handle_admin_import_games(body):
    """Recibe {game_collections: [...], games: [...]} y REEMPLAZA por completo
    el contenido de game_collections/games.

    T-games-1: antes era aditivo (insertaba solo lo que no existía ya), lo que
    dejaba basura si una colección o partida se borraba en disco. games/
    game_collections no se editan nunca desde el cliente (son de solo lectura
    para tsumevault.html), así que un reemplazo total en cada import es seguro
    y más simple que diffear. Ninguna otra tabla referencia estos ids (ver
    db_schema.sql), por lo que no quedan huérfanos.
    """
    game_collections = body.get("game_collections", [])
    games = body.get("games", [])
    if not isinstance(game_collections, list) or not isinstance(games, list):
        return {"error": "game_collections and games must be lists"}, 400
    for col in game_collections:
        if not isinstance(col, dict) or "name" not in col or "folder" not in col:
            return {"error": "invalid game_collections entry"}, 400
    for game in games:
        if (
            not isinstance(game, dict)
            or "collection_name" not in game
            or "name" not in game
            or "sgf_path" not in game
        ):
            return {"error": "invalid games entry"}, 400

    inserted_cols = 0
    inserted_games = 0
    skipped_games = 0
    with db_connect() as con:
        # Orden de borrado: games antes que game_collections (FK, PRAGMA
        # foreign_keys=ON).
        con.execute("DELETE FROM games")
        con.execute("DELETE FROM game_collections")

        col_ids = {}  # name -> id
        for col in game_collections:
            cur = con.execute(
                "INSERT INTO game_collections (name, folder) VALUES (?, ?)",
                (col["name"], col["folder"]),
            )
            col_ids[col["name"]] = cur.lastrowid
            inserted_cols += 1

        for game in games:
            col_id = col_ids.get(game["collection_name"])
            if col_id is None:
                skipped_games += 1
                continue
            con.execute(
                "INSERT INTO games (game_collection_id, name, sgf_path) VALUES (?, ?, ?)",
                (col_id, game["name"], game["sgf_path"]),
            )
            inserted_games += 1
        con.commit()
    return {
        "collections": inserted_cols,
        "games": inserted_games,
        "skipped_games": skipped_games,
    }


def handle_sync_sm2_pull(qs):
    """Devuelve registros sm2_state actualizados desde el timestamp indicado.

    Fase 1 (3.10): se usa >= en lugar de > para que, con resolución de
    segundo, un registro escrito en el mismo segundo que el cursor no quede
    excluido para siempre. El cliente aplica LWW, así que re-recibir el
    registro frontera es un no-op inocuo.
    """
    since = qs.get("since", ["1970-01-01T00:00:00Z"])[0]
    with db_connect() as con:
        rows = rows_to_list(
            con.execute(
                "SELECT * FROM sm2_state WHERE updated_at >= ? ORDER BY updated_at ASC",
                (since,),
            ).fetchall()
        )
    return {"sm2_state": rows}


def handle_sync_sm2_push(body):
    """Recibe registros sm2_state del cliente y los inserta/actualiza."""
    records = body.get("sm2_state", [])
    # ── Validación de entrada (Fase 1, 3.11) ──
    if not isinstance(records, list):
        return {"error": "sm2_state must be a list"}, 400
    required = (
        "source",
        "problem_id",
        "due_date",
        "interval",
        "easiness",
        "repetitions",
        "updated_at",
    )
    for r in records:
        if not isinstance(r, dict) or any(f not in r for f in required):
            return {"error": "invalid sm2_state entry"}, 400
    with db_connect() as con:
        for r in records:
            existing = con.execute(
                "SELECT updated_at FROM sm2_state WHERE source=? AND problem_id=?",
                (r["source"], r["problem_id"]),
            ).fetchone()
            # Solo actualizar si el registro del cliente es mas reciente
            if existing is None or r["updated_at"] > existing[0]:
                con.execute(
                    """
                    INSERT INTO sm2_state (source, problem_id, due_date, interval, easiness, repetitions, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, problem_id) DO UPDATE SET
                        due_date    = excluded.due_date,
                        interval    = excluded.interval,
                        easiness    = excluded.easiness,
                        repetitions = excluded.repetitions,
                        updated_at  = excluded.updated_at
                """,
                    (
                        r["source"],
                        r["problem_id"],
                        r["due_date"],
                        r["interval"],
                        r["easiness"],
                        r["repetitions"],
                        r["updated_at"],
                    ),
                )
        con.commit()
    return {"ok": True, "count": len(records)}


def handle_sync_static_version(qs):
    with db_connect() as con:
        row = con.execute("SELECT MAX(rowid) FROM problems").fetchone()
    return {"version": row[0] or 0}


def handle_sync_games(qs):
    """Devuelve todas las game_collections y games."""
    with db_connect() as con:
        game_collections = rows_to_list(
            con.execute("SELECT * FROM game_collections").fetchall()
        )
        games = rows_to_list(con.execute("SELECT * FROM games").fetchall())
    return {"game_collections": game_collections, "games": games}


def handle_sync_pull(qs):
    """Devuelve attempts y runs nuevos desde los IDs indicados."""
    since_attempt_id = int(qs.get("since_attempt_id", ["0"])[0])
    since_run_id = int(qs.get("since_run_id", ["0"])[0])
    with db_connect() as con:
        # run_uuid acompaña a cada attempt para que los clientes nuevos puedan
        # remapear run_id a su id LOCAL (los ids del servidor ya no se reutilizan
        # como PK local; ver colisión de ids en la auditoría). Los clientes
        # antiguos ignoran la clave extra.
        attempts = rows_to_list(
            con.execute(
                """SELECT a.*, r.uuid AS run_uuid FROM attempts a
                   LEFT JOIN runs r ON r.id = a.run_id
                   WHERE a.id > ? ORDER BY a.id ASC""",
                (since_attempt_id,),
            ).fetchall()
        )
        runs = rows_to_list(
            con.execute(
                "SELECT * FROM runs WHERE id > ? ORDER BY id ASC", (since_run_id,)
            ).fetchall()
        )
        # run_items de los runs devueltos
        run_ids = [r["id"] for r in runs]
        run_items = []
        if run_ids:
            placeholders = ",".join("?" * len(run_ids))
            run_items = rows_to_list(
                con.execute(
                    f"SELECT * FROM run_items WHERE run_id IN ({placeholders})", run_ids
                ).fetchall()
            )
    return {"attempts": attempts, "runs": runs, "run_items": run_items}


def handle_sync_push(body):
    """
    Recibe attempts y runs del móvil e inserta los que no existen.
    - attempts: deduplicados por uuid (si existe) o por (source, problem_id, created_at)
    - runs: deduplicados por uuid
    Devuelve IDs asignados por el servidor para que el móvil actualice su DB.
    """
    attempts_in = body.get("attempts", [])
    runs_in = body.get("runs", [])

    # ── Validación de entrada (Fase 1, 3.11) ──
    if not isinstance(attempts_in, list) or not isinstance(runs_in, list):
        return {"error": "attempts/runs must be lists"}, 400
    for a in attempts_in:
        if not isinstance(a, dict):
            return {"error": "invalid attempt entry"}, 400
        for f in ("source", "problem_id", "result", "created_at"):
            if f not in a:
                return {"error": f"attempt missing field: {f}"}, 400
        if a["result"] not in ("correct", "wrong"):
            return {"error": "invalid attempt result"}, 400
    for r in runs_in:
        if not isinstance(r, dict):
            return {"error": "invalid run entry"}, 400
        if not r.get("uuid"):
            continue  # los runs sin uuid se ignoran (comportamiento previo)
        for f in ("source", "type", "status", "total", "done", "started_at"):
            if f not in r:
                return {"error": f"run missing field: {f}"}, 400
        if not isinstance(r.get("run_items", []), list):
            return {"error": "invalid run_items"}, 400

    log.info("sync/push: %d runs, %d attempts", len(runs_in), len(attempts_in))

    inserted_attempts = []  # {client_id, server_id}
    inserted_runs = []  # {client_uuid, server_id}

    with db_connect() as con:
        # ── Runs primero (para poder mapear run_id en attempts) ──
        client_to_server_run_id = {}  # client run_id → server run_id

        # ── Runs ──
        for r in runs_in:
            uuid = r.get("uuid")
            if not uuid:
                continue
            existing = con.execute(
                "SELECT id FROM runs WHERE uuid=?", (uuid,)
            ).fetchone()
            if existing:
                server_run_id = existing[0]
                # Actualizar status/done/closed_at si ha cambiado
                con.execute(
                    """
                    UPDATE runs SET status=?, done=?, closed_at=?
                    WHERE id=?
                """,
                    (r["status"], r["done"], r.get("closed_at"), server_run_id),
                )
                # Actualizar resultados de run_items
                for item in r.get("run_items", []):
                    if item.get("result"):
                        con.execute(
                            "UPDATE run_items SET result=? WHERE run_id=? AND problem_id=?",
                            (item["result"], server_run_id, item["problem_id"]),
                        )
            else:
                cur = con.execute(
                    """
                    INSERT INTO runs (source, set_id, chapter_id, vc_id, type, status,
                                      total, done, started_at, closed_at, uuid)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                    (
                        r["source"],
                        r.get("set_id"),
                        r.get("chapter_id"),
                        r.get("vc_id"),
                        r["type"],
                        r["status"],
                        r["total"],
                        r["done"],
                        r["started_at"],
                        r.get("closed_at"),
                        uuid,
                    ),
                )
                server_run_id = cur.lastrowid

                # run_items
                for item in r.get("run_items", []):
                    con.execute(
                        """
                        INSERT OR IGNORE INTO run_items (run_id, source, problem_id, order_in_run, result)
                        VALUES (?,?,?,?,?)
                    """,
                        (
                            server_run_id,
                            item["source"],
                            item["problem_id"],
                            item["order_in_run"],
                            item.get("result"),
                        ),
                    )

            inserted_runs.append({"client_uuid": uuid, "server_id": server_run_id})
            client_run_id = r.get("id") or r.get("client_id")
            if client_run_id is not None:
                client_to_server_run_id[int(client_run_id)] = server_run_id

        # ── Attempts ──
        for a in attempts_in:
            uuid = a.get("uuid")
            if uuid:
                existing = con.execute(
                    "SELECT id FROM attempts WHERE uuid=?", (uuid,)
                ).fetchone()
            else:
                existing = con.execute(
                    "SELECT id FROM attempts WHERE source=? AND problem_id=? AND created_at=?",
                    (a["source"], a["problem_id"], a["created_at"]),
                ).fetchone()
            if existing:
                inserted_attempts.append(
                    {"client_id": a.get("client_id"), "server_id": existing[0]}
                )
                continue

            # mapear run_id del cliente al del servidor
            client_run_id = a.get("run_id")
            if client_run_id is not None:
                server_run_id = client_to_server_run_id.get(int(client_run_id))
                if server_run_id is None:
                    # El run ya existía en el servidor — buscarlo por uuid en el payload
                    run_data = next(
                        (
                            r
                            for r in runs_in
                            if (r.get("id") or r.get("client_id")) == int(client_run_id)
                        ),
                        None,
                    )
                    if run_data and run_data.get("uuid"):
                        row = con.execute(
                            "SELECT id FROM runs WHERE uuid=?", (run_data["uuid"],)
                        ).fetchone()
                        if row:
                            server_run_id = row[0]
                if server_run_id is None and a.get("run_uuid"):
                    # Fase 1 (3.1): los clientes nuevos adjuntan run_uuid a cada
                    # attempt; permite resolver el run aunque ese run no viaje
                    # en este push (p. ej. ya sincronizado). Los clientes
                    # antiguos no envían run_uuid: se conserva el fallback previo.
                    row = con.execute(
                        "SELECT id FROM runs WHERE uuid=?", (a["run_uuid"],)
                    ).fetchone()
                    if row:
                        server_run_id = row[0]
            else:
                server_run_id = None

            cur = con.execute(
                "INSERT INTO attempts (source, problem_id, run_id, result, time_ms, created_at, uuid) VALUES (?,?,?,?,?,?,?)",
                (
                    a["source"],
                    a["problem_id"],
                    server_run_id,
                    a["result"],
                    a.get("time_ms"),
                    a["created_at"],
                    uuid,
                ),
            )
            inserted_attempts.append(
                {"client_id": a.get("client_id"), "server_id": cur.lastrowid}
            )

        con.commit()

    return {"ok": True, "attempts": inserted_attempts, "runs": inserted_runs}


def handle_put_chapter_mostrar(body):
    chapter_id = body.get("chapter_id")
    mostrar = body.get("mostrar")
    if chapter_id is None or mostrar is None:
        return {"error": "chapter_id y mostrar son requeridos"}, 400
    with db_connect() as con:
        con.execute(
            "UPDATE chapters SET mostrar=? WHERE id=?",
            (int(bool(mostrar)), int(chapter_id)),
        )
        con.commit()
    return {"ok": True}


def handle_sync_check_runs(body):
    uuids = body.get("uuids", [])
    if not isinstance(uuids, list):
        return {"error": "uuids must be a list"}, 400
    if not uuids:
        return {"missing": []}
    with db_connect() as con:
        placeholders = ",".join("?" * len(uuids))
        existing = con.execute(
            f"SELECT uuid FROM runs WHERE uuid IN ({placeholders})", uuids
        ).fetchall()
    existing_set = {r[0] for r in existing}
    missing = [u for u in uuids if u not in existing_set]
    log.info(
        "check_runs: recibidos=%d existentes=%d missing=%d",
        len(uuids),
        len(existing_set),
        len(missing),
    )
    return {"missing": missing}


def handle_sync_chapters_mostrar(body):
    """Actualiza el flag mostrar de chapters (antes lógica inline en do_PUT)."""
    chapters = body.get("chapters")
    if not isinstance(chapters, list):
        return {"error": "chapters (list) required"}, 400
    normalized = []
    for ch in chapters:
        if not isinstance(ch, dict) or "id" not in ch or "mostrar" not in ch:
            return {"error": "invalid chapter entry"}, 400
        try:
            # Fase 1 (§4.4): normalizar mostrar a 0/1 (antes se escribía tal cual).
            normalized.append((int(bool(ch["mostrar"])), int(ch["id"])))
        except (TypeError, ValueError):
            return {"error": "invalid chapter entry"}, 400
    with db_connect() as con:
        for mostrar, chapter_id in normalized:
            con.execute(
                "UPDATE chapters SET mostrar=? WHERE id=?", (mostrar, chapter_id)
            )
        con.commit()
    return {"ok": True}


def handle_sync_problems_hidden(body):
    """T13: merge de problemas ocultos (borrado lógico).

    El cliente envía la lista de sus ocultos locales; el servidor marca
    hidden=1 en esas filas (UNIÓN: este endpoint nunca pone 0 — des-ocultar
    se hace manualmente en la BD) y responde con la lista completa de
    ocultos resultante, que el cliente aplica como verdad absoluta. Así un
    UPDATE manual hidden=0 en el servidor se propaga solo a los clientes.
    No crea filas: un problem_id inexistente en el catálogo se ignora.
    """
    problems = body.get("problems")
    if not isinstance(problems, list):
        return {"error": "problems (list) required"}, 400
    normalized = []
    for pr in problems:
        if not isinstance(pr, dict) or "source" not in pr or "problem_id" not in pr:
            return {"error": "invalid problem entry"}, 400
        normalized.append((str(pr["source"]), str(pr["problem_id"])))
    updated = 0
    with db_connect() as con:
        for source, problem_id in normalized:
            cur = con.execute(
                "UPDATE problems SET hidden=1 WHERE source=? AND problem_id=? AND hidden=0",
                (source, problem_id),
            )
            updated += cur.rowcount
        con.commit()
        rows = rows_to_list(
            con.execute(
                "SELECT source, problem_id FROM problems WHERE hidden=1"
            ).fetchall()
        )
    if updated:
        log.info("problems_hidden: %d problemas ocultados; total ocultos=%d", updated, len(rows))
    return {"hidden": rows, "updated": updated}


GET_ROUTES = {
    "/db/collections": handle_get_collections,
    "/db/chapters": handle_get_chapters,
    "/db/problems": handle_get_problems,
    "/db/problem": handle_get_problem,
    "/db/runs": handle_get_runs,
    "/db/last_run_stats": handle_get_last_run_stats,
    "/db/last_run_stats_all": handle_get_last_run_stats_all,
    "/db/struggling": handle_get_struggling,
    "/db/run/items": handle_get_run_items,
    "/db/difficulty_range": handle_get_difficulty_range,
    "/sync/snapshot": handle_sync_snapshot,
    "/sync/pull": handle_sync_pull,
    "/sync/static_version": handle_sync_static_version,
    "/sync/games": handle_sync_games,
    "/sync/sm2/pull": handle_sync_sm2_pull,
}


POST_ROUTES = {
    "/db/attempt": handle_post_attempt,
    "/db/run": handle_post_run,
    "/sync/push": handle_sync_push,
    "/db/runs/delete": handle_delete_runs,
    "/sync/check_runs": handle_sync_check_runs,
    "/admin/import_games": handle_admin_import_games,
    "/sync/sm2/push": handle_sync_sm2_push,
}

PUT_ROUTES = {
    "/db/run": handle_put_run,
    "/db/chapter/mostrar": handle_put_chapter_mostrar,
    "/sync/chapters_mostrar": handle_sync_chapters_mostrar,
    "/sync/problems_hidden": handle_sync_problems_hidden,  # T13
}


class Handler(BaseHTTPRequestHandler):
    # Fase 1 (§4.2): timeout de socket — una conexión colgada no retiene el hilo.
    timeout = 30

    def log_message(self, fmt, *args):
        # Log de acceso vía logging (sin bodies — Fase 1, §4.3).
        log.info("%s %s", self.address_string(), fmt % args)

    def _send_cors(self):
        """Fase 1 (§4.1): CORS restringido — solo se refleja un Origin permitido."""
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Auth-Token")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _gate(self, write=False):
        """Auth por token + verificación de Origin en escrituras (Fase 1, §4.1).

        Devuelve True si la petición puede continuar; si no, responde y
        devuelve False. Con TSUMEVAULT_TOKEN sin definir la auth se omite
        (modo compatibilidad).
        """
        if AUTH_TOKEN:
            if self.headers.get("X-Auth-Token", "") != AUTH_TOKEN:
                self._respond(401, {"error": "unauthorized"})
                return False
        if write:
            origin = self.headers.get("Origin")
            # Origin ausente = cliente no-navegador (curl, scripts propios): permitido.
            if origin is not None and origin not in ALLOWED_ORIGINS:
                self._respond(403, {"error": "forbidden origin"})
                return False
        return True

    def _dispatch(self, handler, arg):
        try:
            with DB_LOCK:
                result = handler(arg)
        except (ValueError, TypeError, KeyError) as e:
            # Parámetros/payload malformados → 400 (Fase 1, 3.11).
            log.warning("bad request %s: %r", self.path, e)
            self._respond(400, {"error": "bad request"})
            return
        except Exception:
            # Fase 1 (§4.3): el detalle queda en el log, no en la respuesta.
            log.exception("error handling %s", self.path)
            self._respond(500, {"error": "internal server error"})
            return
        if isinstance(result, tuple):
            self._respond(result[1], result[0])
        else:
            self._respond(200, result)

    def do_GET(self):
        parsed = urlparse(self.path)
        handler = GET_ROUTES.get(parsed.path)
        if not handler:
            self._respond(404, {"error": "not found"})
            return
        if not self._gate(write=False):
            return
        self._dispatch(handler, parse_qs(parsed.query))

    def do_POST(self):
        self._handle_write(POST_ROUTES)

    def do_PUT(self):
        self._handle_write(PUT_ROUTES)

    def _handle_write(self, routes):
        parsed = urlparse(self.path)
        handler = routes.get(parsed.path)
        if not handler:
            self._respond(404, {"error": "not found"})
            return
        if not self._gate(write=True):
            return
        try:
            body = self._read_body()
        except _BodyError as e:
            self._respond(e.code, {"error": str(e)})
            return
        self._dispatch(handler, body)

    def _read_body(self):
        """Lee y parsea el body JSON. Lanza _BodyError si es inválido.

        Fase 1 (3.11/§4.2): antes un JSON malformado explotaba fuera del try
        del dispatcher (conexión colgada) y no había límite de tamaño.
        """
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            raise _BodyError(400, "invalid content-length")
        if length > MAX_BODY_BYTES:
            raise _BodyError(413, "body too large")
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            raise _BodyError(400, "invalid json")
        if not isinstance(body, dict):
            raise _BodyError(400, "invalid json")
        return body

    def _respond(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        accept_encoding = self.headers.get("Accept-Encoding", "")
        self.send_response(code)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        if "gzip" in accept_encoding and len(body) > 1024:
            body = gzip.compress(body, compresslevel=6)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not os.path.isfile(DB_PATH):
        log.warning(
            "DB no encontrada: %s — ejecuta tsumevault_init.py primero.", DB_PATH
        )

    try:
        import socket

        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        # Fase 1 (§4.6): un host sin resolución de hostname ya no impide arrancar.
        local_ip = "?"
    log.info("TsumeVault API → http://localhost:%d", PORT)
    log.info("Red local      → http://%s:%d", local_ip, PORT)
    log.info("DB             → %s", DB_PATH)
    if AUTH_TOKEN:
        log.info("Auth: X-Auth-Token ACTIVADO")
    else:
        log.warning(
            "Auth: TSUMEVAULT_TOKEN no definido — autenticación DESACTIVADA (modo compatibilidad)"
        )
    log.info("Orígenes permitidos: %s", ", ".join(sorted(ALLOWED_ORIGINS)))
    migrate_db()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True

    # T11: apagado limpio con SIGTERM/SIGINT (systemd/docker). shutdown() debe
    # invocarse desde otro hilo: llamado desde el propio hilo de serve_forever
    # se bloquearia. Tras serve_forever se cierra el socket y se sale con 0.
    def _shutdown(signum, _frame):
        log.info("Señal %d recibida — apagando limpiamente…", signum)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    server.serve_forever()
    server.server_close()
    log.info("Servidor detenido.")
    sys.exit(0)
