#!/usr/bin/env python3
"""backfill_review_run_items.py — T19: reconstruye run_items de reviews antiguas.

Contexto (bug "0%" en Runs pese a acertar):
startReview() no creaba run_items hasta el fix de T19; las reviews previas a
ese fix solo dejaron su rastro en `attempts` (con run_id = la review), nunca
en `run_items`. La pestaña Runs calcula el % de aciertos a partir de
run_items, así que esas reviews siempre mostraban 0%.

Este script reconstruye, para cada run de tipo 'review' que no tenga ninguna
fila en run_items, un run_item por problema respondido — tomando el attempt
más antiguo de cada (run_id, problem_id) — igual que hace el fix ya aplicado
en tsumevault.html para las reviews NUEVAS a partir de ahora.

USO (ejecutar sobre una COPIA LOCAL de tsumeVault.db, no contra el fichero
que está usando el servidor en caliente — ver instrucciones del canal):

    python3 backfill_review_run_items.py tsumeVault.db              # aplica
    python3 backfill_review_run_items.py tsumeVault.db --dry-run    # solo informa
    python3 backfill_review_run_items.py tsumeVault.db --no-backup  # sin copia .bak

Por defecto crea primero una copia de seguridad "<db>.bak-YYYYmmddHHMMSS"
junto al fichero original, antes de escribir nada.

Idempotente: un run que ya tiene run_items (los reconstruidos en una pasada
anterior, o los que ya traía de fábrica un run normal) nunca se toca — el
filtro es siempre "runs de tipo review con CERO run_items".

Limitación conocida y aceptada: si una review quedó a medias, los problemas
que nunca se respondieron no se pueden recuperar (esa lista nunca se
persistió en ningún sitio). No afecta al % de aciertos que se ve en Runs,
que se calcula sobre `done`, no sobre `total`.
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime


def find_stale_reviews(con):
    """Runs type='review' sin ninguna fila en run_items."""
    return con.execute(
        """
        SELECT id, source FROM runs
        WHERE type='review'
          AND NOT EXISTS (SELECT 1 FROM run_items WHERE run_items.run_id = runs.id)
        ORDER BY id
        """
    ).fetchall()


def first_attempts_per_problem(con, run_id):
    """Un attempt por problem_id (el más antiguo con ese run_id), sin
    depender de "bare columns" de GROUP BY (mismo principio que T8/3.12 en
    el servidor: SQL explícito, no implícito)."""
    return con.execute(
        """
        SELECT a.problem_id, a.result FROM attempts a
        WHERE a.run_id = ?
          AND a.id = (
            SELECT MIN(id) FROM attempts a2
            WHERE a2.run_id = a.run_id AND a2.problem_id = a.problem_id
          )
        ORDER BY a.id ASC
        """,
        (run_id,),
    ).fetchall()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db_path", help="Ruta a la copia LOCAL de tsumeVault.db")
    ap.add_argument("--dry-run", action="store_true", help="Solo informa, no escribe nada")
    ap.add_argument("--no-backup", action="store_true", help="No crear copia .bak antes de escribir")
    args = ap.parse_args()

    if not args.dry_run and not args.no_backup:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = f"{args.db_path}.bak-{stamp}"
        shutil.copy2(args.db_path, backup_path)
        print(f"[backup] copia de seguridad creada en {backup_path}")

    con = sqlite3.connect(args.db_path)
    con.execute("PRAGMA foreign_keys=ON")

    stale = find_stale_reviews(con)
    if not stale:
        print("Nada que hacer: todas las reviews ya tienen run_items.")
        con.close()
        return

    print(f"Reviews sin run_items encontradas: {len(stale)}")
    total_items = 0
    for run_id, source in stale:
        attempts = first_attempts_per_problem(con, run_id)
        if not attempts:
            print(f"  run #{run_id} ({source}): 0 attempts encontrados — se omite (no hay nada que reconstruir)")
            continue
        print(f"  run #{run_id} ({source}): {len(attempts)} run_items a crear")
        if not args.dry_run:
            for order, (problem_id, result) in enumerate(attempts, start=1):
                con.execute(
                    """
                    INSERT INTO run_items (run_id, source, problem_id, order_in_run, result)
                    VALUES (?,?,?,?,?)
                    """,
                    (run_id, source, problem_id, order, result),
                )
        total_items += len(attempts)

    if args.dry_run:
        print(f"\n[dry-run] {total_items} run_items se crearían en {len(stale)} reviews. No se ha escrito nada.")
        con.rollback()
    else:
        con.commit()
        print(f"\nHecho: {total_items} run_items creados en {len(stale)} reviews.")
    con.close()


if __name__ == "__main__":
    sys.exit(main())
