"""
joseki_lib.py — Validador y compilador de ficheros maestros de josekis para
TsumeVault. Lo usan import_joseki.py (JSON de la pestaña Joseki) y
generate_joseki_problems.py (problemas de la source `joseki`).

Convierte un SGF de josekis (árbol de variaciones editado con SmartGo, Drago o
GoGrinari) en un JSON normalizado que el cliente solo lee y juega:

    {
      "format": 1, "file": <nombre>, "sgf_hash": <sha256 corto>,
      "size": 19, "description": <comentario raíz o "">,
      "root": {"ch": [<nodo>, ...]}, "ack_root": bool
    }

    nodo     = {"m": "pd"|"pass", "c": "B"|"W", "ch": [...],
                opcionales: "q": "bad"|"doubtful", "te": true, "it": true,
                "implicit": true, "name": str, "comment": str, "ack": true,
                "marks": {"TR": [...], ..., "LB": [[coord, texto], ...]}}
    contexto = {"m": "ctx-…", "c": "", "ctx": {"B": [...], "W": [...]},
                "name": str, "ch": [...], opcionales: "comment", "marks", "ack"}

"ack"/"ack_root" (línea «#ok») solo los usa el generador; el cliente los ignora.

Coordenadas siempre en la orientación del fichero (la rotación es cosa del
cliente). Reutiliza parse_sgf/Node de sgf_lib.py sin modificarlo.
"""

import hashlib
import json

from sgf_lib import SGFParseError, parse_sgf

FORMAT = 1
SIZE = 19
NAME_MAX = 40
COLS = "ABCDEFGHJKLMNOPQRST"  # sin la I, como en los tableros reales
MARK_PROPS = ("TR", "SQ", "CR", "MA")
SETUP_PROPS = ("AB", "AW", "AE")

ERROR = "ERROR"
WARNING = "WARNING"


def other(color):
    return "W" if color == "B" else "B"


# ── Coordenadas ──────────────────────────────────────────────────────────────


def is_pass_value(v):
    """En 19x19, '' y 'tt' son pase (tt es la forma antigua que usa SmartGo)."""
    return v == "" or v == "tt"


def parse_coord(v):
    """'pd' -> (15, 3). None si no es una coordenada válida de 19x19."""
    if len(v) != 2:
        return None
    x, y = ord(v[0]) - 97, ord(v[1]) - 97
    if 0 <= x < SIZE and 0 <= y < SIZE:
        return x, y
    return None


def human(m):
    """'pd' -> 'Q16', 'pass' -> 'pase'."""
    if m == "pass":
        return "pase"
    xy = parse_coord(m)
    if xy is None:
        return m
    return "%s%d" % (COLS[xy[0]], SIZE - xy[1])


# ── Reglas de Go ─────────────────────────────────────────────────────────────


class IllegalMove(Exception):
    pass


def _neighbors(x, y):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < SIZE and 0 <= ny < SIZE:
            yield nx, ny


def _group(board, start):
    color = board[start]
    stones, libs, stack = {start}, set(), [start]
    while stack:
        p = stack.pop()
        for n in _neighbors(*p):
            c = board.get(n)
            if c is None:
                libs.add(n)
            elif c == color and n not in stones:
                stones.add(n)
                stack.append(n)
    return stones, libs


def play(board, color, xy, ko_board):
    """Devuelve el tablero nuevo (dict (x,y)->color) tras jugar `color` en
    `xy`. `ko_board` es el tablero de dos jugadas atrás (ko simple: no se
    puede volver a él). Lanza IllegalMove."""
    if xy in board:
        raise IllegalMove("punto ocupado")
    nb = dict(board)
    nb[xy] = color
    for n in _neighbors(*xy):
        if nb.get(n) == other(color):
            stones, libs = _group(nb, n)
            if not libs:
                for s in stones:
                    del nb[s]
    _, libs = _group(nb, xy)
    if not libs:
        raise IllegalMove("suicidio")
    if ko_board is not None and nb == ko_board:
        raise IllegalMove("ko (recupera el ko inmediatamente)")
    return nb


