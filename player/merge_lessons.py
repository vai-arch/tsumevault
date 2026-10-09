#!/usr/bin/env python3
"""
Une varios all_lessons.json (uno por fuente) en el all_lessons.json que lee el player.

Cada fuente se mantiene por separado; este script solo los junta:
    otra_web.json       (lecciones de la otra web)
    awesome_baduk.json  (all_lessons.new.json que genera awesome_to_player.py)

Uso (PowerShell):
    python merge_lessons.py lessons_sources\\otra_web.json lessons_sources\\awesome_baduk.json --out all_lessons.json
    python merge_lessons.py lessons_sources\\otra_web.json lessons_sources\\awesome_baduk.json --out all_lessons.json --dry-run
    python merge_lessons.py ... --out all_lessons.json --check-files D:\\servidor\\lessons

Que hace:
  - Valida cada fila (campos que usa el player, lessonLength numerico) y PARA si hay errores.
  - Detecta lessonId repetidos (dentro de una fuente o entre fuentes) y PARA.
  - Hace copia del --out anterior (con fecha) antes de sobrescribirlo.
  - --dry-run: cuenta lo que haria sin escribir nada.
  - --check-files DIR: comprueba que existen {id}.sgf, {id}.json y {id}.ogg de cada leccion en la
    ruta que calcula el player (tipo/coleccion/nombre[/sufijo]/).
"""
import argparse
import collections
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def player_sanitize(name):
    """Igual que sanitize() de player.html."""
    if not name:
        return ''
    return re.sub(r'\.+$', '', re.sub(r'[\\/:*?"<>\'|]', '_', name).strip())


def lesson_dir(row):
    p = Path(player_sanitize((row.get('typeName') or '').strip())) / \
        player_sanitize((row.get('collectionName') or '').strip()) / \
        player_sanitize((row.get('lessonName') or '').strip())
    suf = player_sanitize((row.get('lessonSuffix') or '').strip())
    return p / suf if suf else p


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_source(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    rows = data.get('rows') if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise SystemExit(f'{path}: no tiene el formato {{"rows": [...]}} ni es una lista.')
    nulls = sum(1 for r in rows if r is None)
    return [r for r in rows if r is not None], nulls


def validate(row):
    """Devuelve (errores, avisos) de una fila."""
    errs, warns = [], []
    lid = row.get('lessonId')
    if not isinstance(lid, int) or isinstance(lid, bool):
        errs.append(f'lessonId debe ser un entero (es {lid!r})')
    for k in ('lessonName', 'typeName', 'collectionName'):
        v = row.get(k)
        if not isinstance(v, str) or not v.strip():
            errs.append(f'{k} vacio o no es texto ({v!r})')
    ln = row.get('lessonLength')
    if ln is None or ln == '':
        warns.append('sin lessonLength')
    elif not is_num(ln):
        errs.append(f'lessonLength debe ser un numero de minutos (es {ln!r}); el player lo suma y saldria NaN')
    d = row.get('lessonDifficulty')
    if d not in (None, '') and not is_num(d) and not (isinstance(d, str) and d.isdigit()):
        warns.append(f'lessonDifficulty raro ({d!r})')
    if d in (None, ''):
        warns.append('sin lessonDifficulty')
    return errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sources', nargs='+', help='all_lessons.json de cada fuente, en el orden de salida')
    ap.add_argument('--out', required=True, help='all_lessons.json final')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-backup', action='store_true')
    ap.add_argument('--check-files', default=None, metavar='DIR',
                    help='carpeta lessons: comprobar que existen .sgf, .json y .ogg de cada leccion')
    ap.add_argument('--check-source', action='append', default=[],
                    help='con --check-files, limitar a fuentes cuyo nombre de fichero contenga este texto')
    args = ap.parse_args()

    merged, by_id, problems = [], {}, []
    stats = collections.OrderedDict()
    for path in args.sources:
        name = Path(path).name
        rows, nulls = load_source(path)
        warn_count = collections.Counter()
        for i, row in enumerate(rows):
            errs, warns = validate(row)
            for e in errs:
                problems.append(f'{name} fila {i + 1} (id {row.get("lessonId")}): {e}')
            for w in warns:
                warn_count[w] += 1
            lid = row.get('lessonId')
            if isinstance(lid, int):
                if lid in by_id:
                    prev = by_id[lid]
                    problems.append(f'lessonId {lid} repetido: {prev[0]} "{prev[1]}"  y  {name} "{row.get("lessonName")}"')
                else:
                    by_id[lid] = (name, row.get('lessonName'))
            row['__src'] = name
            merged.append(row)
        ids = [r['lessonId'] for r in rows if isinstance(r.get('lessonId'), int)]
        stats[name] = {'filas': len(rows), 'nulos descartados': nulls,
                       'ids': f'{min(ids)}..{max(ids)}' if ids else '-', 'avisos': dict(warn_count)}

    print('==== FUENTES ====')
    for name, st in stats.items():
        print(f'{name}: {st["filas"]} lecciones, ids {st["ids"]}, nulos descartados {st["nulos descartados"]}')
        if st['avisos']:
            print(f'    avisos: {st["avisos"]}')
    print(f'TOTAL: {len(merged)} lecciones')

    missing = collections.Counter()
    if args.check_files:
        base = Path(args.check_files)
        examples = []
        for row in merged:
            if args.check_source and not any(t.lower() in row['__src'].lower() for t in args.check_source):
                continue
            d = base / lesson_dir(row)
            for ext in ('sgf', 'json', 'ogg'):
                if not (d / f'{row["lessonId"]}.{ext}').exists():
                    missing[(row['__src'], ext)] += 1
                    if len(examples) < 5:
                        examples.append(str(d / f'{row["lessonId"]}.{ext}'))
        print('\n==== FICHEROS ====')
        if missing:
            for (src, ext), n in sorted(missing.items()):
                print(f'  faltan {n} .{ext} de {src}')
            print('  ejemplos:', *examples, sep='\n    ')
        else:
            print('  todas las lecciones tienen .sgf, .json y .ogg')

    if problems:
        print(f'\n==== ERRORES ({len(problems)}) - no se escribe nada ====')
        for p in problems[:25]:
            print('  -', p)
        if len(problems) > 25:
            print(f'  ... y {len(problems) - 25} mas')
        sys.exit(1)

    out = Path(args.out)
    for row in merged:
        row.pop('__src', None)
    text = json.dumps({'rows': merged}, indent=2, ensure_ascii=False) + '\n'
    if args.dry_run:
        print(f'\n[dry-run] se escribirian {len(merged)} lecciones ({len(text) // 1024} KiB) en {out}')
        return
    if out.exists() and not args.no_backup:
        bak = out.with_name(f'{out.name}.bak-{datetime.now():%Y%m%d-%H%M%S}')
        shutil.copy2(out, bak)
        print(f'\ncopia de seguridad: {bak}')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding='utf-8')
    print(f'escrito {out} ({len(merged)} lecciones)')


if __name__ == '__main__':
    main()
