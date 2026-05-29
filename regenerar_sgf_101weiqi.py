"""
regenerar_sgf_101weiqi.py — Regenera los SGFs de 101weiqi desde los .json locales.

Uso:
    python regenerar_sgf_101weiqi.py

Ejecutar desde la raíz del proyecto.
Lee output/{book_id}/{chapter_id}/{qid}.json y sobreescribe:
  - output/{book_id}/{chapter_id}/{qid}.sgf
  - 101_weiqi/problems_std/{book_id}/{chapter_id}/{qid}.sgf
"""

import json
import os
import re
import shutil
import sys

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR   = os.path.join(SCRIPT_DIR, "output")
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "101_weiqi", "problems_std")

# ── Traducción (mínima, sin Google Translator) ────────────────────────────────

GO_TERMS = {
    "围棋": "Go", "棋": "Go", "基础": "Fundamentals", "入门": "Beginner",
    "初级": "Elementary", "中级": "Intermediate", "高级": "Advanced",
    "训练": "Training", "习题": "Problems", "题集": "Problem Collection",
    "实战": "Practical Play", "死活": "Life and Death", "手筋": "Tesuji",
    "官子": "Endgame", "布局": "Fuseki", "定式": "Joseki", "中盘": "Middlegame",
    "对杀": "Capturing race", "死活题": "Life and Death", "手筋题": "Tesuji",
    "对杀题": "Capturing race", "吃子": "Capture",
}


def translate(text: str) -> str:
    if not text or not text.strip():
        return text
    working = text.strip()
    for zh, en in sorted(GO_TERMS.items(), key=lambda x: -len(x[0])):
        working = working.replace(zh, en)
    return working


# ── SGF desde andata ──────────────────────────────────────────────────────────

def andata_to_sgf(qqdata: dict, black_stones: list, white_stones: list) -> str:
    andata = qqdata.get("andata", {})
    if not andata:
        return None

    lu         = qqdata.get("lu", 19)
    blackfirst = qqdata.get("blackfirst", True)
    title      = qqdata.get("name") or qqdata.get("title") or ""
    levelname  = qqdata.get("levelname", "")
    qtypename  = qqdata.get("qtypename_en") or qqdata.get("qtypename", "")
    vote       = qqdata.get("vote", 0)
    yes_count  = qqdata.get("yes_count", 0)
    no_count   = qqdata.get("no_count", 0)
    desc       = qqdata.get("desc") or ""

    def node_color(depth: int) -> str:
        if blackfirst:
            return "B" if depth % 2 == 1 else "W"
        else:
            return "W" if depth % 2 == 1 else "B"

    def build_node(node_id: int, depth: int) -> str:
        node = andata.get(str(node_id))
        if node is None:
            return ""
        pt   = node.get("pt", "")
        subs = node.get("subs", [])
        o    = node.get("o", 0)
        c    = node.get("c", 0)
        f    = node.get("f", 0)
        tip  = node.get("tip_en") or node.get("tip", "")
        parts = []
        if depth > 0 and pt:
            color = node_color(depth)
            parts.append(f"{color}[{pt}]")
        if not subs:
            comments = []
            if o == 1 or c == 1:
                if "RIGHT" not in tip.upper():
                    comments.append("RIGHT")
            elif f == 1:
                if "WRONG" not in tip.upper():
                    comments.append("WRONG")
            if tip:
                comments.append(tip)
            if comments:
                parts.append(f"C[{' — '.join(comments)}]")
        node_str = ";" + "".join(parts)
        if not subs:
            return node_str
        if len(subs) == 1:
            return node_str + build_node(subs[0], depth + 1)
        branches = "".join(f"({build_node(s, depth + 1)})" for s in subs)
        return node_str + branches

    ab = "".join(f"AB[{s}]" for s in black_stones)
    aw = "".join(f"AW[{s}]" for s in white_stones)
    header = f";FF[4]CA[UTF-8]GM[1]SZ[{lu}]"
    if title:
        title_en = qqdata.get("title_en") or translate(title)
        header += f"GN[{title_en.replace(']', chr(92) + ']')}]"
    gc_parts = []
    if qtypename:
        gc_parts.append(f"Type: {qtypename}")
    if levelname:
        gc_parts.append(f"Level: {levelname}")
    if vote:
        total = yes_count + no_count
        pct = round(yes_count / total * 100) if total > 0 else 0
        gc_parts.append(f"Rating: {vote}/5")
        gc_parts.append(f"Correct: {pct}% ({yes_count}/{total})")
    if desc:
        gc_parts.append(f"Desc: {qqdata.get('desc_en') or translate(desc)}")
    gc_parts.append(f"First move: {'Black' if blackfirst else 'White'}")
    if gc_parts:
        gc_str = " | ".join(gc_parts).replace("]", "\\]")
        header += f"GC[{gc_str}]"
    if ab:
        header += ab
    if aw:
        header += aw

    tree = build_node(0, 0)
    # FIX: eliminar el ";" inicial del nodo raíz que rompe el parser WGo
    if tree.startswith(";"):
        tree = tree[1:]
    return f"({header}{tree})"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.isdir(INPUT_DIR):
        print(f"[ERROR] No se encontró: {INPUT_DIR}")
        sys.exit(1)

    ok = skipped = errors = 0

    for book_id in sorted(os.listdir(INPUT_DIR)):
        book_path = os.path.join(INPUT_DIR, book_id)
        if not os.path.isdir(book_path):
            continue

        for chapter_id in sorted(os.listdir(book_path)):
            chap_path = os.path.join(book_path, chapter_id)
            if not os.path.isdir(chap_path):
                continue

            for fname in sorted(os.listdir(chap_path)):
                if not fname.endswith(".json") or fname == "chapter.json":
                    continue

                qid = fname[:-5]
                json_path = os.path.join(chap_path, fname)

                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        qqdata = json.load(f)
                except Exception as e:
                    print(f"  [ERROR] leyendo {json_path}: {e}")
                    errors += 1
                    continue

                if not qqdata.get("andata"):
                    skipped += 1
                    continue

                black_stones = qqdata.get("black_stones", [])
                white_stones = qqdata.get("white_stones", [])

                try:
                    sgf = andata_to_sgf(qqdata, black_stones, white_stones)
                except Exception as e:
                    print(f"  [ERROR] generando SGF {qid}: {e}")
                    errors += 1
                    continue

                if not sgf:
                    skipped += 1
                    continue

                # Sobreescribir en output/
                sgf_src = os.path.join(chap_path, f"{qid}.sgf")
                with open(sgf_src, "w", encoding="utf-8") as f:
                    f.write(sgf)

                # Copiar a 101_weiqi/problems_std/
                sgf_dst = os.path.join(OUTPUT_DIR, book_id, chapter_id, f"{qid}.sgf")
                os.makedirs(os.path.dirname(sgf_dst), exist_ok=True)
                shutil.copy2(sgf_src, sgf_dst)

                ok += 1

    print(f"\nResumen:")
    print(f"  SGFs regenerados : {ok}")
    print(f"  Sin andata (skip): {skipped}")
    print(f"  Errores          : {errors}")


if __name__ == "__main__":
    main()
