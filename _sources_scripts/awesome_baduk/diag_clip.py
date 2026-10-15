#!/usr/bin/env python3
"""Diagnostico de un clip: para cada :move muestra hijos del nodo actual, color esperado y nodo elegido.

Uso (desde _sources_scripts\\awesome_baduk):
    python diag_clip.py lessons.json d7P7EfIVERczbQP2BLuG 2 80 112
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

src, CID, CLIP, T0, T1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
def describe(sgf, ev_out):
    nodes = a.parse_sgf_model(sgf)
    mv = {}
    for nd in nodes:
        for name, vals in nd['props']:
            if name in ('B', 'W'):
                mv[nd['nn']] = f'{name}[{vals[0] if vals else ""}]'
    res = {}
    for ev in ev_out:
        if 'addProp' in ev:
            nn, prop = ev['addProp']
            if prop[:2] in ('B[', 'W['):
                mv[nn] = prop
        if 'activate' in ev:
            res.setdefault(ev['time'], []).append(mv.get(ev['activate'], '(sin jugada)'))
    return res


for course_id, course in a.load_course(src):
    if course_id != CID:
        continue
    bd = course.get('board') or {}
    tree = a.edn(bd['variations']) if bd.get('variations') else {'id': 'root', 'children': []}
    print('Curso con arbol original:', bool(bd.get('variations')))
    size = int(tree.get('board-size') or 19)
    for mode in ('ignore', 'white'):
        a.FLAG_MODE = mode
        sig, uid_sigs, persisted = [], {}, {}
        print(f'\n===== FLAG_MODE={mode} =====')
        for ci, clip in enumerate(course['clips'], 1):
            raw = clip.get('events')
            events = a.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
            root, byid = a.build_tree(tree)
            start = a.resolve(root, byid, sig)
            sgf, n_nodes = a.emit_sgf(root, 'x', size)
            ev_out, end, _ = a.translate(events, root, byid, start, n_nodes, 'first',
                                         collections.Counter(), size, uid_sigs, persisted)
            sig = a.signature(end)
            if ci != CLIP:
                continue
            desc = describe(sgf, ev_out)
            for ms, e in events:
                t = round(ms / 1000.0, 3)
                if T0 <= t <= T1:
                    print(f'{t:7.1f}s {e[:3] if str(e[0]) == "move" else e}   -> activa {desc.get(t)}')
