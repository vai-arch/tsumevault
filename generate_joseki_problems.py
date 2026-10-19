#!/usr/bin/env python3
"""
generate_joseki_problems.py — JP1: convierte los ficheros maestros de josekis
(joseki/*.sgf) en problemas de tsumego normales de la source `joseki`, y los
publica con el mismo endpoint que import_my_collections.py
(/admin/import_my_collection), con retirada automática de los que ya no
existen (retire_missing). Ver WORKPLAN_JOSEKI_PROBLEMS.md.

Organización:
    source      joseki
    colección   un fichero maestro            (p. ej. "4-4 Joseki")
    capítulo    familia × color               (p. ej. "Keima Approach · B")
                familia = nombre (1.ª línea del comentario) de la 2.ª jugada
    problema    una línea y un color (o un tramo, si tu tenuki la corta)
    fichero     joseki_problems/<fichero>/<B|W>-<jugadas>.sgf   (ruta estable)
    problem_id  <fichero>/<B|W>-<jugadas>  (jugadas SGF seguidas, pase = tt)

Uso (desde la carpeta del proyecto, en Windows igual):
    python generate_joseki_problems.py joseki joseki_problems --dry-run
    python generate_joseki_problems.py joseki joseki_problems --no-publish
    (subir con el .bat)
    python generate_joseki_problems.py joseki joseki_problems

Opciones: --server URL (por defecto http://localhost:3002), --token T (o la
variable TSUMEVAULT_TOKEN), --source NAME (por defecto joseki), --dry-run (no
escribe ni publica), --no-publish (escribe pero no publica), --aceptar-avisos
(JP.8: añade «#ok» en el SGF maestro a los avisos de «castigo sin castigo» y
«línea sin problema nuevo»; con --dry-run solo enseña dónde; deja copia .bak).

Códigos de salida: 0 bien; 1 errores (no se escribe ni publica nada) o el
servidor rechazó la carga; 2 uso incorrecto.
"""
import argparse
import os
import sys

import re

from joseki_lib import ERROR, IllegalMove, compile_joseki, first_line, human, is_endpoint, norm_comment, parse_coord, play
from sgf_lib import parse_sgf, validate_problem

try:  # el script de Victor se llama import_my_collections.py (su docstring dice import_my_collection.py)
    from import_my_collections import kyu_dan_to_num, post_import
except ImportError:  # pragma: no cover
    from import_my_collection import kyu_dan_to_num, post_import

SOURCE = "joseki"
SGF_PREFIX = "joseki_problems"
DIFFICULTY_RAW = "10k"
DIFFICULTY_NUM = kyu_dan_to_num("difficulty-" + DIFFICULTY_RAW)
COLOR_NAME = {"B": "B", "W": "W"}


class GeneratorError(Exception):
    """Fallo interno: un SGF generado no pasa validate_problem. Nunca debería
    ocurrir; si ocurre no se escribe ni publica nada."""


# ── utilidades ───────────────────────────────────────────────────────────────

def esc(text):
    """Escapa texto para un valor SGF C[...]."""
    return text.replace("\\", "\\\\").replace("]", "\\]")


def coord(m):
    return "" if m == "pass" else m


def compact(tokens):
    return "".join("tt" if t == "pass" else t for t in tokens)


def is_pass(node):
    return node["m"] == "pass"


def is_ctx(node):
    """JP.4: nodo de contexto (piedras añadidas, sin jugada)."""
    return "ctx" in node


def is_player_stone(node, color):
    return node["c"] == color and not node.get("implicit") and not is_pass(node)


def safe_mid(text):
    """Un comentario intermedio no puede empezar por RIGHT/WRONG (el motor
    cerraría ahí el problema): se antepone un punto medio."""
    t = text.lstrip().upper()
    if t.startswith("RIGHT") or t.startswith("WRONG"):
        return "· " + text
    return text


def instruction(parent, node, color):
    """('whatif'|'choice', nombre) si tu jugada `node` necesita instrucción;
    None si no. Los nombres vacíos se devuelven como '' para dar error."""
    if node.get("it"):
        return ("whatif", first_line(node.get("comment")))
    good = [k for k in parent["ch"]
            if k["c"] == color and not k.get("implicit") and "q" not in k and not k.get("it")]
    if len(good) >= 2:
        return ("choice", first_line(node.get("comment")))
    return None


def instruction_text(ins):
    kind, name = ins
    return ("→ ¿Y si…? " if kind == "whatif" else "→ Ahora: ") + name


def marks_props(node):
    out = ""
    for mp, vals in sorted((node.get("marks") or {}).items()):
        if mp == "LB":  # JP.5: letras [coord, texto]
            out += "LB" + "".join("[%s:%s]" % (v[0], esc(v[1])) for v in vals)
        else:
            out += mp + "".join("[%s]" % v for v in vals)
    return out


def quality_props(node):
    """T33: marcas de calidad del maestro, para que el cliente pinte su símbolo
    en la última jugada (IT ?, BM ✕, DO ▲, TE ★). El pase implícito no es una
    jugada del fichero y no lleva IT."""
    out = ""
    if node.get("it") and not node.get("implicit"):
        out += "IT[]"
    if node.get("q") == "bad":
        out += "BM[1]"
    elif node.get("q") == "doubtful":
        out += "DO[1]"
    if node.get("te"):
        out += "TE[1]"
    return out


def resolve(root, tokens):
    nodes, cur = [], root
    for t in tokens:
        cur = next(k for k in cur["ch"] if k["m"] == t)
        nodes.append(cur)
    return nodes


# ── informe legible (Victor, 19-oct: el log tiene que decir qué arreglar y dónde) ──

COLOR_ES = {"B": "negro", "W": "blanco"}


