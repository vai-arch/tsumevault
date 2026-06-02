"""
cleanup_guo_juan.py - Limpia chapters y runs de guo_juan para reimportar con chunking.

Elimina:
  - run_items de runs de guo_juan
  - runs de guo_juan
  - chapters de guo_juan

Preserva:
  - collections de guo_juan
  - problems de guo_juan (solo se pone chapter_id y order_in_chapter a NULL)
  - attempts de guo_juan

Ejecutar desde tsumevault antes de tsumevault_init.py.
"""

import os
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "tsumeVault.db")


def main():
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys=ON")

    # 1. Borrar run_items de runs de guo_juan
    con.execute(
        "DELETE FROM run_items WHERE run_id IN (SELECT id FROM runs WHERE source = 'guo_juan')"
    )
    print(f"  run_items borrados : {con.execute('SELECT changes()').fetchone()[0]}")

    # 2. Borrar runs de guo_juan
    con.execute("DELETE FROM runs WHERE source = 'guo_juan'")
    print(f"  runs borrados      : {con.execute('SELECT changes()').fetchone()[0]}")

    # 3. Desasociar problems de sus chapters ANTES de borrar chapters (FK constraint)
    con.execute(
        "UPDATE problems SET chapter_id = NULL, order_in_chapter = NULL WHERE source = 'guo_juan'"
    )
    print(f"  problems reseteados: {con.execute('SELECT changes()').fetchone()[0]}")

    # 4. Borrar chapters de guo_juan
    con.execute("DELETE FROM chapters WHERE source = 'guo_juan'")
    print(f"  chapters borrados  : {con.execute('SELECT changes()').fetchone()[0]}")

    con.commit()
    con.close()
    print("\nListo. Ejecuta tsumevault_init.py para reimportar guo_juan.")


if __name__ == "__main__":
    main()
