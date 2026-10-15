#!/usr/bin/env python3
"""Compara como se guardan los :add (cada uno como nodo hijo, o dentro del nodo actual) con la
regla v25. Cuenta las jugadas sobre punto ocupado por curso. Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk, con awesome_to_player.py v25):
    python probar_add_mode.py lessons.json
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

src = sys.argv[1] if len(sys.argv) > 1 else 'lessons.json'
DISCARD = ('navigate a nodo desconocido', 'move sobre punto ocupado',
           'move existente con color distinto al esperado (revisar)')
VARIANTS = [('v24 (toggle, hijo)', 'toggle', 'child'),
            ('v25 (remove, hijo)', 'remove', 'child'),
            ('remove, en el nodo', 'remove', 'inplace'),
            ('remove, auto', 'remove', 'auto'),
            ('remove, auto2', 'remove', 'auto2')]


def run(add_sem, add_mode):
    a.FLAG_MODE, a.ADD_SEM, a.ADD_MODE = 'white', add_sem, add_mode
    occ, audio_only, selfbad = collections.Counter(), 0, []
    first = {}
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
            a.DIAG = []
            ev_out, end, expected = a.translate(events, root, byid, start, n_nodes, 'first', w, size,
                                                uid_sigs, persisted)
            diag, a.DIAG = a.DIAG, None
            sig = a.signature(end)
            if not has_tree and any(k in w for k in DISCARD):
                audio_only += 1
                continue
            prob = a.selfcheck(sgf, ev_out, expected, size)
            if prob:
                selfbad.append((title, cid, ci, prob[0]))
            for kind, ms, info in diag:
                if kind == 'jugada_ocupada':
                    occ[(cid, title, ci)] += 1
                    first.setdefault((cid, title, ci), round(ms / 1000.0, 1))
    return occ, audio_only, selfbad, first


res = {name: run(sem, mode) for name, sem, mode in VARIANTS}
print(f'{"":22} {"ocupadas":>9} {"clips con ocupadas":>19} {"solo audio":>11} {"selfcheck mal":>14}')
for name, _, _ in VARIANTS:
    occ, ao, sb, _ = res[name]
    print(f'{name:22} {sum(occ.values()):>9} {len(occ):>19} {ao:>11} {len(sb):>14}')

for name, _, _ in VARIANTS[2:]:
    occ, _, _, first = res[name]
    print(f'\nClips con mas ocupadas en "{name}" (curso / clip / n / primera en):')
    for (cid, title, ci), n in occ.most_common(12):
        t = first[(cid, title, ci)]
        print(f'   {title[:44]:44} {cid} clip {ci:02d}  {n:3}  {int(t // 60)}:{int(t % 60):02d}')

for name, _, _ in VARIANTS[2:]:
    sb = res[name][2]
    if sb:
        print(f'\nClips con autocomprobacion fallida en "{name}":')
        for title, cid, ci, msg in sb:
            print(f'   {title[:44]:44} {cid} clip {ci:02d}  {msg}')