def issue(sev, where, problem, fix="", after=False):
    """sev: 'fix' (bloquea) | 'warn' (no bloquea). where: lista de jugadas SGF
    desde el principio ('pass' = pase), 'raiz' o 'fichero'. after=True: el
    fallo está justo DESPUÉS de esa jugada (p. ej. un nodo vacío)."""
    return {"sev": sev, "where": where, "problem": problem, "fix": fix, "after": after}


def _raw_moves(raw_root):
    """Primeras jugadas del SGF crudo (sgf_lib): la raíz si ya trae jugada."""
    if raw_root is None:
        return []
    if "B" in raw_root.props or "W" in raw_root.props:
        return [raw_root]
    return list(raw_root.children)


def fmt_path(tokens, raw_root=None):
    """['qd','qc'] -> '1.B R16  2.W R17'. El color sale del SGF crudo; un pase
    que no está en el fichero es el tenuki implícito que añade el compilador."""
    out, cands, last = [], _raw_moves(raw_root), None
    for i, t in enumerate(tokens, 1):
        if t.startswith("ctx-"):  # JP.4: nodo de contexto
            ctxn = next((c for c in cands if "B" not in c.props and "W" not in c.props
                         and ("AB" in c.props or "AW" in c.props)), None)
            stones = ",".join(human(v) for k in ("AB", "AW") for v in (ctxn.props.get(k, []) if ctxn else []))
            out.append("%d.[contexto %s]" % (i, stones))
            cands = list(ctxn.children) if ctxn else []
            continue
        match = None
        expected = ("B" if last == "W" else "W") if last else None
        for c in cands:
            col = "B" if "B" in c.props else ("W" if "W" in c.props else None)
            if col is None:
                continue
            v = (c.props[col][0] if c.props[col] else "")
            if (t == "pass" and v in ("", "tt")) or v == t:
                # JP.6: si hay varias ramas con la misma coordenada (p. ej. R18 de blanco IT y
                # R18 de negro), manda la del color al que le toca.
                if match is None or (col == expected and match[1] != expected):
                    match = (c, col)
        if match:
            node, col = match
            out.append("%d.%s %s" % (i, col, human(t)))
            cands, last = list(node.children), col
        elif t == "pass" and last:
            col = "B" if last == "W" else "W"
            out.append("%d.%s tenuki (implícito)" % (i, col))
            last = col          # las ramas IT cuelgan del mismo nodo: no se avanza en el crudo
        else:
            out.append("%d.%s" % (i, human(t)))
            cands = []
    return "  ".join(out)


def _j1_issue(sev, path, msg, root_setup):
    """Traduce un aviso/error del compilador J1 (joseki_lib) a issue()."""
    sev = "fix" if sev == ERROR else "warn"
    where = "fichero" if path == "(fichero)" else ("raiz" if path == "(raíz)" else path.split())
    m = re.match(r"piedras de contexto \((\w+)\) en la raíz", msg)
    if m:
        stones = " ".join(human(v) for v in root_setup.get(m.group(1), []))
        prop = m.group(1)
        return issue(sev, "raiz",
                     "La piedra inicial (%s) está COLOCADA como piedra de inicio (%s en la raíz), no JUGADA. "
                     "Drago lo hace si la pones en modo «añadir piedra»." % (stones or "?", prop),
                     "Con un editor de texto, al principio del fichero cambia %s[..] por ;%s[..] "
                     "(p. ej. AB[qd] → ;B[qd]). O en Drago: bórrala y juégala como primera jugada."
                     % (prop, "B" if prop == "AB" else "W"))
    if msg.startswith("nodo sin jugada"):
        return issue(sev, where, "Justo después de esta jugada hay un NODO VACÍO (sin piedra; solo comentario o marcas).",
                     "En Drago ve a esa jugada, avanza una y borra el nodo vacío. Si tenía un comentario útil, "
                     "cópialo antes a la jugada anterior o a la siguiente.", after=True)
    m = re.match(r"dos jugadas seguidas de (\w) sin IT", msg)
    if m:
        return issue(sev, where, "Dos jugadas seguidas de %s (falta la del otro color)." % COLOR_ES[m.group(1)],
                     "Si es un «¿y si?» con tenuki del rival, marca la segunda con IT; si no, falta una jugada o un pase entre medias.")
    m = re.match(r"(rama de bifurcación|rama ¿y si…\? \(IT\)) sin nombre", msg)
    if m:
        what = "Hay varias jugadas buenas en este punto" if m.group(1).startswith("rama de bif") else "Es una rama ¿y si? (IT)"
        return issue(sev, where, "%s y esta no tiene nombre." % what,
                     "Solo es obligatorio si te toca jugarla en un problema: entonces sale también en HAY QUE ARREGLAR.")
    m = re.match(r"nombre repetido entre hermanas: '(.*)'", msg)
    if m:
        return issue(sev, where, "Dos variantes de este mismo punto empiezan con la misma primera línea «%s»: "
                     "si te toca jugarlas, la instrucción sería idéntica y no sabrías cuál." % m.group(1),
                     "Haz distinta la primera línea de una de las dos.")
    m = re.match(r"nombre de (\d+) caracteres", msg)
    if m:
        return issue(sev, where, "La primera línea del comentario es larga (%s caracteres) y se usa como nombre." % m.group(1),
                     "Pon solo el nombre en la línea 1 y la explicación en la línea 2.")
    if msg.startswith("línea sin tarjetas"):
        return issue(sev, where, "Esta línea no genera ningún problema: los dos colores juegan alguna jugada mala/dudosa (BM/DO).",
                     "Normal si es un error de ambos; si no, revisa las marcas.")
    # JP.4/JP.5: contexto y letras
    if msg.startswith("contexto sin nombre"):
        return issue(sev, where, "Este nodo de contexto (piedras añadidas) no tiene nombre.",
                     "Escribe el nombre del contexto en la PRIMERA línea de su comentario (p. ej. «Negro tiene N17»).")
    m = re.match(r"piedra de contexto en un punto ocupado: (\S+)", msg)
    if m:
        return issue(sev, where, "Una piedra de contexto está en %s, que ya está ocupado." % m.group(1),
                     "Quita esa piedra del contexto o muévela a un punto libre.")
    if msg.startswith("contexto con AE"):
        return issue(sev, where, "El contexto QUITA piedras (AE): no se admite.", "Usa solo piedras añadidas (AB/AW).")
    if msg.startswith("contexto antes de la primera jugada"):
        return issue(sev, where, "Hay un contexto antes de la primera jugada.", "El contexto tiene que ir después de alguna jugada.")
    m = re.match(r"PL\[(\w+)\] en el contexto, pero juega (\w)", msg)
    if m:
        return issue(sev, where, "El contexto dice que juega %s (PL), pero por el orden de jugadas le toca a %s."
                     % (COLOR_ES.get(m.group(1), m.group(1)), COLOR_ES[m.group(2)]),
                     "Se ignora el PL; revísalo si el contexto debía cambiar el turno.")
    if msg.startswith("letra L con coordenada") or msg.startswith("etiqueta LB no válida"):
        return issue(sev, where, "Una letra del tablero tiene una coordenada o texto no válidos y se ignora.", "Vuelve a ponerla en Drago.")
    if msg.startswith("falta CA[UTF-8]"):
        return issue(sev, "raiz", "Falta CA[UTF-8]: los acentos de los comentarios podrían verse mal.",
                     "Con un editor de texto añade CA[UTF-8] justo después de FF[4].")
    known = {
        "BM y DO en el mismo nodo": "Deja solo una de las dos marcas (mala o dudosa).",
        "BM y TE en el mismo nodo": "Tiene marca de mala y de buena a la vez: deja una.",
        "nodo con jugada de B y de W a la vez": "Un nodo tiene dos piedras: sepáralas en dos jugadas.",
        "jugada repetida entre hermanos": "La misma jugada aparece dos veces como variante en el mismo punto: fusiónalas.",
        "dos pases seguidos": "Quita uno de los dos pases.",
        "un pase no puede ser la primera jugada del fichero": "Empieza el fichero con una jugada.",
        "el fichero no contiene jugadas": "Comprueba que has guardado el fichero correcto.",
    }
    for k, fx in known.items():
        if msg.startswith(k):
            return issue(sev, where, msg[0].upper() + msg[1:] + ".", fx)
    return issue(sev, where, msg[0].upper() + msg[1:] + ".",
                 "Vuelve a guardarlo desde Drago." if where == "fichero" else "")


