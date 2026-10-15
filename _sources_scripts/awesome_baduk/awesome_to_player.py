#!/usr/bin/env python3
"""
Traduce los cursos de awesomebaduk (arbol EDN + eventos por clip) al formato
que ya entiende player.html: por cada clip  {id}.sgf + {id}.json (+ {id}.ogg)
y una fila para all_lessons.json.

Uso (desde ...\\awesome_baduk):
    python awesome_to_player.py punishment.json --out player_out ^
        --audio-root out\\cursos_final --convert-audio

Salida:
    <out>/lessons/<type>/<collection>/<Clip NN>/<id>.sgf|.json|.ogg
    <out>/all_lessons.new.json     filas nuevas (NO toca tu all_lessons.json)
    <out>/lesson_ids.json          registro curso/clip -> lessonId (estable)
    <out>/convert_report.json      avisos por clip

Hipotesis validadas con "Punishment": continuidad entre clips, alternancia de
color de los :move en vivo, legalidad.  NO validadas aun (se avisan en el
informe): :stones como reemplazo total, flag de :move/:add, marcas (toggle),
etiquetas auto, :variation-backspace, :forwards con varios hijos.
"""
import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

sys.setrecursionlimit(20000)
VERSION = 'v27 - :navigate nil = ir a la raiz (tablero vacio sin arbol); v26: :add auto2; v25: :add quita cualquier piedra; v24: color por alternancia; v23: flag=true = blanca'
B, W = 1, -1
FLAG_MODE = 'white'         # flag=true en :move: 'white' (piedra blanca, validado en video, como :add) | 'ignore' | 'invert'
ADD_MODE = 'auto2'          # :add -> 'auto2' (v26): en el nodo si no tiene jugada, si no nodo hijo; retroceder salta los retoques | 'auto' | 'child' (v22-v25) | 'inplace'
ADD_FLAG_TRUE = 'white'     # color de :add con flag=true ('white' | 'black'); con flag=false el otro
MARKS_PERSIST = 'clip'      # marcas y etiquetas de un nodo se conservan al pasar al clip siguiente ('clip') o no ('none')
MARK_REPEAT = 'toggle'      # marca repetida en el mismo nodo: 'toggle' (la quita) | 'keep' (se queda)
LABEL_REPEAT = 'toggle'      # etiqueta sobre un punto ya etiquetado: 'toggle' (la quita) | 'keep' (se superpone)
LABEL_SCOPE = 'node'        # contador de etiquetas A,B,C / 1,2,3: 'node' (reinicia en cada nodo) | 'clip' (continua en todo el clip)
ADD_SEM = 'remove'         # :add 'remove': si hay CUALQUIER piedra la quita, si no pone (validado: reproduce la captura) | 'toggle': solo quita si es del mismo color (v22-v24) | 'place': siempre pone
SUICIDE_MODE = 'remove'     # jugada suicida: 'remove' quita el grupo | 'keep' deja la piedra
NAV_NIL = 'root'            # :navigate nil -> 'root' (v27: va a la raiz, validado con captura) | 'ignore' (v22-v26: nodo desconocido)
DIAG = None                 # si es una lista, translate() anota ahi las anomalias (para el censo)


def _diag(kind, ms, **info):
    if DIAG is not None:
        DIAG.append((kind, ms, info))


STONES_MODE = 'replace'   # 'replace': :stones reemplaza la posicion | 'add': se suma a la existente

# ------------------------------------------------------------------ EDN
class K(str):
    __slots__ = ()


_TOK = re.compile(r'\s*(?:,)*\s*(\[|\]|\{|\}|"(?:[^"\\]|\\.)*"|:[^\s\[\]\{\}",]+|[^\s\[\]\{\}",]+)')


def edn(s):
    toks = [m.group(1) for m in _TOK.finditer(s)]
    pos = 0

    def val():
        nonlocal pos
        t = toks[pos]
        pos += 1
        if t == '[':
            out = []
            while toks[pos] != ']':
                out.append(val())
            pos += 1
            return out
        if t == '{':
            out = {}
            while toks[pos] != '}':
                k = val()
                v = val()
                out[tuple(k) if isinstance(k, list) else k] = v
            pos += 1
            return out
        if t[0] == '"':
            return json.loads(t)
        if t[0] == ':':
            return K(t[1:])
        if t == 'nil':
            return None
        if t == 'true':
            return True
        if t == 'false':
            return False
        try:
            return int(t)
        except ValueError:
            try:
                return float(t)
            except ValueError:
                return t
    return val()


# ----------------------------------------------------------------- Go board
class Board:
    def __init__(self, n=19):
        self.n = n
        self.g = {}

    def nb(self, p):
        x, y = p
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if 0 <= q[0] < self.n and 0 <= q[1] < self.n:
                yield q

    def group(self, p):
        c = self.g[p]
        seen, st, lib = {p}, [p], set()
        while st:
            a = st.pop()
            for q in self.nb(a):
                if q not in self.g:
                    lib.add(q)
                elif self.g[q] == c and q not in seen:
                    seen.add(q)
                    st.append(q)
        return seen, lib

    def play(self, p, c):
        if p in self.g:
            return 'occupied'
        self.g[p] = c
        for q in self.nb(p):
            if self.g.get(q) == -c:
                grp, lib = self.group(q)
                if not lib:
                    for r in grp:
                        del self.g[r]
        grp, lib = self.group(p)
        if not lib:
            if SUICIDE_MODE == 'remove':
                for r in grp:
                    del self.g[r]
            return 'suicide'
        return 'ok'


# --------------------------------------------------------------------- tree
class Node:
    def __init__(self, id=None, move=None, parent=None, base=False):
        self.id = id
        self.move = move          # ((x,y)|'pass', color) o None
        self.stones = None        # {(x,y): color}  -> REEMPLAZO total (hipotesis)
        self.adds = []            # [((x,y), color)] -> setup aditivo (:add)
        self.labels = {}          # {(x,y): "A"}
        self.comment = None
        self.children = []
        self.parent = parent
        self.base = base
        self.nn = None


ODD_VALUES = collections.Counter()   # valores de color que no son black/white (se ignoran)


