import os, re, json, sys, shutil
from analyze_all import parse_edn

# ── Config ─────────────────────────────────────────────
COLLECTION = "Mastering basic side shapes"   # nombre de la carpeta de la colección
DST = "salida_sgf"                           # carpeta de salida (no toca my_collections)
DIFFICULTY = None                            # p.ej. "20k" crea difficulty-20k en cada chapter
# ───────────────────────────────────────────────────────

def coord(x, y):
    return chr(97 + x) + chr(97 + y)

def esc(v):
    return v.replace("\\", "\\\\").replace("]", "\\]")

# Descripcion del problema -> comentario del nodo raiz.
# Se quita solo el turno ("Black to play"), al principio o al final, separado
# por "/" o salto de linea. Una "/" dentro de la frase se conserva.
TURNO = r"(?:b+lack+|w+hite+)\s+(?:to\s+)?(?:play|move)\s*[.!]?"
RE_INI = re.compile(r"^\s*" + TURNO + r"\s*(?:/|\n|$)\s*", re.I)
RE_FIN = re.compile(r"\s*(?:/|\n)\s*" + TURNO + r"\s*$", re.I)

def enunciado(desc):
    t = (desc or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    while True:
        nuevo = RE_FIN.sub("", RE_INI.sub("", t, count=1), count=1).strip()
        if nuevo == t:
            return t
        t = nuevo

def marcas_nodo(nodo):
    props = []
    m = nodo.get(':marks')
    if not isinstance(m, dict):
        m = {}
    for clave, sgf in ((':triangle', 'TR'), (':circle', 'CR'), (':square', 'SQ')):
        pts = sorted(coord(x, y) for (x, y) in (m.get(clave) or ()))
        if pts:
            props.append((sgf, pts))
    lab = nodo.get(':labels')
    if isinstance(lab, dict) and lab:
        etiquetas = [f"{coord(x, y)}:{t}" for (x, y), t in sorted(lab.items())]
        props.append(("LB", etiquetas))
    return props

def build_children(children, first):
    out = []
    for ch in children or ():
        if ':move' not in ch:      # nodo sin jugada (p.ej. {:stones {}}): se ignora
            continue
        (x, y), color = ch[':move']
        props = [("B" if color == ':black' else "W", [coord(x, y)])]
        props += marcas_nodo(ch)
        kids = ch.get(':children')
        comment = (ch.get(':comment') or "").strip()
        if kids:
            if comment:
                props.append(("C", [comment]))
        else:
            res = "RIGHT" if color == first else "WRONG"
            props.append(("C", [res + ("\n" + comment if comment else "")]))
        out.append({"props": props, "children": build_children(kids, first)})
    return out

def serialize(node):
    s = ";"
    for k, vs in node["props"]:
        s += k + "".join(f"[{esc(v)}]" for v in vs)
    kids = node["children"]
    if not kids:
        return s
    if len(kids) == 1:
        return s + serialize(kids[0])
    return s + "".join("(" + serialize(c) + ")" for c in kids)

def problem_to_sgf(d):
    t = parse_edn(d['variations'])
    first = ':' + d['to-play']
    stones = t.get(':stones') or {}
    ab = sorted(coord(x, y) for (x, y), c in stones.items() if c == ':black')
    aw = sorted(coord(x, y) for (x, y), c in stones.items() if c == ':white')
    props = [("GM", ["1"]), ("FF", ["4"]), ("SZ", [str(t.get(':board-size', 19))]),
             ("PL", ["B" if first == ':black' else "W"])]
    if ab:
        props.append(("AB", ab))
    if aw:
        props.append(("AW", aw))
    marks = t.get(':marks') or {}
    tr = sorted(coord(x, y) for (x, y) in (marks.get(':triangle') or ()))
    cr = sorted(coord(x, y) for (x, y) in (marks.get(':circle') or ()))
    sq = sorted(coord(x, y) for (x, y) in (marks.get(':square') or ()))
    if tr:
        props.append(("TR", tr))
    if cr:
        props.append(("CR", cr))
    if sq:
        props.append(("SQ", sq))
    labels = t.get(':labels') or {}
    if labels:
        etiquetas = [f"{coord(x, y)}:{txt}" for (x, y), txt in sorted(labels.items())]
        props.append(("LB", etiquetas))
    texto = enunciado(d.get('description'))
    if texto:
        props.append(("C", [texto]))
    root = {"props": props, "children": build_children(t.get(':children'), first)}
    problems = []
    for ch in root["children"]:
        if ch["props"][0][0] != ("B" if first == ':black' else "W"):
            problems.append("primera jugada del color contrario")
    return "(" + serialize(root) + ")", problems

def main():
    days = json.load(open("days.json", encoding="utf-8"))
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    stats = {"ficheros": 0, "sin_RIGHT": [], "avisos": [], "labels": 0, "comentarios": 0}
    for n, it in enumerate(days, 1):
        title_n = int(it["doc"]["title"].split()[-1])
        if title_n != n:
            stats["avisos"].append(f"chapter {title_n} en posición {n}")
        chap_dir = os.path.join(DST, COLLECTION, f"{n:02d}-Chapter {n}")
        os.makedirs(chap_dir, exist_ok=True)
        if DIFFICULTY:
            open(os.path.join(chap_dir, f"difficulty-{DIFFICULTY}"), "w").close()
        for pos, pid in enumerate(it["doc"]["problems"], 1):
            ruta = os.path.join("problems_raw", pid + ".json")
            d = json.load(open(ruta, encoding="utf-8"))
            sgf, probs = problem_to_sgf(d)
            if "C[RIGHT" not in sgf:
                stats["sin_RIGHT"].append(pid[:8])
            for p in probs:
                stats["avisos"].append(f"{pid[:8]}: {p}")
            stats["labels"] += "LB[" in sgf
            stats["comentarios"] += bool(enunciado(d.get("description")))
            fichero = os.path.join(chap_dir, f"{pos:02d}_{pid[:8]}.sgf")
            with open(fichero, "w", encoding="utf-8", newline="\n") as f:
                f.write(sgf)
            stats["ficheros"] += 1
    print("ficheros escritos:", stats["ficheros"], "| con label:", stats["labels"],
          "| con comentario:", stats["comentarios"])
    print("sin ninguna hoja RIGHT:", stats["sin_RIGHT"])
    print("avisos:", stats["avisos"])
    print("carpeta:", os.path.abspath(os.path.join(DST, COLLECTION)))

if __name__ == "__main__":
    main()