def _node_at(data, tokens):
    try:
        return resolve(data["root"], tokens)[-1] if tokens else None
    except StopIteration:
        return None


def _apply_ack(items, data):
    """JP.7: oculta los AVISOS de una jugada cuyo comentario lleva una línea «#ok»
    (o de la raíz). Los HAY QUE ARREGLAR nunca se ocultan. Devuelve
    (items, nº de avisos ocultados, jugadas con #ok que no tapan ningún aviso)."""
    keep, hidden, used = [], set(), set()
    for it in items:
        if it["sev"] == "warn":
            w = it["where"]
            if w == "raiz" and data.get("ack_root"):
                hidden.add(("raiz", it["problem"]))
                used.add(("raiz",))
                continue
            if isinstance(w, list):
                n = _node_at(data, w)
                if n is not None and n.get("ack"):
                    hidden.add((tuple(w), it["problem"]))
                    used.add(tuple(w))
                    continue
        keep.append(it)
    acks = []

    def walk(node, path):
        for k in node["ch"]:
            p = path + [k["m"]]
            if k.get("ack"):
                acks.append(p)
            walk(k, p)
    walk(data["root"], [])
    unused = [a for a in acks if tuple(a) not in used]
    return keep, len(hidden), unused


def _explain_no_problem(it, data):
    """JP.7: «línea sin problema» con el motivo concreto en vez del texto genérico de J1."""
    if not (it["problem"].startswith("Esta línea no genera ningún problema") and isinstance(it["where"], list)):
        return it
    try:
        nodes = resolve(data["root"], it["where"])
    except StopIteration:
        return it
    last = nodes[-1]
    if last.get("q") == "bad" and last["c"]:
        prob = ("Esta línea no añade ningún problema nuevo: las jugadas buenas de antes ya se practican en otras líneas "
                "y acaba en el error de %s (%s) sin la respuesta que lo castiga." % (COLOR_ES[last["c"]], human(last["m"])))
        fix = ("Si quieres practicar ese castigo, añade la respuesta después de %s; si no, añade una línea «#ok» "
               "en el comentario de %s." % (human(last["m"]), human(last["m"])))
    else:
        prob = ("Esta línea no añade ningún problema nuevo: las jugadas buenas ya se practican en otras líneas "
                "y lo demás son jugadas después de un error propio.")
        fix = "Normal en líneas de errores; para no ver este aviso, añade una línea «#ok» en el comentario de %s." % human(last["m"])
    return dict(it, problem=prob, fix=fix, okable=True)   # JP.8: --aceptar-avisos puede ponerle #ok


def print_report(out, items, raw_root):
    """Bloques HAY QUE ARREGLAR / AVISOS, sin duplicados (un mensaje por jugada)."""
    seen, fixes, warns = set(), [], []
    for it in items:
        key = (it["sev"], tuple(it["where"]) if isinstance(it["where"], list) else it["where"], it["problem"])
        if key in seen:
            continue
        seen.add(key)
        (fixes if it["sev"] == "fix" else warns).append(it)
    fix_where = {tuple(i["where"]) for i in fixes if isinstance(i["where"], list)}
    warns = [w for w in warns if not (isinstance(w["where"], list) and tuple(w["where"]) in fix_where)]

    def where_txt(it):
        w = it["where"]
        if w == "raiz":
            return "Inicio del fichero"
        if w == "fichero":
            return "El fichero"
        return ("Justo después de: " if it["after"] else "Jugada: ") + (fmt_path(w, raw_root) or "(inicio)")
    if fixes:
        out("HAY QUE ARREGLAR (%d)" % len(fixes))
        for n, it in enumerate(fixes, 1):
            out(" %d. %s" % (n, where_txt(it)))
            out("    Problema: " + it["problem"])
            if it["fix"]:
                out("    Arreglo:  " + it["fix"])
    if warns:
        out("AVISOS, no bloquean (%d)" % len(warns))
        for it in warns:
            out(" - %s" % where_txt(it))
            out("   " + it["problem"] + ((" → " + it["fix"]) if it["fix"] else ""))
    return len(fixes)


