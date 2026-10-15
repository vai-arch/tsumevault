#!/usr/bin/env python3
"""Lista los clips cuya autocomprobacion falla con el conversor actual (v27) y el motivo. Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk):
    python listar_selfcheck.py lessons.json
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

src = sys.argv[1] if len(sys.argv) > 1 else 'lessons.json'
DISCARD = ('navigate a nodo desconocido', 'move sobre punto ocupado',
           'move existente con color distinto al esperado (revisar)')

n = 0
for cid, course in a.load_course(src):
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
        ev_out, end, expected = a.translate(events, root, byid, start, n_nodes, 'first', w, size,
                                            uid_sigs, persisted)
        sig = a.signature(end)
        if not has_tree and any(k in w for k in DISCARD):
            continue
        prob = a.selfcheck(sgf, ev_out, expected, size)
        if prob:
            n += 1
            navs_nil = sum(1 for _, e in events if str(e[0]) == 'navigate' and e[1] is None)
            print(f'{title[:46]:46} {cid} clip {ci:02d}  arbol={has_tree}  navigate nil={navs_nil}')
            for p in prob[:3]:
                print(f'      {p}')
print(f'\nClips con autocomprobacion fallida: {n}')
