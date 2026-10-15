#!/usr/bin/env python3
"""Busca en el arbol del curso el nodo cuya posicion se parece mas a la captura real. Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk, junto a diag_inicio.py):
    python buscar_diagrama.py lessons.json 65pGlVYL33pOyuS8CEAa 80fc32a6-5d5b-4a88-8e58-de68c66da1ee
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

B, W = a.B, a.W
# misma transcripcion de la captura que diag_inicio.py
REAL_TXT = {
    0: {17: 'B'},
    1: {14: 'W', 15: 'W', 16: 'W', 17: 'B', 18: 'W'},
    2: {14: 'B', 15: 'B', 16: 'W', 17: 'B'},
    3: {11: 'W', 13: 'W', 14: 'W', 15: 'W', 16: 'B', 17: 'B', 18: 'B'},
    4: {12: 'W', 13: 'B', 14: 'B', 15: 'B', 16: 'W', 17: 'W', 18: 'W'},
    5: {16: 'W', 18: 'W'},
    6: {13: 'B', 15: 'B', 16: 'B', 17: 'W'},
    7: {17: 'B'},
    8: {16: 'B'},
    11: {2: 'W', 3: 'W', 4: 'W', 5: 'B', 6: 'B', 7: 'W'},
    12: {0: 'W', 1: 'W', 2: 'W', 3: 'B', 4: 'B', 5: 'W', 6: 'W'},
    13: {0: 'B', 1: 'B', 2: 'B', 3: 'B', 4: 'W'},
    14: {0: 'W', 1: 'W', 2: 'W', 3: 'B', 7: 'W'},
    15: {1: 'W', 2: 'W', 3: 'B', 4: 'B', 5: 'W'},
    16: {0: 'B', 1: 'W', 2: 'B', 3: 'B', 4: 'W', 5: 'W'},
    17: {0: 'B', 1: 'W', 2: 'B', 4: 'B', 5: 'W'},
    18: {1: 'W', 2: 'B', 3: 'B', 4: 'B', 5: 'W'},
}
REAL = {(x, y): (B if c == 'B' else W) for y, row in REAL_TXT.items() for x, c in row.items()}


def show(g, title, size=19):
    print(f'\n{title}')
    print('   ' + ' '.join(chr(97 + i) for i in range(size)))
    for y in range(size):
        print(f'{chr(97 + y)}  ' + ' '.join({B: 'X', W: 'O'}.get(g.get((x, y)), '.') for x in range(size)))



src, CID, TARGET = sys.argv[1], sys.argv[2], sys.argv[3]


def dist(g):
    pts = set(g) | set(REAL)
    return sum(1 for p in pts if g.get(p) != REAL.get(p))


for cid, course in a.load_course(src):
    if cid != CID:
        continue
    raw_tree = a.edn(course['board']['variations'])
    size = int(raw_tree.get('board-size') or 19)

    # ids repetidos en el EDN original (antes de que byid se quede con el ultimo)
    ids = collections.Counter()
    stack = [raw_tree]
    while stack:
        d = stack.pop()
        ids[d.get('id')] += 1
        stack.extend(d.get('children', []))
    dup = {k: v for k, v in ids.items() if v > 1}
    print(f'Nodos en el arbol: {sum(ids.values())}  | ids repetidos: {len(dup)}')
    if TARGET in dup:
        print(f'  !! el id del navigate ({TARGET}) aparece {dup[TARGET]} veces')

    root, byid = a.build_tree(raw_tree)
    nodes, stack = [], [root]
    while stack:
        n = stack.pop()
        nodes.append(n)
        stack.extend(n.children)
    scored = sorted(((dist(a.position(n, size).g), n) for n in nodes), key=lambda t: t[0])

    tgt = byid.get(TARGET)
    print(f'Distancia del nodo del navigate a la captura: {dist(a.position(tgt, size).g) if tgt else "no existe"}')
    print('\nNodos mas parecidos a la captura (distancia = puntos distintos):')
    for dd, n in scored[:6]:
        par = n.parent.id if n.parent else None
        kind = 'diagrama' if n.stones is not None else ('jugada' if n.move else 'vacio')
        print(f'  dist {dd:3}  id={n.id}  {kind}  profundidad {len(a.path_of(n)) - 1}'
              f'  padre={par}  {"<- es el del navigate" if n is tgt else ""}'
              f'{"  (id repetido)" if n.id in dup else ""}')
        if n.id == TARGET or (tgt is not None and n.parent is tgt) or (tgt is not None and tgt.parent is n):
            print('           (relacionado con el nodo del navigate)')
    best = scored[0][1]
    if scored[0][0] <= 3:
        show(a.position(best, size).g, f'Posicion del mejor candidato (id={best.id})')
