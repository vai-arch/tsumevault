#!/usr/bin/env python3
"""Compara v22 (flag ignorado, add toggle) con v27 (flag blanca, add remove) sobre TODOS los cursos. Solo lectura.

Uso (desde _sources_scripts\\awesome_baduk, junto a awesome_to_player.py v27):
    python check_flag_modes.py lessons.json
"""
import collections
import json
import sys

sys.path.insert(0, '.')
import awesome_to_player as a

src = sys.argv[1] if len(sys.argv) > 1 else 'lessons.json'
MODES = ('ignore', 'white')
KEYS = ['move sobre punto ocupado', 'move existente con color distinto al esperado (revisar)',
        'move con hermanos de mismo punto y distinto color', 'navigate a nodo desconocido']
DISCARD = ('navigate a nodo desconocido', 'move sobre punto ocupado',
           'move existente con color distinto al esperado (revisar)')
CHECKS = [('6QkZf9casyPnXvUuCMtq', 2, 0, 30), ('65pGlVYL33pOyuS8CEAa', 4, 27, 50)]
AUDIO = set()  # (modo, cid, clip) de los clips que quedan solo audio
ANOM = []      # (modo, cid, clip, t, tipo, punto) de las anomalias de v27


def moves_of(sgf, ev_out):
    """(t, 'B[xx]'/'W[xx]') de cada jugada activada, incluso nodos creados en vivo."""
    mv = {}
    for nd in a.parse_sgf_model(sgf):
        for name, vals in nd['props']:
            if name in ('B', 'W'):
                mv[nd['nn']] = f'{name}[{vals[0] if vals else ""}]'
    res = []
    for ev in ev_out:
        if 'addProp' in ev:
            nn, prop = ev['addProp']
            if prop[:2] in ('B[', 'W['):
                mv[nn] = prop
        if 'activate' in ev:
            res.append((ev['time'], mv.get(ev['activate'], '-')))
    return res


def run(mode):
    a.FLAG_MODE = mode
    a.ADD_SEM = 'toggle' if mode == 'ignore' else 'remove'     # v22 frente a v27
    a.ADD_MODE = 'child' if mode == 'ignore' else 'auto2'
    a.NAV_NIL = 'ignore' if mode == 'ignore' else 'root'
    warns = collections.Counter()
    selfbad = 0
    out, titles, shown = {}, {}, {}
    for cid, course in a.load_course(src):
        titles[cid] = (course.get('title') or cid).strip()
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
            sig = a.signature(end)
            diag, a.DIAG = a.DIAG, None
            if not has_tree and any(k in w for k in DISCARD):
                AUDIO.add((mode, cid, ci))
                ev_out, expected = [{'time': 0, 'activate': 0}], [(0, root)]
                w = collections.Counter({'(clip solo audio)': 1})
                diag = []
            for kind, ms, info in diag:
                if kind != 'navigate_desconocido':
                    ANOM.append((mode, cid, ci, round(ms / 1000.0, 1), kind, a.co(info['pt'])))
            if a.selfcheck(sgf, ev_out, expected, size):
                selfbad += 1
            warns.update(w)
            out[(cid, ci)] = ev_out
            for (ccid, cci, t0, t1) in CHECKS:
                if ccid == cid and cci == ci:
                    shown[(cid, ci)] = [m for m in moves_of(sgf, ev_out) if t0 <= m[0] <= t1]
    return warns, selfbad, out, titles, shown


res = {m: run(m) for m in MODES}
print(f'{"":58} {"v22":>8} {"v27":>8}')
for k in KEYS + ['move: variacion nueva junto a jugada en vivo de otro color', '(clip solo audio)']:
    print(f'{k:58} {res["ignore"][0][k]:>8} {res["white"][0][k]:>8}')
print(f'{"clips con selfcheck distinto de OK":58} {res["ignore"][1]:>8} {res["white"][1]:>8}')

oi, ow, titles = res['ignore'][2], res['white'][2], res['ignore'][3]
diff = [k for k in oi if json.dumps(oi[k]) != json.dumps(ow[k])]
courses = collections.OrderedDict()
for cid, ci in diff:
    courses.setdefault(cid, []).append(ci)
print(f'\nClips que cambian con v27: {len(diff)} de {len(oi)}  |  cursos: {len(courses)}')
for cid, cis in courses.items():
    print(f'   {cid}  {titles[cid][:50]:50}  clips {",".join(f"{c:02d}" for c in cis)}')

for (cid, ci, t0, t1) in CHECKS:
    print(f'\nComprobacion {titles.get(cid, cid)[:40]} clip {ci:02d} ({t0}-{t1} s):')
    for m in MODES:
        js = '  '.join(f'{t:.1f}s {mv}' for t, mv in res[m][4].get((cid, ci), []))
        print(f'  [{m:6}] {js}')

rec = sorted({(cid, ci) for (m, cid, ci) in AUDIO if m == 'ignore'} - {(cid, ci) for (m, cid, ci) in AUDIO if m == 'white'})
print(f'\nClips que recuperan el tablero (dejan de ser solo audio): {len(rec)}')
for cid, ci in rec:
    print(f'   {cid}  {titles[cid][:50]:50}  clip {ci:02d}')

cnt = collections.Counter((m, k) for (m, _, _, _, k, _) in ANOM)
print('\nAnomalias por tipo (diagnostico):')
for k in sorted({k for (_, k) in cnt}):
    print(f'   {k:20} v22 {cnt[("ignore", k)]:>5}   v27 {cnt[("white", k)]:>5}')
rows = [r for r in ANOM if r[0] == 'white']
with open('anomalias_v27.csv', 'w', encoding='utf-8-sig') as f:
    f.write('course_id;titulo;clip;seg;mmss;tipo;punto\n')
    for (_, cid, ci, t, k, pt) in rows:
        f.write(f'{cid};{titles[cid]};{ci};{t};{int(t // 60)}:{int(t % 60):02d};{k};{pt}\n')
print(f'Lista de las {len(rows)} anomalias de v27 -> anomalias_v27.csv')

with open('cursos_a_regenerar.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(courses) + '\n')
print('IDs de los cursos a regenerar -> cursos_a_regenerar.txt')
