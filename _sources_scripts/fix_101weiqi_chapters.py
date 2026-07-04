"""
fix_101weiqi_chapters.py — Corrige chapter_id y set_id de problemas de 101_weiqi
usando los JSONs de output/ como fuente de verdad.

Para Star Go School (set_id=3234), usa el sgf_path como fuente de verdad
ya que no hay JSON propio (es resultado de un merge manual).

Solo actualiza problems.chapter_id y problems.set_id.
No toca attempts, runs, ni mostrar.

Uso:
    python fix_101weiqi_chapters.py

Ejecutar desde la raíz del proyecto (mismo nivel que tsumeVault.db).
"""

import json
import os
import sqlite3
import sys

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "tsumeVault.db")
SOURCE = "101_weiqi"
INPUT_DIR = os.path.join(SCRIPT_DIR, "_sources_scripts", "output")

# Colecciones con chapters mal asignados (con JSON disponible)
TARGET_SETS = [2032, 5120, 5121, 27040, 34103]

# Mapeo para Star Go School (sin JSON): orig_set/lesson_id → chapter_id en DB
# Extraído de: SELECT DISTINCT orig_set, lesson_id, chapter_id FROM problems WHERE set_id=3234
STAR_GO_SCHOOL_SET_ID = 3234
STAR_GO_SCHOOL_MAP = {
    ("3234", "5509"): 6033,  # hug and eat questions
    ("3271", "5542"): 6034,  # Capture question 15042368880
    ("3318", "5579"): 6036,  # Bamboo joint eating question
    ("3319", "5580"): 6037,  # Capture by atari (menchi) questions
    ("3320", "5581"): 6038,  # Net eating questions
    ("3321", "5582"): 6039,  # food challenge
    ("3322", "5583"): 6040,  # Capture direction question
    ("3323", "5584"): 6042,  # Connect and die questions
    ("3324", "5585"): 6043,  # Snapback Questions
    ("3421", "139327"): 6048,  # root directory (1)
    ("3423", "138855"): 6049,  # root directory (2)
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_sgf_path(sgf_path):
    """
    Extrae (orig_set, lesson_id) de un sgf_path del tipo:
    101_weiqi/problems_std/{orig_set}/{lesson_id}/{qid}.sgf
    """
    # Quitar prefijo '101_weiqi/problems_std/'
    prefix = "101_weiqi/problems_std/"
    if not sgf_path.startswith(prefix):
        return None, None
    rest = sgf_path[len(prefix):]
    parts = rest.split("/")
    if len(parts) < 3:
        return None, None
    return parts[0], parts[1]


# ── Fix Star Go School ────────────────────────────────────────────────────────

def fix_star_go_school(con):
    print(f"\n[{STAR_GO_SCHOOL_SET_ID}] Star Go School (caso especial - sin JSON)")

    fixed = already_ok = not_mapped = 0

    rows = con.execute(
        "SELECT p.problem_id, p.sgf_path, p.chapter_id FROM problems p "
        "JOIN chapters ch ON ch.id = p.chapter_id "
        "WHERE p.source=? AND ch.set_id=?",
        (SOURCE, STAR_GO_SCHOOL_SET_ID)
    ).fetchall()

    # También buscar problemas cuyo sgf_path pertenece a Star Go School
    # pero tienen chapter_id de otra colección
    orig_sets = set(k[0] for k in STAR_GO_SCHOOL_MAP.keys())
    for orig_set in orig_sets:
        extra = con.execute(
            "SELECT p.problem_id, p.sgf_path, p.chapter_id FROM problems p "
            "JOIN chapters ch ON ch.id = p.chapter_id "
            "WHERE p.source=? AND p.sgf_path LIKE ? AND ch.set_id != ?",
            (SOURCE, f"101_weiqi/problems_std/{orig_set}/%", STAR_GO_SCHOOL_SET_ID)
        ).fetchall()
        rows = list(rows) + extra

    # Deduplicar
    seen = set()
    unique_rows = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            unique_rows.append(r)

    for problem_id, sgf_path, current_chapter_id in unique_rows:
        orig_set, lesson_id = parse_sgf_path(sgf_path)
        if orig_set is None:
            not_mapped += 1
            continue

        correct_chapter_id = STAR_GO_SCHOOL_MAP.get((orig_set, lesson_id))
        if correct_chapter_id is None:
            print(f"  [WARN] Sin mapeo para orig_set={orig_set} lesson_id={lesson_id} problem_id={problem_id}")
            not_mapped += 1
            continue

        if current_chapter_id == correct_chapter_id:
            already_ok += 1
            continue

        con.execute(
            "UPDATE problems SET chapter_id=?, set_id=? WHERE source=? AND problem_id=?",
            (correct_chapter_id, STAR_GO_SCHOOL_SET_ID, SOURCE, problem_id)
        )
        fixed += 1

    print(f"  Corregidos  : {fixed}")
    print(f"  Ya correctos: {already_ok}")
    print(f"  Sin mapeo   : {not_mapped}")
    return fixed


# ── Fix colecciones con JSON ──────────────────────────────────────────────────

def fix_from_json(con):
    total_fixed = total_not_found = total_already_ok = 0

    for set_id in TARGET_SETS:
        book_dir = os.path.join(INPUT_DIR, str(set_id))
        book_json = os.path.join(book_dir, "book.json")

        if not os.path.isfile(book_json):
            print(f"\n[WARN] No se encontró book.json para set_id={set_id}, skip")
            continue

        with open(book_json, "r", encoding="utf-8") as f:
            book = json.load(f)

        col_name = book.get("name_en") or book.get("name", str(set_id))
        print(f"\n[{set_id}] {col_name}")

        fixed = not_found = already_ok = 0

        for chap_ref in book.get("chapters", []):
            chapter_id_str = str(chap_ref["id"])
            chap_json_path = os.path.join(book_dir, chapter_id_str, "chapter.json")

            if not os.path.isfile(chap_json_path):
                print(f"  [WARN] chapter.json no encontrado: {chap_json_path}")
                continue

            with open(chap_json_path, "r", encoding="utf-8") as f:
                chap = json.load(f)

            chap_name = chap.get("name_en") or chap.get("name", chapter_id_str)

            # Buscar el chapter en la DB por set_id y nombre
            db_chapter = con.execute(
                "SELECT id FROM chapters WHERE source=? AND set_id=? AND name=?",
                (SOURCE, set_id, chap_name)
            ).fetchone()

            if not db_chapter:
                print(f"  [WARN] Chapter no encontrado en DB: set_id={set_id} name='{chap_name}'")
                continue

            db_chapter_id = db_chapter[0]

            for p in chap.get("problems", []):
                qid = p["qid"]

                row = con.execute(
                    "SELECT chapter_id, set_id FROM problems WHERE source=? AND problem_id=?",
                    (SOURCE, qid)
                ).fetchone()

                if not row:
                    not_found += 1
                    continue

                current_chapter_id, current_set_id = row

                if current_chapter_id == db_chapter_id and current_set_id == set_id:
                    already_ok += 1
                    continue

                con.execute(
                    "UPDATE problems SET chapter_id=?, set_id=? WHERE source=? AND problem_id=?",
                    (db_chapter_id, set_id, SOURCE, qid)
                )
                fixed += 1

        print(f"  Corregidos  : {fixed}")
        print(f"  Ya correctos: {already_ok}")
        print(f"  No en DB    : {not_found}")

        total_fixed += fixed
        total_not_found += not_found
        total_already_ok += already_ok

    return total_fixed


# ── Recalcular num_problems ───────────────────────────────────────────────────

def recalculate_num_problems(con):
    print("\nRecalculando num_problems...")
    all_sets = TARGET_SETS + [STAR_GO_SCHOOL_SET_ID]
    for set_id in all_sets:
        con.execute("""
            UPDATE collections
            SET num_problems = (
                SELECT COUNT(*) FROM problems p
                JOIN chapters ch ON ch.id = p.chapter_id
                WHERE p.source = collections.source AND ch.set_id = collections.set_id
            )
            WHERE source=? AND set_id=?
        """, (SOURCE, set_id))
    con.commit()
    print("Listo.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.isfile(DB_FILE):
        print(f"[ERROR] No se encontró tsumeVault.db en: {SCRIPT_DIR}")
        sys.exit(1)

    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")

    try:
        fix_star_go_school(con)
        fix_from_json(con)
        con.commit()
        recalculate_num_problems(con)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print("\n✓ Completado.")


if __name__ == "__main__":
    main()
