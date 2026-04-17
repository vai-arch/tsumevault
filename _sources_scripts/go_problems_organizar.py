import json
from collections import defaultdict
from pathlib import Path

# ── Configuración ──
ROOT = Path("go_problems/problems")
OUT_DIR = Path("go_problems/problems_clean")
ALL_COL_OUT = Path("go_problems/all_collections_aux.json")

# ── Tabla rank → difficultyNum ──
RANK_TO_NUM = {
    "30k": -900,
    "29k": -800,
    "28k": -700,
    "27k": -600,
    "26k": -500,
    "25k": -400,
    "24k": -300,
    "23k": -200,
    "22k": -100,
    "21k": 0,
    "20k": 100,
    "19k": 200,
    "18k": 300,
    "17k": 400,
    "16k": 500,
    "15k": 600,
    "14k": 700,
    "13k": 800,
    "12k": 900,
    "11k": 1000,
    "10k": 1100,
    "9k": 1200,
    "8k": 1300,
    "7k": 1400,
    "6k": 1500,
    "5k": 1600,
    "4k": 1700,
    "3k": 1800,
    "2k": 1900,
    "1k": 2000,
    "1d": 2100,
    "2d": 2200,
    "3d": 2300,
    "4d": 2400,
    "5d": 2500,
    "6d": 2600,
    "7d": 2700,
    "8d": 2800,
    "9d": 2900,
}

RANK_ORDER = list(RANK_TO_NUM.keys())  # 30k → 9d


def rank_label(p):
    r = p.get("rank") or {}
    val = r.get("value")
    unit = r.get("unit")
    if val is None:
        return None
    suffix = "k" if unit == "kyu" else "d" if unit == "dan" else None
    if suffix is None:
        return None
    return f"{val}{suffix}"


def is_valid(p):
    if not p.get("alive", True):
        return False
    if p.get("sandbox"):
        return False
    if p.get("hasNegativeFlags"):
        return False
    elo = p.get("elo")
    if elo is not None and elo == 0:
        return False
    is_canon = p.get("isCanon", False)
    is_standard = p.get("isStandard", False)
    votes = (p.get("rating") or {}).get("votes", 0) or 0
    if is_canon:
        return True
    if is_standard and votes > 0:
        return True
    return False


# ── Paso 1: recorrer y filtrar ──
print("Recorriendo problemas...")
seen_ids = set()
by_rank = defaultdict(list)  # rank_label → [problem]
skipped = 0
kept = 0
no_rank = 0

for set_dir in sorted(ROOT.iterdir()):
    if not set_dir.is_dir():
        continue
    for prob_file in sorted(set_dir.iterdir()):
        if prob_file.suffix != ".json":
            continue
        try:
            with open(prob_file, encoding="utf-8") as f:
                p = json.load(f)
        except Exception as e:
            print(f"  ERROR leyendo {prob_file}: {e}")
            continue

        pid = p.get("id")
        if pid in seen_ids:
            continue
        seen_ids.add(pid)

        if not is_valid(p):
            skipped += 1
            continue

        rl = rank_label(p)
        if rl is None or rl not in RANK_TO_NUM:
            no_rank += 1
            continue

        by_rank[rl].append(p)
        kept += 1

print(f"  Mantenidos: {kept}")
print(f"  Descartados (filtro): {skipped}")
print(f"  Sin rank válido: {no_rank}")

# ── Paso 2: crear carpetas y SGFs ──
print("\nEscribiendo SGFs...")
OUT_DIR.mkdir(parents=True, exist_ok=True)

for rank in RANK_ORDER:
    problems = by_rank.get(rank, [])
    if not problems:
        continue
    rank_dir = OUT_DIR / rank
    rank_dir.mkdir(exist_ok=True)
    # ordenar por elo ascendente
    problems.sort(key=lambda p: p.get("elo") or 0)
    for p in problems:
        sgf_text = (p.get("sgf") or "").replace("\r\n", "\n").replace("\r", "\n")
        out_file = rank_dir / f"{p['id']}.sgf"
        out_file.write_text(sgf_text, encoding="utf-8")

print("  SGFs escritos.")

# ── Paso 3: generar all_collections.json ──
print("\nGenerando all_collections.json...")
collections = []
set_id = 1

for rank in RANK_ORDER:
    problems = by_rank.get(rank, [])
    if not problems:
        continue
    problems.sort(key=lambda p: p.get("elo") or 0)

    diff_num = RANK_TO_NUM[rank]
    diff_raw = f"{rank} ({diff_num})"

    # media de elo de los problemas (para difficultyNum de la colección)
    elos = [p["elo"] for p in problems if p.get("elo")]
    col_diff_num = round(sum(elos) / len(elos)) if elos else diff_num

    prob_list = []
    for p in problems:
        r = p.get("rank") or {}
        p_rank = f"{r.get('value')}{r.get('unit')}" if r.get("value") else rank
        p_diff_num = RANK_TO_NUM.get(p_rank, diff_num)
        tags = [c["name"] for c in (p.get("collections") or [])]
        prob_list.append(
            {
                "problemId": p["id"],
                "difficulty": p_rank,
                "difficultyNum": p_diff_num,
                "difficultyRaw": f"{p_rank} ({p_diff_num})",
                "tags": tags,
            }
        )

    collections.append(
        {
            "setId": set_id,
            "name": rank,
            "difficulty": rank,
            "difficultyNum": col_diff_num,
            "numProblems": len(prob_list),
            "problems": prob_list,
        }
    )
    set_id += 1

ALL_COL_OUT.write_text(
    json.dumps(collections, ensure_ascii=False, indent=2), encoding="utf-8"
)

print(f"  {len(collections)} colecciones escritas en {ALL_COL_OUT}")
print("\nListo.")
