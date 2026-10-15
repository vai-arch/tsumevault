#!/usr/bin/env python3
"""Censo de :move con flag (solo lectura). Mide si flag=True invierte la alternancia.

Uso (desde _sources_scripts\\awesome_baduk, junto a awesome_to_player.py):
    python census_flag.py lessons.json

Para cada :move en vivo cuyo punto coincide con un hijo del arbol ORIGINAL del curso
(color real conocido) y cuyo camino entero es del arbol original (alternancia fiable),
compara el color real con la alternancia pura. Salida: tabla en pantalla y census_flag.csv
con las excepciones a la regla "flag=True invierte, flag=False alterna".
"""
import collections
import csv
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

B, W = a.B, a.W
src = sys.argv[1] if len(sys.argv) > 1 else 'lessons.json'

rec = []
orig_next = a.next_color


def wrapped(n):
    lc = a.last_color(n)
    rec.append({
        'alt': B if lc is None else -lc,
        'lc_none': lc is None,
        'allbase': all(x.base for x in a.path_of(n)),
        'kids': {c.move[0]: c.move[1] for c in n.children if c.base and c.move and c.move[0] != 'pass'},
        'nbase': sum(1 for c in n.children if c.base and c.move),
    })
    return orig_next(n)


a.next_color = wrapped

stats = collections.Counter()     # (flag, real==alt, lc_none) -> n
rows = []
errors = 0
clips_total = 0

for cid, course in a.load_course(src):
    bd = course.get('board') or {}
    if not bd.get('variations'):
        continue
    title = (course.get('title') or cid).strip()
    try:
        tree = a.edn(bd['variations'])
        size = int(tree.get('board-size') or 19)
        sig, uid_sigs, persisted = [], {}, {}
        for ci, clip in enumerate(course.get('clips') or [], 1):
            ev_raw = clip.get('events')
            events = a.edn(ev_raw) if isinstance(ev_raw, str) and ev_raw != 'nil' else []
            root, byid = a.build_tree(tree)
            start = a.resolve(root, byid, sig)
            sgf, n_nodes = a.emit_sgf(root, 'x', size)
            rec.clear()
            warn = collections.Counter()
            _, end, _ = a.translate(events, root, byid, start, n_nodes, 'first', warn, size, uid_sigs, persisted)
            sig = a.signature(end)
            moves = [(ms, e) for ms, e in events if str(e[0]) == 'move']
            clips_total += 1
            if len(moves) != len(rec):
                errors += 1
                continue
            for (ms, e), r in zip(moves, rec):
                (x, y), flag = e[1], bool(e[2])
                if not r['allbase'] or (x, y) not in r['kids']:
                    continue
                real = r['kids'][(x, y)]
                agree = (real == r['alt'])
                stats[(flag, agree, r['lc_none'])] += 1
                rule_ok = (agree != flag)          # flag=False: debe coincidir; flag=True: debe ser el contrario
                if not rule_ok:
                    rows.append([cid, title, ci, round(ms / 1000, 1), f'{x},{y}', flag,
                                 'B' if r['alt'] == B else 'W', 'B' if real == B else 'W',
                                 r['lc_none'], r['nbase']])
    except Exception as ex:  # noqa: BLE001
        errors += 1
        print(f'!! error en "{title}": {type(ex).__name__}: {ex}')

print(f'\nClips analizados: {clips_total}  (clips con desajuste de recuento/errores: {errors})')
print('\nMoves con color real conocido (camino y nodo del arbol original):')
print(f'{"flag":6} {"real==alternancia":18} {"tras diagrama(lc=None)":24} {"n":>7}')
for (flag, agree, lcn), n in sorted(stats.items()):
    print(f'{str(flag):6} {str(agree):18} {str(lcn):24} {n:>7}')
tot = sum(stats.values())
ok_rule = sum(n for (f, ag, _), n in stats.items() if ag != f)
ok_ign = sum(n for (f, ag, _), n in stats.items() if ag)
print(f'\nTotal: {tot}')
print(f'Aciertos con regla "flag invierte":  {ok_rule}  ({100 * ok_rule / max(tot, 1):.2f}%)')
print(f'Aciertos con regla "flag ignorado":  {ok_ign}  ({100 * ok_ign / max(tot, 1):.2f}%)')

with open('census_flag.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['course_id', 'title', 'clip', 'seg', 'punto', 'flag', 'alternancia', 'real', 'tras_diagrama', 'hijos_arbol'])
    w.writerows(rows)
print(f'Excepciones a la regla "flag invierte": {len(rows)} -> census_flag.csv')
