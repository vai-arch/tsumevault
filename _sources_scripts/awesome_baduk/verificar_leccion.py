#!/usr/bin/env python3
"""Dice que version del conversor tiene una leccion: en fix_v26, en tu player local y en el servidor.
Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk):
    python verificar_leccion.py lessons.json 65pGlVYL33pOyuS8CEAa 4 ^
        "C:\\...\\player\\lessons_sources\\awesome_baduk_lessons_ids.json" ^
        "C:\\...\\player\\lessons"
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, '.')
import awesome_to_player as a

src, CID, CLIP, IDS, LOCAL = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
SRV = 'root@tsumevault.duckdns.org'
REMOTE = '/opt/tsumevault/player/lessons'

course = dict(a.load_course(src))[CID]
title = (course.get('title') or CID).strip()
vid = course['clips'][CLIP - 1].get('video-id')
lid = json.loads(Path(IDS).read_text(encoding='utf-8')).get(f'{CID}/{vid}')
if lid is None:
    sys.exit('Ese clip no tiene lessonId publicado.')
rel = f"Awesome Baduk/{a.player_sanitize(title)}/Clip {CLIP:02d}/{lid}.json"
print(f'Curso: {title} | clip {CLIP:02d} | lessonId {lid}\nRuta: lessons/{rel}\n')


def describe(data):
    ev = json.loads(data)
    t0 = [e for e in ev if e['time'] == 0]
    kids = sum('addChild' in e for e in t0)
    props = sum('addProp' in e and 'addChild' not in e for e in t0)
    if kids > 50:
        ver = 'ANTIGUA (v22-v25: retoques como nodos hijos)'
    elif props > 50:
        ver = 'NUEVA (v26: retoques dentro del nodo)'
    else:
        ver = 'no concluyente'
    return f'md5 {hashlib.md5(data).hexdigest()[:12]}  eventos en t=0: {len(t0)} ' \
           f'(addChild {kids}, solo addProp {props})  -> {ver}'


for name, p in (('fix_v26', Path('fix_v26/lessons') / rel), ('player local', Path(LOCAL) / rel)):
    print(f'{name:13}: ' + (describe(p.read_bytes()) if p.exists() else f'NO EXISTE ({p})'))

r = subprocess.run(['ssh', SRV, f"cat '{REMOTE}/{rel}'"], capture_output=True)
print(f'{"servidor":13}: ' + (describe(r.stdout) if r.returncode == 0 and r.stdout
                              else f'no se pudo leer ({r.stderr.decode(errors="replace").strip()[:120]})'))
