#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recorded_quitar_draw.py - Quita de recorded.json las lecciones que tienen dibujo a mano.

Para que el reproductor vuelva a ofrecerlas como "pendientes de grabar" y el video
nuevo incluya los dibujos del profesor.

Uso (desde _sources_scripts\\awesome_baduk):
    python recorded_quitar_draw.py RUTA\\recorded.json                 (usa draw_out\\lessons)
    python recorded_quitar_draw.py RUTA\\recorded.json --draw-dir OTRA\\CARPETA
    python recorded_quitar_draw.py RUTA\\recorded.json --dry-run       (solo informa)

Un lessonId "tiene dibujo" si existe un fichero <lessonId>_draw.json bajo --draw-dir
(se busca en todas las subcarpetas). Por defecto: draw_out\\lessons, que es lo que genera
awesome_to_player.py --draw-only.

Antes de escribir guarda una copia recorded.json.bak (salvo --no-backup).
No toca los videos ya descargados: solo la lista.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('recorded', help='ruta de recorded.json')
    ap.add_argument('--draw-dir', default='draw_out/lessons',
                    help='carpeta con los <id>_draw.json (por defecto draw_out/lessons)')
    ap.add_argument('--out', default=None, help='fichero de salida (por defecto sobrescribe recorded.json)')
    ap.add_argument('--dry-run', action='store_true', help='solo informa, no escribe')
    ap.add_argument('--no-backup', action='store_true', help='no crear recorded.json.bak')
    args = ap.parse_args()

    rec_path = Path(args.recorded)
    if not rec_path.is_file():
        sys.exit(f'No existe {rec_path}')
    draw_dir = Path(args.draw_dir)
    if not draw_dir.is_dir():
        sys.exit(f'No existe la carpeta de dibujos: {draw_dir}\n'
                 f'Indica la correcta con --draw-dir (la que contiene los *_draw.json).')

    # ids con dibujo, a partir del nombre de fichero <id>_draw.json
    with_draw = set()
    for p in draw_dir.rglob('*_draw.json'):
        m = re.fullmatch(r'(\d+)_draw\.json', p.name)
        if m:
            with_draw.add(int(m.group(1)))
    if not with_draw:
        sys.exit(f'No he encontrado ningun *_draw.json bajo {draw_dir}; no cambio nada.')

    data = json.loads(rec_path.read_text(encoding='utf-8-sig'))
    if isinstance(data, dict) and isinstance(data.get('recorded'), list):
        ids = data['recorded']
        wrap = True
    elif isinstance(data, list):
        ids, wrap = data, False
    else:
        sys.exit('Formato de recorded.json no reconocido (esperaba {"recorded": [...]} o una lista).')

    removed = [i for i in ids if i in with_draw]
    kept = [i for i in ids if i not in with_draw]

    print(f'Lecciones con dibujo (en {draw_dir}): {len(with_draw)}')
    print(f'recorded.json: {len(ids)} ids  ->  se quitan {len(removed)}, quedan {len(kept)}')
    if removed:
        print('Se quitan (hay que volver a grabarlas):')
        print('  ' + ', '.join(str(i) for i in removed))
    else:
        print('Ninguna de las lecciones grabadas tiene dibujo: no hay nada que quitar.')

    if args.dry_run:
        print('\n--dry-run: no se escribe nada.')
        return
    if not removed:
        return

    if wrap:
        data['recorded'] = kept
    else:
        data = kept
    out = Path(args.out) if args.out else rec_path
    if out == rec_path and not args.no_backup:
        bak = rec_path.with_name(rec_path.name + '.bak')
        shutil.copy2(rec_path, bak)
        print(f'\nCopia de seguridad: {bak}')
    out.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(f'Escrito {out}')


if __name__ == '__main__':
    main()