# ── tramos de una línea ──────────────────────────────────────────────────────

def segments(nodes, color, after=None):
    """Tramos jugables de una línea para `color`: [(inicio, fin, corte)].
    inicio = índice de tu jugada con piedra en la que empiezas; tu PRIMERA
    jugada con piedra de la línea va siempre puesta, con la respuesta del rival
    (Victor, 19-oct: con blancas no estaba claro dónde poner la aproximación;
    con negras la 1.ª ya era la piedra del fichero). Así B empieza tras Q16+O17
    y W tras Q16+O17+la respuesta de negro.
    fin = último nodo del problema; corte = None | 'tenuki' (tu pase) |
    'implicit' (pase implícito de tu color: solo prepara una rama ¿y si?, el
    tramo previo ya lo cubre otra línea y no se genera)."""
    first = next((j for j in range(len(nodes)) if is_player_stone(nodes[j], color)), None)
    if after is not None:   # JP.6 (A): todo hasta `after` (tu último error) va puesto
        first = after
    if first is None:
        return []
    out, pos = [], first + 1
    while True:
        s = next((j for j in range(pos, len(nodes)) if is_player_stone(nodes[j], color)), None)
        if s is None:
            return out
        cut, e = None, len(nodes) - 1
        for k in range(s + 1, len(nodes)):
            if nodes[k]["c"] == color and is_pass(nodes[k]):
                # JP.2: un tenuki tuyo marcado IT es un «¿y si…?», no la jugada recomendada:
                # como el implícito, no genera el tramo previo (acabaría en «→ Ahora tenuki»).
                cut, e = ("implicit" if (nodes[k].get("implicit") or nodes[k].get("it")) else "tenuki"), k - 1
                break
        # JP.4: el motor no puede añadir piedras a mitad de problema → se empieza tras el
        # último contexto del tramo (lo anterior se practica en la rama sin contexto).
        ctxs = [j for j in range(s, e + 1) if is_ctx(nodes[j])]
        if ctxs:
            s = next((j for j in range(ctxs[-1] + 1, e + 1) if is_player_stone(nodes[j], color)), None)
        if s is not None:
            out.append((s, e, cut))
        if cut is None:
            return out
        pos = e + 2


# ── un problema ──────────────────────────────────────────────────────────────

