#!/usr/bin/env python3
"""Reproduce un clip arrancando desde la posicion REAL de la captura en vez del diagrama del arbol.
Si con la posicion real desaparecen las jugadas sobre punto ocupado, el diagrama del arbol no es
el que se uso al grabar el video. Solo lectura.

Uso: python probar_real.py lessons.json 65pGlVYL33pOyuS8CEAa 4 80fc32a6-5d5b-4a88-8e58-de68c66da1ee
"""
import collections
import sys

sys.path.insert(0, '.')
import awesome_to_player as a
from buscar_diagrama_real import REAL

src, CID, CLIP, TARGET = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
a.FLAG_MODE = 'white'


def run(override):
    for cid, course in a.load_course(src):
        if cid != CID:
            continue
        tree = a.edn(course['board']['variations'])
        size = int(tree.get('board-size') or 19)
        sig, uid_sigs, persisted = [], {}, {}
        for ci, clip in enumerate(course['clips'], 1):
            raw = clip.get('events')
            events = a.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
            root, byid = a.build_tree(tree)
            if override and TARGET in byid:
                byid[TARGET].stones = dict(REAL)
            start = a.resolve(root, byid, sig)
            sgf, n_nodes = a.emit_sgf(root, 'x', size)
            w = collections.Counter()
            a.DIAG = []
            _, end, _ = a.translate(events, root, byid, start, n_nodes, 'first', w, size, uid_sigs, persisted)
            diag, a.DIAG = a.DIAG, None
            sig = a.signature(end)
            if ci == CLIP:
                t0 = events[0][0] / 1000 if events else None
                occ = [(round(ms / 1000, 1), a.co(i['pt'])) for k, ms, i in diag if k == 'jugada_ocupada']
                return t0, len([e for _, e in events if str(e[0]) == 'move']), occ


for label, ov in (('diagrama del arbol', False), ('posicion de la captura', True)):
    t0, nmoves, occ = run(ov)
    print(f'{label:24}: jugadas en el clip {nmoves}, sobre punto ocupado {len(occ)}  {occ[:8]}')
print(f'(el primer evento del clip, el navigate, ocurre en el segundo {t0})')
