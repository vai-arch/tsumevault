"""
dominated_at_date.py
Calcula cuántos problemas estaban dominados (>=80% en últimos 5 intentos) en una fecha concreta.

Uso:
    python dominated_at_date.py 2026-05-01
    python dominated_at_date.py 2026-05-01 --source guo_juan
"""
import sqlite3
import sys

DB_PATH = "tsumeVault.db"

def dominated_at(date_str, source=None):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    source_filter = "AND p.source = ?" if source else ""
    params_visible = [date_str]
    if source:
        params_visible = [source, date_str]

    query = f"""
        WITH visible AS (
          SELECT p.source, p.set_id, p.problem_id
          FROM problems p
          JOIN chapters ch ON ch.id = p.chapter_id
          WHERE ch.mostrar = 1
          {source_filter}
        ),
        last5 AS (
          SELECT a.source, a.problem_id, a.result, a.created_at,
            ROW_NUMBER() OVER (
              PARTITION BY a.source, a.problem_id
              ORDER BY a.created_at DESC
            ) AS rn
          FROM attempts a
          JOIN visible v ON v.source = a.source AND v.problem_id = a.problem_id
          WHERE a.run_id IS NOT NULL
          AND a.created_at <= ?
        ),
        seen AS (
          SELECT v.source, v.set_id, v.problem_id,
            COUNT(*) AS total_attempts,
            SUM(CASE WHEN l.result = 'correct' THEN 1 ELSE 0 END) AS total_correct
          FROM visible v
          JOIN last5 l ON l.source = v.source AND l.problem_id = v.problem_id
          WHERE l.rn <= 5
          GROUP BY v.source, v.set_id, v.problem_id
        )
        SELECT
          COUNT(*) AS total_visible,
          COUNT(s.problem_id) AS total_seen,
          SUM(CASE WHEN s.total_attempts > 0
               AND CAST(s.total_correct AS REAL) / s.total_attempts >= 0.8
               THEN 1 ELSE 0 END) AS dominated
        FROM visible v
        LEFT JOIN seen s ON s.source = v.source AND s.problem_id = v.problem_id
    """

    if source:
        row = con.execute(query, [source, date_str]).fetchone()
    else:
        row = con.execute(query, [date_str]).fetchone()

    con.close()
    return row

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python dominated_at_date.py YYYY-MM-DD [--source SOURCE]")
        sys.exit(1)

    date_str = sys.argv[1] + "T23:59:59Z"
    source = None
    if "--source" in sys.argv:
        idx = sys.argv.index("--source")
        source = sys.argv[idx + 1]

    r = dominated_at(date_str, source)
    pct = round(r["dominated"] / r["total_visible"] * 100, 1) if r["total_visible"] > 0 else 0
    cov = round(r["total_seen"] / r["total_visible"] * 100, 1) if r["total_visible"] > 0 else 0

    print(f"Fecha:      {sys.argv[1]}")
    if source:
        print(f"Source:     {source}")
    print(f"Visibles:   {r['total_visible']}")
    print(f"Vistos:     {r['total_seen']} ({cov}%)")
    print(f"Dominados:  {r['dominated']} ({pct}%)")
