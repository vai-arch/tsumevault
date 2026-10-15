#!/usr/bin/env python3
"""Lista los clips que el conversor (v26) publica solo con audio y por que. Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk):
    python listar_solo_audio.py lessons.json
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

src = sys.argv[1] if len(sys.argv) > 1 else 'lessons.json'
DISCARD = ('navigate a nodo desconocido', 'move sobre punto ocupado',
           'move existente con color distinto al esperado (revisar)')

rows = []
for cid, course in a.load_course(src):
    bd = course.get('board') or {}
    if bd.get('variations'):
        continue                                  # solo afecta a cursos sin arbol
    title = (course.get('title') or cid).strip()
    tree = {'id': 'root', 'children': []}
    sig, uid_sigs, persisted = [], {}, {}
    for ci, clip in enumerate(course.get('clips') or [], 1):
        raw = clip.get('events')
        events = a.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
        root, byid = a.build_tree(tree)
        start = a.resolve(root, byid, sig)
        sgf, n_nodes = a.emit_sgf(root, 'x', 19)
        w = collections.Counter()
        a.DIAG = []
        _, end, _ = a.translate(events, root, byid, start, n_nodes, 'first', w, 19, uid_sigs, persisted)
        diag, a.DIAG = a.DIAG, None
        sig = a.signature(end)
        if any(k in w for k in DISCARD):
            moves = sum(1 for _, e in events if str(e[0]) in ('move', 'add'))
            first = min((ms for k, ms, _ in diag if k in ('navigate_desconocido', 'jugada_ocupada',
                                                            'color_inesperado')), default=None)
            why = ', '.join(f'{k.split(" (")[0]} x{w[k]}' for k in DISCARD if k in w)
            rows.append((title, cid, ci, moves, first, why))

print(f'Clips solo audio: {len(rows)}\n')
for title, cid, ci, moves, first, why in rows:
    t = f'{int(first // 60000)}:{int(first // 1000 % 60):02d}' if first is not None else '?'
    print(f'{title[:46]:46} clip {ci:02d}  jugadas {moves:4}  primer fallo {t:>6}  ({why})')
