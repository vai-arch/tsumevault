"""
generar_collections_guojuan.py — Genera guo_juan/all_collections.json
a partir de guo_juan/all_lessons.json y los SGFs en guo_juan/problems_std/

Estructura output:
  set     = collectionId / collectionName
  chapter = lessonId / lessonName  (solo si tiene SGFs en disco)
  problem = problemId (nombre de fichero sin .sgf)

Dificultad:
  lessonDifficulty 1-11 → 15k-5k
  difficulty_num = 600 + (lessonDifficulty - 1) * 100
  difficulty_raw = f"{16 - lessonDifficulty}k"

Uso:
    python generar_collections_guojuan.py [ruta_guo_juan]

Por defecto:
    guo_juan/   (relativo al script)

Output:
    guo_juan/all_collections.json
"""

import os
import sys
import json
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT  = os.path.join(SCRIPT_DIR, 'guo_juan')
# ─────────────────────────────────────────────────────────────────────────────

GUO_JUAN_ROOT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT
LESSONS_FILE  = os.path.join(GUO_JUAN_ROOT, 'all_lessons.json')
STD_ROOT      = os.path.join(GUO_JUAN_ROOT, 'problems_std')
OUTPUT_FILE   = os.path.join(GUO_JUAN_ROOT, 'all_collections.json')


def diff_num(lesson_difficulty):
    """lessonDifficulty 1-11 → difficulty_num (consistente con diffLabel JS)"""
    if lesson_difficulty is None:
        return None
    return 600 + (int(lesson_difficulty) - 1) * 100


def diff_raw(lesson_difficulty):
    """lessonDifficulty 1-11 → '15k'..'5k'"""
    if lesson_difficulty is None:
        return None
    return f"{16 - int(lesson_difficulty)}k"


def avg(nums):
    nums = [n for n in nums if n is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums))


def main():
    # Leer all_lessons.json
    if not os.path.isfile(LESSONS_FILE):
        print(f"ERROR: No se encuentra {LESSONS_FILE}")
        sys.exit(1)

    with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Soporta tanto array directo como {rows: [...]}
    if isinstance(data, list):
        lessons = data
    elif isinstance(data, dict) and 'rows' in data:
        lessons = data['rows']
    else:
        print("ERROR: Formato de all_lessons.json no reconocido")
        sys.exit(1)

    print(f"Lecciones en JSON : {len(lessons)}")

    # Escanear problems_std para saber qué lecciones tienen SGFs
    if not os.path.isdir(STD_ROOT):
        print(f"ERROR: No se encuentra {STD_ROOT}")
        sys.exit(1)

    lesson_problems = {}  # lessonId -> [problemId, ...]
    for folder in os.listdir(STD_ROOT):
        folder_path = os.path.join(STD_ROOT, folder)
        if not os.path.isdir(folder_path):
            continue
        try:
            lesson_id = int(folder)
        except ValueError:
            continue
        sgfs = sorted([
            os.path.splitext(f)[0]
            for f in os.listdir(folder_path)
            if f.lower().endswith('.sgf')
        ])
        if sgfs:
            lesson_problems[lesson_id] = sgfs

    print(f"Lecciones con SGFs: {len(lesson_problems)}")

    # Agrupar lecciones por collectionId
    collections = defaultdict(list)  # collectionId -> [lesson, ...]
    collection_meta = {}             # collectionId -> {name, order}

    for lesson in lessons:
        lesson_id = lesson.get('lessonId')
        if lesson_id not in lesson_problems:
            continue  # sin SGFs, saltar

        cid = lesson.get('collectionId')
        if cid is None:
            continue

        collections[cid].append(lesson)
        if cid not in collection_meta:
            collection_meta[cid] = {
                'name'  : lesson.get('collectionName', f'Collection {cid}'),
                'order' : lesson.get('collectionOrder', 9999),
                'type_order': lesson.get('typeOrder', 9999),
            }

    print(f"Sets (colecciones) : {len(collections)}")

    # Construir JSON
    result = []

    for cid in sorted(collections.keys(),
                      key=lambda c: (collection_meta[c]['type_order'],
                                     collection_meta[c]['order'])):
        lessons_in_col = sorted(collections[cid], key=lambda l: l.get('lessonId', 0))

        # Agrupar por lessonName → capítulo
        chapter_groups = defaultdict(list)  # lessonName -> [lesson, ...]
        chapter_order  = []                 # para preservar orden de aparición
        for lesson in lessons_in_col:
            name = lesson.get('lessonName', f'Lesson {lesson["lessonId"]}')
            if name not in chapter_order:
                chapter_order.append(name)
            chapter_groups[name].append(lesson)

        chapters = []
        all_diff_nums = []

        for chapter_name in chapter_order:
            group = chapter_groups[chapter_name]
            # Usar la dificultad de la primera lección del grupo (todas deberían ser iguales)
            ldifficulty = group[0].get('lessonDifficulty')
            dn = diff_num(ldifficulty)
            dr = diff_raw(ldifficulty)

            problems = []
            for lesson in group:
                lesson_id = lesson['lessonId']
                for pid in lesson_problems[lesson_id]:
                    problems.append({
                        'problemId'      : pid,
                        'lessonId'       : lesson_id,
                        'difficulty_raw' : dr,
                        'difficulty_num' : dn,
                    })

            all_diff_nums.extend([dn] * len(problems))

            # chapterId: lessonId del grupo si es único, sino el primero
            chapter_id = group[0]['lessonId']

            chapters.append({
                'chapterId'      : chapter_id,
                'name'           : chapter_name,
                'difficulty_raw' : dr,
                'difficulty_num' : dn,
                'numProblems'    : len(problems),
                'problems'       : problems,
            })

        set_diff_num = avg(all_diff_nums)
        set_diff_raw = diffLabel_py(set_diff_num) if set_diff_num is not None else None

        result.append({
            'setId'          : cid,
            'name'           : collection_meta[cid]['name'],
            'difficulty_raw' : set_diff_raw,
            'difficulty_num' : set_diff_num,
            'numProblems'    : sum(ch['numProblems'] for ch in chapters),
            'chapters'       : chapters,
        })

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_problems = sum(s['numProblems'] for s in result)
    print(f"Sets generados     : {len(result)}")
    print(f"Chapters generados : {sum(len(s['chapters']) for s in result)}")
    print(f"Problemas totales  : {total_problems}")
    print(f"Output             : {OUTPUT_FILE}")
    print("Listo.")


def diffLabel_py(num):
    """Equivalente Python de diffLabel() JS"""
    if num is None:
        return None
    if num <= 2000:
        k = round((2000 - num) / 100) + 1
        return f"{k}k"
    else:
        d = round((num - 2000) / 100)
        return f"{d}d"


if __name__ == '__main__':
    main()
