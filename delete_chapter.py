#!/usr/bin/env python3
"""
delete_chapter.py -- Borra un capitulo de TsumeVault con todo su historial.

Por defecto es DRY-RUN: solo informa de lo que se borraria. Nada se toca
hasta que se pasa --apply. Debe ejecutarse con el servidor PARADO.

Identificacion del capitulo (una de las dos formas):
    --source S --collection C --chapter N      (C puede ser name o folder)
    --source S --chapter-id ID                 (--collection opcional, se verifica)

Uso:
    python delete_chapter.py --source my_collections ^
        --collection "All About Life and Death - 01" ^
        --chapter "01-Life and Death on the Second Line"            (dry-run)
    ... --apply                                                      (borra)

Opciones:
    --db PATH     Ruta de la BD (por defecto tsumeVault.db junto al script).
    --apply       Ejecuta el borrado (hace copia de seguridad antes).
    --force       Continua aunque el servidor parezca estar en marcha.
    --port N      Puerto del servidor para la comprobacion (por defecto 3002).

Que se borra:
    attempts, run_items, sm2_state, problem_tags y problems de ese capitulo;
    los runs del capitulo; el capitulo. Los runs de OTROS capitulos que
    contengan esos problemas se ajustan (total/done) y, si se quedan sin
    items, se borran. focus_chapters NO se borra: se marca active=0 con
    updated_at nuevo para que los clientes lo reciban por LWW.
    Se recalculan problem_count de los capitulos y los agregados de la
    coleccion. La coleccion nunca se borra (el importador reutiliza set_id).

Codigos de salida: 0 ok / dry-run correcto, 1 comprobacion fallida, 2 uso.
"""
import argparse
import datetime
import importlib
import os
import socket
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def die(msg, code=1):
    print(f"ERROR: {msg}")
    sys.exit(code)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def server_running(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def has_table(con, name):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def resolve_chapter(con, a):
    if a.chapter_id is not None:
        rows = con.execute("SELECT * FROM chapters WHERE id=? AND source=?",
                           (a.chapter_id, a.source)).fetchall()
        if len(rows) != 1:
            die(f"no existe el capitulo id={a.chapter_id} en la fuente '{a.source}'")
        ch = rows[0]
        col = con.execute("SELECT * FROM collections WHERE source=? AND set_id=?",
                          (a.source, ch["set_id"])).fetchone()
        if a.collection and (not col or a.collection not in (col["name"], col["folder"])):
            die(f"el capitulo {a.chapter_id} no pertenece a la coleccion '{a.collection}'")
        return ch, col
    if not (a.collection and a.chapter):
        die("indica --collection y --chapter, o bien --chapter-id", 2)
    cols = con.execute("SELECT * FROM collections WHERE source=? AND (name=? OR folder=?)",
                       (a.source, a.collection, a.collection)).fetchall()
    if len(cols) != 1:
        names = [r["name"] for r in con.execute(
            "SELECT name FROM collections WHERE source=?", (a.source,))]
        die(f"coleccion '{a.collection}' no encontrada de forma unica en '{a.source}'. "
            f"Disponibles: {names}")
    col = cols[0]
    rows = con.execute("SELECT * FROM chapters WHERE source=? AND set_id=? AND name=?",
                       (a.source, col["set_id"], a.chapter)).fetchall()
    if len(rows) != 1:
        names = [r["name"] for r in con.execute(
            "SELECT name FROM chapters WHERE source=? AND set_id=? ORDER BY chapter_num",
            (a.source, col["set_id"]))]
        die(f"capitulo '{a.chapter}' no encontrado de forma unica en la coleccion. "
            f"Disponibles: {names}")
    return rows[0], col


def load_temp(con, source, chapter_id):
    """Tablas temporales con los problem_id (como texto) y los runs del capitulo."""
    con.execute("DROP TABLE IF EXISTS temp.tmp_pids")
    con.execute("DROP TABLE IF EXISTS temp.tmp_runs")
    con.execute("DROP TABLE IF EXISTS temp.tmp_other")
    con.execute("CREATE TEMP TABLE tmp_pids (pid TEXT PRIMARY KEY)")
    con.execute("CREATE TEMP TABLE tmp_runs (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TEMP TABLE tmp_other (id INTEGER PRIMARY KEY)")
    con.execute("INSERT OR IGNORE INTO tmp_pids SELECT CAST(problem_id AS TEXT) "
                "FROM problems WHERE source=? AND chapter_id=?", (source, chapter_id))
    con.execute("INSERT OR IGNORE INTO tmp_runs SELECT id FROM runs WHERE chapter_id=?",
                (chapter_id,))
    con.execute("INSERT OR IGNORE INTO tmp_other SELECT DISTINCT run_id FROM run_items "
                "WHERE source=? AND CAST(problem_id AS TEXT) IN (SELECT pid FROM tmp_pids) "
                "AND run_id NOT IN (SELECT id FROM tmp_runs)", (source,))


PID_IN = "CAST(problem_id AS TEXT) IN (SELECT pid FROM tmp_pids)"


def gather_counts(con, source, chapter_id):
    def one(sql, params=()):
        return con.execute(sql, params).fetchone()[0]
    c = {
        "problems": one("SELECT COUNT(*) FROM tmp_pids"),
        "attempts": one(f"SELECT COUNT(*) FROM attempts WHERE (source=? AND {PID_IN}) "
                        "OR run_id IN (SELECT id FROM tmp_runs)", (source,)),
        "sm2_state": one(f"SELECT COUNT(*) FROM sm2_state WHERE source=? AND {PID_IN}", (source,)),
        "problem_tags": one(f"SELECT COUNT(*) FROM problem_tags WHERE source=? AND {PID_IN}", (source,)),
        "run_items": one(f"SELECT COUNT(*) FROM run_items WHERE (source=? AND {PID_IN}) "
                         "OR run_id IN (SELECT id FROM tmp_runs)", (source,)),
        "runs_del": one("SELECT COUNT(*) FROM tmp_runs"),
        "runs_adj": one("SELECT COUNT(*) FROM tmp_other"),
        "virtual_items": one(f"SELECT COUNT(*) FROM virtual_items WHERE source=? AND {PID_IN}", (source,))
        if has_table(con, "virtual_items") else 0,
        "focus_active": one("SELECT COUNT(*) FROM focus_chapters WHERE chapter_id=? AND active=1",
                            (chapter_id,)) if has_table(con, "focus_chapters") else 0,
    }
    return c


LABELS = [
    ("problems", "problemas (filas en problems)"),
    ("attempts", "attempts"),
    ("sm2_state", "sm2_state"),
    ("problem_tags", "problem_tags (activas e inactivas)"),
    ("run_items", "run_items"),
    ("runs_del", "runs del capitulo (se borran)"),
    ("runs_adj", "runs de otros capitulos (se ajustan)"),
    ("virtual_items", "virtual_items"),
    ("focus_active", "focus_chapters activos (se marcan active=0)"),
]


def print_counts(c):
    for key, label in LABELS:
        print(f"  {label:<48} {c[key]:>6}")


def recalc_collection(con, source, set_id):
    con.execute("UPDATE chapters SET problem_count="
                "(SELECT COUNT(*) FROM problems WHERE problems.chapter_id=chapters.id) "
                "WHERE source=? AND set_id=?", (source, set_id))
    agg = con.execute("SELECT COUNT(*) AS n, COALESCE(SUM(problem_count),0) AS p, "
                      "AVG(diff_avg) AS d FROM chapters WHERE source=? AND set_id=?",
                      (source, set_id)).fetchone()
    diff = round(agg["d"]) if agg["d"] is not None else None
    con.execute("UPDATE collections SET chapter_count=?, num_problems=?, difficulty_num=? "
                "WHERE source=? AND set_id=?", (agg["n"], agg["p"], diff, source, set_id))
    return agg["n"], agg["p"], diff


def apply_delete(con, source, chapter_id, set_id):
    out = {}

    def run(label, sql, params=()):
        out[label] = con.execute(sql, params).rowcount

    run("attempts", f"DELETE FROM attempts WHERE (source=? AND {PID_IN}) "
        "OR run_id IN (SELECT id FROM tmp_runs)", (source,))
    run("run_items", f"DELETE FROM run_items WHERE (source=? AND {PID_IN}) "
        "OR run_id IN (SELECT id FROM tmp_runs)", (source,))
    run("runs del capitulo", "DELETE FROM runs WHERE id IN (SELECT id FROM tmp_runs)")
    run("runs ajustados", "UPDATE runs SET "
        "total=(SELECT COUNT(*) FROM run_items WHERE run_id=runs.id), "
        "done=(SELECT COUNT(*) FROM run_items WHERE run_id=runs.id AND result IS NOT NULL) "
        "WHERE id IN (SELECT id FROM tmp_other)")
    run("runs vacios borrados", "DELETE FROM runs WHERE id IN (SELECT id FROM tmp_other) AND total=0")
    run("sm2_state", f"DELETE FROM sm2_state WHERE source=? AND {PID_IN}", (source,))
    run("problem_tags", f"DELETE FROM problem_tags WHERE source=? AND {PID_IN}", (source,))
    if has_table(con, "virtual_items"):
        run("virtual_items", f"DELETE FROM virtual_items WHERE source=? AND {PID_IN}", (source,))
    if has_table(con, "focus_chapters"):
        run("focus_chapters desactivados",
            "UPDATE focus_chapters SET active=0, updated_at=? WHERE chapter_id=? AND active=1",
            (now_iso(), chapter_id))
    run("problems", "DELETE FROM problems WHERE source=? AND chapter_id=?", (source, chapter_id))
    run("chapters", "DELETE FROM chapters WHERE id=?", (chapter_id,))
    out["_coleccion"] = recalc_collection(con, source, set_id)
    return out


def run_audit_summary(db_path):
    """Ejecuta run_audit de tsumevault_server.py en modo solo lectura."""
    saved_argv = sys.argv
    try:
        sys.argv = [saved_argv[0]]  # el servidor interpreta argv[1] como puerto
        if SCRIPT_DIR not in sys.path:
            sys.path.insert(0, SCRIPT_DIR)
        srv = importlib.import_module("tsumevault_server")
    except Exception as e:
        print(f"(auditoria omitida: no se pudo importar tsumevault_server.py: {e})")
        return
    finally:
        sys.argv = saved_argv
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.row_factory = sqlite3.Row
    try:
        rep = srv.run_audit(con, limit=3, skip_integrity=True)
    finally:
        con.close()
    s = rep["summary"]
    print(f"  errores={s['errors']} warnings={s['warnings']} info={s['info']} pass={s['pass']}")
    for ch in rep["checks"]:
        if ch["severity"] in ("ERROR", "WARNING"):
            print(f"  [{ch['severity']}] {ch['id']} {ch['title']}: {ch['count']}")
    print("  (los WARNING 1/3/11/18b pueden ser historicos previos a este borrado)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--collection")
    ap.add_argument("--chapter")
    ap.add_argument("--chapter-id", type=int)
    ap.add_argument("--db", default=os.path.join(SCRIPT_DIR, "tsumeVault.db"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--port", type=int, default=3002)
    a = ap.parse_args()

    if not os.path.isfile(a.db):
        die(f"BD no encontrada: {a.db}", 2)

    running = server_running(a.port)
    if running:
        msg = f"hay algo escuchando en el puerto {a.port} (el servidor parece estar en marcha)"
        if a.apply and not a.force:
            die(msg + ". Paralo o usa --force.")
        print("AVISO: " + msg)

    mode = "rw" if a.apply else "ro"
    con = sqlite3.connect("file:%s?mode=%s" % (a.db.replace("\\", "/"), mode), uri=True)
    con.row_factory = sqlite3.Row

    ch, col = resolve_chapter(con, a)
    set_id = ch["set_id"]
    print(f"Capitulo : id={ch['id']} num={ch['chapter_num']} nombre='{ch['name']}'")
    print(f"Coleccion: set_id={set_id} nombre='{col['name'] if col else '?'}' "
          f"(capitulos en la coleccion: {con.execute('SELECT COUNT(*) FROM chapters WHERE source=? AND set_id=?', (a.source, set_id)).fetchone()[0]})")
    print(f"Fuente   : {a.source}")

    load_temp(con, a.source, ch["id"])
    counts = gather_counts(con, a.source, ch["id"])
    if counts["problems"] == 0:
        print("AVISO: el capitulo no tiene problemas en la BD.")
    print("\nSe veria afectado:")
    print_counts(counts)

    if not a.apply:
        print("\nDRY-RUN: no se ha modificado nada. Repite con --apply para borrar.")
        con.close()
        return

    # --- copia de seguridad con la API de backup de SQLite ---
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak_path = f"{a.db}.backup-{ts}"
    bak = sqlite3.connect(bak_path)
    con.backup(bak)
    bak.close()
    print(f"\nCopia de seguridad: {bak_path}")

    con.execute("PRAGMA foreign_keys=ON")
    try:
        with con:  # una sola transaccion: commit al salir, rollback si hay excepcion
            out = apply_delete(con, a.source, ch["id"], set_id)
    except Exception as e:
        print(f"ERROR durante el borrado, transaccion revertida: {e!r}")
        print(f"La copia sigue en {bak_path}")
        sys.exit(1)

    print("\nBorrado completado:")
    for k, v in out.items():
        if k == "_coleccion":
            n, p, d = v
            print(f"  coleccion recalculada: chapter_count={n} num_problems={p} difficulty_num={d}")
        else:
            print(f"  {k:<34} {v:>6}")
    con.close()

    print("\nAuditoria (solo lectura):")
    run_audit_summary(a.db)
    print("\nSiguiente paso: reorganizar las carpetas y ejecutar el importador.")


if __name__ == "__main__":
    main()
