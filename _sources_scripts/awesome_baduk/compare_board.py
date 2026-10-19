#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_board.py - SOLO LECTURA: compara lo que se VE en el tablero entre la leccion publicada
y la regenerada con --board-only, instante a instante.

Uso (en la misma carpeta que awesome_to_player.py):
    python compare_board.py board_out "RUTA\\player\\lessons\\Awesome Baduk"

Para cada leccion de board_out\\board_changes.json reproduce el .sgf + .json viejo y el nuevo
como el player (addChild / addProp / activate) y compara las piedras en cada instante.
  - "IGUAL"   : solo cambia la numeracion interna; lo que se ve es identico.
  - "DISTINTO": lista los primeros instantes en que difieren, con las piedras de mas/de menos.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import awesome_to_player as A   # noqa: E402

COLS = 'ABCDEFGHJKLMNOPQRST'


def mmss(t):
    return f'{int(t // 60)}:{t % 60:05.2f}'


def stone(p, c):
    x, y = p
    return f"{'B' if c == A.B else 'W'}{COLS[x]}{19 - y}"


def timeline(sgf_text, events):
    """[(t, posicion)] con la posicion visible tras TODOS los eventos de cada instante."""
    nodes = A.parse_sgf_model(sgf_text)
    out, active = [], 0
    for i, e in enumerate(events):
        if 'addChild' in e:
            p, c = e['addChild']
            while len(nodes) <= c:
                nodes.append(None)
            nodes[c] = {'nn': c, 'parent': nodes[p] if p < len(nodes) else None, 'props': []}
        if 'addProp' in e:
            nn, prop = e['addProp']
            bi = prop.index('[')
            if nn < len(nodes) and nodes[nn] is not None:
                nodes[nn]['props'].append((prop[:bi], [prop[bi + 1:-1]]))
        if 'activate' in e:
            active = e['activate']
        last_of_instant = i + 1 == len(events) or events[i + 1]['time'] != e['time']
        if last_of_instant:
            out.append((e['time'], dict(A.model_position(nodes, active))))
    return out


def at(tl, t):
    pos = {}
    for tt, p in tl:
        if tt > t:
            break
        pos = p
    return pos


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    board_out, pub = Path(sys.argv[1]), Path(sys.argv[2])
    changes = json.loads((board_out / 'board_changes.json').read_text(encoding='utf-8'))['detail']
    new_index = {int(p.stem): p.parent for p in board_out.rglob('*.json') if p.stem.isdigit()}
    old_index = {int(p.stem): p.parent for p in pub.rglob('*.json') if p.stem.isdigit()}
    n_same = n_diff = 0
    for c in changes:
        lid = c['lessonId']
        dn, do = new_index.get(lid), old_index.get(lid)
        if dn is None or do is None:
            print(f'{lid}  ?? no encuentro los ficheros')
            continue
        tl_new = timeline((dn / f'{lid}.sgf').read_text(encoding='utf-8-sig'),
                          json.loads((dn / f'{lid}.json').read_text(encoding='utf-8-sig')))
        tl_old = timeline((do / f'{lid}.sgf').read_text(encoding='utf-8-sig'),
                          json.loads((do / f'{lid}.json').read_text(encoding='utf-8-sig')))
        times = sorted({t for t, _ in tl_new} | {t for t, _ in tl_old})
        diffs = []
        for t in times:
            a, b = at(tl_old, t), at(tl_new, t)
            if a != b:
                mas = [stone(p, v) for p, v in sorted(b.items()) if a.get(p) != v]
                menos = [stone(p, v) for p, v in sorted(a.items()) if b.get(p) != v]
                diffs.append((t, mas, menos))
        head = f'{lid}  {c["curso"][:40]:40} clip {c["clip"]:2}'
        if not diffs:
            n_same += 1
            print(f'{head}  IGUAL')
            continue
        n_diff += 1
        print(f'{head}  DISTINTO en {len(diffs)} instantes (de {len(times)})')
        for t, mas, menos in diffs[:4]:
            print(f'      {mmss(t):>9}  ahora de mas: {" ".join(mas[:8]) or "-"}   ahora de menos: {" ".join(menos[:8]) or "-"}')
        if len(diffs) > 4:
            print(f'      ... y {len(diffs) - 4} instantes mas (ultimo en {mmss(diffs[-1][0])})')
    print(f'\nTotal: {n_same} IGUAL, {n_diff} DISTINTO')


if __name__ == '__main__':
    main()
