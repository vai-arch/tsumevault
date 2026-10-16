#!/usr/bin/env python3
"""Quita de recorded.json las lecciones cuyo tablero ha cambiado con las correcciones de octubre
(v22 publicada -> v27 actual), para que el player las vuelva a ofrecer como pendientes de grabar.

Compara, clip a clip, el .sgf y el .json que genera la v22 con los que genera la v27 (en memoria,
sin escribir lecciones). Solo los clips cuyo resultado difiere cuentan como cambiados.

Uso (desde _sources_scripts\\awesome_baduk, junto a awesome_to_player.py v27):
    python recorded_quitar_cambiadas.py lessons.json <lesson_ids.json real> <recorded.json>           (simulacion)
    python recorded_quitar_cambiadas.py lessons.json <lesson_ids.json real> <recorded.json> --apply   (escribe)

Con --apply guarda antes una copia recorded.json.bak-AAAAMMDD-HHMMSS junto al original.
"""
import argparse
import collections
import datetime
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, '.')
import awesome_to_player as a

ap = argparse.ArgumentParser()
ap.add_argument('lessons')
ap.add_argument('ids')
ap.add_argument('recorded')
ap.add_argument('--apply', action='store_true')
args = ap.parse_args()

DISCARD = ('navigate a nodo desconocido', 'move sobre punto ocupado',
           'move existente con color distinto al esperado (revisar)')
V22 = dict(FLAG_MODE='ignore', ADD_SEM='toggle', ADD_MODE='child', NAV_NIL='ignore')
V27 = dict(FLAG_MODE='white', ADD_SEM='remove', ADD_MODE='auto2', NAV_NIL='root')


def run(cfg):
    for k, v in cfg.items():
        setattr(a, k, v)
    out = {}
    for cid, course in a.load_course(args.lessons):
        title = (course.get('title') or cid).strip()
        bd = course.get('board') or {}
        has_tree = bool(bd.get('variations'))
        tree = a.edn(bd['variations']) if has_tree else {'id': 'root', 'children': []}
        size = int(tree.get('board-size') or 19)
        sig, uid_sigs, persisted = [], {}, {}
        for ci, clip in enumerate(course.get('clips') or [], 1):
            raw = clip.get('events')
            events = a.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
            root, byid = a.build_tree(tree)
            start = a.resolve(root, byid, sig)
            sgf, n_nodes = a.emit_sgf(root, 'x', size)
            w = collections.Counter()
            ev_out, end, _ = a.translate(events, root, byid, start, n_nodes, 'first', w, size,
                                         uid_sigs, persisted)
            sig = a.signature(end)
            if not has_tree and any(k in w for k in DISCARD):
                ev_out = [{'time': 0, 'activate': 0}]          # igual que el conversor: solo audio
            out[f'{cid}/{clip.get("video-id")}'] = (title, ci, sgf, json.dumps(ev_out, sort_keys=True))
    return out


print(f'awesome_to_player {a.VERSION[:4]} (comparando v22 con v27)')
old, new = run(V22), run(V27)
changed = {k for k in new if k in old and old[k][2:] != new[k][2:]}

ids = json.loads(Path(args.ids).read_text(encoding='utf-8'))
changed_ids = {}
for key in changed:
    lid = ids.get(key)
    if lid is not None:
        changed_ids[int(lid)] = new[key][:2]
print(f'Clips cambiados: {len(changed)} (publicados: {len(changed_ids)})')

rec_path = Path(args.recorded)
rec = json.loads(rec_path.read_text(encoding='utf-8'))
recorded = rec['recorded']
to_remove = [x for x in recorded if int(x) in changed_ids]
print(f'Grabadas en {rec_path.name}: {len(recorded)}  ->  a quitar (hay que regrabar): {len(to_remove)}\n')
for x in sorted(to_remove, key=int):
    title, ci = changed_ids[int(x)]
    print(f'   {x}  {title[:55]:55} Clip {ci:02d}')

if not to_remove:
    print('Nada que quitar.')
elif args.apply:
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = rec_path.with_name(f'{rec_path.name}.bak-{stamp}')
    shutil.copy2(rec_path, bak)
    drop = {int(x) for x in to_remove}
    rec['recorded'] = [x for x in recorded if int(x) not in drop]
    rec_path.write_text(json.dumps(rec, indent=2) + '\n', encoding='utf-8')
    print(f'\nEscrito {rec_path} ({len(rec["recorded"])} grabadas). Copia de seguridad: {bak.name}')
else:
    print('\nSimulacion: no se ha escrito nada. Repite con --apply para quitarlas.')