# ── Utilidades de texto ──────────────────────────────────────────────────────


def norm_comment(c):
    c = c.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in c.split("\n")).strip()


def split_ack(raw_comment):
    """JP.7: una línea que sea solo «#ok» en un comentario acepta los avisos de esa
    jugada (o de la raíz). Se quita del comentario en todos los modos, para que no
    salga en la pestaña Joseki ni en los problemas, ni se tome como nombre.
    Devuelve (comentario_limpio, había_ok)."""
    c = norm_comment(raw_comment or "")
    lines = c.split("\n")
    keep = [l for l in lines if l.strip().lower() != "#ok"]
    return norm_comment("\n".join(keep)), len(keep) != len(lines)


def first_line(comment):
    for line in (comment or "").split("\n"):
        line = line.strip()
        if line:
            return line
    return ""


def path_str(tokens):
    return " ".join(tokens) if tokens else "(raíz)"


# ── Compilador ───────────────────────────────────────────────────────────────


class _State:
    """Estado de la posición al llegar a un nodo."""

    __slots__ = ("board", "prev_board", "last_color", "last_pass", "tokens")

    def __init__(self, board, prev_board, last_color, last_pass, tokens):
        self.board = board            # tablero actual
        self.prev_board = prev_board  # tablero antes de la última jugada
        self.last_color = last_color  # color de la última jugada (None al inicio)
        self.last_pass = last_pass    # la última jugada fue un pase
        self.tokens = tokens          # ruta de jugadas (para mensajes)

    def after_pass(self, color):
        return _State(self.board, self.board, color, True, self.tokens + ["pass"])

    def after_move(self, color, m, new_board):
        return _State(new_board, self.board, color, False, self.tokens + [m])


