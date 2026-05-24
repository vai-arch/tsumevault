"""
merge_duplicate_chapters.py
Detecta y mergea chapters duplicados cuyo nombre difiere solo en espacios
(leading/trailing). El chapter con nombre sin espacios extra es el "keeper";
el otro (duplicado) se elimina tras reasignar sus problemas.

Uso:
    python merge_duplicate_chapters.py [--dry-run] [path/to/tsumeVault.db]

Si no se especifica la DB se busca tsumeVault.db en el mismo directorio.

Comportamiento:
  - Reasigna problems del duplicado al keeper, recalculando order_in_chapter
  - Borra runs/run_items referenciados al chapter duplicado
  - Actualiza problem_count del keeper
  - Elimina el chapter duplicado
  - En modo --dry-run no modifica nada, solo imprime el informe
"""

import os
import sys
import sqlite3

DRY_RUN = "--dry-run" in sys.argv

# Determinar ruta a la DB
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if args:
    DB_FILE = args[0]
else:
    DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tsumeVault.db")

if not os.path.isfile(DB_FILE):
    print(f"[ERROR] No se encuentra la DB: {DB_FILE}")
    sys.exit(1)

print(f"DB: {DB_FILE}")
print(f"Modo: {'DRY-RUN (sin cambios)' if DRY_RUN else 'ESCRITURA'}\n")

con = sqlite3.connect(DB_FILE)
con.row_factory = sqlite3.Row
con.execute("PRAGMA foreign_keys=OFF")  # necesario para DELETE de chapters con FK

# ── 1. Detectar duplicados ────────────────────────────────────────────────────
#
# Grupos con mismo (source, set_id, TRIM(name)) pero nombres distintos entre sí.
# Dentro de cada grupo, el keeper es el que tiene TRIM(name) == name (sin espacios extra).
# Si todos tienen espacios, el keeper es el de id más bajo.

rows = con.execute("""
    SELECT id, source, set_id, chapter_num, name, problem_count, mostrar
    FROM chapters
    ORDER BY source, set_id, TRIM(name), id
""").fetchall()

# Agrupar por (source, set_id, TRIM(name))
from collections import defaultdict
groups = defaultdict(list)
for r in rows:
    key = (r["source"], r["set_id"], r["name"].strip())
    groups[key].append(dict(r))

duplicates = {k: v for k, v in groups.items() if len(v) > 1}

if not duplicates:
    print("No se encontraron chapters duplicados. Nada que hacer.")
    con.close()
    sys.exit(0)

print(f"Grupos duplicados encontrados: {len(duplicates)}\n")
print("=" * 70)

total_merged = 0
total_problems_moved = 0
total_runs_deleted = 0

for (source, set_id, trimmed_name), members in sorted(duplicates.items()):
    print(f"  source={source}  set_id={set_id}  name='{trimmed_name}'")

    # Keeper: preferir el que ya tiene el nombre limpio; si empate, el de id menor
    clean = [m for m in members if m["name"] == trimmed_name]
    keeper = clean[0] if clean else min(members, key=lambda m: m["id"])
    dupes  = [m for m in members if m["id"] != keeper["id"]]

    print(f"    KEEPER  → id={keeper['id']}  chapter_num={keeper['chapter_num']}"
          f"  name='{keeper['name']}'  problems={keeper['problem_count']}")
    for d in dupes:
        print(f"    DUPLICADO → id={d['id']}  chapter_num={d['chapter_num']}"
              f"  name='{d['name']}'  problems={d['problem_count']}")

    for dup in dupes:
        dup_id    = dup["id"]
        keeper_id = keeper["id"]

        # Problemas en el duplicado
        dup_problems = con.execute(
            "SELECT source, problem_id FROM problems WHERE chapter_id=? ORDER BY order_in_chapter",
            (dup_id,)
        ).fetchall()

        # Máximo order actual en el keeper
        max_order_row = con.execute(
            "SELECT MAX(order_in_chapter) FROM problems WHERE chapter_id=?",
            (keeper_id,)
        ).fetchone()
        max_order = max_order_row[0] or 0

        print(f"      → Moviendo {len(dup_problems)} problema(s) al keeper (order desde {max_order+1})")
        total_problems_moved += len(dup_problems)

        if not DRY_RUN:
            for i, p in enumerate(dup_problems, 1):
                con.execute(
                    "UPDATE problems SET chapter_id=?, order_in_chapter=? WHERE source=? AND problem_id=?",
                    (keeper_id, max_order + i, p["source"], p["problem_id"])
                )

        # Runs asociados al duplicado
        dup_runs = con.execute(
            "SELECT id FROM runs WHERE chapter_id=?", (dup_id,)
        ).fetchall()
        run_ids = [r["id"] for r in dup_runs]

        if run_ids:
            print(f"      → Borrando {len(run_ids)} run(s) del duplicado: {run_ids}")
            total_runs_deleted += len(run_ids)
            if not DRY_RUN:
                for rid in run_ids:
                    con.execute("DELETE FROM run_items WHERE run_id=?", (rid,))
                con.execute(
                    f"DELETE FROM runs WHERE id IN ({','.join('?' for _ in run_ids)})",
                    run_ids
                )

        # Actualizar problem_count del keeper
        new_count = keeper["problem_count"] + len(dup_problems)
        print(f"      → Actualizando problem_count del keeper: {keeper['problem_count']} → {new_count}")

        if not DRY_RUN:
            con.execute(
                "UPDATE chapters SET problem_count=? WHERE id=?",
                (new_count, keeper_id)
            )
            # También actualizar mostrar si el duplicado lo tenía activo y el keeper no
            if dup["mostrar"] and not keeper["mostrar"]:
                con.execute("UPDATE chapters SET mostrar=1 WHERE id=?", (keeper_id,))
                print(f"      → mostrar del keeper activado (heredado del duplicado)")

        # Eliminar chapter duplicado
        print(f"      → Eliminando chapter duplicado id={dup_id}")
        if not DRY_RUN:
            con.execute("DELETE FROM chapters WHERE id=?", (dup_id,))

        # Actualizar keeper para siguientes iteraciones (si hay más de 2 en el grupo)
        keeper["problem_count"] = new_count

    total_merged += len(dupes)
    print()

# ── 2. Actualizar chapter_count en collections ────────────────────────────────
if not DRY_RUN:
    con.execute("""
        UPDATE collections SET chapter_count = (
            SELECT COUNT(*) FROM chapters c
            WHERE c.source = collections.source AND c.set_id = collections.set_id
        )
    """)

if not DRY_RUN:
    con.commit()
    print(f"Cambios guardados en DB.")
else:
    print(f"[DRY-RUN] No se modificó nada.")

con.close()

print("\n── Resumen ──────────────────────────────────────────────────────────")
print(f"  Grupos duplicados   : {len(duplicates)}")
print(f"  Chapters eliminados : {total_merged}")
print(f"  Problemas movidos   : {total_problems_moved}")
print(f"  Runs borrados       : {total_runs_deleted}")
print("─────────────────────────────────────────────────────────────────────")
