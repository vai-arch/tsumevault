#!/usr/bin/env python3
"""
Inspecciona un clip: dice que eventos hay cerca de un minuto y que tablero DEBERIA verse
segun el conversor, para compararlo con el video original.

Uso (desde ...\\awesome_baduk, con awesome_to_player.py en la misma carpeta):
    python inspect_clip.py lessons.json --course "How to Escape" --clip 2 --at 0:36
    python inspect_clip.py lessons.json --course "Which way?" --clip 3 --at 1:10 --window 20
    python inspect_clip.py lessons.json --course "Hane VS Nobi" --clip 1 --at 0:00 --odd

Muestra: lessonId y video de Vimeo, los eventos crudos de la ventana, lo que emite el
conversor, y el tablero (X negro, O blanco, . vacio; junto a cada punto la marca:
T triangulo, S cuadrado, C circulo, M aspa, o el texto de la etiqueta) en el minuto
pedido y al final de la ventana. Con las mismas opciones del conversor puedes probar
hipotesis, p. ej. --add-flag-true black --mark-repeat keep --label-scope clip.
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import awesome_to_player as A  # noqa: E402

LETTERS = 'ABCDEFGHJKLMNOPQRST'


def parse_t(s):
    parts = [float(x) for x in str(s).split(':')]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def mmss(sec):
    return f'{int(sec // 60)}:{sec % 60:04.1f}'


def gocoord(pt, size):
    x, y = pt
    return f'{LETTERS[x]}{size - y}' if 0 <= x < len(LETTERS) else f'({x},{y})'


def decode_prop(prop, size):
    m = re.match(r'^([A-Z]+)\[([a-z]{0,2})(?::(.*))?\]$', prop)
    if not m:
        return prop
    k, c, t = m.groups()
    pt = (ord(c[0]) - 97, ord(c[1]) - 97) if len(c) == 2 else None
    where = f'{pt} {gocoord(pt, size)}' if pt else 'pasa'
    names = {'B': 'jugada negra', 'W': 'jugada blanca', 'AB': 'piedra negra (setup)',
             'AW': 'piedra blanca (setup)', 'AE': 'quita piedra', 'TR': 'triangulo',
             'SQ': 'cuadrado', 'CR': 'circulo', 'MA': 'aspa'}
    if k == 'LB':
        return f"etiqueta '{t}' en {where}"
    return f'{names.get(k, k)} en {where}'


def raw_event_text(ev, size):
    op = str(ev[0])
    if op in ('move', 'add'):
        pt = tuple(ev[1])
        return f'{op} {pt} {gocoord(pt, size)} flag={ev[2]}'
    if op in ('triangle', 'square', 'circle', 'label-char', 'label-num'):
        pt = tuple(ev[1])
        return f'{op} {pt} {gocoord(pt, size)}'
    if op == 'navigate':
        return f'navigate {str(ev[1])[:8]}'
    return op


def json_event_text(e, size):
    parts = []
    if 'addChild' in e:
        parts.append(f'crea nodo {e["addChild"][1]} (hijo de {e["addChild"][0]})')
    if 'addProp' in e:
        parts.append(f'{decode_prop(e["addProp"][1], size)} [nodo {e["addProp"][0]}]')
    if 'removeProp' in e:
        parts.append(f'QUITA {decode_prop(e["removeProp"][1], size)} [nodo {e["removeProp"][0]}]')
    if 'activate' in e:
        parts.append(f'muestra nodo {e["activate"]}')
    return '; '.join(parts)


MARKUP = ('LB', 'TR', 'SQ', 'CR', 'MA')


def nodes_by_nn(root):
    nodes, stack = {}, [root]
    while stack:
        n = stack.pop()
        if n.nn is not None:
            nodes[n.nn] = n
        stack.extend(n.children)
    return nodes


def update_persisted(persisted, out, root):
    """Aplica las marcas/etiquetas de un clip sobre las acumuladas, indexadas por firma de nodo."""
    nodes = nodes_by_nn(root)
    for e in out:
        for key in ('addProp', 'removeProp'):
            if key not in e:
                continue
            nn, prop = e[key]
            if prop[:2] not in MARKUP or nn not in nodes:
                continue
            sg = tuple(A.signature(nodes[nn]))
            lst = persisted.setdefault(sg, [])
            if key == 'addProp':
                lst.append(prop)
            else:
                head = prop.split(':')[0] if prop.startswith('LB') else prop
                lst[:] = [x for x in lst if not (x.split(':')[0] if x.startswith('LB') else x) == head]


def render(out, root, size, T):
    nodes = {}
    stack = [root]
    while stack:
        n = stack.pop()
        if n.nn is not None:
            nodes[n.nn] = n
        stack.extend(n.children)
    active, props = 0, collections.defaultdict(list)
    for e in out:
        if e['time'] > T:
            break
        if 'addProp' in e:
            props[e['addProp'][0]].append(e['addProp'][1])
        if 'removeProp' in e and e['removeProp'][1] in props[e['removeProp'][0]]:
            props[e['removeProp'][0]].remove(e['removeProp'][1])
        if 'activate' in e:
            active = e['activate']
    node = nodes.get(active)
    if node is None:
        return f'(nodo {active} no encontrado)'
    g = A.position(node, size).g
    marks = {}
    for pt, txt in node.labels.items():
        marks[pt] = txt[:1]
    for pr in props[active]:
        m = re.match(r'^(TR|SQ|CR|MA|LB)\[([a-z]{2})(?::(.*))?\]$', pr)
        if m:
            k, c, t = m.groups()
            marks[(ord(c[0]) - 97, ord(c[1]) - 97)] = {'TR': 'T', 'SQ': 'S', 'CR': 'C', 'MA': 'M'}.get(k, (t or '?')[:1])
    path = [a for a in A.path_of(node) if a.move]
    last = ', '.join(
        f"{'negro' if a.move[1] == A.B else 'blanco'} {gocoord(a.move[0], size) if a.move[0] != 'pass' else 'pasa'}"
        for a in path[-5:])
    lines = [f'   nodo activo {active}; ultimas jugadas del camino: {last or "(ninguna)"}']
    lines.append('        ' + ''.join(f'{x:<3d}' for x in range(size)) + '  <- x')
    lines.append('        ' + ''.join(f'{LETTERS[x]:<3s}' for x in range(size)) + '  (letra Go)')
    for y in range(size):
        row = ''
        for x in range(size):
            st = g.get((x, y))
            row += ('X' if st == A.B else 'O' if st == A.W else '.') + marks.get((x, y), ' ') + ' '
        lines.append(f'   y={y:<2d}{size - y:>2d} ' + row)
    lines.append('   (izq: y = indice de fila; segundo numero = fila Go contando desde abajo)')
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('course_json')
    ap.add_argument('--course', required=True, help='parte del titulo o id del curso')
    ap.add_argument('--clip', type=int, default=1)
    ap.add_argument('--at', default='0:00', help='minuto, p. ej. 6:14 o 374')
    ap.add_argument('--window', type=float, default=12, help='segundos tras el minuto que se muestran')
    ap.add_argument('--before', type=float, default=4, help='segundos antes del minuto')
    ap.add_argument('--out', default='player_test/player', help='carpeta donde esta lesson_ids.json')
    ap.add_argument('--odd', action='store_true', help='listar puntos con valores de color raros en el arbol')
    ap.add_argument('--stones-mode', choices=['replace', 'add'], default='replace')
    ap.add_argument('--flag-mode', choices=['invert', 'ignore'], default='ignore')
    ap.add_argument('--add-mode', choices=['child', 'inplace'], default='child')
    ap.add_argument('--add-flag-true', choices=['white', 'black'], default='white')
    ap.add_argument('--add-sem', choices=['place', 'toggle'], default='toggle')
    ap.add_argument('--mark-repeat', choices=['toggle', 'keep'], default='toggle')
    ap.add_argument('--label-scope', choices=['node', 'clip'], default='node')
    args = ap.parse_args()
    A.STONES_MODE, A.FLAG_MODE, A.ADD_MODE = args.stones_mode, args.flag_mode, args.add_mode
    A.ADD_FLAG_TRUE, A.ADD_SEM = args.add_flag_true, args.add_sem
    A.MARK_REPEAT, A.LABEL_SCOPE = args.mark_repeat, args.label_scope

    courses = A.load_course(args.course_json)
    q = args.course.lower()
    match = [(cid, c) for cid, c in courses
             if q in (c.get('title') or '').lower() or q == cid.lower()]
    if not match:
        raise SystemExit(f'Ningun curso coincide con "{args.course}".')
    if len(match) > 1:
        print('Varios cursos coinciden, afina --course:')
        for cid, c in match:
            print(f'  {cid}  {c.get("title")}')
        return
    cid, course = match[0]
    title = (course.get('title') or cid).strip()
    bd = course.get('board') or {}
    boardless = not bd.get('variations')
    tree = A.edn(bd['variations']) if not boardless else {'id': 'root', 'children': []}
    size = int(tree.get('board-size') or 19)
    uuid2vid = {u: p.split('/')[-1] for u, p in (course.get('vimeo-ids') or {}).items()}
    clips = course.get('clips') or []
    if not 1 <= args.clip <= len(clips):
        raise SystemExit(f'El curso tiene {len(clips)} clips.')

    sig, uid_sigs, pers = [], {}, {}
    persisted_before = {}
    for ci, clip in enumerate(clips, 1):
        raw = clip.get('events')
        events = A.edn(raw) if isinstance(raw, str) and raw != 'nil' else []
        root, byid = A.build_tree(tree)
        start = A.resolve(root, byid, sig)
        sgf, n_nodes = A.emit_sgf(root, title, size)
        warn = collections.Counter()
        if ci == args.clip:
            persisted_before = {k: {kk: list(vv) for kk, vv in v.items()} for k, v in pers.items()}
        out, end, expected = A.translate(events, root, byid, start, n_nodes, 'first', warn, size, uid_sigs, pers)
        if boardless and any(k in warn for k in ('navigate a nodo desconocido', 'move sobre punto ocupado')):
            out, end = [{'time': 0, 'activate': 0}], root
        sig = A.signature(end)
        if ci == args.clip:
            start_nn = out[0].get('activate', 0)
            break

    lid = None
    ids_path = Path(args.out) / 'lesson_ids.json'
    if ids_path.exists():
        lid = json.loads(ids_path.read_text(encoding='utf-8')).get(f'{cid}/{clip["video-id"]}')
    T = parse_t(args.at)
    print(f'CURSO  : {title}   (id {cid}, tablero {size}x{size})')
    print(f'CLIP   : {args.clip} de {len(clips)}   duracion {mmss((clip.get("runtime") or 0) / 1000)}')
    print(f'PLAYER : lessonId {lid if lid is not None else "(no encontrado: ejecuta antes el conversor)"}'
          f'   Vimeo https://vimeo.com/{uuid2vid.get(clip["video-id"], "?")}')
    print(f'MINUTO : {mmss(T)}   ventana [{mmss(max(0, T - args.before))} , {mmss(T + args.window)}]')
    if clip.get('draw-events') not in (None, 'nil', ''):
        print('AVISO  : este clip tiene dibujo a mano (el player no lo muestra todavia)')
    if warn:
        print('AVISOS del conversor en este clip:', dict(warn))

    lo, hi = T - args.before, T + args.window
    print('\n--- EVENTOS CRUDOS en la ventana (tal como los grabo la app) ---')
    shown = 0
    for ms, ev in events:
        if lo <= ms / 1000 <= hi:
            print(f'  {mmss(ms / 1000):>8s}  {raw_event_text(ev, size)}')
            shown += 1
            if shown >= 60:
                print('  ... (recortado)')
                break
    if not shown:
        print('  (ninguno)')
    print('\n--- LO QUE EMITE EL CONVERSOR en la ventana ---')
    shown = 0
    for e in out:
        if lo <= e['time'] <= hi:
            print(f'  {mmss(e["time"]):>8s}  {json_event_text(e, size)}')
            shown += 1
            if shown >= 60:
                print('  ... (recortado)')
                break
    if not shown:
        print('  (ninguno)')
    nmap = nodes_by_nn(root)
    snode = nmap.get(start_nn)
    print('\n--- ETIQUETAS/MARCAS EN EL NODO QUE SE MUESTRA A t=0 (posibles origenes) ---')
    if snode is None:
        print('  (nodo inicial no encontrado)')
    else:
        pl = [a for a in A.path_of(snode) if a.move]
        print(f'  nodo inicial: {"del arbol" if snode.base else "creado en vivo"}, profundidad {len(A.path_of(snode)) - 1}, '
              f'ultima jugada: {gocoord(pl[-1].move[0], size) if pl and pl[-1].move[0] != "pass" else "ninguna"}')
        own = {gocoord(p, size): t for p, t in snode.labels.items()}
        par = {gocoord(p, size): t for p, t in snode.parent.labels.items()} if snode.parent else {}
        ent = persisted_before.get(tuple(A.signature(snode))) or {}
        inh = (['+' + x for x in ent.get('add', [])] + ['-' + x for x in ent.get('remove', [])])
        print(f'  1) etiquetas del ARBOL en este nodo            : {own or "ninguna"}')
        print(f'  2) etiquetas del arbol en su nodo PADRE        : {par or "ninguna"}   '
              '(solo se verian si el nodo mostrado fuera el padre)')
        print(f'  3) marcas de eventos de CLIPS ANTERIORES aqui   : {inh or "ninguna"}   '
              '(se reaplican a t=0: las marcas persisten entre clips; +añade, -quita)')
        first = [raw_event_text(ev, size) for ms, ev in events if ms <= 5000
                 and str(ev[0]) in ('label-char', 'label-num', 'triangle', 'square', 'circle')]
        print(f'  4) eventos de marcas/etiquetas en los 5 primeros s del clip: {first or "ninguno"}')
    print(f'\n--- TABLERO ESPERADO a {mmss(T)} ---\n{render(out, root, size, T)}')
    print(f'\n--- TABLERO ESPERADO a {mmss(hi)} (final de la ventana) ---\n{render(out, root, size, hi)}')

    if args.odd:
        print('\n--- PUNTOS CON VALOR DE COLOR RARO en el arbol (se ignoran) ---')
        found, stack = [], [tree]
        while stack:
            d = stack.pop()
            for k, v in (d.get('stones') or {}).items():
                if str(v) not in ('black', 'white'):
                    found.append((str(d.get('id'))[:8], 'stones', tuple(k), str(v)))
            mv = d.get('move')
            if mv and str(mv[1]) not in ('black', 'white'):
                found.append((str(d.get('id'))[:8], 'move', mv[0], str(mv[1])))
            stack.extend(d.get('children', []))
        for nid, kind, pt, v in found[:25]:
            pt = tuple(pt) if not isinstance(pt, str) else pt
            print(f'  nodo {nid}: {kind} {pt} {gocoord(pt, size) if isinstance(pt, tuple) else ""} = :{v}')
        if not found:
            print('  (ninguno en este curso)')


if __name__ == '__main__':
    main()
