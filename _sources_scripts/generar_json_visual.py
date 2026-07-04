"""
generar_json_visual.py
Genera img/boards/boards.json e img/stones/stones.json
a partir de la estructura de carpetas existente.

Ejecutar desde la carpeta tsumevault/:
    python generar_json_visual.py
"""

import json
import os
from pathlib import Path

BASE = Path(__file__).parent
BOARDS_DIR = BASE / "img" / "boards"
STONES_DIR = BASE / "img" / "stones"

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

def is_image(p: Path) -> bool:
    return p.suffix.lower() in IMG_EXTS

# ── BOARDS ──
def gen_boards():
    entries = []

    # Imágenes sueltas en raíz de img/boards/
    for f in sorted(BOARDS_DIR.iterdir()):
        if f.is_file() and is_image(f):
            entries.append({
                "label": f.stem,
                "file": f.name
            })

    # Subcarpetas: tomar la primera imagen que encuentre (board*.png o cualquiera)
    for folder in sorted(BOARDS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        images = sorted([f for f in folder.iterdir() if f.is_file() and is_image(f)])
        if not images:
            continue
        # Preferir board*.png si existe, si no la primera
        board_imgs = [f for f in images if f.stem.lower().startswith("board")]
        chosen = board_imgs[0] if board_imgs else images[0]
        entries.append({
            "label": folder.name,
            "file": f"{folder.name}/{chosen.name}"
        })

    out = BOARDS_DIR / "boards.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f"boards.json → {len(entries)} entradas")
    for e in entries:
        print(f"  {e['label']:30s} {e['file']}")

# ── STONES ──
def gen_stones():
    entries = []

    for folder in sorted(STONES_DIR.iterdir()):
        if not folder.is_dir():
            continue
        all_images = sorted([f for f in folder.iterdir() if f.is_file() and is_image(f)])
        black = [f"{folder.name}/{f.name}" for f in all_images if f.stem.lower().startswith("black")]
        white = [f"{folder.name}/{f.name}" for f in all_images if f.stem.lower().startswith("white")]
        if not black or not white:
            print(f"  SKIP {folder.name}: faltan black o white")
            continue
        entries.append({
            "label": folder.name,
            "black": black,
            "white": white
        })

    out = STONES_DIR / "stones.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f"stones.json → {len(entries)} entradas")
    for e in entries:
        print(f"  {e['label']:30s} black:{len(e['black'])} white:{len(e['white'])}")

if __name__ == "__main__":
    gen_boards()
    print()
    gen_stones()
