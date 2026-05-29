"""
import_101weiqi.py — Importa el source 101weiqi a tsumeVault.db.

Uso:
    python import_101weiqi.py

Ejecutar desde la raíz del proyecto (mismo nivel que tsumeVault.db).

Estructura de entrada:
    output/{book_id}/book.json
    output/{book_id}/{chapter_id}/chapter.json
    output/{book_id}/{chapter_id}/{qid}.sgf

Estructura de salida (SGFs):
    101weiqi/problems_std/{book_id}/{chapter_id}/{qid}.sgf

Comportamiento incremental:
    - Colecciones ya existentes en DB → skip
    - Colecciones nuevas → se insertan con sus capítulos y problemas
    - SGFs se copian a 101weiqi/problems_std/ si no están ya allí
"""

import json
import os
import re
import shutil
import sqlite3
import sys

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "tsumeVault.db")
SOURCE = "101_weiqi"
INPUT_DIR = os.path.join(SCRIPT_DIR, "output")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, SOURCE, "problems_std")

# ── Difficulty helpers ────────────────────────────────────────────────────────

# Convierte levelname de 101weiqi a difficulty_num en la escala TsumeVault:
#   21k=0, cada grado=100 pts, "+" = 50 pts adicionales
# Ejemplos: "15K+" → 650, "15K" → 600, "1K" → 2000, "1D" → 2100, "5D" → 2500

LEVEL_RE = re.compile(r"^(\d+)\s*([KkDd])\s*(\+?)$")


def snap_to_rank(r):
    return round(r / 100) * 100


def parse_levelname(levelname: str):
    """Devuelve (difficulty_num, difficulty_raw) o (None, levelname) si no parsea."""
    if not levelname:
        return None, levelname
    m = LEVEL_RE.match(levelname.strip())
    if not m:
        return None, levelname
    num = int(m.group(1))
    grade = m.group(2).upper()
    plus = m.group(3) == "+"

    if grade == "K":
        base = (21 - num) * 100  # 15k → 600, 1k → 2000
    else:
        base = 2000 + num * 100  # 1d → 2100, 9d → 2900

    diff_num = base + (50 if plus else 0)
    return diff_num, levelname


# ── SGF helpers ───────────────────────────────────────────────────────────────


