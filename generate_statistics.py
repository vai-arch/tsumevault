"""
export_chapters_report.py
Genera un listado CSV (;-separado) para pegar en Google Sheets.
Columnas: Source | Collection | Chapter | Date | Average | Time

Ejecutar desde el directorio donde está tsumeVault.db:
    python export_chapters_report.py
"""

import sqlite3
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "tsumeVault.db")

SQL = """
SELECT
    ch.source                                           AS source,
    col.name                                            AS collection,
    ch.name                                             AS chapter,
    r.closed_at                                         AS closed_at,
    r.id                                                AS run_id
FROM chapters ch
JOIN collections col ON col.source = ch.source AND col.set_id = ch.set_id
LEFT JOIN (
    SELECT chapter_id, MAX(id) AS last_run_id
    FROM runs
    WHERE type = 'chapter' AND status = 'closed'
    GROUP BY chapter_id
) lr ON lr.chapter_id = ch.id
LEFT JOIN runs r ON r.id = lr.last_run_id
WHERE ch.mostrar = 1
ORDER BY ch.source, col.name, ch.chapter_num
"""

SQL_RUN_STATS = """
SELECT
    SUM(CASE WHEN ri.result = 'correct' THEN 1 ELSE 0 END) AS correct,
    COUNT(*)                                                  AS total,
    (JULIANDAY(r.closed_at) - JULIANDAY(r.started_at)) * 86400000 AS duration_ms
FROM run_items ri
JOIN runs r ON r.id = ri.run_id
WHERE ri.run_id = ?
"""

def fmt_date(iso):
    if not iso:
        return ""
    date_part = iso[:10]
    y, m, d = date_part.split("-")
    return f"{d}/{m}/{y}"

def fmt_pct(correct, total):
    if not total:
        return ""
    return f"{round(correct / total * 100)}%"

def fmt_time(ms):
    if ms is None:
        return ""
    total_s = int(ms / 1000)
    m = total_s // 60
    s = total_s % 60
    return f"{m}m{s:02d}s"

def main():
    con = sqlite3.connect(DB_FILE)
    rows = con.execute(SQL).fetchall()

    lines = ["Source;Collection;Chapter;Date;Average;Time"]

    for source, collection, chapter, closed_at, run_id in rows:
        if run_id is not None:
            att = con.execute(SQL_RUN_STATS, (run_id,)).fetchone()
            correct, total, duration_ms = att
            date_str = fmt_date(closed_at)
            avg_str  = fmt_pct(correct, total)
            time_str = fmt_time(duration_ms)
        else:
            date_str = time_str = ""
            avg_str = 0

        lines.append(f"{source};{collection};{chapter};{date_str};{avg_str};{time_str}")

    con.close()

    output = "\n".join(lines)
    print(output)

if __name__ == "__main__":
    main()