class _Compiler:
    def __init__(self, file_name):
        self.file_name = file_name
        self.issues = []  # (severidad, ruta, mensaje)

    def issue(self, sev, tokens, msg):
        self.issues.append((sev, path_str(tokens), msg))

    # -- nodos --

    def node(self, src, st):
        """Compila un nodo con jugada. Devuelve el dict o None si es ilegal
        (su subárbol se descarta, los errores ya están anotados)."""
        props = src.props
        color = "B" if "B" in props else "W"
        v = props[color][0] if props[color] else ""
        here = st.tokens + [v or "pass"]

        for sp in SETUP_PROPS:
            if sp in props:
                self.issue(ERROR, here, "piedras de setup (%s) no admitidas en la v1" % sp)

        if is_pass_value(v):
            m = "pass"
            if st.last_color is None:
                self.issue(ERROR, here, "un pase no puede ser la primera jugada del fichero")
                return None
            if st.last_pass:
                self.issue(ERROR, here, "dos pases seguidos")
                return None
            nst = st.after_pass(color)
        else:
            xy = parse_coord(v)
            if xy is None:
                self.issue(ERROR, here, "coordenada no válida: %r" % v)
                return None
            m = v
            try:
                nb = play(st.board, color, xy, st.prev_board)
            except IllegalMove as e:
                self.issue(ERROR, here, "jugada ilegal de %s en %s: %s" % (color, human(m), e))
                return None
            nst = st.after_move(color, m, nb)

        out = {"m": m, "c": color}
        bm, do = "BM" in props, "DO" in props
        if bm and do:
            self.issue(ERROR, here, "BM y DO en el mismo nodo")
        if bm:
            out["q"] = "bad"
        elif do:
            out["q"] = "doubtful"
        if "TE" in props:
            out["te"] = True
            if bm:
                self.issue(WARNING, here, "BM y TE en el mismo nodo")
        if "IT" in props:
            out["it"] = True
        comment, acked = split_ack(src.comment)   # JP.7
        if comment:
            out["comment"] = comment
        if acked:
            out["ack"] = True
        marks = self.marks(props, here)
        if marks:
            out["marks"] = marks

        out["ch"] = self.children(src.children, nst)
        return out

    def marks(self, props, here):
        marks = {}
        for mp in MARK_PROPS:
            vals = props.get(mp)
            if not vals:
                continue
            good = []
            for v in vals:
                if parse_coord(v) is None:
                    self.issue(WARNING, here, "marca %s con coordenada no válida: %r (ignorada)" % (mp, v))
                else:
                    good.append(v)
            if good:
                marks[mp] = good
        # JP.5: letras. L[] (formato antiguo) -> A, B, C… por orden; LB[xx:texto] tal cual
        labels = []
        for i, v in enumerate(props.get("L") or []):
            if parse_coord(v) is None:
                self.issue(WARNING, here, "letra L con coordenada no válida: %r (ignorada)" % v)
            else:
                labels.append([v, chr(65 + i) if i < 26 else "?"])
        for v in props.get("LB") or []:
            xy, _, text = v.partition(":")
            if parse_coord(xy) is None or not text:
                self.issue(WARNING, here, "etiqueta LB no válida: %r (ignorada)" % v)
            else:
                labels.append([xy, text])
        if labels:
            marks["LB"] = labels
        return marks

    def context(self, src, st):
        """JP.4: nodo de contexto (sin jugada, con piedras AB/AW): todo lo que
        cuelga de él supone esas piedras. No cambia el turno."""
        props = src.props
        stones = {"B": sorted(props.get("AB") or []), "W": sorted(props.get("AW") or [])}
        token = "ctx-" + "".join(c + "".join(stones[c]) for c in ("B", "W") if stones[c])
        here = st.tokens + [token]
        if st.last_color is None:
            self.issue(ERROR, here, "contexto antes de la primera jugada")
            return None
        if "AE" in props:
            self.issue(ERROR, here, "contexto con AE (quitar piedras): no admitido")
            return None
        board = dict(st.board)
        for c in ("B", "W"):
            for v in stones[c]:
                xy = parse_coord(v)
                if xy is None:
                    self.issue(ERROR, here, "coordenada no válida: %r" % v)
                    return None
                if xy in board:
                    self.issue(ERROR, here, "piedra de contexto en un punto ocupado: %s" % human(v))
                    return None
                board[xy] = c
        expected = other(st.last_color)
        pl = (props.get("PL") or [""])[0].strip().upper()
        if pl and pl != expected:
            self.issue(WARNING, here, "PL[%s] en el contexto, pero juega %s" % (pl, expected))
        out = {"m": token, "c": "", "ctx": stones}
        comment, acked = split_ack(src.comment)   # JP.7
        if comment:
            out["comment"] = comment
        if acked:
            out["ack"] = True
        nm = first_line(comment)
        if nm:
            out["name"] = nm
        else:
            self.issue(ERROR, here, "contexto sin nombre (primera línea del comentario)")
        marks = self.marks(props, here)
        if marks:
            out["marks"] = marks
        nst = _State(board, None, st.last_color, st.last_pass, here)
        out["ch"] = self.children(src.children, nst)
        return out

    # -- hijos --

    def children(self, srcs, st):
        out = []            # lista de hijos compilados (o el marcador del pase implícito)
        implicit = []       # hijos IT del mismo color que la última jugada
        implicit_at = None  # posición del pase implícito (orden del fichero)

        for s in srcs:
            props = s.props
            has_b, has_w = "B" in props, "W" in props
            if has_b and has_w:
                self.issue(ERROR, st.tokens, "nodo con jugada de B y de W a la vez")
                continue
            if not has_b and not has_w:
                if "AB" in props or "AW" in props or "AE" in props:  # JP.4: nodo de contexto
                    out.append(self.context(s, st))
                    continue
                self.issue(ERROR, st.tokens, "nodo sin jugada (solo comentario o propiedades)")
                continue
            color = "B" if has_b else "W"
            if st.last_color is not None and color == st.last_color:
                if "IT" in props:
                    if implicit_at is None:
                        implicit_at = len(out)
                        out.append(None)  # hueco para el pase implícito
                    implicit.append(s)
                else:
                    v = props[color][0] if props[color] else ""
                    self.issue(ERROR, st.tokens + [v or "pass"],
                               "dos jugadas seguidas de %s sin IT (alternancia rota)" % color)
                continue
            out.append(self.node(s, st))

        if implicit:
            pc = other(st.last_color)
            if st.last_pass:
                self.issue(ERROR, st.tokens + ["pass"],
                           "tenuki implícito tras un pase: serían dos pases seguidos")
                out[implicit_at] = None
            else:
                pst = st.after_pass(pc)
                out[implicit_at] = {
                    "m": "pass", "c": pc, "implicit": True, "it": True,
                    "ch": [n for n in (self.node(s, pst) for s in implicit) if n is not None],
                }

        out = [n for n in out if n is not None]
        seen = {}
        for n in out:
            key = (n["m"], n["c"])
            if key in seen:
                if n["m"] == "pass" and (n.get("implicit") or seen[key].get("implicit")):
                    self.issue(ERROR, st.tokens,
                               "pase explícito y tenuki implícito (IT del mismo color) en el mismo "
                               "nodo: cuelga la rama IT del pase explícito")
                else:
                    self.issue(ERROR, st.tokens + [n["m"]], "jugada repetida entre hermanos")
            else:
                seen[key] = n
        return out