def build_sgf(stem, color, nodes, s, e, cut, errors, where, note=None, tri=()):
    # posición inicial: las jugadas anteriores a tu primera jugada del tramo
    board, prev = {}, None
    for n in nodes[:s]:
        if is_ctx(n):  # JP.4: piedras de contexto (sin capturas ni ko)
            for c in ("B", "W"):
                for v in n["ctx"][c]:
                    board[parse_coord(v)] = c
            prev = None
            continue
        if is_pass(n):
            continue
        try:
            nb = play(board, n["c"], parse_coord(n["m"]), prev)
        except IllegalMove as ex:  # pragma: no cover (J1 ya lo valida)
            raise GeneratorError("%s: jugada ilegal en la posición inicial: %s" % (" ".join(where), ex))
        prev, board = board, nb
    ab = sorted("%s%s" % (chr(97 + x), chr(97 + y)) for (x, y), c in board.items() if c == "B")
    aw = sorted("%s%s" % (chr(97 + x), chr(97 + y)) for (x, y), c in board.items() if c == "W")
    ctx_nodes = [n for n in nodes[:s] if is_ctx(n)]
    last = next(n for n in reversed(nodes[:s]) if not is_ctx(n))   # última jugada (o pase) puesta

    def need(k):
        ins = instruction(nodes[k - 1], nodes[k], color)
        if ins and not ins[1]:
            n = nodes[k]
            if ins[0] == "choice":
                goods = [human(x["m"]) for x in nodes[k - 1]["ch"]
                         if x["c"] == color and not x.get("implicit") and "q" not in x and not x.get("it")]
                prob = ("En la jugada %d %s tiene varias jugadas buenas (%s) y %s no tiene nombre: "
                        "el problema no podría decirte cuál jugar." % (k + 1, COLOR_ES[color], ", ".join(goods), human(n["m"])))
            else:
                prob = ("La jugada %d (%s %s) abre una rama ¿y si? (IT) que te toca jugar y no tiene nombre: "
                        "el problema no podría decirte que la juegues." % (k + 1, COLOR_ES[color], human(n["m"])))
            errors.append(issue("fix", [x["m"] for x in nodes[:k + 1]], prob,
                                "Escribe su nombre en la PRIMERA línea del comentario de %s %s." % (COLOR_ES[color], human(n["m"]))))
        return ins

    head = ["%s · Juegas %s" % (stem, color)]
    if note:  # JP.6
        head.append(note)
    own_passes = [n for n in nodes[1:s] if n["c"] == color and is_pass(n)]
    if own_passes:
        lp = own_passes[-1]
        if lp.get("it") and not lp.get("implicit"):   # JP.2: tenuki tuyo como «¿y si…?»
            nm = first_line(lp.get("comment"))
            head.append("¿Y si haces tenuki?" + ((" " + nm) if nm else ""))
        else:
            head.append("(Tras tu tenuki)")
    for cn in ctx_nodes:  # JP.4: «Contexto: <nombre>» + el resto de su comentario (el escenario va primero)
        lines = (cn.get("comment") or "").split("\n")
        head.append("Contexto: " + (cn.get("name") or "?") + ("\n" + "\n".join(lines[1:]) if len(lines) > 1 else ""))
    ctx = norm_comment(last.get("comment") or "")
    if is_pass(last):
        ctx = "Tenuki." + ((" " + ctx) if ctx else "")
    if ctx:
        head.append(ctx)
    ins0 = need(s)
    if ins0:
        head.append(instruction_text(ins0))
    root = "(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[%s]" % color
    if ab:
        root += "AB" + "".join("[%s]" % v for v in ab)
    if aw:
        root += "AW" + "".join("[%s]" % v for v in aw)
    if not is_pass(last):
        root += "CR[%s]" % last["m"]
    # JP.5: letras de la última jugada puesta y de los contextos; JP.4: cuadrado en las
    # piedras de contexto que no tengan letra.
    labels = [l for n in [last] + ctx_nodes for l in ((n.get("marks") or {}).get("LB") or [])]
    lab_at = {l[0] for l in labels}
    sq = sorted(v for cn in ctx_nodes for c in ("B", "W") for v in cn["ctx"][c] if v not in lab_at and v in ab + aw)
    if sq:
        root += "SQ" + "".join("[%s]" % v for v in sq)
    tri = sorted(v for v in tri if v not in lab_at and v != last["m"])   # JP.6: tus errores ya puestos
    if tri:
        root += "TR" + "".join("[%s]" % v for v in tri)
    if labels:
        root += "LB" + "".join("[%s:%s]" % (l[0], esc(l[1])) for l in labels)
    root += "C[%s]" % esc(safe_mid("\n".join(head)))

    def comment_for(k):
        n = nodes[k]
        base = norm_comment(n.get("comment") or "")
        if is_pass(n):
            base = "Tenuki." + ((" " + base) if base else "")
        parts = [base] if base else []
        if k == e:
            if cut == "tenuki":
                nxt = norm_comment(nodes[e + 1].get("comment") or "")
                parts.append("→ Ahora tenuki" + ((". " + nxt) if nxt else ""))
            return "RIGHT" + (("\n" if parts else "") + "\n".join(parts))
        if k + 1 <= e and nodes[k + 1]["c"] == color:
            ins = need(k + 1)
            if ins:
                parts.append(instruction_text(ins))
        return safe_mid("\n".join(parts))

    def wrongs(k):
        n, parent = nodes[k], nodes[k - 1]
        out = []
        for sib in parent["ch"]:
            if sib is n or not is_player_stone(sib, color) or sib.get("q") not in ("bad", "doubtful"):
                continue
            txt = norm_comment(sib.get("comment") or "")
            if sib.get("q") == "doubtful":
                txt = "Dudosa." + ((" " + txt) if txt else "")
            out.append(";%s[%s]%s%sC[%s]" % (sib["c"], sib["m"], marks_props(sib), quality_props(sib),
                                           esc("WRONG" + ((" " + txt) if txt else ""))))
        return out

    def chain(k):
        n = nodes[k]
        txt = comment_for(k)
        here = ";%s[%s]%s%s" % (n["c"], coord(n["m"]), marks_props(n), quality_props(n)) + ("C[%s]" % esc(txt) if txt else "")
        rest = chain(k + 1) if k < e else ""
        nxt_w = wrongs(k + 1) if k < e and nodes[k + 1]["c"] == color else []
        if nxt_w:
            return here + "(" + rest + ")" + "".join("(" + w + ")" for w in nxt_w)
        return here + rest

    first_w = wrongs(s)
    body = chain(s)
    if first_w:
        body = "(" + body + ")" + "".join("(" + w + ")" for w in first_w)
    return root + body + ")\n"


