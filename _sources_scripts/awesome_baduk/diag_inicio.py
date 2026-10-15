#!/usr/bin/env python3
"""Compara la posicion con la que ARRANCA un clip (v24) con la posicion real del video. Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk):
    python diag_inicio.py lessons.json 65pGlVYL33pOyuS8CEAa 4

La posicion real (REAL) esta transcrita a mano de la captura del segundo 0:01 del Clip 04
de "Counting Liberties - Increase 2". Coordenadas (columna, fila) desde arriba a la izquierda.
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

src, CID, CLIP = sys.argv[1], sys.argv[2], int(sys.argv[3])
B, W = a.B, a.W

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


def origin(node, pt, size):
    """Que nodo del camino deja la piedra (o el hueco) en pt: recorre root->node."""
    hist = []
    b = a.Board(size)
    for n in a.path_of(node):
        before = b.g.get(pt)
        if n.stones is not None:
            b.g = dict(n.stones) if a.STONES_MODE == 'replace' else {**b.g, **n.stones}
        for p, c in n.adds:
            if c == 0:
                b.g.pop(p, None)
            else:
                b.g[p] = c
        if n.move and n.move[0] != 'pass':
            b.play(n.move[0], n.move[1])
        after = b.g.get(pt)
        if before != after:
            kind = ('diagrama' if n.stones is not None else 'add' if n.adds else
                    f'jugada {"B" if n.move[1] == B else "W"}[{a.co(n.move[0]) if n.move[0] != "pass" else "pass"}]'
                    if n.move else '?')
            hist.append(f'{kind} ({"arbol" if n.base else "en vivo"}, id={n.id}) -> '
                        f'{ {B: "negra", W: "blanca", None: "vacio"}[after] }')
    return hist


a.FLAG_MODE = 'white'
for cid, course in a.load_course(src):
    if cid != CID:
        continue
    bd = course.get('board') or {}
    has_tree = bool(bd.get('variations'))
    tree = a.edn(bd['variations']) if has_tree else {'id': 'root', 'children': []}
    size = int(tree.get('board-size') or 19)
    print(f'Curso: {course.get("title")}  | arbol original: {has_tree}  | tamano {size}')
    sig, uid_sigs, persisted = [], {}, {}
    for ci, clip in enumerate(course['clips'], 1):
        raw = clip.get('events')
        events = a.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
        root, byid = a.build_tree(tree)
        start = a.resolve(root, byid, sig)
        sgf, n_nodes = a.emit_sgf(root, 'x', size)
        if ci == CLIP:
            first = events[0][1] if events else None
            init = start
            if first is not None and str(first[0]) == 'navigate' and byid.get(first[1]):
                init = byid[first[1]]
            print(f'Clip {ci:02d}: primer evento = {first}')
            print(f'  nodo de arranque: {"el del primer navigate" if init is not start else "donde acabo el clip anterior"}'
                  f'  (camino de {len(a.path_of(init))} nodos)')
            ours = a.position(init, size).g
            show(ours, 'NUESTRA posicion al arrancar (X negra, O blanca)')
            show(REAL, 'Posicion REAL del video en 0:01')
            extra = sorted(p for p in ours if p not in REAL)
            missing = sorted(p for p in REAL if p not in ours)
            wrong = sorted(p for p in REAL if p in ours and ours[p] != REAL[p])
            print(f'\nSobran {len(extra)}, faltan {len(missing)}, color cambiado {len(wrong)}')
            for label, pts in (('SOBRA', extra), ('FALTA', missing), ('COLOR', wrong)):
                for p in pts:
                    print(f'  {label} {a.co(p)}: ' + ' | '.join(origin(init, p, size)[-3:]))
            # resumen del camino: diagramas y procedencia de las jugadas
            path = a.path_of(init)
            kinds = collections.Counter('diagrama' if n.stones is not None else 'add' if n.adds else
                                        'jugada' if n.move else 'vacio' for n in path)
            print(f'\nCamino hasta el arranque: {dict(kinds)}; nodos en vivo: {sum(not n.base for n in path)}')
            break
        ev_out, end, _ = a.translate(events, root, byid, start, n_nodes, 'first',
                                     collections.Counter(), size, uid_sigs, persisted)
        sig = a.signature(end)
        print(f'Clip {ci:02d} termina en un nodo a {len(a.path_of(end))} pasos de la raiz')