# ── Nombres de variante ──────────────────────────────────────────────────────


def _assign_names(node, tokens, issues):
    kids = node["ch"]
    good_main = [k for k in kids if not k.get("it") and "q" not in k and "ctx" not in k]
    needs = []
    if len(good_main) >= 2:
        needs += [(k, "rama de bifurcación") for k in good_main]
    needs += [(k, "rama ¿y si…? (IT)") for k in kids if k.get("it") and not k.get("implicit")]
    if needs:
        names = {}
        for k, what in needs:
            here = path_str(tokens + [k["m"]])
            nm = first_line(k.get("comment"))
            if not nm:
                issues.append((WARNING, here, "%s sin nombre (primera línea del comentario)" % what))
                continue
            if len(nm) > NAME_MAX:
                issues.append((WARNING, here,
                               "nombre de %d caracteres (máx. %d): ¿es una explicación y no un nombre?"
                               % (len(nm), NAME_MAX)))
            if nm.lower() in names:
                issues.append((WARNING, here, "nombre repetido entre hermanas: %r" % nm))
            names[nm.lower()] = True
            k["name"] = nm
    for k in kids:
        _assign_names(k, tokens + [k["m"]], issues)


# ── Finales de línea ─────────────────────────────────────────────────────────


def is_endpoint(node):
    """Final de línea: nodo sin hijos que no sean ramas ¿y si…? (J-71).
    Un pase implícito nunca es final: es solo preparación de sus ramas IT."""
    if node.get("implicit"):
        return False
    return not any(not k.get("it") for k in node["ch"])


def count_lines(root):
    """Número de líneas (finales de línea) del árbol."""
    return sum(is_endpoint(k) + count_lines(k) for k in root["ch"])


# ── Informe del árbol ────────────────────────────────────────────────────────


def _token(n, num):
    if "ctx" in n:  # JP.4
        st = " ".join("%s:%s" % (c, ",".join(human(v) for v in n["ctx"][c])) for c in ("B", "W") if n["ctx"][c])
        return "%d.[contexto %s] [%s]" % (num, st, n.get("name", "?"))
    t = "%d.%s %s" % (num, n["c"], human(n["m"]))
    if n.get("implicit"):
        t += " (implícito)"
    flags = []
    if n.get("q") == "bad":
        flags.append("BM")
    elif n.get("q") == "doubtful":
        flags.append("DO")
    if n.get("te"):
        flags.append("TE")
    if n.get("it") and not n.get("implicit"):
        flags.append("IT")
    if flags:
        t += " " + "+".join(flags)
    if n.get("name"):
        t += " [%s]" % n["name"]
    return t