def build_tree(tree):
    byid = {}

    def mk(d, parent):
        n = Node(d.get('id'), None, parent, True)
        mv = d.get('move')
        if mv:
            pos, col = mv
            if col in ('black', 'white'):
                n.move = ('pass' if isinstance(pos, str) else tuple(pos), B if col == 'black' else W)
            else:
                ODD_VALUES['move:' + str(col)] += 1      # color desconocido: no es una jugada
        if d.get('stones') is not None:
            n.stones = {}
            for k, v in d['stones'].items():
                if v in ('black', 'white'):
                    n.stones[tuple(k)] = B if v == 'black' else W
                else:
                    ODD_VALUES['stones:' + str(v)] += 1  # p. ej. un marcador: no es una piedra
        if d.get('labels'):
            n.labels = {tuple(k): v for k, v in d['labels'].items()}
        n.comment = d.get('comment')
        byid[n.id] = n
        for ch in d.get('children', []):
            n.children.append(mk(ch, n))
        return n
    return mk(tree, None), byid


def path_of(n):
    p = []
    while n:
        p.append(n)
        n = n.parent
    return p[::-1]


def position(n, size=19):
    """Posicion tras recorrer root->n (reglas del player: setup, luego jugada)."""
    b = Board(size)
    for a in path_of(n):
        if a.stones is not None:
            if STONES_MODE == 'replace':
                b.g = dict(a.stones)
            else:
                b.g.update(a.stones)
        for p, c in a.adds:
            if c == 0:
                b.g.pop(p, None)
            else:
                b.g[p] = c
        if a.move and a.move[0] != 'pass':
            b.play(a.move[0], a.move[1])
    return b


def last_color(n):
    for a in reversed(path_of(n)):
        if a.move:
            return a.move[1]
        if a.stones is not None and STONES_MODE == 'replace':
            return None            # un diagrama nuevo reinicia a quien le toca
    return None


def next_color(n):
    """Color que juega en n: el de sus hijos si los hay (los hermanos comparten color),
    y si no, alternando respecto a la ultima jugada del camino (negro por defecto)."""
    kids = collections.Counter(c.move[1] for c in n.children if c.move)
    if kids:
        return kids.most_common(1)[0][0]
    lc = last_color(n)
    return B if lc is None else -lc


# ---------------------------------------------------------------------- SGF
def co(p):
    return chr(97 + p[0]) + chr(97 + p[1])


def esc(txt):
    txt = str(txt).replace(';', ',')           # u() del player corrompe ';'
    return txt.replace('\\', '\\\\').replace(']', '\\]')


def node_props(n, size):
    s = ''
    if n.stones is not None:
        before = position(n.parent, size).g if n.parent else {}
        if STONES_MODE == 'add':
            before = {}
        ae = [p for p in before if p not in n.stones]
        ab = [p for p, c in n.stones.items() if before.get(p) != c and c == B]
        aw = [p for p, c in n.stones.items() if before.get(p) != c and c == W]
        if ae:
            s += 'AE' + ''.join(f'[{co(p)}]' for p in sorted(ae))
        if ab:
            s += 'AB' + ''.join(f'[{co(p)}]' for p in sorted(ab))
        if aw:
            s += 'AW' + ''.join(f'[{co(p)}]' for p in sorted(aw))
    for p, c in n.adds:
        s += ('AE' if c == 0 else 'AB' if c == B else 'AW') + f'[{co(p)}]'
    if n.move:
        s += ('B' if n.move[1] == B else 'W') + ('[]' if n.move[0] == 'pass' else f'[{co(n.move[0])}]')
    for p, t in n.labels.items():
        s += f'LB[{co(p)}:{esc(t)}]'
    if n.comment:
        s += f'C[{esc(n.comment)}]'
    return s


def emit_sgf(root, title, size=19):
    out = [f'(;GM[1]FF[4]CA[UTF-8]SZ[{size}]GN[{esc(title)}]' + node_props(root, size)]
    counter = [0]

    def emit(n):
        while True:
            n.nn = counter[0]
            counter[0] += 1
            if n is not root:
                out.append(';' + node_props(n, size))
            if len(n.children) == 1:
                n = n.children[0]
                continue
            for ch in n.children:
                out.append('(')
                emit(ch)
                out.append(')')
            return
    emit(root)
    out.append(')')
    return ''.join(out), counter[0]


# ------------------------------------------------------------ path signature
def signature(n):
    sig = []
    for a in path_of(n)[1:]:
        if a.base:
            sig.append(('b', a.id))
        elif a.move:
            sig.append(('m', a.move))
        else:
            sig.append(('a', tuple(a.adds)))
    return sig


def resolve(root, byid, sig):
    cur = root
    for el in sig:
        if el[0] == 'b':
            cur = byid[el[1]]
            continue
        hit = None
        for ch in cur.children:
            if el[0] == 'm' and ch.move == el[1]:
                hit = ch
            if el[0] == 'a' and not ch.move and tuple(ch.adds) == el[1]:
                hit = ch
        if hit is None:
            hit = Node(None, el[1] if el[0] == 'm' else None, cur, False)
            if el[0] == 'a':
                hit.adds = list(el[1])
            cur.children.append(hit)
        cur = hit
    return cur


# -------------------------------------------------------- events -> player
def _parse_markup(prop):
    m = re.match(r'^([A-Z]{2})\[([a-z]{2})(?::(.*))?\]$', prop)
    k, c, t = m.groups()
    return k, (ord(c[0]) - 97, ord(c[1]) - 97), t


# ------------------------------------------------------- dibujo a mano (draw-events)
DRAW_SIZE = 600                 # lado (px) del lienzo original; verificado con el censo (max 599.6)
DRAW_DEFAULT_COLOR = '#f44336'  # color si un trazo empieza sin :set-color previo en el clip


