#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diag_ocupadas.py - Diagnostico de SOLO LECTURA: jugadas sobre punto ocupado de un curso.

Uso (en la misma carpeta que awesome_to_player.py):
    python diag_ocupadas.py lessons.json "9kyu 2"
    python diag_ocupadas.py lessons.json "9kyu 2" --clip 2

Reproduce la conversion de awesome_to_player.py (mismas opciones por defecto) SIN escribir
ningun fichero, y para cada jugada sobre punto ocupado imprime: instante, punto (en coordenadas
del tablero del player, A-T sin I y 19 arriba), la piedra que ya estaba y los eventos previos.
"""
import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import awesome_to_player as A   # noqa: E402

COLS = 'ABCDEFGHJKLMNOPQRST'


def gtp(p, size=19):
    x, y = p
    return f'{COLS[x]}{size - y}'


def mmss(ms):
    s = ms / 1000.0
    return f'{int(s // 60)}:{s % 60:05.2f}'


def short(ev):
    return ' '.join(str(e) for e in ev)[:70]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('lessons_json')
    ap.add_argument('texto', help='texto del titulo del curso')
    ap.add_argument('--clip', type=int, default=None, help='solo este clip (1, 2, ...)')
    ap.add_argument('--before', type=int, default=6, help='eventos previos a mostrar (6)')
    args = ap.parse_args()

    print(f'awesome_to_player {A.VERSION}')
    found = [(cid, c) for cid, c in A.load_course(args.lessons_json)
             if args.texto.lower() in str(c.get('title', '')).lower()]
    if not found:
        sys.exit('No hay ningun curso con ese titulo.')
    for cid, course in found:
        title = course.get('title')
        bd = course.get('board') or {}
        tree = A.edn(bd['variations']) if bd.get('variations') else {'id': 'root', 'children': []}
        size = int(tree.get('board-size') or 19)
        print('=' * 72)
        print(f'CURSO {cid} "{title}"  arbol: {"SI" if bd.get("variations") else "NO (en vivo)"}')
        sig, uid_sigs, persisted = [], {}, {}
        for ci, clip in enumerate(course.get('clips') or [], 1):
            raw = clip.get('events')
            events = A.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
            warn = collections.Counter()
            root, byid = A.build_tree(tree)
            start = A.resolve(root, byid, sig)
            _, n_nodes = A.emit_sgf(root, 'x', size)
            A.DIAG = []
            _, end, _ = A.translate(events, root, byid, start, n_nodes, 'first', warn, size, uid_sigs, persisted)
            diag = A.DIAG
            A.DIAG = None
            sig = A.signature(end)
            if args.clip is not None and ci != args.clip:
                continue
            occ = [d for d in diag if d[0] == 'jugada_ocupada']
            other = collections.Counter(d[0] for d in diag if d[0] != 'jugada_ocupada')
            print(f'\n-- Clip {ci:02d}: {len(events)} eventos, jugadas sobre punto ocupado: {len(occ)}'
                  + (f', otras anomalias: {dict(other)}' if other else ''))
            for kind, ms, info in occ:
                node = info['node']
                had = A.position(node, size).g.get(info['pt'])
                col = 'negra' if info['color'] == A.B else 'blanca'
                prev = 'negra' if had == A.B else 'blanca' if had == A.W else '?'
                print(f'\n   t={mmss(ms)}  jugada {col} en {gtp(info["pt"], size)} {list(info["pt"])}'
                      f'  flag={info["flag"]}  -> ya habia una piedra {prev}')
                idx = next((i for i, (t, ev) in enumerate(events)
                            if t == ms and str(ev[0]) == 'move' and tuple(ev[1]) == tuple(info['pt'])), None)
                if idx is not None:
                    for t, ev in events[max(0, idx - args.before):idx + 1]:
                        print(f'      {mmss(t):>9}  {short(ev)}')


if __name__ == '__main__':
    main()