def render_tree(root):
    lines = []

    def segment(node, num):
        toks, n = [], node
        while True:
            toks.append(_token(n, num))
            if len(n["ch"]) != 1 or n["ch"][0].get("it"):   # un final de línea siempre corta aquí
                break
            n, num = n["ch"][0], num + 1
        text = "  ".join(toks)
        if is_endpoint(n):
            text += "  => fin"
        return text, n, num

    def emit(kids, indent, num):
        many = len(kids) > 1
        for i, k in enumerate(kids):
            last = i == len(kids) - 1
            text, end, endnum = segment(k, num)
            lines.append(indent + ("+- " if many else "") + text)
            sub = indent + (("   " if last else "|  ") if many else "")
            emit(end["ch"], sub, endnum + 1)

    emit(root["ch"], "  ", 1)
    return lines


# ── API pública ──────────────────────────────────────────────────────────────


def compile_joseki(raw_bytes, file_name):
    """Compila los bytes de un SGF de josekis. Devuelve:
        {
          "ok": bool,               # False si hay algún ERROR
          "issues": [(sev, ruta, msg), ...],
          "tree": [str, ...],       # informe del árbol (vacío si no compila)
          "data": dict | None,      # JSON listo para serializar (None si no ok)
          "lines": int,             # nº de líneas (finales de línea)
        }
    Compila también los nodos de contexto (JP.4) y las letras L/LB (JP.5); lo mismo
    para la pestaña Joseki y para el generador de problemas.
    """
    issues = []

    def fail():
        return {"ok": False, "issues": issues, "tree": [], "data": None, "lines": 0}

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        issues.append((ERROR, "(fichero)", "no es UTF-8 válido: %s" % e))
        return fail()
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        src_root = parse_sgf(text)
    except (SGFParseError, IndexError) as e:
        issues.append((ERROR, "(fichero)", "no se puede parsear el SGF: %s" % e))
        return fail()

    rp = src_root.props
    sz = rp.get("SZ")
    if not sz:
        issues.append((WARNING, "(raíz)", "falta SZ: se asume 19x19"))
    elif sz[0].strip() != "19":
        issues.append((ERROR, "(raíz)", "tablero de %s: solo se admite 19x19" % sz[0]))
        return fail()
    ca = (rp.get("CA") or [""])[0].strip().upper()
    if ca not in ("UTF-8", "UTF8"):
        issues.append((WARNING, "(raíz)",
                       "falta CA[UTF-8]: añádelo o los acentos de los comentarios pueden romperse"))

    comp = _Compiler(file_name)
    root_ack = False
    start = _State({}, None, None, False, [])
    has_move = "B" in rp or "W" in rp
    if has_move:
        # Algunos editores guardan la primera jugada en el nodo raíz.
        description = ""
        top = comp.children([src_root], start)
    else:
        for sp in SETUP_PROPS:
            if sp in rp:
                comp.issue(ERROR, [], "piedras de contexto (%s) en la raíz: no admitidas en la v1" % sp)
        description, root_ack = split_ack(src_root.comment)   # JP.7
        top = comp.children(src_root.children, start)
    issues.extend(comp.issues)

    root = {"ch": top}
    if not top and not any(s == ERROR for s, _, _ in issues):
        issues.append((ERROR, "(raíz)", "el fichero no contiene jugadas"))

    if any(s == ERROR for s, _, _ in issues):
        return fail()

    _assign_names(root, [], issues)
    tree = render_tree(root)

    data = {
        "format": FORMAT,
        "file": file_name,
        "sgf_hash": hashlib.sha256(raw_bytes).hexdigest()[:16],
        "size": SIZE,
        "description": description,
        "root": root,
    }
    # JP.7: «#ok» en el comentario de la raíz (o de la 1.ª jugada si va en la raíz)
    data["ack_root"] = bool(root_ack or (has_move and top and top[0].get("ack")))
    return {"ok": True, "issues": issues, "tree": tree, "data": data, "lines": count_lines(root)}


def serialize(data):
    """JSON compacto y determinista (sin marcas de tiempo) para hash estable."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def content_hash(blob):
    return hashlib.sha256(blob).hexdigest()[:16]
