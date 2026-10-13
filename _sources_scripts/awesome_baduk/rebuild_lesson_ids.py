#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_lesson_ids.py - Reconstruye lesson_ids.json cuando se ha perdido.

lesson_ids.json guarda, para cada clip, el lessonId que le dio awesome_to_player.py:
    "<id_curso>/<video-id del clip>": 900123

El manifest ya publicado (awesome_baduk_lessons.json) tiene por cada leccion:
lessonId, sourceCourseId y sourceVimeoId. Con lessons.json se recupera de que clip
(video-id) es cada una, y de ahi se rehace el fichero.

Uso (desde _sources_scripts\\awesome_baduk):
    python rebuild_lesson_ids.py lessons.json RUTA\\awesome_baduk_lessons.json ^
        --lessons-dir RUTA\\player\\lessons\\"Awesome Baduk" ^
        --out player_test\\player\\lesson_ids.json

  --lessons-dir (recomendado): carpeta con las lecciones publicadas. Sirve para
      1) comprobar que cada lessonId del manifest tiene su <id>.json en disco, y
      2) reservar los IDs de lecciones que se quitaron del catalogo pero cuyos
         ficheros siguen ahi: se anota la clave "_floor" para que el conversor
         no vuelva a repartir esos numeros.
  --dry-run: solo informa, no escribe.
  --force: sobrescribe un lesson_ids.json que ya tenga contenido.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), strict=False)


def iter_courses(path):
    """Igual que load_course() del conversor: (id_curso, dict) de cada dict con 'clips'."""
    txt = Path(path).read_text(encoding='utf-8-sig').strip()
    d = None
    for cand in (txt, '{' + txt.rstrip(',').strip() + '}'):
        try:
            d = json.loads(cand, strict=False)
            break
        except json.JSONDecodeError as e:
            err = e
    if d is None:
        raise SystemExit(f'No pude parsear {path}: {err}')
    found = []

    def walk(n, k):
        if isinstance(n, dict):
            if 'clips' in n:
                found.append((str(k).split('/')[-1], n))
            else:
                for kk, v in n.items():
                    walk(v, kk)
    walk(d, 'root')
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('lessons_json')
    ap.add_argument('manifest')
    ap.add_argument('--out', default='player_test/player/lesson_ids.json')
    ap.add_argument('--lessons-dir', default=None)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    # (id_curso, vimeo) -> clave "<curso>/<video-id>"
    key_of = {}
    n_clips = 0
    for cid, course in iter_courses(args.lessons_json):
        uuid2vid = {}
        for u, p in (course.get('vimeo-ids') or {}).items():
            m = re.search(r'/videos/(\d+)', str(p))
            if m:
                uuid2vid[u] = int(m.group(1))
        for clip in course.get('clips') or []:
            n_clips += 1
            vid = uuid2vid.get(clip.get('video-id'))
            if vid is not None:
                key_of[(cid, vid)] = f'{cid}/{clip.get("video-id")}'
    print(f'lessons.json: {n_clips} clips, {len(key_of)} con vimeo-id conocido')

    man = load_json(args.manifest)
    rows = man.get('rows', man) if isinstance(man, dict) else man
    rows = [r for r in rows if isinstance(r, dict) and r.get('sourceCourseId') is not None]
    print(f'Manifest: {len(rows)} lecciones con sourceCourseId')

    ids, unmatched, conflicts = {}, [], []
    used = {}
    for r in rows:
        try:
            lid = int(r['lessonId'])
            key = key_of.get((str(r['sourceCourseId']), int(r['sourceVimeoId'])))
        except (KeyError, TypeError, ValueError):
            unmatched.append(r)
            continue
        if key is None:
            unmatched.append(r)
            continue
        if key in ids and ids[key] != lid:
            conflicts.append((key, ids[key], lid))
            continue
        if lid in used and used[lid] != key:
            conflicts.append((key, used[lid], lid))
            continue
        ids[key] = lid
        used[lid] = key

    print(f'\nRecuperados: {len(ids)}   Sin clip en lessons.json: {len(unmatched)}   Conflictos: {len(conflicts)}')
    for r in unmatched[:10]:
        print(f'  sin clip: lessonId {r.get("lessonId")}  curso {r.get("sourceCourseId")}  '
              f'vimeo {r.get("sourceVimeoId")}  {r.get("collectionName", "")[:40]}')
    for c in conflicts[:10]:
        print(f'  conflicto: {c}')

    floor = max(ids.values()) if ids else 0
    if args.lessons_dir:
        base = Path(args.lessons_dir)
        if not base.is_dir():
            sys.exit(f'--lessons-dir no existe: {base}')
        on_disk = {int(p.stem) for p in base.rglob('*.json') if p.stem.isdigit()}
        in_man = {int(r['lessonId']) for r in rows if str(r.get('lessonId', '')).isdigit()}
        missing = sorted(in_man - on_disk)
        extra = sorted(on_disk - in_man)
        print(f'\nEn disco: {len(on_disk)} lecciones   Manifest sin fichero: {len(missing)}   '
              f'Ficheros fuera del manifest: {len(extra)}')
        if missing:
            print('  faltan en disco (primeros):', missing[:10])
        if extra:
            print('  en disco pero no en el manifest (primeros):', extra[:10],
                  '-> IDs de lecciones quitadas; se reservan con "_floor"')
        if on_disk:
            floor = max(floor, max(on_disk))
    if floor > (max(ids.values()) if ids else 0):
        ids['_floor'] = floor
        print(f'Se anota "_floor": {floor} (el conversor seguira desde {floor + 1})')

    if not ids:
        sys.exit('\nNo se ha recuperado ningun ID; no escribo nada.')
    out = Path(args.out)
    if out.exists() and not args.force:
        try:
            current = json.loads(out.read_text(encoding='utf-8-sig') or '{}')
        except json.JSONDecodeError:
            current = {'?': 1}
        if current:
            sys.exit(f'\n{out} ya tiene contenido ({len(current)} entradas); usa --force para sobrescribirlo.')
    if args.dry_run:
        print('\n--dry-run: no se escribe nada.')
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ids, indent=2), encoding='utf-8')
    print(f'\nEscrito {out} ({len(ids)} entradas). Guardalo en git o en una copia aparte.')


if __name__ == '__main__':
    main()
