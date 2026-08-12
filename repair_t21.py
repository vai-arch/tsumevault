#!/usr/bin/env python3
"""
repair_t21.py — Reparación quirúrgica de las cicatrices de colisión de ids de
sync (runs de mayo-2026) detectadas por la auditoría T20 en TsumeVault.

REQUISITO: este script debe estar en el MISMO directorio que tsumevault_server.py
(importa run_audit de él para la verificación antes/después).

USO:
    python3 repair_t21.py tsumeVault.db              # DRY-RUN: informa, no toca nada
    python3 repair_t21.py tsumeVault.db --apply      # aplica los cambios
    python3 repair_t21.py tsumeVault.db --verbose    # dry-run sin límite de ejemplos

ANTES DE --apply, OBLIGATORIO:
  1. Parar el servidor (systemctl stop tsumevault o equivalente).
  2. Backup (la BD está en WAL: NUNCA copiar el fichero en caliente):
         sqlite3 tsumeVault.db ".backup tsumeVault_pre_t21.db"
  3. Ejecutar primero el dry-run y revisar el informe completo.

REPARACIONES (el orden importa):
  R1  attempts cuyo source ≠ source de su run (colisión demostrada, p.ej. los 86
      "del run 457"): se crea un run sintético 'recuperado' por cada grupo
      (run_id erróneo × source) que los adopta con sus run_items.
      SM-2 QUEDA INTACTO: el replay solo distingue run_id NULL / no-NULL,
      nunca su valor concreto.
  R2  run_items contestados sin attempt en su propio run (cicatriz 6c del audit):
      se ELIMINAN. Su historial real vive en attempts bajo otro run.
  R3  fantasmas: attempts, run_items y sm2_state de (source, problem_id) que ya
      no existen en problems (los 6 de 101_weiqi): se ELIMINAN juntos.
  R4  recompute global de contadores: runs.total = COUNT(run_items) y
      runs.done = COUNT(run_items con result). Corrige los reviews pre-T19
      (total=0), el run 777 (done de más) y similares.

VERIFICACIÓN: ejecuta run_audit (el REAL del servidor) antes y después dentro de
la misma transacción y muestra el diff de severidades/counts. En dry-run la
transacción se revierte (ROLLBACK); con --apply se confirma (COMMIT).

Tras aplicar en el servidor real, recomendación: resetear la BD local del
cliente y re-pull completo, para que la contabilidad local herede la reparación.
"""

import os
import sqlite3
import sys
import uuid as uuidlib

# ── argumentos (ANTES de importar el servidor: su línea PORT lee sys.argv[1]) ──
args = sys.argv[1:]
APPLY = "--apply" in args
VERBOSE = "--verbose" in args
paths = [a for a in args if not a.startswith("--")]
if len(paths) != 1:
    print(__doc__)
    sys.exit(2)
DB = paths[0]
if not os.path.isfile(DB):
    print(f"ERROR: no existe {DB}")
    sys.exit(2)
LIMIT = None if VERBOSE else 20

sys.argv = [sys.argv[0]]  # neutralizar antes del import (PORT = int(sys.argv[1]))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tsumevault_server import run_audit  # noqa: E402

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
q = lambda sql, p=(): [dict(r) for r in con.execute(sql, p).fetchall()]

print("=" * 64)
print("T21 — REPARACIÓN DE CICATRICES DE SYNC (mayo 2026)")
print("Modo:", "APPLY (se confirmarán los cambios)" if APPLY else "DRY-RUN (rollback al final)")
print("BD:", DB)
print("=" * 64)

print("\n── Auditoría PREVIA ──")
before = run_audit(con, limit=0, skip_integrity=True)
b_map = {str(c["id"]): c for c in before["checks"]}
print(f"errors={before['summary']['errors']} warnings={before['summary']['warnings']} "
      f"info={before['summary']['info']} pass={before['summary']['pass']}")

con.execute("BEGIN")