def generate_file(data, stem):
    """Problemas de un fichero maestro ya compilado por joseki_lib.
    Devuelve (problemas, errores, avisos); problemas = lista de dicts
    {problem_id, color, chapter, rel_path, sgf, order}."""
    root = data["root"]
    errors, warnings, problems, seen = [], [], [], set()
    chap_count = {}

    def emit(nodes, color, family, segs, where, note=None, tri=(), line=None):
        for s, e, cut in segs:
            if cut == "implicit":
                continue
            pid_tokens = [n["m"] for n in nodes[:e + 1]]
            name = "%s-%s" % (color, compact(pid_tokens))
            pid = "%s/%s" % (stem, name)
            if pid in seen:
                continue
            seen.add(pid)
            sgf = build_sgf(stem, color, nodes, s, e, cut, errors, where, note=note, tri=tri)
            chapter = "%s · %s" % (family, color)
            chap_count[chapter] = chap_count.get(chapter, 0) + 1
            problems.append({"problem_id": pid, "color": color, "chapter": chapter,
                             "rel_path": "%s/%s.sgf" % (stem, name), "sgf": sgf,
                             "order": chap_count[chapter], "tokens": pid_tokens, "line": line})

    for card in data["cards"]:
        color, tokens = card["color"], card["path"]
        nodes = resolve(root, tokens)
        where = list(tokens)
        if len(nodes) < 2:
            errors.append(issue("fix", where[:1], "Esta línea tiene una sola jugada: no hay familia ni problema.",
                                "Añade la continuación o borra la línea."))
            continue
        i1 = next((i for i in range(1, len(nodes)) if not is_ctx(nodes[i])), 1)
        family = first_line(nodes[i1].get("comment"))
        if not family:
            n1 = nodes[i1]
            errors.append(issue("fix", where[:i1 + 1],
                                "%s %s empieza una familia (es el nombre del capítulo) y no tiene nombre."
                                % (COLOR_ES[n1["c"]].capitalize(), human(n1["m"])),
                                "Escribe el nombre de la familia en la PRIMERA línea de su comentario (p. ej. «3-3 Invasion»)."))
            family = "?"   # se sigue revisando la línea para dar TODOS los errores de una vez (no se publica nada)
        last = nodes[-1]
        if last["c"] != color and last.get("q") == "bad":
            warnings.append(dict(okable=True, **issue("warn", where,
                                  "Línea de castigo para %s que acaba en el error del rival (%s), sin tu jugada de castigo: "
                                  "el problema solo enseña el error." % (COLOR_ES[color], human(last["m"])),
                                  "Si quieres practicar el castigo, añade tu respuesta después del error; si te vale "
                                  "ver solo el error, añade una línea «#ok» en el comentario de %s." % human(last["m"]))))
        emit(nodes, color, family, segments(nodes, color), where)

    # JP.6: líneas con errores de los dos colores (antes no generaban nada para el que falla).
    lines = []

    def walk(node, path):
        if path and is_endpoint(node):
            lines.append(path)
        for k in node["ch"]:
            walk(k, path + [k])
    walk(root, [])
    normal = [p for p in problems]
    for nodes in lines:
        tokens = [n["m"] for n in nodes]
        if len(nodes) < 2:
            continue
        i1 = next((i for i in range(1, len(nodes)) if not is_ctx(nodes[i])), 1)
        family = first_line(nodes[i1].get("comment")) or "?"
        for color in ("B", "W"):
            own = [i for i, n in enumerate(nodes) if n["c"] == color and not n.get("implicit")]
            bad = [i for i in own if "q" in nodes[i]]
            if not bad:
                continue          # línea normal: ya la cubren las tarjetas de J1
            # A — castigo: tras TU ÚLTIMO error el rival también falla (justo después o más
            # tarde, JP.7); empiezas en tu primera jugada después de ese fallo del rival.
            lb = bad[-1]
            ob = next((i for i in range(lb + 1, len(nodes)) if nodes[i]["c"] not in (color, "")
                       and nodes[i].get("q") == "bad"
                       and any(j > i and not is_pass(nodes[j]) for j in own)), None)
            if ob is not None:
                note = "Tu %s fue un error y %s también ha fallado con %s: castiga." % (
                    human(nodes[lb]["m"]), COLOR_ES[nodes[ob]["c"]], human(nodes[ob]["m"]))
                emit(nodes, color, family, segments(nodes, color, after=ob - 1), tokens, note=note,
                     tri=[nodes[i]["m"] for i in bad if not is_pass(nodes[i])], line=tokens)
            # C — tramo bueno ANTES de tu primer error, si ninguna otra línea lo cubre ya.
            fb = bad[0]
            pre = nodes[:fb]
            if pre and any(is_player_stone(n, color) for n in pre[1:]):
                for s, e, cut in segments(pre, color):
                    if cut == "implicit":
                        continue
                    # cubierto si otra línea ya practica TUS jugadas hasta la última de este tramo
                    # (da igual la respuesta final del rival)
                    lp = max(i for i in range(s, e + 1) if is_player_stone(pre[i], color))
                    toks = tokens[:lp + 1]
                    if any(p["color"] == color and p["tokens"][:len(toks)] == toks for p in normal):
                        continue
                    emit(pre, color, family, [(s, e, cut)], tokens, line=tokens)
    return problems, errors, warnings


def self_validate(problems):
    """Cada SGF generado debe pasar parse_sgf + validate_problem sin ninguna
    incidencia y empezar con el color del problema."""
    for p in problems:
        res = validate_problem(parse_sgf(p["sgf"]))
        if res["issues"] or res["color_to_play"] != p["color"]:
            raise GeneratorError("%s: el SGF generado no valida: %s (color %s)"
                                 % (p["problem_id"], res["issues"], res["color_to_play"]))


def payload_for(stem, problems):
    chapters = []
    for p in problems:
        ch = next((c for c in chapters if c["folder"] == p["chapter"]), None)
        if ch is None:
            ch = {"folder": p["chapter"], "difficulty_raw": DIFFICULTY_RAW,
                  "difficulty_num": DIFFICULTY_NUM, "problems": []}
            chapters.append(ch)
        ch["problems"].append({"problem_id": p["problem_id"],
                               "sgf_path": SGF_PREFIX + "/" + p["rel_path"],
                               "order_in_chapter": p["order"], "color_to_play": p["color"]})
    return {"folder": stem, "retire_missing": True, "chapters": chapters}


# ── disco ────────────────────────────────────────────────────────────────────

def plan_disk(out_dir, stem, problems):
    """(nuevos, cambiados, iguales, a_borrar) para la carpeta de un fichero."""
    folder = os.path.join(out_dir, stem)
    existing = set()
    if os.path.isdir(folder):
        existing = {f for f in os.listdir(folder) if f.lower().endswith(".sgf")}
    new, changed, same = [], [], []
    wanted = set()
    for p in problems:
        fname = p["rel_path"].split("/", 1)[1]
        wanted.add(fname)
        path = os.path.join(folder, fname)
        if fname not in existing:
            new.append(fname)
        else:
            with open(path, "rb") as fh:
                (same if fh.read() == p["sgf"].encode("utf-8") else changed).append(fname)
    return new, changed, same, sorted(existing - wanted)


def write_disk(out_dir, stem, problems, stale):
    folder = os.path.join(out_dir, stem)
    os.makedirs(folder, exist_ok=True)
    for p in problems:
        path = os.path.join(out_dir, *p["rel_path"].split("/"))
        data = p["sgf"].encode("utf-8")
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                if fh.read() == data:
                    continue
        with open(path, "wb") as fh:
            fh.write(data)
    for fname in stale:
        os.remove(os.path.join(folder, fname))


# ── --aceptar-avisos (JP.8): añade «#ok» en el SGF maestro ───────────────────

class _RNode:
    """Nodo del SGF crudo con posiciones en el texto (para insertar sin reescribir)."""
    __slots__ = ("props", "spans", "children", "end")

    def __init__(self):
        self.props, self.spans, self.children, self.end = {}, {}, [], 0


