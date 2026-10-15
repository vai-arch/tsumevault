#!/usr/bin/env python3
"""Aplica los :add del inicio de un clip sobre el diagrama del navigate con varias semanticas
posibles y compara cada resultado con la captura real. Solo lectura.

Uso: python probar_add.py lessons.json 65pGlVYL33pOyuS8CEAa 4 1.0
     (el ultimo numero: hasta que segundo se aplican los :add)
"""
import sys

sys.path.insert(0, '.')
import awesome_to_player as a
from buscar_diagrama_real import REAL, show

src, CID, CLIP, TMAX = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
B, W = a.B, a.W


def apply(base, adds, sem):
    g = dict(base)
    for (x, y), flag in adds:
        p, col = (x, y), (W if flag else B)
        cur = g.get(p)
        if sem == 'toggle':              # actual: mismo color -> quita; si no, pone ese color
            if cur == col:
                del g[p]
            else:
                g[p] = col
        elif sem == 'place':             # siempre pone
            g[p] = col
        elif sem == 'quita-si-hay':      # cualquier piedra -> la quita; vacio -> pone
            if cur is None:
                g[p] = col
            else:
                del g[p]
    return g


def dist(g):
    return sum(1 for p in set(g) | set(REAL) if g.get(p) != REAL.get(p))


for cid, course in a.load_course(src):
    if cid != CID:
        continue
    tree = a.edn(course['board']['variations'])
    size = int(tree.get('board-size') or 19)
    root, byid = a.build_tree(tree)
    ev = a.edn(course['clips'][CLIP - 1]['events'])
    nav = next((e[1] for ms, e in ev if str(e[0]) == 'navigate'), None)
    adds = [(tuple(e[1]), bool(e[2])) for ms, e in ev if str(e[0]) == 'add' and ms <= TMAX * 1000]
    print(f'navigate a {nav}; :add aplicados (hasta {TMAX}s): {len(adds)}')
    bases = {'diagrama del navigate': a.position(byid[nav], size).g, 'tablero vacio': {}}
    best = None
    for bname, base in bases.items():
        for sem in ('toggle', 'place', 'quita-si-hay'):
            g = apply(base, adds, sem)
            d = dist(g)
            print(f'  base {bname:22} semantica {sem:13} -> distancia a la captura {d}')
            if best is None or d < best[0]:
                best = (d, bname, sem, g)
    d, bname, sem, g = best
    print(f'\nMejor: base "{bname}", semantica "{sem}", distancia {d}')
    if d:
        for p in sorted(set(g) | set(REAL)):
            if g.get(p) != REAL.get(p):
                print(f'  {a.co(p)}: nuestra={ {B: "negra", W: "blanca", None: "vacio"}[g.get(p)] }'
                      f'  captura={ {B: "negra", W: "blanca", None: "vacio"}[REAL.get(p)] }')