def translate_draw(raw, warn):
    """draw-events (EDN) de un clip -> dict para <id>_draw.json, o None si no hay tinta.

    Mismo eje de tiempos que translate(): ms/1000 redondeado a 3 decimales, sin desplazamiento.
    Solo se guardan los puntos CON tinta (entre :start-drawing y :stop-drawing); los
    :draw-move con el boton arriba se descartan. :delete-drawing borra todo lo anterior.
    Los avisos se anotan en `warn` (Counter) con el prefijo 'draw:'.
    """
    if not isinstance(raw, str) or raw.strip() in ('', 'nil'):
        return None
    try:
        evs = edn(raw)
        if not isinstance(evs, list):
            raise ValueError('draw-events no es una lista')
    except Exception as e:  # noqa: BLE001
        warn[f'draw: draw-events ilegible ({type(e).__name__}), dibujo omitido'] += 1
        return None

    strokes, clears = [], []
    color, color_seen, cur = DRAW_DEFAULT_COLOR, False, None

    def close():
        nonlocal cur
        strokes.append(cur)
        cur = None

    def pt(t_ms, p):
        return [round((t_ms - cur['t0']) / 1000.0, 3), round(float(p[0]), 1), round(float(p[1]), 1)]

    for ev in evs:
        try:
            t, body = ev[0], ev[1]
            kind = str(body[0])
        except (IndexError, TypeError):
            warn['draw: evento malformado ignorado'] += 1
            continue
        if kind == 'set-color':
            color, color_seen = str(body[1]), True
        elif kind == 'start-drawing':
            if cur is not None:
                warn['draw: start-drawing sin stop previo (trazo anterior cerrado)'] += 1
                close()
            if not color_seen:
                warn[f'draw: trazo sin set-color previo (usa {DRAW_DEFAULT_COLOR})'] += 1
            cur = {'t0': t, 'c': color, 'p': []}
            cur['p'].append(pt(t, body[1]))
        elif kind == 'draw-move':
            if cur is not None:
                cur['p'].append(pt(t, body[1]))
        elif kind == 'stop-drawing':
            if cur is None:
                warn['draw: stop-drawing sin start (ignorado)'] += 1
            else:
                close()
        elif kind == 'delete-drawing':
            if cur is not None:
                close()
            clears.append(round(t / 1000.0, 3))
        else:
            warn[f'draw: evento desconocido {kind}'] += 1
    if cur is not None:
        warn['draw: trazo abierto al final del clip (cerrado en su ultimo punto)'] += 1
        close()
    if not strokes:
        return None
    out = [{'t': round(st['t0'] / 1000.0, 3), 'c': st['c'], 'p': st['p']} for st in strokes]
    out.sort(key=lambda st: st['t'])
    return {'size': DRAW_SIZE, 'strokes': out, 'clears': sorted(clears)}


def _is_live_add(n):
    """Nodo creado en vivo solo con retoques (:add), sin jugada."""
    return n is not None and not n.base and not n.move and bool(n.adds) and n.stones is None


