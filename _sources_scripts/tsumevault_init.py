"""
tsumevault_init.py — Crea/actualiza esquema SQLite e importa todos los sources.

Uso:
    python tsumevault_init.py

Ejecutar desde tsumevault\.
Escanea subdirectorios buscando all_collections.json.
El nombre del subdirectorio es el source.

Estructura esperada por source:
    {source}/
        all_collections.json
        problems_std/{setId}/{problemId}.sgf

Comportamiento incremental:
    - Colecciones ya existentes en DB → skip (no se tocan)
    - Colecciones nuevas → se insertan con sus capítulos y problemas
    - Problemas existentes sin SGF → se actualiza sgf_exists/color_to_play
      si el fichero ya está en disco
    - attempts y runs nunca se tocan
"""

import json
import os
import re
import sqlite3
import sys
import argparse
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "tsumeVault.db")
CHAPTER_SIZE = 50
CHAPTER_MIN = 25

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
    source          TEXT    NOT NULL,
    set_id          INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    folder          TEXT    NOT NULL,
    difficulty_raw  TEXT,
    difficulty_num  INTEGER,
    num_problems    INTEGER,
    on_disk         INTEGER NOT NULL DEFAULT 0,
    chapter_count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, set_id)
);

CREATE TABLE IF NOT EXISTS chapters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,
    set_id          INTEGER NOT NULL,
    chapter_num     INTEGER NOT NULL,
    name            TEXT,
    diff_min        INTEGER,
    diff_max        INTEGER,
    diff_avg        INTEGER,
    problem_count   INTEGER NOT NULL DEFAULT 0,
    mostrar         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source, set_id, chapter_num),
    FOREIGN KEY (source, set_id) REFERENCES collections(source, set_id)
);

CREATE TABLE IF NOT EXISTS problems (
    source          TEXT    NOT NULL,
    problem_id      INTEGER NOT NULL,
    set_id          INTEGER NOT NULL,
    chapter_id      INTEGER,
    order_in_chapter INTEGER,
    sgf_path        TEXT    NOT NULL,
    sgf_exists      INTEGER NOT NULL DEFAULT 0,
    difficulty_raw  TEXT,
    difficulty_num  INTEGER,
    color_to_play   TEXT,
    PRIMARY KEY (source, problem_id),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    problem_id  INTEGER NOT NULL,
    run_id      INTEGER,
    result      TEXT    NOT NULL,
    time_ms     INTEGER,
    created_at  TEXT    NOT NULL,
    uuid        TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,
    set_id      INTEGER,
    chapter_id  INTEGER,
    vc_id       INTEGER,
    type        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'open',
    total       INTEGER NOT NULL DEFAULT 0,
    done        INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT    NOT NULL,
    closed_at   TEXT
);

