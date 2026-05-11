"""
fix_attempt_run_ids.py
Asocia attempts huérfanos (run_id NULL) a su run correcto usando la ventana
de tiempo started_at / closed_at de cada run.

Ejecutar desde el directorio donde está tsumeVault.db:
    python fix_attempt_run_ids.py
"""

import sqlite3
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "tsumeVault.db")

def main():
    con = sqlite3.connect(DB_FILE)

    runs = con.execute("""
        SELECT id, source, started_at, closed_at
        FROM runs
        WHERE status = 'closed'
        AND closed_at IS NOT NULL
        ORDER BY id
    """).fetchall()

    total_updated = 0
    ambiguous = 0

    for run_id, source, started_at, closed_at in runs:
        # Contar attempts en esta ventana que aún no tienen run_id
        count = con.execute("""
            SELECT COUNT(*) FROM attempts
            WHERE run_id IS NULL
            AND source = ?
            AND created_at >= ?
            AND created_at <= ?
        """, (source, started_at, closed_at)).fetchone()[0]

        if count == 0:
            continue

        # Verificar que no haya otro run solapado en el mismo source
        overlapping = con.execute("""
            SELECT COUNT(*) FROM runs
            WHERE id != ?
            AND source = ?
            AND status = 'closed'
            AND started_at <= ?
            AND closed_at >= ?
        """, (run_id, source, closed_at, started_at)).fetchone()[0]

        if overlapping > 0:
            print(f"[SKIP] run {run_id} ({source}) — {overlapping} run(s) solapados, no se puede asignar con certeza")
            ambiguous += 1
            continue

        updated = con.execute("""
            UPDATE attempts
            SET run_id = ?
            WHERE run_id IS NULL
            AND source = ?
            AND created_at >= ?
            AND created_at <= ?
        """, (run_id, source, started_at, closed_at)).rowcount

        print(f"[OK] run {run_id} ({source}) {started_at[:16]} → {updated} attempts actualizados")
        total_updated += updated

    con.commit()
    con.close()

    print(f"\nTotal attempts actualizados: {total_updated}")
    if ambiguous:
        print(f"Runs saltados por solapamiento: {ambiguous}")

if __name__ == "__main__":
    main()