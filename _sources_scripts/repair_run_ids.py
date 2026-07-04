"""
repair_run_ids.py
Asigna run_id a attempts que tienen run_id = NULL pero pertenecen a un run.
Lógica: un attempt pertenece a un run si:
  - mismo source
  - problem_id está en run_items de ese run
  - created_at está entre started_at y closed_at del run (con margen de 1h)
"""
import sqlite3
import sys

DB_PATH = "tsumeVault.db"

def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    # Attempts sin run_id
    orphans = con.execute("""
        SELECT id, source, problem_id, created_at
        FROM attempts
        WHERE run_id IS NULL
        ORDER BY created_at
    """).fetchall()

    print(f"Attempts con run_id=NULL: {len(orphans)}")

    # Runs cerrados con sus run_items
    runs = con.execute("""
        SELECT r.id, r.source, r.started_at, r.closed_at
        FROM runs r
        WHERE r.status = 'closed'
        AND r.started_at IS NOT NULL
        AND r.closed_at IS NOT NULL
    """).fetchall()

    print(f"Runs cerrados: {len(runs)}")

    # Índice: run_id → set de problem_ids
    run_problems = {}
    for run in runs:
        items = con.execute("""
            SELECT problem_id FROM run_items WHERE run_id = ?
        """, (run["id"],)).fetchall()
        run_problems[run["id"]] = {str(item["problem_id"]) for item in items}

    updated = 0
    ambiguous = 0

    for a in orphans:
        matches = []
        for run in runs:
            if run["source"] != a["source"]:
                continue
            if str(a["problem_id"]) not in run_problems.get(run["id"], set()):
                continue
            # Comprobar que created_at está dentro del run (con 1h de margen)
            started = run["started_at"]
            closed = run["closed_at"]
            if started and closed and started <= a["created_at"] <= closed:
                matches.append(run["id"])

        if len(matches) == 1:
            con.execute("UPDATE attempts SET run_id=? WHERE id=?", (matches[0], a["id"]))
            updated += 1
        elif len(matches) > 1:
            ambiguous += 1
            print(f"  Ambiguo: attempt {a['id']} ({a['source']}, {a['problem_id']}, {a['created_at']}) → runs {matches}")

    con.commit()
    con.close()

    print(f"\nActualizados: {updated}")
    print(f"Ambiguos (no tocados): {ambiguous}")
    print(f"Sin match (free practice): {len(orphans) - updated - ambiguous}")

if __name__ == "__main__":
    main()