def translate(events, root, byid, start, n_nodes, forwards_mode, warn, size=19, uid_sigs=None, persisted=None):
    out = []
    uid_map = {}
    nn_next = n_nodes
    cur = start
    lastvisit = {}
    markers = collections.defaultdict(set)      # nn -> {(tipo, x, y)}
    counters = collections.defaultdict(lambda: [0, 0])  # nn -> [letras, numeros]
    labels_state = {}                           # nn -> {punto: texto} de las etiquetas visibles
    expected = []                               # (idx en out, nodo activo)

    def add(ms, **kw):
        out.append({'time': round(ms / 1000.0, 3), **kw})

    # decision 4: t=0 muestra el primer nodo al que se navega
    initial = start
    if events and str(events[0][1][0]) == 'navigate':
        if events[0][1][1] is None and NAV_NIL == 'root':
            tgt = root                      # v27: navigate nil = raiz
        else:
            tgt = byid.get(events[0][1][1]) if events[0][1][1] is not None else None
        if tgt:
            initial = tgt
    cur = initial
    out.append({'time': 0, 'activate': cur.nn})
    expected.append((0, cur))

    def mark(idx):
        expected.append((idx, cur))

    def realize(sig_list, ms):
        """Asegura el camino de una firma (creando nodos en vivo con addChild) y devuelve el nodo final."""
        nonlocal nn_next
        node = root
        for el in sig_list:
            if el[0] == 'b':
                node = byid.get(el[1])
                if node is None:
                    return None
                continue
            hit = None
            for ch in node.children:
                if (el[0] == 'm' and ch.move == el[1]) or (el[0] == 'a' and not ch.move and tuple(ch.adds) == el[1]):
                    hit = ch
                    break
            if hit is None:
                hit = Node(None, el[1] if el[0] == 'm' else None, node, False)
                if el[0] == 'a':
                    hit.adds = list(el[1])
                hit.nn = nn_next
                nn_next += 1
                node.children.append(hit)
                if el[0] == 'm':
                    mv = el[1]
                    props = [('B' if mv[1] == B else 'W') + ('[]' if mv[0] == 'pass' else f'[{co(mv[0])}]')]
                else:
                    props = [('AE' if c == 0 else 'AB' if c == B else 'AW') + f'[{co(p)}]' for p, c in el[1]]
                add(ms, addChild=[node.nn, hit.nn], addProp=[hit.nn, props[0]])
                for extra in props[1:]:
                    add(ms, addProp=[hit.nn, extra])
                apply_persisted(hit, ms)
            node = hit
        return node

    persisted_on = persisted is not None and MARKS_PERSIST == 'clip'

    def sig_key(node):
        return tuple(signature(node))

    def find_by_sig(sig_list):
        node = root
        for el in sig_list:
            if el[0] == 'b':
                node = byid.get(el[1])
                if node is None:
                    return None
                continue
            found = None
            for ch in node.children:
                if (el[0] == 'm' and ch.move == el[1]) or (el[0] == 'a' and not ch.move and tuple(ch.adds) == el[1]):
                    found = ch
                    break
            if found is None:
                return None
            node = found
        return node

    def apply_persisted(node, ms):
        """Reaplica las marcas/etiquetas que este nodo tenia al acabar clips anteriores."""
        if not persisted_on:
            return
        ent = persisted.get(sig_key(node))
        if not ent:
            return
        nn = node.nn
        st = labels_state.setdefault(nn, {pt: str(t) for pt, t in node.labels.items()})
        for prop in ent.get('remove', []):
            k, pt, t = _parse_markup(prop)
            if pt in st:
                st.pop(pt)
                add(ms, removeProp=[nn, prop])
        for prop in ent.get('add', []):
            k, pt, t = _parse_markup(prop)
            if k == 'LB':
                if pt in st and st[pt] != t:
                    add(ms, removeProp=[nn, f'LB[{co(pt)}:{st[pt]}]'])
                st[pt] = t
            else:
                markers[nn].add((k, pt[0], pt[1]))
            add(ms, addProp=[nn, prop])

    if persisted_on:
        for sg in list(persisted):
            node0 = find_by_sig(list(sg))
            if node0 is not None:
                apply_persisted(node0, 0)

    for ms, ev in events:
        op = str(ev[0])
        if op == 'navigate':
            if ev[1] is None and NAV_NIL == 'root':
                cur = root                  # v27: navigate nil = ir a la raiz (tablero vacio si no hay arbol)
                add(ms, activate=cur.nn)
                mark(len(out) - 1)
                continue
            tgt = (uid_map.get(ev[1]) or byid.get(ev[1])) if ev[1] is not None else None
            if tgt is None and uid_sigs is not None and ev[1] in uid_sigs:
                tgt = realize(uid_sigs[ev[1]], ms)
                if tgt is not None:
                    uid_map[ev[1]] = tgt
                    warn['navigate a nodo creado en un clip anterior (reconstruido)'] += 1
            if tgt is None:
                warn['navigate a nodo desconocido'] += 1
                _diag('navigate_desconocido', ms, id=str(ev[1]))
                continue
            cur = tgt
            add(ms, activate=cur.nn)
            mark(len(out) - 1)
        elif op == 'move':
            (x, y), flag, uid = ev[1], ev[2], ev[3]
            if flag:
                warn['move con flag=true (blanca)'] += 1
            if FLAG_MODE == 'white':
                # v24: flag=true -> blanca; si no, alterna respecto a la ultima jugada del camino.
                # Los hijos solo deciden si no hay jugada previa (inicio o justo tras un diagrama).
                if flag:
                    col = W
                else:
                    lc = last_color(cur)
                    col = next_color(cur) if lc is None else -lc
                    if lc is None and not any(c.move for c in cur.children):
                        _diag('turno_supuesto', ms, pt=(x, y), color=col, node=cur)   # sin dato: negra por defecto
            else:                        # modos antiguos (v22): color segun los hijos
                col = next_color(cur)
                if flag and FLAG_MODE == 'invert':
                    col = -col
            match = [c for c in cur.children if c.move and c.move[0] == (x, y)]
            # el arbol puede tener hermanos en el mismo punto con colores distintos
            # (p. ej. B[12 4] y W[12 4] bajo W[12 3]): preferir el de color esperado
            same_col = [c for c in match if c.move[1] == col]
            if len(match) > 1:
                warn['move con hermanos de mismo punto y distinto color'] += 1
            # v24: si el hijo de ese punto es una jugada EN VIVO de otro color, se crea una variacion
            # hermana con el color correcto; si es del arbol original, se respeta el arbol (y se avisa)
            new_sibling = (FLAG_MODE == 'white' and match and not same_col
                           and not any(c.base for c in match))
            if new_sibling:
                warn['move: variacion nueva junto a jugada en vivo de otro color'] += 1
            if match and not new_sibling:
                nxt = (same_col or match)[0]
                if not same_col:
                    warn['move existente con color distinto al esperado (revisar)'] += 1
                    _diag('color_inesperado', ms, pt=(x, y), esperado=col, hijo=match[0].move[1], flag=flag, node=cur)
                add(ms, activate=nxt.nn)
            else:
                if position(cur, size).g.get((x, y)):
                    warn['move sobre punto ocupado'] += 1
                    _diag('jugada_ocupada', ms, pt=(x, y), color=col, flag=flag, node=cur)
                nxt = Node(uid, ((x, y), col), cur, False)
                nxt.nn = nn_next
                nn_next += 1
                cur.children.append(nxt)
                add(ms, addChild=[cur.nn, nxt.nn],
                    addProp=[nxt.nn, f"{'B' if col == B else 'W'}[{co((x, y))}]"],
                    activate=nxt.nn)
                apply_persisted(nxt, ms)
            uid_map[uid] = nxt
            if uid_sigs is not None:
                uid_sigs[uid] = signature(nxt)
            lastvisit[cur] = nxt
            cur = nxt
            mark(len(out) - 1)
        elif op == 'add':
            (x, y), flag, uid = ev[1], ev[2], ev[3]
            warn['add (validado en video)'] += 1
            white_if_true = (ADD_FLAG_TRUE == 'white')
            col = (W if flag else B) if white_if_true else (B if flag else W)
            eff = col
            if ADD_SEM == 'toggle' and position(cur, size).g.get((x, y)) == col:
                eff = 0                      # ya habia una piedra de ese color: se quita
            elif ADD_SEM == 'remove' and position(cur, size).g.get((x, y)):
                eff = 0                      # v25: habia una piedra (de cualquier color): se quita
            aprop = f"AE[{co((x, y))}]" if eff == 0 else f"{'AB' if eff == B else 'AW'}[{co((x, y))}]"
            if ADD_MODE == 'inplace' or (ADD_MODE in ('auto', 'auto2') and not cur.move):
                cur.adds.append(((x, y), eff))
                add(ms, addProp=[cur.nn, aprop])
                uid_map[uid] = cur
                if uid_sigs is not None:
                    uid_sigs[uid] = signature(cur)
                continue
            nxt = Node(uid, None, cur, False)
            nxt.adds = [((x, y), eff)]
            nxt.nn = nn_next
            nn_next += 1
            cur.children.append(nxt)
            add(ms, addChild=[cur.nn, nxt.nn], addProp=[nxt.nn, aprop], activate=nxt.nn)
            apply_persisted(nxt, ms)
            uid_map[uid] = nxt
            if uid_sigs is not None:
                uid_sigs[uid] = signature(nxt)
            cur = nxt
            mark(len(out) - 1)
        elif op == 'backwards':
            if cur.parent is None:
                continue
            if ADD_MODE == 'auto2':
                # los retoques (:add) en vivo cuentan como parte del nodo al que se aplicaron:
                # retroceder desde ellos sube hasta ese nodo y luego un paso mas
                while _is_live_add(cur) and cur.parent is not None and cur.parent.parent is not None:
                    cur = cur.parent
            lastvisit[cur.parent] = cur
            cur = cur.parent
            add(ms, activate=cur.nn)
            mark(len(out) - 1)
        elif op == 'forwards':
            if not cur.children:
                continue
            lv = lastvisit.get(cur)
            if len(cur.children) > 1 and lv is not None and lv is not cur.children[0]:
                warn['forwards ambiguo: primer hijo y ultimo visitado difieren (tramo transitorio)'] += 1
            ch = lastvisit.get(cur, cur.children[0]) if forwards_mode == 'last' else cur.children[0]
            cur = ch
            add(ms, activate=cur.nn)
            mark(len(out) - 1)
        elif op in ('triangle', 'square', 'circle'):
            t = {'triangle': 'TR', 'square': 'SQ', 'circle': 'CR'}[op]
            (x, y) = ev[1]
            warn['marcas TR/SQ/CR'] += 1
            key = (t, x, y)
            prop = f'{t}[{co((x, y))}]'
            if key in markers[cur.nn]:
                if MARK_REPEAT == 'toggle':
                    markers[cur.nn].discard(key)
                    add(ms, removeProp=[cur.nn, prop])
            else:
                markers[cur.nn].add(key)
                add(ms, addProp=[cur.nn, prop])
        elif op in ('label-char', 'label-num'):
            (x, y) = ev[1]
            warn['etiquetas auto'] += 1
            if cur.nn not in labels_state:
                labels_state[cur.nn] = {pt: str(t) for pt, t in cur.labels.items()}
            st = labels_state[cur.nn]
            if (x, y) in st and LABEL_REPEAT == 'toggle':
                add(ms, removeProp=[cur.nn, f'LB[{co((x, y))}:{st.pop((x, y))}]'])
                continue
            if LABEL_SCOPE == 'node':
                used = set(st.values())
                if op == 'label-char':
                    txt = next((chr(65 + i) for i in range(26) if chr(65 + i) not in used), '?')
                else:
                    n = 1
                    while str(n) in used:
                        n += 1
                    txt = str(n)
            else:                                # contador continuo en todo el clip (opcion antigua)
                c = counters[0]
                if op == 'label-char':
                    txt = chr(ord('A') + c[0] % 26)
                    c[0] += 1
                else:
                    c[1] += 1
                    txt = str(c[1])
            st[(x, y)] = txt
            add(ms, addProp=[cur.nn, f'LB[{co((x, y))}:{txt}]'])
        elif op == 'variation-backspace':
            warn['variation-backspace tratado como backwards (equivalente visualmente)'] += 1
            if cur.parent is not None:
                cur = cur.parent
                add(ms, activate=cur.nn)
                mark(len(out) - 1)
        else:
            warn[f'evento desconocido {op}'] += 1
    if persisted_on:
        nodes_map, stack = {}, [root]
        while stack:
            n_ = stack.pop()
            if n_.nn is not None:
                nodes_map[n_.nn] = n_
            stack.extend(n_.children)
        for nn in set(markers) | set(labels_state):
            node = nodes_map.get(nn)
            if node is None:
                continue
            ent = {'add': [], 'remove': []}
            for (t, x, y) in sorted(markers.get(nn, ())):
                ent['add'].append(f'{t}[{co((x, y))}]')
            st = labels_state.get(nn)
            if st is not None:
                base = {pt: str(t) for pt, t in node.labels.items()}
                for pt, t in st.items():
                    if base.get(pt) != t:
                        ent['add'].append(f'LB[{co(pt)}:{t}]')
                for pt, t in base.items():
                    if pt not in st:
                        ent['remove'].append(f'LB[{co(pt)}:{t}]')
            key = sig_key(node)
            if ent['add'] or ent['remove']:
                persisted[key] = ent
            else:
                persisted.pop(key, None)
    return out, cur, expected