def detect_color_to_play(sgf_path: str):
    try:
        with open(sgf_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = re.search(r";\s*([BW])\s*\[", text[text.find(";") + 1 :])
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


# ── Main import ───────────────────────────────────────────────────────────────


def import_101weiqi(con: sqlite3.Connection):
    if not os.path.isdir(INPUT_DIR):
        print(f"[ERROR] No se encontró la carpeta input: {INPUT_DIR}")
        sys.exit(1)

    col_new = col_skip = chap_new = prob_new = sgf_copied = 0

    # Iterar book_ids (subcarpetas de output/)
    book_dirs = sorted(
        e.name
        for e in os.scandir(INPUT_DIR)
        if e.is_dir() and os.path.isfile(os.path.join(e.path, "book.json"))
    )

    if not book_dirs:
        print("[ERROR] No se encontraron carpetas con book.json en output/")
        sys.exit(1)

    print(f"[{SOURCE}] {len(book_dirs)} books encontrados")

    for book_id_str in book_dirs:
        book_id = int(book_id_str)
        book_path = os.path.join(INPUT_DIR, book_id_str)

        with open(os.path.join(book_path, "book.json"), "r", encoding="utf-8") as f:
            book = json.load(f)

        # Usar name_en si existe, si no name
        col_name = book.get("name_en") or book.get("name", str(book_id))

        # ── Colección ya existente → skip ──
        existing = con.execute(
            "SELECT 1 FROM collections WHERE source=? AND set_id=?", (SOURCE, book_id)
        ).fetchone()

        if existing:
            print(f"  skip  book {book_id} ({col_name})")
            col_skip += 1
            continue

        print(f"  nuevo book {book_id} ({col_name})")

        # Acumular capítulos para calcular dificultad global de la colección
        chapters_data = []

        for chap_num, chap_ref in enumerate(book.get("chapters", []), 1):
            chapter_id_str = str(chap_ref["id"])
            chap_dir = os.path.join(book_path, chapter_id_str)
            chap_json_path = os.path.join(chap_dir, "chapter.json")

            if not os.path.isfile(chap_json_path):
                print(f"    [WARN] chapter.json no encontrado: {chap_json_path}")
                continue

            with open(chap_json_path, "r", encoding="utf-8") as f:
                chap = json.load(f)

            chap_name = chap.get("name_en") or chap.get("name", f"Ch {chap_num}")

            problems = []
            for p in chap.get("problems", []):
                qid = p["qid"]
                levelname = p.get("levelname", "")
                diff_num, diff_raw = parse_levelname(levelname)

                # Ruta SGF origen y destino
                sgf_src = os.path.join(chap_dir, f"{qid}.sgf")
                sgf_dest_rel = os.path.join(
                    SOURCE, "problems_std", book_id_str, chapter_id_str, f"{qid}.sgf"
                ).replace("\\", "/")
                sgf_dest_abs = os.path.join(
                    OUTPUT_DIR, book_id_str, chapter_id_str, f"{qid}.sgf"
                )

                # Copiar SGF si existe en origen y no está ya en destino
                sgf_exists = 0
                color = None
                if os.path.isfile(sgf_src):
                    if not os.path.isfile(sgf_dest_abs):
                        os.makedirs(os.path.dirname(sgf_dest_abs), exist_ok=True)
                        shutil.copy2(sgf_src, sgf_dest_abs)
                        sgf_copied += 1
                    sgf_exists = 1
                    color = detect_color_to_play(sgf_dest_abs)

                problems.append(
                    {
                        "qid": qid,
                        "diff_raw": diff_raw,
                        "diff_num": diff_num,
                        "sgf_path": sgf_dest_rel,
                        "sgf_exists": sgf_exists,
                        "color": color,
                        "order": p.get("qindex", len(problems) + 1),
                    }
                )

            # Estadísticas de dificultad del capítulo
            diffs = [p["diff_num"] for p in problems if p["diff_num"] is not None]
            chapters_data.append(
                {
                    "chapter_num": chap_num,
                    "name": chap_name,
                    "diff_min": min(diffs) if diffs else None,
                    "diff_max": max(diffs) if diffs else None,
                    "diff_avg": snap_to_rank(sum(diffs) / len(diffs))
                    if diffs
                    else None,
                    "problems": problems,
                }
            )

        # Dificultad global de la colección
        all_diffs = [
            p["diff_num"]
            for chap in chapters_data
            for p in chap["problems"]
            if p["diff_num"] is not None
        ]
        col_diff_num = (
            snap_to_rank(sum(all_diffs) / len(all_diffs)) if all_diffs else None
        )

        # on_disk: SGFs ya copiados
        on_disk = sum(
            p["sgf_exists"] for chap in chapters_data for p in chap["problems"]
        )

        # ── Insertar colección ──
        con.execute(
            """
            INSERT INTO collections
                (source, set_id, name, folder, difficulty_raw, difficulty_num,
                 num_problems, on_disk, chapter_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SOURCE,
                book_id,
                col_name,
                book_id_str,  # folder = book_id
                None,  # sin difficulty_raw global en 101weiqi
                col_diff_num,
                sum(len(c["problems"]) for c in chapters_data),
                on_disk,
                len(chapters_data),
            ),
        )
        col_new += 1

        # ── Insertar capítulos y problemas ──
        for chap in chapters_data:
            cur = con.execute(
                """
                INSERT INTO chapters
                    (source, set_id, chapter_num, name,
                     diff_min, diff_max, diff_avg, problem_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    SOURCE,
                    book_id,
                    chap["chapter_num"],
                    chap["name"],
                    chap["diff_min"],
                    chap["diff_max"],
                    chap["diff_avg"],
                    len(chap["problems"]),
                ),
            )
            chapter_id = cur.lastrowid
            chap_new += 1

            for p in chap["problems"]:
                con.execute(
                    """
                    INSERT OR IGNORE INTO problems
                        (source, problem_id, set_id, chapter_id, order_in_chapter,
                         sgf_path, sgf_exists, difficulty_raw, difficulty_num, color_to_play)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        SOURCE,
                        p["qid"],
                        book_id,
                        chapter_id,
                        p["order"],
                        p["sgf_path"],
                        p["sgf_exists"],
                        p["diff_raw"],
                        p["diff_num"],
                        p["color"],
                    ),
                )
                prob_new += 1

    con.commit()
    print("\nResumen:")
    print(f"  Colecciones nuevas  : {col_new}")
    print(f"  Colecciones skip    : {col_skip}")
    print(f"  Capítulos nuevos    : {chap_new}")
    print(f"  Problemas nuevos    : {prob_new}")
    print(f"  SGFs copiados       : {sgf_copied}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    if not os.path.isfile(DB_FILE):
        print(f"[ERROR] No se encontró tsumeVault.db en: {SCRIPT_DIR}")
        print("        Ejecuta tsumevault_init.py primero.")
        sys.exit(1)

    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")

    try:
        import_101weiqi(con)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print("\nListo.")


if __name__ == "__main__":
    main()
