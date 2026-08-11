#!/usr/bin/env python3
"""T18 — reparación retroactiva de attempts huérfanos tras deleteRun().

Contexto (ver HALLAZGO_T18_attempts_huerfanos.md): deleteRun() (cliente y
servidor) borraba runs+run_items pero nunca tocaba attempts. Cualquier
attempt cuyo run_id apuntaba a un run ya borrado quedaba huérfano
(run_id NOT NULL pero sin fila correspondiente en runs). El código ya está
corregido (deleteRun/syncDeletedRuns/handle_delete_runs desvinculan a NULL
en el momento del borrado); este script solo repara el HISTÓRICO ya
huérfano en la base de datos existente, dejando todos los dispositivos
coherentes entre sí: los attempts pasan a contar como Free Practice
(run_id=NULL), igual que ya hace el código nuevo para borrados futuros.

Decisión de producto (T18, confirmada): mantener los attempts (no
borrarlos) y re-apuntarlos a NULL.

Uso:
    python3 fix_orphan_attempts.py [ruta_db] [--dry-run]

Sin argumentos, usa tsumeVault.db en el mismo directorio que este script
(igual convención que tsumevault_server.py: DB_PATH = SCRIPT_DIR/tsumeVault.db).

Seguro de ejecutar con el servidor corriendo: la base está en WAL mode
(igual que db_connect() del servidor) y esto es una única transacción corta
(UPDATE + commit). Aun así, por prudencia, mejor lanzarlo en un momento de
poco uso.
"""
import os
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(SCRIPT_DIR, "tsumeVault.db")

ORPHAN_COUNT_SQL = """
SELECT COUNT(*) FROM attempts a
WHERE a.run_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM runs r WHERE r.id = a.run_id)
"""

FIX_SQL = """
UPDATE attempts SET run_id = NULL
WHERE run_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM runs r WHERE r.id = attempts.run_id)
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv[1:]
    db_path = args[0] if args else DEFAULT_DB_PATH

    if not os.path.exists(db_path):
        print(f"ERROR: no existe la base de datos: {db_path}")
        sys.exit(1)

    print(f"Base de datos: {db_path}")
    print(f"Modo: {'DRY-RUN (no se escribe nada)' if dry_run else 'APLICAR CAMBIOS'}")
    print()

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")

    before = con.execute(ORPHAN_COUNT_SQL).fetchone()[0]
    print(f"Attempts huérfanos ANTES: {before}")

    if before == 0:
        print("Nada que reparar. Saliendo.")
        con.close()
        return

    if dry_run:
        print("(dry-run: no se aplica el UPDATE)")
        con.close()
        return

    cur = con.execute(FIX_SQL)
    con.commit()
    print(f"Filas actualizadas (run_id -> NULL): {cur.rowcount}")

    after = con.execute(ORPHAN_COUNT_SQL).fetchone()[0]
    print(f"Attempts huérfanos DESPUÉS: {after}")

    if after != 0:
        print("ERROR: quedan huérfanos tras la reparación. Revisar manualmente.")
        con.close()
        sys.exit(1)

    print("OK: reparación completada, 0 huérfanos restantes.")
    con.close()


if __name__ == "__main__":
    main()