# --------------------------------------------- autocomprobacion (modelo player)
def parse_sgf_model(text):
    """Mini parser SGF; NN = indice del ';' en el texto (igual que u() del player)."""
    nodes = []
    stack = []
    last = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '(':
            stack.append(last)
            i += 1
        elif ch == ')':
            last = stack.pop()
            i += 1
        elif ch == ';':
            nd = {'nn': len(nodes), 'parent': last, 'props': []}
            nodes.append(nd)
            last = nd
            i += 1
        elif ch.isalpha() and last is not None:
            j = i
            while j < n and text[j].isalpha():
                j += 1
            name = text[i:j]
            vals = []
            while j < n and text[j] == '[':
                k = j + 1
                buf = ''
                while text[k] != ']':
                    if text[k] == '\\':
                        k += 1
                    buf += text[k]
                    k += 1
                vals.append(buf)
                j = k + 1
            last['props'].append((name, vals))
            i = j
        else:
            i += 1
    return nodes


def model_position(nodes, nn, size=19):
    chain = []
    nd = nodes[nn]
    while nd is not None:
        chain.append(nd)
        nd = nd['parent']
    b = Board(size)
    for nd in reversed(chain):
        for name, vals in nd['props']:
            if name == 'AE':
                for v in vals:
                    b.g.pop((ord(v[0]) - 97, ord(v[1]) - 97), None)
            if name in ('AB', 'AW'):
                for v in vals:
                    b.g[(ord(v[0]) - 97, ord(v[1]) - 97)] = B if name == 'AB' else W
        for name, vals in nd['props']:
            if name in ('B', 'W') and vals and vals[0]:
                b.play((ord(vals[0][0]) - 97, ord(vals[0][1]) - 97), B if name == 'B' else W)
    return b.g


def selfcheck(sgf, events, expected, size=19):
    """Reproduce el JSON como el player y compara posiciones con el simulador."""
    problems = []
    nodes = parse_sgf_model(sgf)
    if sgf.count(';') != len(nodes):
        problems.append("recuento de ';' != nodos")
    for idx, ev in enumerate(events):
        if 'addChild' in ev:
            p, c = ev['addChild']
            if c < len(nodes) and nodes[c]['nn'] == c and c in [x['nn'] for x in nodes]:
                problems.append(f'addChild id {c} ya existe')
            nd = {'nn': c, 'parent': nodes[p] if p < len(nodes) else None, 'props': []}
            while len(nodes) <= c:
                nodes.append(None)
            nodes[c] = nd
        if 'addProp' in ev:
            nn, prop = ev['addProp']
            bi = prop.index('[')
            if nodes[nn] is not None:
                nodes[nn]['props'].append((prop[:bi], [prop[bi + 1:-1]]))
    for idx, node in expected:
        nn = events[idx].get('activate')
        if nn is None:
            continue
        if model_position(nodes, nn, size) != position(node, size).g:
            problems.append(f'evento {idx} t={events[idx]["time"]}: posicion distinta (nn {nn})')
            if len(problems) > 5:
                break
    return problems


