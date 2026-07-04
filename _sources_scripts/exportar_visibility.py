"""
exportar_visibility.py — Genera conf/chapters_visibility.json desde tsumeVault.db.

Uso:
    python exportar_visibility.py

Salida: conf/chapters_visibility.json (relativo al directorio del script)
El fichero respeta el valor actual de mostrar en la BD.
Súbelo a GitHub en vai-arch/tsumevault/conf/chapters_visibility.json
"""

import json
import os
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "tsumeVault.db")
OUT_DIR = os.path.join(SCRIPT_DIR, "conf")
OUT_PATH = os.path.join(OUT_DIR, "chapters_visibility.json")


def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with db_connect() as con:
        collections = con.execute(
            "SELECT source, set_id, name FROM collections ORDER BY source, name"
        ).fetchall()

        chapters = con.execute(
            """
            SELECT id, source, set_id, chapter_num, name, diff_min, diff_max, diff_avg, mostrar
            FROM chapters
            ORDER BY source, set_id, chapter_num
            """
        ).fetchall()

    # Indexar chapters por (source, set_id)
    chaps_by_col = {}
    for ch in chapters:
        key = (ch["source"], ch["set_id"])
        chaps_by_col.setdefault(key, []).append(ch)

    result = {}
    for col in collections:
        source = col["source"]
        set_id = col["set_id"]
        col_name = col["name"]

        if source not in result:
            result[source] = {}

        key = (source, set_id)
        chap_list = chaps_by_col.get(key, [])

        result[source][col_name] = {
            "set_id": set_id,
            "chapters": [
                {
                    "id": ch["id"],
                    "name": ch["name"] or f"Ch {ch['chapter_num']}",
                    "mostrar": ch["mostrar"],
                }
                for ch in chap_list
            ],
        }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_cols = sum(len(v) for v in result.values())
    total_chaps = sum(
        len(col["chapters"])
        for source in result.values()
        for col in source.values()
    )
    total_visible = sum(
        ch["mostrar"]
        for source in result.values()
        for col in source.values()
        for ch in col["chapters"]
    )
    print(f"[OK] {OUT_PATH}")
    print(f"     {total_cols} colecciones, {total_chaps} chapters, {total_visible} marcados como visibles")


if __name__ == "__main__":
    main()