# ═════ R1: attempts con source ≠ source de su run → run sintético ═════
print("\n── R1: attempts colgados de un run de OTRO source ──")
grupos = q("""
    SELECT a.run_id AS run_erroneo, a.source, COUNT(*) AS n,
           MIN(a.created_at) AS t0, MAX(a.created_at) AS t1, r.source AS run_source
    FROM attempts a JOIN runs r ON r.id = a.run_id
    WHERE a.source <> r.source
    GROUP BY a.run_id, a.source ORDER BY a.run_id
""")
r1_creados = []
for g in grupos:
    atts = q("""SELECT id, problem_id, result, created_at FROM attempts
                WHERE run_id=? AND source=? ORDER BY created_at ASC, id ASC""",
             (g["run_erroneo"], g["source"]))
    # capítulo/set dominantes de los problemas implicados (puede no haber: NULL)
    dom = q("""
        SELECT p.chapter_id, p.set_id, COUNT(*) AS n FROM problems p
        WHERE p.source=? AND CAST(p.problem_id AS TEXT) IN (%s)
        GROUP BY p.chapter_id, p.set_id ORDER BY n DESC LIMIT 1
    """ % ",".join("?" * len({str(a["problem_id"]) for a in atts})),
        [g["source"]] + sorted({str(a["problem_id"]) for a in atts}))
    chapter_id = dom[0]["chapter_id"] if dom else None
    set_id = dom[0]["set_id"] if dom else None
    # último resultado por problema y orden de primera aparición
    ultimo, orden = {}, []
    for a in atts:
        pid = str(a["problem_id"])
        if pid not in ultimo:
            orden.append(pid)
        ultimo[pid] = a["result"]
    new_uuid = str(uuidlib.uuid4())
    cur = con.execute(
        """INSERT INTO runs (source,set_id,chapter_id,vc_id,type,status,total,done,
                             started_at,closed_at,uuid)
           VALUES (?,?,?,NULL,'chapter','closed',?,?,?,?,?)""",
        (g["source"], set_id, chapter_id, len(orden), len(orden), g["t0"], g["t1"], new_uuid))
    new_id = cur.lastrowid
    for i, pid in enumerate(orden, 1):
        con.execute("""INSERT INTO run_items (run_id,source,problem_id,order_in_run,result)
                       VALUES (?,?,?,?,?)""", (new_id, g["source"], pid, i, ultimo[pid]))
    con.execute("UPDATE attempts SET run_id=? WHERE run_id=? AND source=?",
                (new_id, g["run_erroneo"], g["source"]))
    r1_creados.append({"run_erroneo": g["run_erroneo"], "source": g["source"],
                       "attempts": g["n"], "problemas": len(orden),
                       "nuevo_run": new_id, "uuid": new_uuid,
                       "started_at": g["t0"], "closed_at": g["t1"],
                       "chapter_id": chapter_id})
if not r1_creados:
    print("  (nada que reparar)")
for r in r1_creados:
    print(f"  run erróneo {r['run_erroneo']} × {r['source']}: {r['attempts']} attempts "
          f"({r['problemas']} problemas) → run sintético {r['nuevo_run']} "
          f"[{r['started_at']} .. {r['closed_at']}] chapter_id={r['chapter_id']} uuid={r['uuid']}")

# ═════ R2: run_items contestados sin attempt en su run → DELETE ═════
print("\n── R2: run_items contestados sin attempt en su propio run ──")
huerfanos = q("""
    SELECT ri.run_id, ri.source, ri.problem_id, ri.result
    FROM run_items ri LEFT JOIN attempts a ON a.run_id=ri.run_id
      AND a.source=ri.source AND a.problem_id=ri.problem_id
    WHERE ri.result IS NOT NULL AND a.id IS NULL
""")
por_run = {}
for h in huerfanos:
    por_run.setdefault((h["run_id"], h["source"]), 0)
    por_run[(h["run_id"], h["source"])] += 1
print(f"  a eliminar: {len(huerfanos)} items en {len(por_run)} (run × source)")
for (rid, srcp), n in sorted(por_run.items())[:LIMIT or len(por_run)]:
    print(f"    run {rid} × {srcp}: {n} items")
if LIMIT and len(por_run) > LIMIT:
    print(f"    … y {len(por_run) - LIMIT} grupos más (--verbose para todos)")
con.execute("""
    DELETE FROM run_items WHERE result IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM attempts a WHERE a.run_id=run_items.run_id
          AND a.source=run_items.source AND a.problem_id=run_items.problem_id)
""")