# ------------------------------------------------------------------- driver
def player_sanitize(name):
    return re.sub(r'\.+$', '', re.sub(r'[\\/:*?"<>\'|]', '_', name or '').strip())


def load_course(path):
    txt = Path(path).read_text(encoding='utf-8-sig').strip()
    d = None
    for cand in (txt, '{' + txt.rstrip(',').strip() + '}'):
        try:
            d = json.loads(cand, strict=False)
            break
        except json.JSONDecodeError as e:
            err = e
    if d is None:
        raise SystemExit(f'No pude parsear {path}: {err}')
    found = []

    def walk(n, k):
        if isinstance(n, dict):
            if 'clips' in n:
                found.append((str(k).split('/')[-1], n))
            else:
                for kk, v in n.items():
                    walk(v, kk)
    walk(d, 'root')
    return found


# Escala de dificultad (mayor = mas dificil). group-all = "todos los niveles" = 0.
GROUP_LEVELS = {'beginners': 1, 'beginner': 1, 'd': 2, 'c': 3, 'b': 4, 'a': 5}


def difficulty_from_group(g):
    """target-group -> dificultad. group-all -> "0" (texto), beginners 1, d 2, c 3, b 4, a 5; '' si no se puede.
    Tolera mayusculas, espacios, '_' y '-'. El 0 va como TEXTO: el player trata el numero 0 como
    "sin dificultad" (muestra "-" y lo excluye del filtro), pero "0" si cuenta."""
    txt = str(g or '').strip().lower()
    m = re.fullmatch(r'(?:group[-_ ]*)?(all|beginners?|[a-d])', txt)
    if not m:
        return ''
    v = m.group(1)
    return '0' if v == 'all' else GROUP_LEVELS[v]


def minutes(ms):
    """Duracion para el manifest: MINUTOS enteros (el player suma lessonLength como numero de minutos).
    Un clip no vacio dura al menos 1; sin duracion devuelve 0."""
    return max(1, round(ms / 60000)) if ms else 0


