"""
export_to_gsheets.py
Lee tsumeVault.db y vuelca los resultados en la hoja "Problems" del Google Sheet.

Requisitos:
    pip install gspread

Colocar el fichero JSON de credenciales junto a este script y
ajustar CREDENTIALS_FILE con su nombre.

Ejecutar desde el directorio donde está tsumeVault.db:
    python export_to_gsheets.py
"""

import sqlite3
import os
import gspread

SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
DB_FILE          = os.path.join(SCRIPT_DIR, "tsumeVault.db")
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "conf/tsumevault-ad87227d16a1.json")
SPREADSHEET_ID   = "1MPPne1DvPD4ui0st4vtq1u1s49Qj4S2EhGmui2Jgmag"
SHEET_NAME       = "Problems"

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
    (SELECT ROUND(AVG(time_ms) / 1000.0, 1)
     FROM attempts
     WHERE run_id = ri.run_id) AS avg_secs
FROM run_items ri
WHERE ri.run_id = ?
"""

def fmt_date(iso):
    if not iso:
        return ""
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"

def fmt_pct(correct, total):
    if not total:
        return ""
    return f"{round(correct / total * 100)}%"

def build_rows(con):
    rows = con.execute(SQL).fetchall()
    result = []
    for source, collection, chapter, closed_at, run_id in rows:
        if run_id is not None:
            correct, total, avg_secs = con.execute(SQL_RUN_STATS, (run_id,)).fetchone()
            date_str    = fmt_date(closed_at)
            avg_str     = fmt_pct(correct, total)
            time_str    = str(avg_secs) if avg_secs is not None else ""
            n_str       = str(total)
            correct_str = str(correct)
        else:
            date_str = avg_str = time_str = n_str = correct_str = ""
        result.append([source, collection, chapter, date_str, n_str, correct_str, avg_str, time_str])
    return result

def main():
    # Leer DB
    con = sqlite3.connect(DB_FILE)
    rows = build_rows(con)
    con.close()

    # Conectar a Sheets
    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)

    # Limpiar y escribir
    header = [["Source", "Collection", "Chapter", "Date", "Num. Prob.", "Correct", "Average", "Avg_secs"]]
    ws.clear()
    ws.update(header + rows, value_input_option="USER_ENTERED")

    # Imprimir en pantalla
    print(";".join(["Source", "Collection", "Chapter", "Date", "Num. Prob.", "Correct", "Average", "Avg_secs"]))
    for row in rows:
        print(";".join(row))

    print(f"\nOK — {len(rows)} filas escritas en '{SHEET_NAME}'")

if __name__ == "__main__":
    main()