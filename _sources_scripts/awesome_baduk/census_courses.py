#!/usr/bin/env python3
"""
Censo de TODOS los cursos del export de awesomebaduk (solo lectura, no escribe lecciones).

Para cada curso cuenta que eventos usa y ejecuta la misma conversion que
awesome_to_player.py en seco (sin escribir ficheros), para saber:
  - LISTO: solo usa lo ya validado;  REVISAR: usa algo no validado;
  - PROBLEMA: anomalias reales (jugadas ilegales, eventos desconocidos, auto-comprobacion fallida).

Uso (desde ...\\awesome_baduk, con awesome_to_player.py en la misma carpeta):
    python census_courses.py export_completo.json
    python census_courses.py export.json --compare     # ademas contrasta hipotesis con los datos
    python census_courses.py export.json --fast        # sin simulacion (muy rapido)

Salida en --out (por defecto "census"):
    census_courses.csv      una fila por curso
    census_features.json    caracteristica -> cursos, clips y EJEMPLOS con minuto (para mirar en el video)
"""
import argparse
import collections
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import awesome_to_player as A  # noqa: E402

KNOWN_OPS = {'navigate', 'move', 'forwards', 'backwards', 'triangle', 'square', 'circle',
             'label-char', 'label-num', 'add', 'variation-backspace'}

FEATURES = {
    'add': ('eventos :add (validado en video: interruptor, piedra en nodo hijo)', 'info'),
    'move_flag_true': (':move con flag=true (decidido con datos: se ignora)', 'info'),
    'add_flag_true': (':add con flag=true (validado en video)', 'info'),
    'stones_anidados': (':stones colgando de una jugada o de otro :stones (decidido con datos: reemplaza)', 'info'),
    'marca_repetida': ('misma marca repetida en el mismo nodo: se quita (validado en video)', 'info'),
    'label_num': ('etiquetas numericas: se quitan al repetir, numeracion por nodo (validado en video)', 'info'),
    'hermanos_color_distinto': ('hermanos en el mismo punto con colores distintos (gestionado)', 'info'),
    'arbol_no_alterna': ('nodos con el mismo color que su padre (gestionado)', 'info'),
    'tablero_no_19': ('tablero que no es 19x19 (gestionado)', 'info'),
    'depende_clip_anterior': ('clips cuyo primer evento no es :navigate (heredan estado)', 'info'),
    'dibujo_a_mano': ('clips con draw-events (fase 2)', 'info'),
    'clip_sin_eventos': ('clips sin eventos (solo posicion inicial)', 'info'),
    'sin_clips': ('curso sin clips', 'info'),
    'sin_board_descartado': ('curso sin arbol cuyos eventos no cuadran: se convierte como solo audio', 'info'),
    'sin_board': ('curso sin arbol: se convierte como leccion solo audio con tablero vacio', 'info'),
    'clip_sin_vimeo': ('clip cuyo video-id no esta en vimeo-ids', 'problem'),
    'op_desconocida': ('operaciones de evento desconocidas', 'problem'),
    'navigate_desconocido': (':navigate a un nodo que no existe', 'problem'),
    'jugada_ocupada': (':move sobre un punto ocupado', 'problem'),
    'color_inesperado': (':move existente con color distinto al esperado', 'problem'),
    'selfcheck_falla': ('la auto-comprobacion del conversor falla', 'problem'),
    'valor_raro': ('valores distintos de black/white en :stones o :move (ahora se ignoran, antes contaban como blanco)', 'review'),
    'excepcion': ('excepcion al procesar', 'problem'),
}
ANOMALIES = ('jugada_ocupada', 'color_inesperado', 'navigate_desconocido', 'selfcheck_falla')
FACTORS = ('tablero_no_19', 'stones_anidados', 'arbol_no_alterna', 'hermanos_color_distinto',
           'add', 'move_flag_true', 'depende_clip_anterior', 'sin_board')
CFG = {'forwards': 'first'}
DEFAULTS = {'STONES_MODE': 'replace', 'FLAG_MODE': 'ignore', 'ADD_MODE': 'child',
            'ADD_FLAG_TRUE': 'white', 'SUICIDE_MODE': 'remove', 'ADD_SEM': 'toggle'}