def sgf_positions(text):
    """Árbol del SGF con, por nodo, sus propiedades, el tramo [ini, fin) del texto de
    cada valor y el final del nodo. Respeta los escapes (\\] dentro de C[...])."""
    i, n, stack, root, cur = 0, len(text), [], None, None
    while i < n:
        ch = text[i]
        if ch == "(":
            stack.append(cur); i += 1
        elif ch == ")":
            cur = stack.pop() if stack else None; i += 1
        elif ch == ";":
            node = _RNode()
            if root is None:
                root = node
            elif cur is not None:
                cur.children.append(node)
            cur = node
            i += 1
            while True:
                while i < n and text[i] in " \t\r\n":
                    i += 1
                j = i
                while j < n and text[j].isalpha():
                    j += 1
                if j == i or j >= n or text[j:j + 1] not in ("[", " ", "\t", "\r", "\n"):
                    break
                ident = "".join(c for c in text[i:j] if c.isupper())
                i = j
                vals, spans = [], []
                while True:
                    while i < n and text[i] in " \t\r\n":
                        i += 1
                    if i >= n or text[i] != "[":
                        break
                    k = i + 1
                    while k < n and text[k] != "]":
                        k += 2 if text[k] == "\\" else 1
                    vals.append(text[i + 1:k]); spans.append((i + 1, k))
                    i = k + 1
                node.props.setdefault(ident, []).extend(vals)
                node.spans.setdefault(ident, []).extend(spans)
                node.end = i
        else:
            i += 1
    return root


def raw_node_at(tokens, root):
    """La jugada de `tokens` en el árbol crudo (misma regla que fmt_path: entre ramas con
    la misma coordenada, la del color que toca; el pase implícito no está en el fichero)."""
    if root is None:
        return None
    cands = [root] if ("B" in root.props or "W" in root.props) else list(root.children)
    node, last = None, None
    for t in tokens:
        if t.startswith("ctx-"):
            node = next((c for c in cands if "B" not in c.props and "W" not in c.props
                         and ("AB" in c.props or "AW" in c.props)), None)
            if node is None:
                return None
            cands = list(node.children)
            continue
        expected = ("B" if last == "W" else "W") if last else None
        match = None
        for c in cands:
            col = "B" if "B" in c.props else ("W" if "W" in c.props else None)
            if col is None:
                continue
            v = c.props[col][0] if c.props[col] else ""
            if (t == "pass" and v in ("", "tt")) or v == t:
                if match is None or (col == expected and match[1] != expected):
                    match = (c, col)
        if match:
            node, last = match
            cands = list(node.children)
        elif t == "pass" and last:
            last = "B" if last == "W" else "W"
        else:
            return None
    return node


def insert_ok(text, nodes):
    """Inserta una línea «#ok» en el comentario de cada nodo (o C[#ok] si no tiene),
    sin tocar nada más del texto. Usa el salto de línea del propio fichero."""
    nl = "\r\n" if "\r\n" in text else "\n"
    edits = []
    for nd in nodes:
        if "C" in nd.spans:
            a, b = nd.spans["C"][0]
            edits.append((b, (nl + "#ok") if b > a else "#ok"))
        else:
            edits.append((nd.end, "C[#ok]"))
    for pos, txt in sorted(edits, reverse=True):
        text = text[:pos] + txt + text[pos:]
    return text


def analyze(raw, stem):
    """Compila y genera un fichero maestro. Devuelve un dict con todo lo que usa run()."""
    res = compile_joseki(raw, stem, extended=True)   # JP.4/JP.5
    try:
        raw_root = parse_sgf(raw.decode("utf-8").lstrip("\ufeff"))
        root_setup = {k: list(raw_root.props.get(k, [])) for k in ("AB", "AW", "AE")}
    except Exception:
        raw_root, root_setup = None, {}
    items = [_j1_issue(sev, where, msg, root_setup) for sev, where, msg in res["issues"]]
    out = {"res": res, "raw_root": raw_root, "items": items, "acked": 0, "unused": [],
           "problems": [], "errors": []}
    if not res["ok"]:
        return out
    problems, errors, warnings = generate_file(res["data"], stem)
    # JP.6: el aviso de J1 «línea sin tarjetas» sobra si la línea ya genera problemas (A/C)
    covered = {tuple(p["line"]) for p in problems if p.get("line")}
    items = [it for it in items if not (it["problem"].startswith("Esta línea no genera ningún problema")
                                        and isinstance(it["where"], list) and tuple(it["where"]) in covered)]
    items = [_explain_no_problem(it, res["data"]) for it in items]   # JP.7: texto concreto
    items, acked, unused = _apply_ack(items + errors + warnings, res["data"])
    out.update(items=items, acked=acked, unused=unused, problems=problems, errors=errors)
    return out


def accept_warnings(joseki_dir, fname, analysis, dry_run, out):
    """JP.8: pone «#ok» en las jugadas de los avisos que lo recomiendan (castigo sin
    castigo y línea sin problema nuevo). Copia .bak, inserción textual y verificación:
    si algo no cuadra, restaura el original. Devuelve True si todo fue bien."""
    path = os.path.join(joseki_dir, fname)
    stem = os.path.splitext(fname)[0]
    targets = [it for it in analysis["items"] if it.get("okable") and it["sev"] == "warn"]
    if not targets:
        return True
    with open(path, "rb") as fh:
        raw = fh.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")[1 if bom else 0:]
    rroot = sgf_positions(text)
    nodes, seen = [], set()
    out("Se añade «#ok» en:")
    for it in targets:
        nd = raw_node_at(it["where"], rroot)
        if nd is None:
            out("  ? no encuentro la jugada de: " + fmt_path(it["where"], analysis["raw_root"]))
            return False
        if id(nd) not in seen:
            seen.add(id(nd))
            nodes.append(nd)
            out("  - " + fmt_path(it["where"], analysis["raw_root"]))
    if dry_run:
        out("--dry-run: no se escribe nada.")
        return True
    new = insert_ok(text, nodes).encode("utf-8")
    if bom:
        new = b"\xef\xbb\xbf" + new
    with open(path + ".bak", "wb") as fh:
        fh.write(raw)
    with open(path, "wb") as fh:
        fh.write(new)
    after = analyze(new, stem)
    before_p = {p["problem_id"]: p["sgf"] for p in analysis["problems"]}
    after_p = {p["problem_id"]: p["sgf"] for p in after["problems"]}
    still = [it for it in after["items"] if it.get("okable")]
    ok = (after["res"]["ok"] and before_p == after_p and not still
          and len(after["errors"]) == len(analysis["errors"])
          and after["acked"] == analysis["acked"] + len(targets))
    if not ok:
        with open(path, "wb") as fh:
            fh.write(raw)
        out("ERROR: la comprobación tras añadir los #ok no cuadra; se ha restaurado el fichero original "
            "(la copia sigue en %s.bak). Pásale este mensaje a Claude." % fname)
        return False
    out("Hecho: %d «#ok» añadidos en %s (copia del original en %s.bak). Los problemas no cambian." % (len(nodes), fname, fname))
    return True