CREATE TABLE IF NOT EXISTS run_items (
    run_id      INTEGER NOT NULL,
    source      TEXT    NOT NULL,
    problem_id  INTEGER NOT NULL,
    order_in_run INTEGER NOT NULL,
    result      INTEGER,
    PRIMARY KEY (run_id, problem_id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS virtual_collections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS virtual_items (
    vc_id       INTEGER NOT NULL,
    source      TEXT    NOT NULL,
    problem_id  INTEGER NOT NULL,
    PRIMARY KEY (vc_id, source, problem_id),
    FOREIGN KEY (vc_id) REFERENCES virtual_collections(id)
);

CREATE INDEX IF NOT EXISTS idx_problems_set   ON problems(source, set_id);
CREATE INDEX IF NOT EXISTS idx_problems_diff  ON problems(source, difficulty_num);
CREATE INDEX IF NOT EXISTS idx_problems_chap  ON problems(chapter_id);
CREATE INDEX IF NOT EXISTS idx_attempts_prob  ON attempts(source, problem_id);
CREATE INDEX IF NOT EXISTS idx_attempts_run   ON attempts(run_id);
CREATE INDEX IF NOT EXISTS idx_run_items_run  ON run_items(run_id);
CREATE INDEX IF NOT EXISTS idx_attempts_source_problem_created ON attempts(source, problem_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chapters_mostrar ON chapters(id, mostrar);

CREATE TABLE IF NOT EXISTS game_collections (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL UNIQUE,
    folder  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    game_collection_id  INTEGER NOT NULL,
    name                TEXT    NOT NULL,
    sgf_path            TEXT    NOT NULL,
    FOREIGN KEY (game_collection_id) REFERENCES game_collections(id)
);

CREATE INDEX IF NOT EXISTS idx_games_collection ON games(game_collection_id);
"""

SCHEMA_VIEW = """
DROP VIEW IF EXISTS problem_stats;
CREATE VIEW problem_stats AS
SELECT
    source,
    problem_id,
    COUNT(*)                                                    AS total_attempts,
    SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END)          AS total_correct,
    SUM(CASE WHEN result='wrong'   THEN 1 ELSE 0 END)          AS total_wrong,
    ROUND(AVG(CASE WHEN result='correct' THEN 1.0 ELSE 0 END) * 100, 1) AS pct_correct,
    AVG(time_ms)                                                AS avg_time_ms,
    MAX(created_at)                                             AS last_seen
FROM attempts
GROUP BY source, problem_id;
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

RAW_RE = re.compile(r"\(([+-]?\d+(?:\.\d+)?)\)")
LEVEL_RE = re.compile(r"^(\d+)\s*([KkDd])\s*(\+?)$")


def parse_levelname_101weiqi(levelname):
    """Escala consistente con el resto de sources. 30k=-900, 1k=1900, 1d=2100."""
    if not levelname:
        return None
    m = LEVEL_RE.match(levelname.strip())
    if not m:
        return None
    num = int(m.group(1))
    grade = m.group(2).upper()
    plus = m.group(3) == "+"
    base = (2000 + num * 100) if grade == "D" else (2000 - num * 100)
    return base + (50 if plus else 0)


def snap_to_rank(r):
    return round(r / 100) * 100


def parse_difficulty_num(difficulty_raw):
    if not difficulty_raw:
        return None
    m = RAW_RE.search(difficulty_raw)
    if not m:
        return None
    return snap_to_rank(float(m.group(1)))


def detect_color_to_play(sgf_path):
    try:
        with open(sgf_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = re.search(r";\s*([BW])\s*\[", text[text.find(";") + 1 :])
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def find_sources(script_dir):
    """Escanea subdirectorios buscando all_collections.json o estructura 101_weiqi."""
    sources = []
    for entry in os.scandir(script_dir):
        if not entry.is_dir():
            continue
        col_file = os.path.join(entry.path, "all_collections.json")
        problems_dir = os.path.join(entry.path, "problems_std")
        if os.path.isfile(col_file):
            sources.append({
                "source": entry.name,
                "collections_file": col_file,
                "problems_dir": problems_dir,
            })
        elif entry.name == "101_weiqi" and os.path.isdir(problems_dir):
            sources.append({
                "source": entry.name,
                "collections_file": None,
                "problems_dir": problems_dir,
            })
    return sources


# ── Import de un source ───────────────────────────────────────────────────────


def import_source(con, source_info):
    source = source_info["source"]
    col_file = source_info["collections_file"]
    problems_dir = source_info["problems_dir"]

    with open(col_file, "r", encoding="utf-8") as f:
        collections = json.load(f)

    print(f"\n[{source}] {len(collections)} colecciones en JSON")

    col_new = col_skip = prob_new = prob_updated = chap_new = 0

    for col in collections:
        set_id = col["setId"]
        name = col["name"]
        diff_raw = col.get("difficulty")
        num_probs = col.get("numProblems", 0)
        problems = col.get("problems", [])

        folder_name = str(set_id)
        folder_path = os.path.join(problems_dir, folder_name)

        # ── Colección ya existente → actualizar sgf_exists y skip resto ──
        existing = con.execute(
            "SELECT 1 FROM collections WHERE source=? AND set_id=?", (source, set_id)
        ).fetchone()

        if existing:
            # Actualizar sgf_exists / color_to_play para problemas sin SGF
            missing = con.execute(
                "SELECT problem_id, sgf_path FROM problems WHERE source=? AND set_id=? AND sgf_exists=0",
                (source, set_id),
            ).fetchall()
            for row in missing:
                problem_id, sgf_path = row[0], row[1]
                sgf_abs = os.path.join(SCRIPT_DIR, sgf_path.replace("/", os.sep))
                if os.path.isfile(sgf_abs):
                    color = detect_color_to_play(sgf_abs)
                    con.execute(
                        "UPDATE problems SET sgf_exists=1, color_to_play=? WHERE source=? AND problem_id=?",
                        (color, source, problem_id),
                    )
                    prob_updated += 1
            col_skip += 1
            continue

        # ── Colección nueva ──
        on_disk = 0

        if "chapters" in col:
            # ── Formato con capítulos pre-definidos (ej: guo_juan) ──
            # Cada chapter del JSON se chunkea igual que tsumego_hero (CHAPTER_SIZE/CHAPTER_MIN).
            # Si resulta más de un chunk, el nombre lleva sufijo (i/total).
            chapters = []

            for chap_json in col["chapters"]:
                chap_name = chap_json.get("name", f"Ch {len(chapters) + 1}")
                chap_folder = str(
                    chap_json.get("folder") or chap_json.get("chapterId", set_id)
                )

                # Normalizar problemas
                norm_problems = []
                for p in chap_json.get("problems", []):
                    norm_problems.append(
                        {
                            "problemId": p["problemId"],
                            "difficultyRaw": p.get("difficulty_raw") or p.get("difficultyRaw"),
                            "difficultyNum": p.get("difficulty_num")
                            or parse_difficulty_num(p.get("difficultyRaw")),
                            "lessonId": p.get("lessonId"),
                        }
                    )

                # on_disk: contar SGFs en todas las carpetas de lessons del chapter
                lesson_ids = set(str(p["lessonId"]) for p in norm_problems if p.get("lessonId"))
                for lid in lesson_ids:
                    lid_path = os.path.join(problems_dir, lid)
                    if os.path.isdir(lid_path):
                        on_disk += sum(
                            1 for f in os.listdir(lid_path) if f.lower().endswith(".sgf")
                        )

                # Chunking igual que tsumego_hero
                raw_chunks = []
                for i in range(0, len(norm_problems), CHAPTER_SIZE):
                    raw_chunks.append(norm_problems[i : i + CHAPTER_SIZE])
                if len(raw_chunks) > 1 and len(raw_chunks[-1]) < CHAPTER_MIN:
                    raw_chunks[-2] = raw_chunks[-2] + raw_chunks[-1]
                    raw_chunks.pop()

                total_chunks = len(raw_chunks)
                for chunk_idx, chunk in enumerate(raw_chunks, 1):
                    if total_chunks > 1:
                        chunk_name = f"{chap_name} ({chunk_idx}/{total_chunks})"
                    else:
                        chunk_name = chap_name
                    diffs = [p["difficultyNum"] for p in chunk if p["difficultyNum"] is not None]
                    avg_diff = snap_to_rank(sum(diffs) / len(diffs)) if diffs else None
                    chapters.append(
                        {
                            "chapter_num": len(chapters) + 1,
                            "name": chunk_name,
                            "diff_min": min(diffs) if diffs else None,
                            "diff_max": max(diffs) if diffs else None,
                            "diff_avg": avg_diff,
                            "problems": chunk,
                            "folder": chap_folder,
                        }
                    )

            all_diffs = [
                p["difficultyNum"]
                for chap in chapters
                for p in chap["problems"]
                if p["difficultyNum"] is not None
            ]
            col_diff_num = (
                snap_to_rank(sum(all_diffs) / len(all_diffs)) if all_diffs else None
            )

        else:
            # ── Formato tsumego_hero: calcular capítulos por bloques de 50 ──
            if os.path.isdir(folder_path):
                on_disk = sum(
                    1 for f in os.listdir(folder_path) if f.lower().endswith(".sgf")
                )

            def sort_key(p):
                d = parse_difficulty_num(p.get("difficultyRaw"))
                return (d if d is not None else 0, p["problemId"])

            problems_sorted = sorted(problems, key=sort_key)

            raw_chunks = []
            for i in range(0, len(problems_sorted), CHAPTER_SIZE):
                raw_chunks.append(problems_sorted[i : i + CHAPTER_SIZE])
            if len(raw_chunks) > 1 and len(raw_chunks[-1]) < CHAPTER_MIN:
                raw_chunks[-2] = raw_chunks[-2] + raw_chunks[-1]
                raw_chunks.pop()

            chapters = []
            for chunk in raw_chunks:
                diffs = [parse_difficulty_num(p.get("difficultyRaw")) for p in chunk]
                diffs = [d for d in diffs if d is not None]
                avg_diff = snap_to_rank(sum(diffs) / len(diffs)) if diffs else None
                chapters.append(
                    {
                        "chapter_num": len(chapters) + 1,
                        "name": f"Ch {len(chapters) + 1}",
                        "diff_min": min(diffs) if diffs else None,
                        "diff_max": max(diffs) if diffs else None,
                        "diff_avg": avg_diff,
                        "problems": chunk,
                        "folder": folder_name,
                    }
                )

            all_diffs = [
                parse_difficulty_num(p.get("difficultyRaw")) for p in problems_sorted
            ]
            all_diffs = [d for d in all_diffs if d is not None]
            col_diff_num = (
                snap_to_rank(sum(all_diffs) / len(all_diffs))
                if all_diffs
                else parse_difficulty_num(diff_raw)
            )

        con.execute(
            """
            INSERT INTO collections
                (source, set_id, name, folder, difficulty_raw, difficulty_num,
                 num_problems, on_disk, chapter_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                source,
                set_id,
                name,
                folder_name,
                diff_raw,
                col_diff_num,
                num_probs,
                on_disk,
                len(chapters),
            ),
        )
        col_new += 1

        for chap in chapters:
            cur = con.execute(
                """
                INSERT INTO chapters (source, set_id, chapter_num, name, diff_min, diff_max, diff_avg, problem_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    source,
                    set_id,
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

            chap_folder = chap["folder"]

            for order, p in enumerate(chap["problems"], 1):
                problem_id = p["problemId"]
                p_diff_raw = p.get("difficultyRaw")
                p_diff_num = p.get("difficultyNum") or parse_difficulty_num(p_diff_raw)

                lesson_folder = str(p.get("lessonId") or chap["folder"])
                lesson_folder_path = os.path.join(problems_dir, lesson_folder)
                sgf_filename = f"{problem_id}.sgf"
                sgf_abs = os.path.join(lesson_folder_path, sgf_filename)
                sgf_rel = os.path.join(
                    source, "problems_std", lesson_folder, sgf_filename
                ).replace("\\", "/")
                sgf_exists = 1 if os.path.isfile(sgf_abs) else 0
                color = detect_color_to_play(sgf_abs) if sgf_exists else None

                con.execute(
                    """
                    INSERT OR REPLACE INTO problems
                        (source, problem_id, set_id, chapter_id, order_in_chapter,
                         sgf_path, sgf_exists, difficulty_raw, difficulty_num, color_to_play)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        source,
                        problem_id,
                        set_id,
                        chapter_id,
                        order,
                        sgf_rel,
                        sgf_exists,
                        p_diff_raw,
                        p_diff_num,
                        color,
                    ),
                )
                prob_new += 1

    con.commit()
    print(f"  Colecciones nuevas   : {col_new}")
    print(f"  Colecciones skip     : {col_skip}")
    print(f"  Capítulos nuevos     : {chap_new}")
    print(f"  Problemas nuevos     : {prob_new}")
    print(f"  Problemas actualizados (SGF): {prob_updated}")


# ── Import 101weiqi (fuente de verdad = disco) ───────────────────────────────


def import_source_101weiqi(con, source_info):
    source = source_info["source"]
    problems_dir = source_info["problems_dir"]

    if not os.path.isdir(problems_dir):
        print(f"\n[{source}] problems_dir no encontrado: {problems_dir}")
        return

    book_dirs = sorted(
        (e for e in os.scandir(problems_dir) if e.is_dir()),
        key=lambda e: int(e.name) if e.name.isdigit() else 0,
    )
    print(f"\n[{source}] {len(book_dirs)} books en disco")

    col_new = col_skip = chap_new = prob_new = prob_updated = 0

    for book_entry in book_dirs:
        set_id = int(book_entry.name) if book_entry.name.isdigit() else None
        if set_id is None:
            continue
        book_path = book_entry.path

        # ── Colección ya existente → actualizar sgf_exists y skip ──
        existing = con.execute(
            "SELECT 1 FROM collections WHERE source=? AND set_id=?", (source, set_id)
        ).fetchone()
        if existing:
            missing = con.execute(
                "SELECT problem_id, sgf_path FROM problems "
                "WHERE source=? AND set_id=? AND sgf_exists=0",
                (source, set_id),
            ).fetchall()
            for problem_id, sgf_path in missing:
                sgf_abs = os.path.join(SCRIPT_DIR, sgf_path.replace("/", os.sep))
                if os.path.isfile(sgf_abs):
                    color = detect_color_to_play(sgf_abs)
                    con.execute(
                        "UPDATE problems SET sgf_exists=1, color_to_play=? "
                        "WHERE source=? AND problem_id=?",
                        (color, source, problem_id),
                    )
                    prob_updated += 1
            col_skip += 1
            continue

        # ── Leer book.json para nombre ──
        book_json_path = os.path.join(book_path, "book.json")
        book_name = str(set_id)
        if os.path.isfile(book_json_path):
            try:
                bj = json.load(open(book_json_path, encoding="utf-8"))
                book_name = bj.get("name_en") or bj.get("name") or book_name
            except Exception:
                pass

        # ── Escanear chapters en disco ──
        chapter_dirs = sorted(
            (e for e in os.scandir(book_path) if e.is_dir()),
            key=lambda e: int(e.name) if e.name.isdigit() else 0,
        )

        all_chunks = []
        on_disk = 0

        for chap_entry in chapter_dirs:
            chap_path = chap_entry.path

            # Problemas reales = SGFs presentes en disco
            sgf_files = sorted(
                f for f in os.listdir(chap_path) if f.lower().endswith(".sgf")
            )
            if not sgf_files:
                continue
            on_disk += len(sgf_files)

            # Leer chapter.json para nombre y metadatos
            chap_json_path = os.path.join(chap_path, "chapter.json")
            chap_name = chap_entry.name
            prob_meta = {}
            if os.path.isfile(chap_json_path):
                try:
                    cj = json.load(open(chap_json_path, encoding="utf-8"))
                    chap_name = cj.get("name_en") or cj.get("name") or chap_name
                    for p in cj.get("problems", []):
                        prob_meta[p["qid"]] = p
                except Exception:
                    pass

            # Construir lista de problemas desde disco
            problems = []
            for fname in sgf_files:
                try:
                    qid = int(os.path.splitext(fname)[0])
                except ValueError:
                    continue
                meta = prob_meta.get(qid, {})
                levelname = meta.get("levelname")
                blackfirst = meta.get("blackfirst")

                # Fallback 1: leer el .json individual del problema
                if levelname is None:
                    prob_json_path = os.path.join(chap_path, f"{qid}.json")
                    if os.path.isfile(prob_json_path):
                        try:
                            pj = json.load(open(prob_json_path, encoding="utf-8"))
                            levelname = pj.get("levelname")
                            if blackfirst is None:
                                blackfirst = pj.get("blackfirst")
                        except Exception:
                            pass

                diff_num = parse_levelname_101weiqi(levelname)
                sgf_rel = f"{source}/problems_std/{book_entry.name}/{chap_entry.name}/{fname}".replace("\\", "/")
                sgf_abs = os.path.join(SCRIPT_DIR, sgf_rel.replace("/", os.sep))
                color = ("B" if blackfirst else None) or detect_color_to_play(sgf_abs)
                problems.append({
                    "problemId": qid,
                    "difficultyRaw": levelname,
                    "difficultyNum": diff_num,
                    "color": color,
                    "sgf_rel": sgf_rel,
                })

            # ── Chunking ──
            raw_chunks = []
            for i in range(0, len(problems), CHAPTER_SIZE):
                raw_chunks.append(problems[i : i + CHAPTER_SIZE])
            if len(raw_chunks) > 1 and len(raw_chunks[-1]) < CHAPTER_MIN:
                raw_chunks[-2] = raw_chunks[-2] + raw_chunks[-1]
                raw_chunks.pop()

            total_chunks = len(raw_chunks)
            for chunk_idx, chunk in enumerate(raw_chunks, 1):
                name = chap_name if total_chunks == 1 else f"{chap_name} ({chunk_idx}/{total_chunks})"
                diffs = [p["difficultyNum"] for p in chunk if p["difficultyNum"] is not None]
                avg_diff = snap_to_rank(sum(diffs) / len(diffs)) if diffs else None

                # Fallback 2: heredar diff_avg del chunk para problemas sin dificultad
                if avg_diff is not None:
                    for p in chunk:
                        if p["difficultyNum"] is None:
                            p["difficultyNum"] = avg_diff

                all_chunks.append({
                    "chapter_num": len(all_chunks) + 1,
                    "name": name,
                    "diff_min": min(diffs) if diffs else None,
                    "diff_max": max(diffs) if diffs else None,
                    "diff_avg": avg_diff,
                    "problems": chunk,
                })

        if not all_chunks:
            continue

        # ── Dificultad media de la colección ──
        all_diffs = [
            p["difficultyNum"]
            for ch in all_chunks
            for p in ch["problems"]
            if p["difficultyNum"] is not None
        ]
        col_diff_num = snap_to_rank(sum(all_diffs) / len(all_diffs)) if all_diffs else None

        con.execute(
            """
            INSERT INTO collections
                (source, set_id, name, folder, difficulty_raw, difficulty_num,
                 num_problems, on_disk, chapter_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source, set_id, book_name, str(set_id), None, col_diff_num,
             on_disk, on_disk, len(all_chunks)),
        )
        col_new += 1

        for chap in all_chunks:
            cur = con.execute(
                """
                INSERT INTO chapters
                    (source, set_id, chapter_num, name,
                     diff_min, diff_max, diff_avg, problem_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source, set_id, chap["chapter_num"], chap["name"],
                 chap["diff_min"], chap["diff_max"], chap["diff_avg"],
                 len(chap["problems"])),
            )
            chapter_id = cur.lastrowid
            chap_new += 1

            for order, p in enumerate(chap["problems"], 1):
                con.execute(
                    """
                    INSERT OR REPLACE INTO problems
                        (source, problem_id, set_id, chapter_id, order_in_chapter,
                         sgf_path, sgf_exists, difficulty_raw, difficulty_num, color_to_play)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (source, p["problemId"], set_id, chapter_id, order,
                     p["sgf_rel"], 1, p["difficultyRaw"], p["difficultyNum"], p["color"]),
                )
                prob_new += 1

    con.commit()
    print(f"  Colecciones nuevas        : {col_new}")
    print(f"  Colecciones skip          : {col_skip}")
    print(f"  Capítulos nuevos          : {chap_new}")
    print(f"  Problemas nuevos          : {prob_new}")
    print(f"  Problemas actualizados    : {prob_updated}")


# ── Import de partidas ────────────────────────────────────────────────────────


def import_games(con):
    games_dir = os.path.join(SCRIPT_DIR, "games")
    if not os.path.isdir(games_dir):
        print("\n[games] Carpeta 'games/' no encontrada, skip.")
        return

    collections = sorted(
        e.name for e in os.scandir(games_dir) if e.is_dir()
    )
    if not collections:
        print("\n[games] Sin subcarpetas en 'games/', skip.")
        return

    print(f"\n[games] {len(collections)} colecciones encontradas")
    col_new = col_skip = game_new = 0

    for col_name in collections:
        col_path = os.path.join(games_dir, col_name)

        existing = con.execute(
            "SELECT id FROM game_collections WHERE name=?", (col_name,)
        ).fetchone()

        if existing:
            col_skip += 1
            continue

        cur = con.execute(
            "INSERT INTO game_collections (name, folder) VALUES (?, ?)",
            (col_name, col_name),
        )
        col_id = cur.lastrowid
        col_new += 1

        sgf_files = sorted(
            f for f in os.listdir(col_path) if f.lower().endswith(".sgf")
        )
        for filename in sgf_files:
            sgf_rel = f"games/{col_name}/{filename}".replace("\\", "/")
            con.execute(
                "INSERT INTO games (game_collection_id, name, sgf_path) VALUES (?, ?, ?)",
                (col_id, filename, sgf_rel),
            )
            game_new += 1

    con.commit()
    print(f"  Colecciones nuevas : {col_new}")
    print(f"  Colecciones skip   : {col_skip}")
    print(f"  Partidas nuevas    : {game_new}")


# ── Import de partidas (remoto) ───────────────────────────────────────────────


def import_games_remote(server_url, games_dir):
    """Envía colecciones y partidas al servidor remoto vía /admin/import_games."""
    if not os.path.isdir(games_dir):
        print("\n[games-remote] Carpeta 'games/' no encontrada, skip.")
        return

    collections = sorted(e.name for e in os.scandir(games_dir) if e.is_dir())
    if not collections:
        print("\n[games-remote] Sin subcarpetas en 'games/', skip.")
        return

    print(f"\n[games-remote] {len(collections)} colecciones encontradas → {server_url}")

    payload_cols = []
    payload_games = []
    for col_name in collections:
        col_path = os.path.join(games_dir, col_name)
        payload_cols.append({"name": col_name, "folder": col_name})
        sgf_files = sorted(f for f in os.listdir(col_path) if f.lower().endswith(".sgf"))
        for filename in sgf_files:
            sgf_rel = f"games/{col_name}/{filename}".replace("\\", "/")
            payload_games.append({
                "collection_name": col_name,
                "name": filename,
                "sgf_path": sgf_rel,
            })

    payload = json.dumps({
        "game_collections": payload_cols,
        "games": payload_games,
    }).encode("utf-8")

    url = server_url.rstrip("/") + "/admin/import_games"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        print(f"  Colecciones nuevas : {result.get('inserted_collections', '?')}")
        print(f"  Partidas nuevas    : {result.get('inserted_games', '?')}")
    except Exception as e:
        print(f"  [ERROR] {e}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", metavar="URL", default=None,
                        help="Si se indica, importa juegos al servidor remoto en lugar de local")
    args = parser.parse_args()

    games_dir = os.path.join(SCRIPT_DIR, "games")

    if args.server:
        # Modo remoto: solo importa juegos al servidor
        import_games_remote(args.server, games_dir)
        print("\nListo.")
        return

    sources = find_sources(SCRIPT_DIR)
    if not sources:
        print("[ERROR] No se encontró ningún subdirectorio con all_collections.json")
        sys.exit(1)

    print(f"Sources encontrados: {[s['source'] for s in sources]}")
    print(f"DB: {DB_FILE}")

    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    con.executescript(SCHEMA_VIEW)

    # Migración: añadir columna mostrar a chapters si no existe
    cols_ch = [r[1] for r in con.execute("PRAGMA table_info(chapters)").fetchall()]
    if "mostrar" not in cols_ch:
        con.execute(
            "ALTER TABLE chapters ADD COLUMN mostrar INTEGER NOT NULL DEFAULT 0"
        )
        con.commit()
        print("Migración: columna 'mostrar' añadida a chapters")

    # Migración: añadir columna name a chapters si no existe
    cols = [r[1] for r in con.execute("PRAGMA table_info(chapters)").fetchall()]
    if "name" not in cols:
        con.execute("ALTER TABLE chapters ADD COLUMN name TEXT")
        con.execute(
            "UPDATE chapters SET name = 'Ch ' || chapter_num WHERE name IS NULL"
        )
        con.commit()
        print("Migración: columna 'name' añadida a chapters")
        # Borrar capítulos y problemas de sources con capítulos pre-definidos para reimportar con nombres
        for s_info in sources:
            s = s_info["source"]
            col_data = json.load(open(s_info["collections_file"], encoding="utf-8"))
            if col_data and "chapters" in col_data[0]:
                con.execute("DELETE FROM problems WHERE source=?", (s,))
                con.execute("DELETE FROM chapters WHERE source=?", (s,))
                con.execute("DELETE FROM collections WHERE source=?", (s,))
                con.commit()
                print(f"  Reimportando {s} con nombres de capítulos...")

    for source_info in sources:
        if source_info["source"] == "101_weiqi":
            import_source_101weiqi(con, source_info)
        else:
            import_source(con, source_info)

    import_games(con)

    con.close()
    print("\nListo.")


if __name__ == "__main__":
    main()
