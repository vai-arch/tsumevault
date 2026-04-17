"""
go_problems_std.py
Lee go_problems/all_collections_aux.json + SGFs de problems_clean/
Genera go_problems/problems_std/{set_id}/{problem_id}.sgf con comentarios estandarizados
y go_problems/all_collections.json limpio (sin problemas conflictivos).

Ejecutar desde el directorio raíz del proyecto (donde está go_problems/).
"""

import json
import os
import re
from pathlib import Path

# ── Config ──
BASE        = Path('go_problems')
AUX_JSON    = BASE / 'all_collections_aux.json'
OUT_JSON    = BASE / 'all_collections.json'
CLEAN_DIR   = BASE / 'problems_clean'
STD_DIR     = BASE / 'problems_std'

# Problemas a excluir (NO_MARKERS + CONFLICT)
EXCLUDE_IDS = {15283, 4833, 10128, 18416, 49872}

# ── SGF comment normalizer ──
COMMENT_RE = re.compile(r'C\[', re.IGNORECASE)

def normalize_comment(comment_text):
    """Convierte el contenido de un comentario al formato estándar."""
    upper = comment_text.upper()
    has_right   = 'RIGHT'   in upper
    has_correct = 'CORRECT' in upper
    has_wrong   = 'WRONG'   in upper

    if has_right or has_correct:
        return 'RIGHT'
    if has_wrong:
        return 'WRONG'
    # Comentario sin marker de resultado — lo dejamos tal cual
    return comment_text

def transform_sgf(text):
    """
    Recorre el SGF carácter a carácter y normaliza los valores de C[...].
    Respeta escapes \] dentro de los valores.
    """
    out = []
    i = 0
    n = len(text)

    while i < n:
        # Buscar "C["
        if text[i] == 'C' and i + 1 < n and text[i+1] == '[':
            out.append('C[')
            i += 2
            # Leer hasta el ] de cierre respetando escapes
            val = []
            while i < n:
                c = text[i]
                if c == '\\' and i + 1 < n:
                    val.append(c)
                    val.append(text[i+1])
                    i += 2
                elif c == ']':
                    i += 1
                    break
                else:
                    val.append(c)
                    i += 1
            original = ''.join(val)
            normalized = normalize_comment(original)
            out.append(normalized)
            out.append(']')
        else:
            out.append(text[i])
            i += 1

    return ''.join(out)

# ── Main ──
def main():
    with open(AUX_JSON, encoding='utf-8') as f:
        collections = json.load(f)

    STD_DIR.mkdir(parents=True, exist_ok=True)

    out_collections = []
    total_written = 0
    total_excluded = 0
    total_missing = 0

    for col in collections:
        set_id   = col['setId']
        rank     = col['name']  # "30k", "29k", etc.
        problems = col['problems']

        # Filtrar excluidos
        clean_problems = [p for p in problems if p['problemId'] not in EXCLUDE_IDS]
        excluded = len(problems) - len(clean_problems)
        total_excluded += excluded

        out_dir = STD_DIR / str(set_id)
        out_dir.mkdir(exist_ok=True)

        written = []
        for p in clean_problems:
            pid      = p['problemId']
            sgf_in   = CLEAN_DIR / rank / f"{pid}.sgf"

            if not sgf_in.exists():
                total_missing += 1
                continue

            text = sgf_in.read_text(encoding='utf-8', errors='replace')
            transformed = transform_sgf(text)

            sgf_out = out_dir / f"{pid}.sgf"
            sgf_out.write_text(transformed, encoding='utf-8')
            written.append(p)
            total_written += 1

        if written:
            out_col = dict(col)
            out_col['problems']    = written
            out_col['numProblems'] = len(written)
            out_collections.append(out_col)

    # Escribir all_collections.json limpio
    OUT_JSON.write_text(
        json.dumps(out_collections, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    print(f"Colecciones escritas : {len(out_collections)}")
    print(f"SGFs escritos        : {total_written}")
    print(f"Excluidos            : {total_excluded}")
    print(f"No encontrados       : {total_missing}")
    print(f"→ {OUT_JSON}")

if __name__ == '__main__':
    main()
