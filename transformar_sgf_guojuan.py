"""
transformar_sgf_guojuan.py — Copia los SGFs válidos de guo_juan/problems_*/
a guo_juan/problems_std/{lessonId}/{problemId}.sgf

Categorías incluidas : RIGHT_ONLY, RIGHT_WRONG
Categorías excluidas : WRONG_ONLY, NO_COMMENTS, DONOTSWAP_NO_RIGHT, UNKNOWN, PASS_ONLY, etc.

Uso:
    python transformar_sgf_guojuan.py [ruta_guo_juan_problems]

Por defecto:
    guo_juan/problems/   (relativo al script)

Salida:
    guo_juan/problems_std/{lessonId}/{problemId}.sgf
    transformar_sgf_guojuan_log.txt
"""

import os
import sys
import shutil
from collections import Counter

# Importar clasificador del script de análisis
from analizar_sgf_guojuan import classify_sgf, scan_guo_juan

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT  = os.path.join(SCRIPT_DIR, 'guo_juan', 'problems')
LOG_FILE      = os.path.join(SCRIPT_DIR, 'transformar_sgf_guojuan_log.txt')

VALID_CATS    = {'RIGHT_ONLY', 'RIGHT_WRONG'}
# ─────────────────────────────────────────────────────────────────────────────

PROBLEMS_ROOT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT
STD_ROOT      = os.path.join(os.path.dirname(PROBLEMS_ROOT), 'problems_std')


def main():
    print(f"Fuente : {PROBLEMS_ROOT}")
    print(f"Destino: {STD_ROOT}")
    print()

    results, _ = scan_guo_juan(PROBLEMS_ROOT)

    counters = Counter()
    log_lines = []

    for r in results:
        cat       = r['category']
        lesson_id = r['lesson_id']
        filename  = r['filename']
        src_path  = r['path']
        problem_id = os.path.splitext(filename)[0]

        if cat in VALID_CATS:
            dest_dir  = os.path.join(STD_ROOT, lesson_id)
            dest_path = os.path.join(dest_dir, f"{problem_id}.sgf")

            if os.path.exists(dest_path):
                counters['skipped'] += 1
                continue

            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src_path, dest_path)
            counters['copied'] += 1
        else:
            counters['excluded'] += 1
            log_lines.append(f"EXCLUIDO [{cat}] {r['folder']}/{filename}")

    # Resumen
    total = len(results)
    print()
    print("=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"  Total SGFs      : {total}")
    print(f"  Copiados        : {counters['copied']}")
    print(f"  Ya existían     : {counters['skipped']}")
    print(f"  Excluidos       : {counters['excluded']}")
    print()

    # Log
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"Total SGFs : {total}\n")
        f.write(f"Copiados   : {counters['copied']}\n")
        f.write(f"Skipped    : {counters['skipped']}\n")
        f.write(f"Excluidos  : {counters['excluded']}\n\n")
        for line in log_lines:
            f.write(line + '\n')

    print(f"Log guardado: {LOG_FILE}")
    print("Listo.")


if __name__ == '__main__':
    main()