# ── main ─────────────────────────────────────────────────────────────────────

def run(joseki_dir, out_dir, dry_run=False, publish=True, server="http://localhost:3002",
        token="", source=SOURCE, poster=post_import, out=print, accept=False):
    if not os.path.isdir(joseki_dir):
        out("No existe la carpeta de ficheros maestros: %s" % joseki_dir)
        return 2
    masters = sorted(f for f in os.listdir(joseki_dir) if f.lower().endswith(".sgf"))
    if not masters:
        out("No hay ficheros .sgf en %s" % joseki_dir)
        return 2
    all_errors, results, accept_failed = [], [], []
    for fname in masters:
        stem = os.path.splitext(fname)[0]
        with open(os.path.join(joseki_dir, fname), "rb") as fh:
            raw = fh.read()
        out("\n=== %s ===" % fname)
        an = analyze(raw, stem)
        res, raw_root, items = an["res"], an["raw_root"], an["items"]
        if not res["ok"]:
            all_errors.append(fname)
            print_report(out, items, raw_root)
            continue
        problems, errors, acked, unused = an["problems"], an["errors"], an["acked"], an["unused"]
        print_report(out, items, raw_root)
        if accept:   # JP.8
            if not accept_warnings(joseki_dir, fname, an, dry_run, out):
                accept_failed.append(fname)
            continue
        if acked:
            out("(%d aviso%s aceptado%s con #ok)" % (acked, "" if acked == 1 else "s", "" if acked == 1 else "s"))
        for u in unused:
            out("#ok sin aviso que tapar (puedes quitarlo): " + fmt_path(u, raw_root))
        all_errors += errors
        if not errors:
            try:
                self_validate(problems)
            except GeneratorError as ex:
                out("HAY QUE ARREGLAR: fallo interno del generador (no es culpa del fichero). "
                    "Pásale este texto a Claude: " + str(ex))
                all_errors.append(str(ex))
                continue
            chapters = {}
            for p in problems:
                chapters[p["chapter"]] = chapters.get(p["chapter"], 0) + 1
            out("  %d líneas · %d problemas en %d capítulos" % (len({tuple(c["path"]) for c in res["data"]["cards"]}),
                                                           len(problems), len(chapters)))
            for ch, n in chapters.items():
                out("    %-40s %d" % (ch, n))
            results.append((stem, problems))
    if accept:   # JP.8: esta ejecución solo acepta avisos; no genera ni publica problemas
        out("\n--aceptar-avisos: no se generan ni se publican problemas en esta ejecución.")
        return 1 if accept_failed else 0
    if os.path.isdir(out_dir):
        orphans = sorted(d for d in os.listdir(out_dir) if os.path.isdir(os.path.join(out_dir, d))
                         and d not in {os.path.splitext(f)[0] for f in masters})
        for d in orphans:
            out("\nAVISO carpeta %s sin fichero maestro: no se toca ni se retira; bórrala a mano si sobra." % d)
    if all_errors:
        out("\nHay cosas que arreglar (arriba, en HAY QUE ARREGLAR): no se escribe ni se publica nada.")
        return 1
    plans = []
    for stem, problems in results:
        new, changed, same, stale = plan_disk(out_dir, stem, problems)
        plans.append((stem, problems, stale))
        out("\n%s: %d nuevos · %d cambiados · %d iguales · %d a borrar (retirados)"
            % (stem, len(new), len(changed), len(same), len(stale)))
    if dry_run:
        out("\n--dry-run: no se escribe ni se publica nada.")
        return 0
    for stem, problems, stale in plans:
        write_disk(out_dir, stem, problems, stale)
    out("\nFicheros escritos en %s." % out_dir)
    if not publish:
        out("--no-publish: sube los ficheros con el .bat y vuelve a ejecutar sin --no-publish para publicar.")
        return 0
    collections = [payload_for(stem, problems) for stem, problems, _ in plans]
    status, body = poster(server, source, collections, token)
    out("\nServidor respondió %s: %s" % (status, body))
    return 0 if status == 200 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("joseki_dir", help="carpeta con los ficheros maestros (.sgf)")
    ap.add_argument("out_dir", help="carpeta de salida (joseki_problems)")
    ap.add_argument("--server", default="http://localhost:3002")
    ap.add_argument("--token", default=os.environ.get("TSUMEVAULT_TOKEN", ""))
    ap.add_argument("--source", default=SOURCE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--aceptar-avisos", action="store_true",
                    help="añade «#ok» en el SGF maestro a los avisos que lo recomiendan (con --dry-run solo los lista)")
    a = ap.parse_args()
    sys.exit(run(a.joseki_dir, a.out_dir, dry_run=a.dry_run, publish=not a.no_publish,
                 server=a.server, token=a.token, source=a.source, accept=a.aceptar_avisos))


if __name__ == "__main__":
    main()