def hms(ms):
    s = int(round(ms / 1000))
    return f'{s // 60}:{s % 60:02d}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('course_json')
    ap.add_argument('--out', default='player_out')
    ap.add_argument('--audio-root', default=None, help='carpeta con los .m4a (cursos_final)')
    ap.add_argument('--convert-audio', action='store_true', help='m4a -> ogg (Vorbis) con ffmpeg')
    ap.add_argument('--ffmpeg', default='ffmpeg')
    ap.add_argument('--type-name', default='Awesome Baduk')
    ap.add_argument('--id-start', type=int, default=900000)
    ap.add_argument('--require-audio', action='store_true',
                    help='omitir (sin leccion ni fila en el manifest) los clips cuyo audio no este en --audio-root')
    ap.add_argument('--manifest-copy', action='store_true',
                    help='escribe tambien all_lessons.json (la copia que lee el player de prueba) con las mismas filas')
    ap.add_argument('--only', action='append', default=[],
                    help='convertir solo cursos cuyo titulo contenga este texto (o cuyo id coincida); repetible')
    ap.add_argument('--draw-only', action='store_true',
                    help='solo genera los <id>_draw.json de los clips YA publicados (usa lesson_ids.json); '
                         'no toca .sgf, .json, .ogg, manifests ni informes, y no necesita audio')
    ap.add_argument('--ids', default=None,
                    help='ruta de lesson_ids.json (por defecto OUT\\lesson_ids.json); permite usar el de otra carpeta')
    ap.add_argument('--new-ids', action='store_true',
                    help='confirma que se empieza SIN lesson_ids.json (IDs nuevos desde --id-start). '
                         'Sin esto, si falta o esta vacio, el conversor se detiene para no repetir IDs ya publicados')
    ap.add_argument('--census', default=None, help='census_courses.csv: convertir solo cursos con ese Estado')
    ap.add_argument('--estado', default='LISTO', help='estados del censo a convertir, separados por comas (LISTO,REVISAR)')
    ap.add_argument('--forwards', choices=['first', 'last'], default='first')
    ap.add_argument('--flag-mode', choices=['white', 'invert', 'ignore'], default='white',
                    help="flag=true en :move: piedra blanca (por defecto, validado en video), se ignora o invierte el color")
    ap.add_argument('--add-mode', choices=['auto2', 'auto', 'child', 'inplace'], default='auto2',
                    help=':add: auto2 (por defecto: dentro del nodo si no tiene jugada y retroceder salta los retoques), auto, nodo hijo (v22-v25) o dentro del nodo')
    ap.add_argument('--add-flag-true', choices=['white', 'black'], default='white')
    ap.add_argument('--add-sem', choices=['remove', 'toggle', 'place'], default='remove',
                    help=':add sobre una piedra: la quita sea del color que sea (por defecto), solo si es del mismo color, o siempre pone')
    ap.add_argument('--marks-persist', choices=['clip', 'none'], default='clip',
                    help='marcas y etiquetas de un nodo se conservan al pasar al clip siguiente (por defecto) o no')
    ap.add_argument('--mark-repeat', choices=['toggle', 'keep'], default='toggle',
                    help='marca TR/SQ/CR repetida sobre el mismo punto y nodo: la quita (por defecto) o se queda')
    ap.add_argument('--label-repeat', choices=['toggle', 'keep'], default='toggle',
                    help='etiqueta sobre un punto ya etiquetado: la quita (por defecto) o se superpone')
    ap.add_argument('--label-scope', choices=['node', 'clip'], default='node',
                    help='contador de etiquetas: reinicia en cada nodo (por defecto) o continua en todo el clip')
    ap.add_argument('--suicide-mode', choices=['remove', 'keep'], default='remove')
    ap.add_argument('--stones-mode', choices=['replace', 'add'], default='replace',
                    help=":stones reemplaza la posicion (por defecto) o se suma a la existente")
    args = ap.parse_args()

    print(f'awesome_to_player {VERSION}')
    global STONES_MODE, FLAG_MODE, ADD_MODE, ADD_FLAG_TRUE, SUICIDE_MODE, ADD_SEM, MARK_REPEAT, LABEL_SCOPE, LABEL_REPEAT, MARKS_PERSIST
    STONES_MODE = args.stones_mode
    FLAG_MODE = args.flag_mode
    ADD_MODE, ADD_FLAG_TRUE, SUICIDE_MODE = args.add_mode, args.add_flag_true, args.suicide_mode
    ADD_SEM = args.add_sem
    MARKS_PERSIST = args.marks_persist
    MARK_REPEAT, LABEL_SCOPE, LABEL_REPEAT = args.mark_repeat, args.label_scope, args.label_repeat
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ids_path = Path(args.ids) if args.ids else out / 'lesson_ids.json'
    ids = json.loads(ids_path.read_text(encoding='utf-8')) if ids_path.exists() else {}
    if not ids and not args.new_ids:
        if args.draw_only:
            sys.exit(f'--draw-only necesita un lesson_ids.json con contenido: {ids_path} no existe o esta vacio. '
                     f'Indica el correcto con --ids RUTA.')
        sys.exit(f'No hay lesson_ids.json con contenido en {ids_path}. Sin el, los lessonId se repartirian desde '
                 f'{args.id_start} y chocarian con los ya publicados. Restauralo (--ids RUTA, o rebuild_lesson_ids.py); '
                 f'si de verdad empiezas desde cero, anade --new-ids.')
    draw_stats = collections.Counter()
    rows_path = out / 'all_lessons.new.json'
    rep_path = out / 'convert_report.json'
    rows_by_id = ({r['lessonId']: r for r in json.loads(rows_path.read_text(encoding='utf-8'))['rows']}
                  if rows_path.exists() else {})
    report = json.loads(rep_path.read_text(encoding='utf-8')) if rep_path.exists() else {}

    audio_index = None
    if args.audio_root:
        audio_index = {p.stem: p for p in Path(args.audio_root).rglob('*.m4a')}
        print(f'Audios encontrados en {args.audio_root}: {len(audio_index)}')
    skipped = []
    errors = []
    course_dirs = {}                  # carpeta de curso -> titulo (para decir que subir)
    unmapped_groups = collections.Counter()
    allowed = None
    if args.census:
        import csv as _csv
        wanted = {e.strip().upper() for e in args.estado.split(',')}
        txt = Path(args.census).read_text(encoding='utf-8-sig')
        delim = ';' if txt.split('\n', 1)[0].count(';') > txt.split('\n', 1)[0].count(',') else ','
        allowed = {r['ID'] for r in _csv.DictReader(txt.splitlines(), delimiter=delim)
                   if (r.get('Estado') or '').upper() in wanted}
        print(f'Censo: {len(allowed)} cursos con estado {sorted(wanted)}')
    for cid, course in load_course(args.course_json):
        title = (course.get('title') or cid).strip()
        if allowed is not None and cid not in allowed:
            continue
        if args.only and not any(o.lower() in title.lower() or o == cid for o in args.only):
            continue
        try:
            bd = course.get('board') or {}
            if bd.get('variations') and not args.draw_only:   # en --draw-only el arbol no hace falta
                tree = edn(bd['variations'])
            else:                                   # curso solo-audio: tablero vacio
                tree = {'id': 'root', 'children': []}
            size = int(tree.get('board-size') or 19)
            uuid2vid = {}
            for u, p in (course.get('vimeo-ids') or {}).items():
                m = re.search(r'/videos/(\d+)', str(p))
                if m:
                    uuid2vid[u] = int(m.group(1))
            group = (course.get('target-group') or '')
            diff = difficulty_from_group(group)
            if diff == '':
                unmapped_groups[str(group)] += 1
            sig = []                      # estado continuo entre clips
            uid_sigs = {}                 # uuid de nodos en vivo -> camino (persisten entre clips)
            persisted = {}                # marcas/etiquetas por nodo (persisten entre clips)
            for ci, clip in enumerate(course.get('clips') or [], 1):
                key = f'{cid}/{clip.get("video-id")}'
                if args.draw_only:
                    lid = ids.get(key)
                    if lid is None:
                        draw_stats['clips sin ID (no publicados, se omiten)'] += 1
                        continue
                    w = collections.Counter()
                    doc = translate_draw(clip.get('draw-events'), w)
                    for k, v in w.items():
                        draw_stats['aviso ' + k] += v
                    if not doc:
                        draw_stats['clips sin dibujo'] += 1
                        continue
                    d = (out / 'lessons' / player_sanitize(args.type_name) / player_sanitize(title)
                         / player_sanitize(f'Clip {ci:02d}'))
                    d.mkdir(parents=True, exist_ok=True)
                    (d / f'{lid}_draw.json').write_text(json.dumps(doc, separators=(',', ':')) + '\n',
                                                        encoding='utf-8')
                    draw_stats['_draw.json escritos'] += 1
                    course_dirs[d.parent.name] = title
                    continue
                ev_raw = clip.get('events')
                events = edn(ev_raw) if isinstance(ev_raw, str) and ev_raw != 'nil' else []
                warn = collections.Counter()
                draw_doc = translate_draw(clip.get('draw-events'), warn)

                root, byid = build_tree(tree)
                start = resolve(root, byid, sig)
                sgf, n_nodes = emit_sgf(root, f'{title} - Clip {ci:02d}', size)
                events_out, end, expected = translate(events, root, byid, start, n_nodes,
                                                      args.forwards, warn, size, uid_sigs, persisted)
                if not bd.get('variations') and any(k in warn for k in (
                        'navigate a nodo desconocido', 'move sobre punto ocupado',
                        'move existente con color distinto al esperado (revisar)')):
                    # sin arbol, los eventos apuntan a nodos que no existen: leccion solo audio
                    events_out, end, expected = [{'time': 0, 'activate': 0}], root, [(0, root)]
                    warn['curso sin arbol: eventos descartados (solo audio)'] += 1
                problems = selfcheck(sgf, events_out, expected, size)
                sig = signature(end)          # el estado avanza aunque el clip se omita

                name = f'Clip {ci:02d}'
                vid = uuid2vid.get(clip.get('video-id'))
                src_audio = audio_index.get(str(vid)) if audio_index is not None else None
                d = out / 'lessons' / player_sanitize(args.type_name) / player_sanitize(title) / player_sanitize(name)
                if args.require_audio and src_audio is None:
                    skipped.append({'curso': title, 'clip': ci, 'vimeo': vid})
                    old = ids.get(key)
                    if old is not None:                       # limpiar restos de ejecuciones anteriores
                        rows_by_id.pop(old, None)
                        report.pop(str(old), None)
                        for fname in (f'{old}.sgf', f'{old}.json', f'{old}_draw.json'):
                            try:
                                (d / fname).unlink()
                            except OSError:
                                pass
                        try:
                            d.rmdir()
                        except OSError:
                            pass
                    print(f'-- omitido (sin audio) {title[:30]:30} {name} vimeo {vid}')
                    continue
                if key not in ids:
                    ids[key] = max([args.id_start - 1] + list(ids.values())) + 1
                lid = ids[key]
                d.mkdir(parents=True, exist_ok=True)
                (d / f'{lid}.sgf').write_text(sgf, encoding='utf-8')
                (d / f'{lid}.json').write_text(json.dumps(events_out, separators=(',', ':')) + '\n',
                                               encoding='utf-8')
                draw_path = d / f'{lid}_draw.json'
                if draw_doc:
                    draw_path.write_text(json.dumps(draw_doc, separators=(',', ':')) + '\n', encoding='utf-8')
                elif draw_path.exists():                   # el clip ya no tiene dibujo: quitar el anterior
                    draw_path.unlink()
                course_dirs[d.parent.name] = title

                audio_status = 'sin --audio-root'
                if args.audio_root:
                    if src_audio is None:
                        audio_status = f'NO ENCONTRADO {vid}.m4a'
                    elif args.convert_audio and (d / f'{lid}.ogg').exists() and (d / f'{lid}.ogg').stat().st_size > 0:
                        audio_status = 'ogg ya existia (se salta)'
                    elif args.convert_audio:
                        dst = d / f'{lid}.ogg'
                        r = subprocess.run([args.ffmpeg, '-y', '-loglevel', 'error', '-i', str(src_audio),
                                            '-vn', '-c:a', 'libvorbis', '-q:a', '4', str(dst)])
                        audio_status = 'ogg OK' if r.returncode == 0 and dst.exists() else 'ffmpeg FALLO'
                    else:
                        audio_status = f'encontrado {src_audio} (usa --convert-audio)'
                rows_by_id[lid] = ({'lessonId': lid, 'lessonName': name, 'lessonSuffix': '',
                             'typeName': args.type_name, 'collectionName': title,
                             'lessonDifficulty': diff, 'lessonLength': minutes(clip.get('runtime') or 0),
                             'sourceCourseId': cid, 'sourceVimeoId': vid})
                report[str(lid)] = {'course': title, 'clip': ci, 'vimeo': vid, 'events_in': len(events),
                                    'events_out': len(events_out), 'nodes_sgf': n_nodes,
                                    'audio': audio_status, 'selfcheck': problems or 'OK',
                                    'warnings': dict(warn)}
                if draw_doc:
                    report[str(lid)]['draw'] = {'strokes': len(draw_doc['strokes']),
                                                'points': sum(len(st['p']) for st in draw_doc['strokes']),
                                                'clears': len(draw_doc['clears'])}
                flag = 'OK ' if not problems else '!! '
                print(f'{flag}{lid} {title[:30]:30} {name} vimeo {vid}  eventos {len(events)}->{len(events_out)}'
                      f'  nodos {n_nodes}  audio: {audio_status}  avisos {sum(warn.values())}'
                      + (f'  dibujo {len(draw_doc["strokes"])} trazos' if draw_doc else ''))

        except Exception as e:  # noqa: BLE001
            errors.append({'curso': title, 'id': cid, 'error': f'{type(e).__name__}: {e}'})
            print(f'!! ERROR en el curso "{title}": {type(e).__name__}: {e}  (se omite y se continua)')

    if args.draw_only:
        print('\n==== --draw-only ====')
        for k, v in sorted(draw_stats.items()):
            print(f'  {k}: {v}')
        if errors:
            print(f'  cursos omitidos por error: {len(errors)} (primero: {errors[0]["curso"]}: {errors[0]["error"]})')
        print(f'\nSolo se han escrito ficheros *_draw.json bajo {out}\\lessons\\{player_sanitize(args.type_name)}\\')
        return
    if unmapped_groups:
        print(f'\nCursos sin nivel de dificultad (target-group no reconocido): {dict(unmapped_groups)}')
    if errors:
        (out / 'errors_courses.json').write_text(json.dumps(errors, indent=2, ensure_ascii=False),
                                                 encoding='utf-8')
        print(f'\nCursos omitidos por error: {len(errors)} (lista en errors_courses.json)')
    if skipped:
        (out / 'skipped_no_audio.json').write_text(json.dumps(skipped, indent=2, ensure_ascii=False),
                                                   encoding='utf-8')
        print(f'\nClips omitidos por no tener audio: {len(skipped)} (lista en skipped_no_audio.json)')
    ids_path.write_text(json.dumps(ids, indent=2), encoding='utf-8')
    manifest_text = json.dumps({'rows': [rows_by_id[k] for k in sorted(rows_by_id)]},
                               indent=2, ensure_ascii=False)
    rows_path.write_text(manifest_text, encoding='utf-8')
    if args.manifest_copy:
        (out / 'all_lessons.json').write_text(manifest_text, encoding='utf-8')
        print(f'all_lessons.json actualizado en {out} ({len(rows_by_id)} lecciones)')
    rep_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    if course_dirs:
        print(f'\nCarpetas de curso generadas ({len(course_dirs)}) bajo lessons\\{player_sanitize(args.type_name)}\\ '
              f'(para subir solo una: _subir_lecciones_a_Hetzner.bat "<carpeta>"):')
        for name in list(course_dirs)[:40]:
            print(f'   {name}')
        if len(course_dirs) > 40:
            print(f'   ... y {len(course_dirs) - 40} mas')
    print(f'\nSalida en {out}')


if __name__ == '__main__':
    main()
