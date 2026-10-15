#!/usr/bin/env python3
"""Para un clip solo audio: que ids pide el primer navigate y donde aparecen en lessons.json.
Tambien lista los campos del curso, por si el arbol esta en otro sitio. Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk):
    python buscar_navigate.py lessons.json "4 corner patterns you must know to be 9kyu 3" 2
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, '.')
import awesome_to_player as a

src, TITLE, CLIP = sys.argv[1], sys.argv[2], int(sys.argv[3])
raw = Path(src).read_text(encoding='utf-8-sig')
data = json.loads(raw, strict=False)

course = cid = None
for c_id, c in a.load_course(src):
    if (c.get('title') or '').strip().lower() == TITLE.strip().lower():
        course, cid = c, c_id
        break
if course is None:
    sys.exit('No encuentro ese curso por titulo.')


def short(v):
    if isinstance(v, str):
        return f'texto de {len(v)} caracteres' + (' (parece EDN)' if v[:1] in '[{(' else '')
    if isinstance(v, (list, dict)):
        return f'{type(v).__name__} de {len(v)} elementos'
    return repr(v)[:60]


print(f'Curso {cid}: {TITLE}')
print('Campos del curso:')
for k, v in course.items():
    if k != 'clips':
        print(f'   {k:22} {short(v)}')
bd = course.get('board') or {}
print('Campos de board:', {k: short(v) for k, v in bd.items()} if isinstance(bd, dict) else short(bd))
clip = course['clips'][CLIP - 1]
print(f'Campos del clip {CLIP:02d}:', {k: short(v) for k, v in clip.items()})

ev = a.edn(clip['events']) if isinstance(clip.get('events'), str) else []
navs = [e[1] for _, e in ev if str(e[0]) == 'navigate']
print(f'\nnavigate en el clip: {len(navs)}; primeros: {navs[:3]}')


def where(obj, needle, path='', out=None, depth=0):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            where(v, needle, f'{path}/{k}', out, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            where(v, needle, f'{path}[{i}]', out, depth + 1)
    elif isinstance(obj, str) and needle in obj:
        out.append(path)
    return out


for nid in dict.fromkeys(navs[:3]):
    hits = where(data, str(nid))
    print(f'\nid {nid}: aparece {raw.count(str(nid))} veces en el fichero')
    for h in hits[:8]:
        print(f'   en {h}')
