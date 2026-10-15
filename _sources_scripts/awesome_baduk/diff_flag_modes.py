#!/usr/bin/env python3
"""Muestra, clip a clip, que cambia entre v22 (FLAG_MODE='ignore') y v24 ('white'). Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk):
    python diff_flag_modes.py lessons.json [ID_CURSO ...] > diff_flag.txt
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

src = sys.argv[1] if len(sys.argv) > 1 else 'lessons.json'
ONLY = set(sys.argv[2:])
MAXSHOW = 4


def describe(sgf, ev_out):
    """Para cada evento 'activate', la jugada del nodo activado (p. ej. 'B[bq]'), incluso nodos creados en vivo."""
    nodes = a.parse_sgf_model(sgf)
    mv = {}
    for nd in nodes:
        for name, vals in nd['props']:
            if name in ('B', 'W'):
                mv[nd['nn']] = f'{name}[{vals[0] if vals else ""}]'
    res = []
    for ev in ev_out:
        if 'addProp' in ev:
            nn, prop = ev['addProp']
            if prop[:2] in ('B[', 'W['):
                mv[nn] = prop
        if 'activate' in ev:
            res.append(mv.get(ev['activate'], '(sin jugada)'))
        else:
            res.append(None)
    return res


def run(mode):
    a.FLAG_MODE = mode
    out = {}
    for cid, course in a.load_course(src):
        if ONLY and cid not in ONLY:
            continue
        bd = course.get('board') or {}
        title = (course.get('title') or cid).strip()
        tree = a.edn(bd['variations']) if bd.get('variations') else {'id': 'root', 'children': []}
        size = int(tree.get('board-size') or 19)
        sig, uid_sigs, persisted = [], {}, {}
        for ci, clip in enumerate(course.get('clips') or [], 1):
            raw = clip.get('events')
            events = a.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
            root, byid = a.build_tree(tree)
            start = a.resolve(root, byid, sig)
            sgf, n_nodes = a.emit_sgf(root, 'x', size)
            ev_out, end, _ = a.translate(events, root, byid, start, n_nodes, 'first',
                                         collections.Counter(), size, uid_sigs, persisted)
            sig = a.signature(end)
            raw_by_t = {}
            for ms, e in events:
                raw_by_t.setdefault(round(ms / 1000.0, 3), []).append(e)
            out[(cid, ci)] = (title, describe(sgf, ev_out), ev_out, raw_by_t)
    return out


ri, rv = run('ignore'), run('white')
n_clip = 0
for key in ri:
    ti, di, ei, raw = ri[key]
    _, dv, ev, _ = rv[key]
    if len(ei) != len(ev):
        print(f'\n## {ti} / {key[0]} clip {key[1]:02d}: LONGITUD distinta {len(ei)} vs {len(ev)}')
        n_clip += 1
        continue
    diffs = [i for i in range(len(ei)) if ei[i] != ev[i] or di[i] != dv[i]]
    if not diffs:
        continue
    n_clip += 1
    print(f'\n## {ti} / {key[0]} clip {key[1]:02d}: {len(diffs)} eventos difieren')
    for i in diffs[:MAXSHOW]:
        t = ei[i]['time']
        src_ev = [e for e in raw.get(t, []) if str(e[0]) in ('move', 'add')]
        print(f'  {t:7.1f}s  fuente={src_ev}')
        print(f'           v22 -> {di[i]}   v24 -> {dv[i]}   (min {int(t // 60)}:{int(t % 60):02d})')
print(f'\nClips con diferencias: {n_clip}')