# ═════ R3: fantasmas de problems inexistentes → DELETE coordinado ═════
print("\n── R3: restos de problemas que ya no existen en problems ──")
fantasmas = q("""
    SELECT source, problem_id FROM (
        SELECT DISTINCT a.source, CAST(a.problem_id AS TEXT) AS problem_id FROM attempts a
        UNION SELECT DISTINCT ri.source, CAST(ri.problem_id AS TEXT) FROM run_items ri
        UNION SELECT DISTINCT s.source, CAST(s.problem_id AS TEXT) FROM sm2_state s
    ) x WHERE NOT EXISTS (
        SELECT 1 FROM problems p
        WHERE p.source=x.source AND CAST(p.problem_id AS TEXT)=x.problem_id)
    ORDER BY source, problem_id
""")
tot = {"attempts": 0, "run_items": 0, "sm2_state": 0}
for f in fantasmas:
    for tabla in ("attempts", "run_items", "sm2_state"):
        cur = con.execute(
            f"DELETE FROM {tabla} WHERE source=? AND CAST(problem_id AS TEXT)=?",
            (f["source"], f["problem_id"]))
        tot[tabla] += cur.rowcount
    print(f"  {f['source']} / {f['problem_id']}")
if not fantasmas:
    print("  (nada que purgar)")
else:
    print(f"  eliminados: {tot['attempts']} attempts, {tot['run_items']} run_items, "
          f"{tot['sm2_state']} sm2_state  ({len(fantasmas)} problemas fantasma)")

# ═════ R4: recompute de contadores total/done ═════
print("\n── R4: recompute runs.total y runs.done desde run_items ──")
descuadrados = q("""
    SELECT r.id, r.type, r.total, r.done,
           (SELECT COUNT(*) FROM run_items ri WHERE ri.run_id=r.id) AS items,
           (SELECT COUNT(*) FROM run_items ri WHERE ri.run_id=r.id
              AND ri.result IS NOT NULL) AS answered
    FROM runs r
    WHERE r.total <> (SELECT COUNT(*) FROM run_items ri WHERE ri.run_id=r.id)
       OR r.done  <> (SELECT COUNT(*) FROM run_items ri WHERE ri.run_id=r.id
                        AND ri.result IS NOT NULL)
    ORDER BY r.id
""")
print(f"  runs con contadores a corregir: {len(descuadrados)}")
for d in descuadrados[:LIMIT or len(descuadrados)]:
    print(f"    run {d['id']} ({d['type']}): total {d['total']}→{d['items']}, "
          f"done {d['done']}→{d['answered']}")
if LIMIT and len(descuadrados) > LIMIT:
    print(f"    … y {len(descuadrados) - LIMIT} más (--verbose para todos)")
con.execute("""
    UPDATE runs SET
      total=(SELECT COUNT(*) FROM run_items ri WHERE ri.run_id=runs.id),
      done =(SELECT COUNT(*) FROM run_items ri WHERE ri.run_id=runs.id
               AND ri.result IS NOT NULL)
""")

# ═════ Verificación: auditoría POSTERIOR (dentro de la transacción) ═════
print("\n── Auditoría POSTERIOR (sobre el estado reparado) ──")
after = run_audit(con, limit=0, skip_integrity=True)
a_map = {str(c["id"]): c for c in after["checks"]}
print(f"errors={after['summary']['errors']} warnings={after['summary']['warnings']} "
      f"info={after['summary']['info']} pass={after['summary']['pass']}")
print("\n  Diff de checks (solo los que cambian):")
cambios = 0
for cid, b in b_map.items():
    a = a_map.get(cid)
    if a and (a["severity"] != b["severity"] or a["count"] != b["count"]):
        print(f"    {cid:>4} {b['title'][:52]:52} {b['severity']} {b['count']} → "
              f"{a['severity']} {a['count']}")
        cambios += 1
if not cambios:
    print("    (sin cambios)")
restantes = [c for c in after["checks"] if c["severity"] in ("ERROR", "WARNING")]
if restantes:
    print("\n  ATENCIÓN — quedan checks no verdes tras la reparación:")
    for c in restantes:
        print(f"    {c['severity']} {c['id']}: {c['title']} (count={c['count']})")

# ═════ Cierre ═════
print()
if APPLY:
    con.commit()
    print("✔ CAMBIOS APLICADOS (COMMIT).")
    print("  Siguientes pasos: arrancar el servidor, lanzar /db/audit?summary=1 para")
    print("  confirmar, y valorar el reseteo + re-pull de la BD local del cliente.")
else:
    con.rollback()
    print("DRY-RUN: todos los cambios revertidos (ROLLBACK). La BD NO se ha modificado.")
    print("Si el informe es correcto: backup + --apply.")
con.close()
sys.exit(0 if not restantes else 1)
