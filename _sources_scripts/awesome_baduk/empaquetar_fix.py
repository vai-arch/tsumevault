#!/usr/bin/env python3
"""Empaqueta para el servidor SOLO los .sgf y .json regenerados de lecciones YA publicadas.

Uso (desde _sources_scripts\\awesome_baduk):
    python empaquetar_fix.py fix_v24 "<ruta del lesson_ids.json REAL>" [--local "<player local>\\lessons"]

- Solo incluye ficheros cuyo lessonId esta en el lesson_ids.json real (los clips no publicados
  que el conversor haya numerado en la copia se ignoran y se listan).
- No incluye .ogg ni _draw.json (no cambian).
- Escribe <carpeta>\\<carpeta>.tar con rutas relativas a lessons\\ ("Awesome Baduk/<curso>/Clip NN/<id>.sgf")
  y <carpeta>\\<carpeta>_lista.txt con la lista (para la copia de seguridad en el servidor).
- Con --local, copia ademas esos mismos ficheros a tu carpeta lessons local (sobrescribe).
"""
import argparse
import json
import shutil
import tarfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('fix_dir')
ap.add_argument('real_ids')
ap.add_argument('--local', default=None, help='carpeta lessons local (la que contiene "Awesome Baduk")')
args = ap.parse_args()

fix = Path(args.fix_dir)
base = fix / 'lessons'
published = {str(v) for v in json.loads(Path(args.real_ids).read_text(encoding='utf-8')).values()}
print(f'lessonId publicados en el fichero real: {len(published)}')

files, ignored = [], set()
for p in sorted((base / 'Awesome Baduk').rglob('*')):
    if not p.is_file() or p.suffix not in ('.sgf', '.json') or p.stem.endswith('_draw'):
        continue
    if p.stem in published:
        files.append(p)
    else:
        ignored.add(p.stem)

if not files:
    raise SystemExit('No hay ficheros que subir: revisa las rutas.')
rels = [p.relative_to(base).as_posix() for p in files]
tar_path = fix / f'{fix.name}.tar'
with tarfile.open(tar_path, 'w') as tf:
    for p, rel in zip(files, rels):
        tf.add(p, arcname=rel)
(fix / f'{fix.name}_lista.txt').write_text('\n'.join(rels) + '\n', encoding='utf-8', newline='\n')
print(f'Ficheros en el paquete: {len(files)} ({len(files) // 2} lecciones) -> {tar_path}')
if ignored:
    print(f'Ignorados (clips no publicados, IDs solo en la copia): {sorted(ignored)}')

if args.local:
    dst_base = Path(args.local)
    n = 0
    for p, rel in zip(files, rels):
        dst = dst_base / rel
        if not dst.parent.is_dir():
            print(f'  !! no existe en local, se omite: {dst.parent}')
            continue
        shutil.copy2(p, dst)
        n += 1
    print(f'Copiados a la carpeta local: {n}')
