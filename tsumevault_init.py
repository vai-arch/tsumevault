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

import os
import re
import sys
import json
import sqlite3

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_FILE      = os.path.join(SCRIPT_DIR, 'tsumeVault.db')
CHAPTER_SIZE = 50
CHAPTER_MIN  = 25

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
    diff_min        INTEGER,
    diff_max        INTEGER,
    diff_avg        INTEGER,
    problem_count   INTEGER NOT NULL DEFAULT 0,
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
    created_at  TEXT    NOT NULL
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

RAW_RE = re.compile(r'\(([+-]?\d+(?:\.\d+)?)\)')

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
        with open(sgf_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        m = re.search(r';\s*([BW])\s*\[', text[text.find(';')+1:])
        if m:
            return m.group(1)
    except Exception:
        pass
    return None

def find_sources(script_dir):
    """Escanea subdirectorios buscando all_collections.json."""
    sources = []
    for entry in os.scandir(script_dir):
        if not entry.is_dir():
            continue
        col_file = os.path.join(entry.path, 'all_collections.json')
        if os.path.isfile(col_file):
            sources.append({
                'source': entry.name,
                'collections_file': col_file,
                'problems_dir': os.path.join(entry.path, 'problems_std'),
            })
    return sources

# ── Import de un source ───────────────────────────────────────────────────────

def import_source(con, source_info):
    source       = source_info['source']
    col_file     = source_info['collections_file']
    problems_dir = source_info['problems_dir']

    with open(col_file, 'r', encoding='utf-8') as f:
        collections = json.load(f)

    print(f"\n[{source}] {len(collections)} colecciones en JSON")

    col_new = col_skip = prob_new = prob_updated = chap_new = 0

    for col in collections:
        set_id   = col['setId']
        name     = col['name']
        diff_raw = col.get('difficulty')
        num_probs = col.get('numProblems', 0)
        problems  = col.get('problems', [])

        folder_name  = str(set_id)
        folder_path  = os.path.join(problems_dir, folder_name)

        # ── Colección ya existente → actualizar sgf_exists y skip resto ──
        existing = con.execute(
            "SELECT 1 FROM collections WHERE source=? AND set_id=?",
            (source, set_id)
        ).fetchone()

        if existing:
            # Actualizar sgf_exists / color_to_play para problemas sin SGF
            missing = con.execute(
                "SELECT problem_id, sgf_path FROM problems WHERE source=? AND set_id=? AND sgf_exists=0",
                (source, set_id)
            ).fetchall()
            for row in missing:
                problem_id, sgf_path = row[0], row[1]
                sgf_abs = os.path.join(SCRIPT_DIR, sgf_path.replace('/', os.sep))
                if os.path.isfile(sgf_abs):
                    color = detect_color_to_play(sgf_abs)
                    con.execute(
                        "UPDATE problems SET sgf_exists=1, color_to_play=? WHERE source=? AND problem_id=?",
                        (color, source, problem_id)
                    )
                    prob_updated += 1
            col_skip += 1
            continue

        # ── Colección nueva ──
        on_disk = 0
        if os.path.isdir(folder_path):
            on_disk = sum(1 for f in os.listdir(folder_path) if f.lower().endswith('.sgf'))

        def sort_key(p):
            d = parse_difficulty_num(p.get('difficultyRaw'))
            return (d if d is not None else 0, p['problemId'])

        problems_sorted = sorted(problems, key=sort_key)

        # Agrupar en capítulos
        raw_chunks = []
        for i in range(0, len(problems_sorted), CHAPTER_SIZE):
            raw_chunks.append(problems_sorted[i:i + CHAPTER_SIZE])
        if len(raw_chunks) > 1 and len(raw_chunks[-1]) < CHAPTER_MIN:
            raw_chunks[-2] = raw_chunks[-2] + raw_chunks[-1]
            raw_chunks.pop()

        chapters = []
        for chunk in raw_chunks:
            diffs = [parse_difficulty_num(p.get('difficultyRaw')) for p in chunk]
            diffs = [d for d in diffs if d is not None]
            avg_diff = snap_to_rank(sum(diffs) / len(diffs)) if diffs else None
            chapters.append({
                'chapter_num': len(chapters) + 1,
                'diff_min':    min(diffs) if diffs else None,
                'diff_max':    max(diffs) if diffs else None,
                'diff_avg':    avg_diff,
                'problems':    chunk,
            })

        all_diffs = [parse_difficulty_num(p.get('difficultyRaw')) for p in problems_sorted]
        all_diffs = [d for d in all_diffs if d is not None]
        col_diff_num = snap_to_rank(sum(all_diffs) / len(all_diffs)) if all_diffs else parse_difficulty_num(diff_raw)

        con.execute("""
            INSERT INTO collections
                (source, set_id, name, folder, difficulty_raw, difficulty_num,
                 num_problems, on_disk, chapter_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (source, set_id, name, folder_name,
              diff_raw, col_diff_num, num_probs, on_disk, len(chapters)))
        col_new += 1

        for chap in chapters:
            cur = con.execute("""
                INSERT INTO chapters (source, set_id, chapter_num, diff_min, diff_max, diff_avg, problem_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (source, set_id, chap['chapter_num'],
                  chap['diff_min'], chap['diff_max'], chap['diff_avg'], len(chap['problems'])))
            chapter_id = cur.lastrowid
            chap_new += 1

            for order, p in enumerate(chap['problems'], 1):
                problem_id = p['problemId']
                p_diff_raw = p.get('difficultyRaw')
                p_diff_num = parse_difficulty_num(p_diff_raw)

                sgf_filename = f"{problem_id}.sgf"
                sgf_abs      = os.path.join(folder_path, sgf_filename)
                sgf_rel      = os.path.join(source, 'problems_std',
                                            folder_name, sgf_filename).replace('\\', '/')
                sgf_exists   = 1 if os.path.isfile(sgf_abs) else 0
                color        = detect_color_to_play(sgf_abs) if sgf_exists else None

                con.execute("""
                    INSERT INTO problems
                        (source, problem_id, set_id, chapter_id, order_in_chapter,
                         sgf_path, sgf_exists, difficulty_raw, difficulty_num, color_to_play)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (source, problem_id, set_id, chapter_id, order,
                      sgf_rel, sgf_exists, p_diff_raw, p_diff_num, color))
                prob_new += 1

    con.commit()
    print(f"  Colecciones nuevas   : {col_new}")
    print(f"  Colecciones skip     : {col_skip}")
    print(f"  Capítulos nuevos     : {chap_new}")
    print(f"  Problemas nuevos     : {prob_new}")
    print(f"  Problemas actualizados (SGF): {prob_updated}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
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

    for source_info in sources:
        import_source(con, source_info)

    con.close()
    print("\nListo.")

if __name__ == '__main__':
    main()