def load_any(path):
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace').strip()
    for cand in (text, '{' + text.rstrip(',').strip() + '}'):
        try:
            return json.loads(cand, strict=False)
        except json.JSONDecodeError:
            continue
    print(f'[aviso] no pude parsear {path}')
    return None


def find_courses(node, key, out):
    if isinstance(node, dict):
        if 'clips' in node or 'vimeo-ids' in node or 'board' in node:
            out.append((str(key).split('/')[-1], node))
        else:
            for k, v in node.items():
                find_courses(v, k, out)
    elif isinstance(node, list):
        for v in node:
            find_courses(v, key, out)


def parse_events(raw):
    if raw in (None, 'nil', ''):
        return []
    return A.edn(raw) if isinstance(raw, str) else raw


def hms(ms):
    s = int(round((ms or 0) / 1000))
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def mmss(ms):
    s = int((ms or 0) // 1000)
    return f'{s // 60}:{s % 60:02d}'


def occupant(node, pt, size):
    """Quien ocupa el punto pt al llegar a node: ('diagrama'|'add'|'jugada base'|'jugada en vivo', color)."""
    b, origin = A.Board(size), {}
    for a in A.path_of(node):
        if a.stones is not None:
            if A.STONES_MODE == 'replace':
                b.g, origin = dict(a.stones), {}
            else:
                b.g.update(a.stones)
            for p in a.stones:
                origin[p] = 'diagrama'
        for p, col in a.adds:
            b.g[p] = col
            origin[p] = 'add'
        if a.move and a.move[0] != 'pass':
            b.play(a.move[0], a.move[1])
            origin[a.move[0]] = 'jugada base' if a.base else 'jugada en vivo'
        for p in [p for p in origin if p not in b.g]:
            del origin[p]
    return origin.get(pt), b.g.get(pt)


def prev_events(events, ms, n=6):
    idx = next((i for i, (t, _) in enumerate(events) if t == ms), None)
    if idx is None:
        return []
    return [f'{mmss(t)} {ev[0]}' + (f' {list(ev[1])}' if len(ev) > 1 and isinstance(ev[1], list) else '')
            for t, ev in events[max(0, idx - n):idx + 1]]


def analyze(cid, c, fast):
    hits = collections.defaultdict(list)           # feature -> [(clip, ms, info)]

    def hit(f, ci=0, ms=None, info=None):
        hits[f].append((ci, ms, info))

    row = {'ID': cid, 'Title': re.sub(r'\s+', ' ', (c.get('title') or cid)).strip(),
           'Published': c.get('published'), 'target-group': c.get('target-group') or ''}
    errors = []
    clips = c.get('clips') or []
    vimeo = c.get('vimeo-ids') or {}
    used = {cl.get('video-id') for cl in clips}
    row.update({'Clips': len(clips), 'VimeoIds': len(vimeo),
                'VimeoSobrantes': len([u for u in vimeo if u not in used]),
                'Runtime': hms(sum((cl.get('runtime') or 0) for cl in clips))})
    if not clips:
        hit('sin_clips')

    # ---- arbol
    tree, size, byid, root = None, 19, {}, None
    bd = c.get('board') or {}
    if bd.get('variations'):
        try:
            tree = A.edn(bd['variations'])
            size = int(tree.get('board-size') or 19)
            root, byid = A.build_tree(tree)
        except Exception as e:  # noqa: BLE001
            hit('excepcion')
            errors.append(f'arbol: {type(e).__name__}')
    else:
        hit('sin_board')
        tree = {'id': 'root', 'children': []}
        root, byid = A.build_tree(tree)
    stack, nnodes, odd = ([tree] if tree else []), 0, collections.Counter()
    while stack:
        d = stack.pop()
        nnodes += 1
        for v in (d.get('stones') or {}).values():
            if str(v) not in ('black', 'white'):
                odd['stones:' + str(v)] += 1
        mv = d.get('move')
        if mv and str(mv[1]) not in ('black', 'white'):
            odd['move:' + str(mv[1])] += 1
        stack.extend(d.get('children', []))
    if odd:
        hit('valor_raro', 0, None, dict(odd))
    stones_nodes = [n for n in byid.values() if n.stones is not None]
    nested = [n for n in stones_nodes
              if any((a.move or a.stones is not None) for a in A.path_of(n)[:-1])]
    nonalt = sum(1 for n in byid.values() if n.parent and n.move and n.parent.move
                 and n.move[1] == n.parent.move[1])
    sibs = 0
    for n in byid.values():
        pts = collections.defaultdict(set)
        for ch in n.children:
            if ch.move and ch.move[0] != 'pass':
                pts[ch.move[0]].add(ch.move[1])
        sibs += sum(1 for cols in pts.values() if len(cols) > 1)
    row.update({'Nodos': nnodes, 'NodosStones': len(stones_nodes), 'StonesAnidados': len(nested),
                'Pass': sum(1 for n in byid.values() if n.move and n.move[0] == 'pass'),
                'Tablero': size, 'NoAlterna': nonalt, 'HermanosColor': sibs})
    if nested:
        hit('stones_anidados')
    if nonalt:
        hit('arbol_no_alterna')
    if sibs:
        hit('hermanos_color_distinto')
    if size != 19:
        hit('tablero_no_19')

    # ---- clips
    created, parsed = {}, []
    for ci0, cl0 in enumerate(clips, 1):
        try:
            evs = parse_events(cl0.get('events'))
        except Exception:  # noqa: BLE001
            evs = []
        parsed.append(evs)
        for _, ev in evs:
            if str(ev[0]) in ('move', 'add') and len(ev) > 3:
                created.setdefault(ev[3], ci0)
    ops = collections.Counter()
    draw_clips = no_event_clips = dep_clips = 0
    sig = []
    uid_sigs = {}
    persisted = {}
    for ci, cl in enumerate(clips, 1):
        events = parsed[ci - 1]
        if cl.get('video-id') not in vimeo:
            hit('clip_sin_vimeo', ci)
        if cl.get('draw-events') not in (None, 'nil', ''):
            draw_clips += 1
            hit('dibujo_a_mano', ci)
        if not events:
            no_event_clips += 1
            hit('clip_sin_eventos', ci)
        elif str(events[0][1][0]) != 'navigate':
            dep_clips += 1
            hit('depende_clip_anterior', ci)
        seen_unknown = False
        for ms, ev in events:
            op = str(ev[0])
            ops[op] += 1
            if op not in KNOWN_OPS and not seen_unknown:
                seen_unknown = True
                hit('op_desconocida', ci, ms, op)
            if op == 'move' and ev[2]:
                hit('move_flag_true', ci, ms, tuple(ev[1]))
            if op == 'add':
                hit('add', ci, ms, tuple(ev[1]))
                if ev[2]:
                    hit('add_flag_true', ci, ms, tuple(ev[1]))
            if op == 'label-num':
                hit('label_num', ci, ms, tuple(ev[1]))
        if fast or root is None:
            continue
        A.DIAG = []
        try:                                   # misma conversion que awesome_to_player, en seco
            r2, b2 = A.build_tree(tree)
            start = A.resolve(r2, b2, sig)
            sgf, n_nodes = A.emit_sgf(r2, row['Title'], size)
            warn = collections.Counter()
            out, end, expected = A.translate(events, r2, b2, start, n_nodes, CFG['forwards'], warn, size, uid_sigs, persisted)
            probs = A.selfcheck(sgf, out, expected, size)
            sig = A.signature(end)
            if probs and 'sin_board' not in hits:
                hit('selfcheck_falla', ci, None, probs[0])
                errors.append(f'selfcheck clip {ci}: {probs[0]}')
            for e in out:
                if 'removeProp' in e:
                    hit('marca_repetida', ci, int(e['time'] * 1000), e['removeProp'][1])
            boardless = 'sin_board' in hits
            for kind, ms, info in A.DIAG:
                info = dict(info)
                if boardless:
                    hit('sin_board_descartado', ci, ms, {'tipo': kind})
                    continue
                node = info.pop('node', None)
                if kind == 'jugada_ocupada' and node is not None:
                    who, col = occupant(node, info['pt'], size)
                    info.update({'ocupante': who, 'color_ocupante': col,
                                 'nodo': 'base' if node.base else 'en vivo',
                                 'prof': len(A.path_of(node)) - 1})
                if kind == 'color_inesperado' and node is not None:
                    info['nodo'] = 'base' if node.base else 'en vivo'
                if kind == 'navigate_desconocido':
                    nid = info.get('id')
                    cc = created.get(nid)
                    info['causa'] = ('curso sin arbol' if 'sin_board' in hits else
                                     f'creado en clip {cc}' + (' (este)' if cc == ci else ' (anterior)' if cc and cc < ci else ' (posterior)')
                                     if cc else 'id inexistente (nodo borrado del arbol?)')
                info['previos'] = prev_events(events, ms)
                hit(kind, ci, ms, info)
        except Exception as e:  # noqa: BLE001
            hit('excepcion', ci)
            errors.append(f'clip {ci}: {type(e).__name__}: {str(e)[:60]}')
            sig = []
        finally:
            A.DIAG = None

    for k in ('move', 'forwards', 'backwards', 'navigate', 'triangle', 'square', 'circle',
              'label-char', 'label-num', 'add', 'variation-backspace'):
        row['ev_' + k] = ops.get(k, 0)
    row.update({'ClipsDibujo': draw_clips, 'ClipsSinEventos': no_event_clips,
                'ClipsHeredanEstado': dep_clips})

    problems = [f for f in hits if FEATURES[f][1] == 'problem']
    review = [f for f in hits if FEATURES[f][1] == 'review']
    if problems or errors:
        row['Estado'] = 'PROBLEMA'
        row['Detalle'] = '; '.join(sorted(problems) + errors[:2])
    elif review:
        row['Estado'] = 'REVISAR'
        row['Detalle'] = '; '.join(sorted(review))
    elif not clips:
        row['Estado'] = 'SIN CLIPS'
        row['Detalle'] = ''
    else:
        row['Estado'] = 'LISTO'
        row['Detalle'] = ''
    return row, hits


def measure(subset, mods, forwards='first'):
    """Re-ejecuta la simulacion con ciertos interruptores y cuenta anomalias (eventos)."""
    for k, v in mods.items():
        setattr(A, k, v)
    CFG['forwards'] = forwards
    tot = collections.Counter()
    try:
        for cid, c in subset:
            _, h = analyze(cid, c, False)
            for f in ANOMALIES:
                tot[f] += len({x[0] for x in h.get(f, [])})
    finally:
        for k, v in DEFAULTS.items():
            setattr(A, k, v)
        CFG['forwards'] = 'first'
    return tot


def compare(results):
    """Contrasta hipotesis con los datos (menos anomalias = mas probable)."""
    print('\n==== COMPARACION DE HIPOTESIS (clips con anomalia; menos = mas probable) ====')
    def show(title, subset, variants):
        print(f'{title} ({len(subset)} cursos):')
        for label, mods, fw in variants:
            tot = measure(subset, mods, fw)
            print(f'   {label:34s}', '  '.join(f'{f}={tot[f]}' for f in ANOMALIES))
    pairs = [(cid, c) for cid, c, _, _ in results]
    stones = [(cid, c) for cid, c, r, _ in results if r['NodosStones'] > 0]
    flag = [(cid, c) for cid, c, _, h in results if 'move_flag_true' in h]
    addc = [(cid, c) for cid, c, _, h in results if 'add' in h]
    anom = [(cid, c) for cid, c, _, h in results if any(f in h for f in ANOMALIES)]
    show(':stones', stones, [('reemplaza la posicion', {}, 'first'),
                             ('se suma a la existente', {'STONES_MODE': 'add'}, 'first')])
    show('flag=true en :move', flag, [('se ignora', {}, 'first'),
                                      ('invierte el color', {'FLAG_MODE': 'invert'}, 'first')])
    show(':add', addc, [('hijo, interruptor (defecto)', {}, 'first'),
                        ('hijo, siempre pone', {'ADD_SEM': 'place'}, 'first'),
                        ('en el nodo, interruptor', {'ADD_MODE': 'inplace'}, 'first'),
                        ('en el nodo, siempre pone', {'ADD_MODE': 'inplace', 'ADD_SEM': 'place'}, 'first'),
                        ('hijo, interruptor, true=negra', {'ADD_FLAG_TRUE': 'black'}, 'first'),
                        ('en el nodo, interruptor, true=negra', {'ADD_MODE': 'inplace', 'ADD_FLAG_TRUE': 'black'}, 'first')])
    show(':forwards con varios hijos', anom, [('primer hijo', {}, 'first'),
                                              ('ultimo visitado', {}, 'last')])
    show('jugada suicida', anom, [('se quita el grupo', {}, 'first'),
                                  ('se deja la piedra', {'SUICIDE_MODE': 'keep'}, 'first')])


def diagnose(results, examples=8):
    """Resumen agregado de causas (solo la PRIMERA anomalia de cada clip: el resto son cascadas)."""
    def first_per_clip(kind):
        out = []
        for cid, _, row, hits in results:
            seen = set()
            for ci, ms, info in hits.get(kind, []):
                if ci in seen:
                    continue
                seen.add(ci)
                out.append((row['Title'], ci, ms, info if isinstance(info, dict) else {'msg': info},
                            'add' in hits))
        return out
    print('\n==== DIAGNOSTICO DE CAUSAS (primera anomalia por clip) ====')
    occ = first_per_clip('jugada_ocupada')
    if occ:
        print(f'jugada_ocupada: {len(occ)} clips')
        print('   ocupante del punto :', dict(collections.Counter(i.get('ocupante') for *_, i, _a in occ)))
        print('   nodo actual        :', dict(collections.Counter(i.get('nodo') for *_, i, _a in occ)))
        print('   con :add en el curso:', dict(collections.Counter(a for *_, a in occ)))
        print('   mismo color que el ocupante:', dict(collections.Counter(
            i.get('color') == i.get('color_ocupante') for *_, i, _a in occ)))
        cn = {1: 'negro', -1: 'blanco', None: '?'}
        print(f'   Ejemplos (los {min(examples, len(occ))} primeros; "previos" = eventos justo antes):')
        for t, ci, ms, i, _a in occ[:examples]:
            print(f'    - {t[:38]} clip {ci} @ {mmss(ms)}: juega {cn.get(i.get("color"))} en {i.get("pt")}, '
                  f'ocupa {i.get("ocupante")} ({cn.get(i.get("color_ocupante"))}), nodo {i.get("nodo")} prof {i.get("prof")}')
            print('        previos: ' + ' | '.join(i.get('previos', [])))
    nav = first_per_clip('navigate_desconocido')
    if nav:
        causa = collections.Counter(re.sub(r'clip \d+', 'clip N', str(i.get('causa'))) for *_, i, _a in nav)
        print(f'navigate_desconocido: {len(nav)} clips ->', dict(causa))
    sc = first_per_clip('selfcheck_falla')
    if sc:
        print(f'selfcheck_falla: {len(sc)} clips; primeros mensajes:')
        for t, ci, _, i, _a in sc[:6]:
            print(f'   {t[:34]} clip {ci}: {i.get("msg")}')
    col = first_per_clip('color_inesperado')
    if col:
        print(f'color_inesperado: {len(col)} clips:')
        for t, ci, ms, i, _a in col[:6]:
            print(f'   {t[:34]} clip {ci} @ {mmss(ms)}: {i.get("pt")} esperado {i.get("esperado")} hijo {i.get("hijo")} flag {i.get("flag")}')
    vr = collections.Counter()
    ncv = 0
    for cid, _, row, hits in results:
        if hits.get('valor_raro'):
            ncv += 1
            for _, _, info in hits['valor_raro']:
                vr.update(info if isinstance(info, dict) else {})
    if vr:
        print(f'valor_raro: {ncv} cursos; valores distintos de black/white (se ignoran):', dict(vr))
    sbd = first_per_clip('sin_board_descartado')
    if sbd:
        print(f'cursos sin arbol con eventos que no cuadran (pasan a solo audio): {len(sbd)} clips')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inputs', nargs='+', help='JSON(s) del export o carpeta')
    ap.add_argument('--out', default='census')
    ap.add_argument('--fast', action='store_true', help='solo recuento, sin simular la conversion')
    ap.add_argument('--examples', type=int, default=8, help='casos detallados de jugada_ocupada a imprimir')
    ap.add_argument('--compare', action='store_true',
                    help='contrasta hipotesis (:stones, flag) con los datos; tarda mas')
    ap.add_argument('--delimiter', default=',', help='separador del CSV (";" para Excel en espanol)')
    args = ap.parse_args()

    files = []
    for p in map(Path, args.inputs):
        files += sorted(p.rglob('*.json')) if p.is_dir() else [p]
    courses = []
    for f in files:
        data = load_any(f)
        if data is not None:
            before = len(courses)
            find_courses(data, f.stem, courses)
            print(f'{f.name}: {len(courses) - before} curso(s)')
    if not courses:
        raise SystemExit('No se encontro ningun curso.')

    results, t0 = [], time.time()
    for i, (cid, c) in enumerate(courses, 1):
        row, hits = analyze(cid, c, args.fast)
        results.append((cid, c, row, hits))
        if i % 25 == 0 or i == len(courses):
            el = time.time() - t0
            print(f'  {i}/{len(courses)} cursos  ({el:.0f}s, quedan ~{el / i * (len(courses) - i):.0f}s)')

    rows = [r for _, _, r, _ in results]
    feat = collections.defaultdict(list)
    course_feats = collections.defaultdict(set)
    for cid, _, row, hits in results:
        for f, lst in hits.items():
            course_feats[cid].add(f)
            feat[f].append({
                'course_id': cid, 'title': row['Title'], 'clips': sorted({x[0] for x in lst}),
                'ejemplos': [{'clip': x[0], 'minuto': mmss(x[1]) if x[1] is not None else None,
                              'info': x[2]} for x in lst[:3]]})

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys())
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(out / 'census_courses.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=args.delimiter, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    (out / 'census_features.json').write_text(json.dumps(
        {f: {'descripcion': FEATURES[f][0], 'categoria': FEATURES[f][1], 'cursos': v}
         for f, v in feat.items()}, indent=1, ensure_ascii=False, default=str), encoding='utf-8')

    anomalies = {}
    for f in ANOMALIES:
        lst, per_course = [], collections.Counter()
        for cid, _, row, hits in results:
            for ci, ms, info in hits.get(f, []):
                if per_course[(f, cid)] >= 3 or len(lst) >= 80:
                    continue
                per_course[(f, cid)] += 1
                lst.append({'curso': row['Title'], 'id': cid, 'clip': ci,
                            'minuto': mmss(ms) if ms is not None else None, 'info': info})
        anomalies[f] = lst
    (out / 'anomalies.json').write_text(json.dumps(anomalies, indent=1, ensure_ascii=False, default=str),
                                        encoding='utf-8')

    est = collections.Counter(r['Estado'] for r in rows)
    print('\n==== RESUMEN ====')
    print(f'Cursos: {len(rows)}   Clips: {sum(r["Clips"] for r in rows)}   '
          f'Vimeo sobrantes (no usados por clips): {sum(r["VimeoSobrantes"] for r in rows)}')
    for k in ('LISTO', 'REVISAR', 'PROBLEMA', 'SIN CLIPS'):
        nclips = sum(r['Clips'] for r in rows if r['Estado'] == k)
        print(f'  {k:10s} {est.get(k, 0):5d} cursos   ({nclips} clips)')
    print('\nCaracteristica (cursos afectados / clips)  -> ejemplo con minuto')
    order = {'problem': 0, 'review': 1, 'info': 2}
    for f in sorted(feat, key=lambda x: (order[FEATURES[x][1]], -len(feat[x]))):
        v = feat[f]
        nclips = sum(len(x['clips']) for x in v)
        ex = next((x for x in v if x['ejemplos'] and x['ejemplos'][0]['minuto']), v[0])
        e0 = ex['ejemplos'][0] if ex['ejemplos'] else {}
        tag = f"{ex['title'][:30]}" + (f" clip {e0['clip']} @ {e0['minuto']}" if e0.get('minuto') else '')
        print(f'  [{FEATURES[f][1]:7s}] {f:24s} {len(v):4d} / {nclips:<5d} -> {tag}')

    present = [f for f in ANOMALIES if f in feat]
    if present:
        print('\nAnomalias: de los cursos afectados, cuantos tienen cada factor (pistas de la causa)')
        print('   ' + ' ' * 22 + ''.join(f'{x[:10]:>12s}' for x in FACTORS) + '   ninguno')
        for f in present:
            ids = {x['course_id'] for x in feat[f]}
            counts = [len([i for i in ids if g in course_feats[i]]) for g in FACTORS]
            none = len([i for i in ids if not any(g in course_feats[i] for g in FACTORS)])
            print(f'   {f:22s}' + ''.join(f'{n:12d}' for n in counts) + f'   {none:7d}   (de {len(ids)})')

    diagnose(results, args.examples)
    if args.compare and not args.fast:
        compare(results)
    print(f'\nCSV: {out / "census_courses.csv"}\nDetalle y ejemplos: {out / "census_features.json"}'
          f'\nAnomalias con contexto (sube este fichero): {out / "anomalies.json"}')


if __name__ == '__main__':
    main()
