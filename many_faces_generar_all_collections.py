import json
import re
from pathlib import Path

BASE_DIR = Path("many_faces", "problems_std")
OUTPUT_FILE = Path("many_faces", "all_collections.json")

# ─────────────────────────────
# difficulty utils
# ─────────────────────────────


def parse_k(name: str):
    m = re.search(r"(\d+)k", name)
    return int(m.group(1)) if m else None


def difficulty_num(k):
    return (30 - k) * 100 - 900


def num_to_raw(n):
    if n is None:
        return None
    k = round(30 - (n + 900) / 100)
    return f"{k}k"


# ─────────────────────────────
# SET ASSIGNMENT
# ─────────────────────────────


def get_set_name(chapter_name: str):
    if chapter_name.startswith("lvl_"):
        k = parse_k(chapter_name)
        if k is None:
            return None

        if k >= 17:
            return "Graded Go Problems I"
        if 13 <= k <= 16:
            return "Graded Go Problems II"
        if 10 <= k <= 12:
            return "Graded Go Problems III"

    if chapter_name.startswith("level_"):
        return "Other Problems"

    return None


SET_META = {
    "Graded Go Problems I": {"setId": 167},
    "Graded Go Problems II": {"setId": 168},
    "Graded Go Problems III": {"setId": 169},
    "Other Problems": {"setId": 170},
}

# ─────────────────────────────
# BUILD
# ─────────────────────────────


def build():
    sets = {}

    for chapter_dir in BASE_DIR.iterdir():
        if not chapter_dir.is_dir():
            continue

        chapter_name = chapter_dir.name
        set_name = get_set_name(chapter_name)

        if not set_name:
            print("[WARN] chapter without set:", chapter_name)
            continue

        k = parse_k(chapter_name)
        if k is None:
            continue

        diff_raw = f"{k}k"
        diff_num = difficulty_num(k)

        chapter_id = abs(hash(chapter_name)) % 10_000_000

        problems = []

        for sgf in sorted(chapter_dir.glob("*.sgf")):
            problems.append(
                {
                    "problemId": sgf.stem,
                    "lessonId": chapter_id,
                    "difficulty_raw": diff_raw,
                    "difficulty_num": diff_num,
                }
            )

        if set_name not in sets:
            sets[set_name] = {
                "setId": SET_META[set_name]["setId"],
                "name": set_name,
                "difficulty_raw": None,
                "difficulty_num": None,
                "numProblems": 0,
                "chapters": [],
                "_diffs": [],
            }

        sets[set_name]["chapters"].append(
            {
                "chapterId": chapter_id,
                "name": chapter_name,
                "folder": chapter_name,
                "difficulty_raw": diff_raw,
                "difficulty_num": diff_num,
                "numProblems": len(problems),
                "problems": problems,
            }
        )

        sets[set_name]["numProblems"] += len(problems)
        sets[set_name]["_diffs"].append(diff_num)

    # ─────────────────────────────
    # finalize set difficulty
    # ─────────────────────────────

    result = []

    for set_obj in sets.values():
        diffs = set_obj.pop("_diffs", [])

        if diffs:
            avg = sum(diffs) / len(diffs)
            avg = round(avg)
            set_obj["difficulty_num"] = avg
            set_obj["difficulty_raw"] = num_to_raw(avg)

        result.append(set_obj)

    # ─────────────────────────────
    # write output
    # ─────────────────────────────

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("OK ->", OUTPUT_FILE)


if __name__ == "__main__":
    build()
