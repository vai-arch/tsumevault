import os, re, json, glob, collections
from analyze_all import parse_edn

def nodos(children):
    for ch in children or ():
        yield ch
        yield from nodos(ch.get(":children"))

def max_coord(t):
    m = -1
    for (x, y) in (t.get(":stones") or {}):
        m = max(m, x, y)
    for n in nodos(t.get(":children")):
        (x, y), _ = n[":move"]
        m = max(m, x, y)
    return m

donde = {}
for ruta in glob.glob("salida_academia/*/*/*.sgf"):
    partes = ruta.replace("\\", "/").split("/")
    m = re.match(r"\d+_(\w{8})\.sgf$", partes[-1])
    if m:
        donde[m.group(1)] = (partes[-3], partes[-2])

tam_cap = collections.defaultdict(collections.Counter)
sin_tam = []
for f in glob.glob("problems_raw/*.json"):
    d = json.load(open(f, encoding="utf-8"))
    id8 = d.get("id", "")[:8]
    if id8 not in donde:
        continue
    try:
        t = parse_edn(d["variations"])
    except Exception:
        continue
    nivel, cap = donde[id8]
    tam = t.get(":board-size")
    if tam is None:
        sin_tam.append((nivel, cap, id8, max_coord(t)))
    else:
        tam_cap[(nivel, cap)][tam] += 1

claros = conflictos = sin_hermanos = 0
print(f"problemas sin tamaño: {len(sin_tam)}\n")
for nivel, cap, id8, mc in sorted(sin_tam):
    herm = tam_cap.get((nivel, cap), collections.Counter())
    if not herm:
        sin_hermanos += 1
        veredicto = "sin hermanos con tamaño"
    elif len(herm) == 1 and mc < next(iter(herm)):
        claros += 1
        veredicto = "claro"
    else:
        conflictos += 1
        veredicto = "REVISAR"
    print(f"{cap[:44]:44s} {id8} coord.max {mc:2d} | hermanos {dict(herm)} | {veredicto}")
print(f"\nclaros: {claros} | a revisar: {conflictos} | sin hermanos: {sin_hermanos}")
mayores = [x for x in sin_tam if x[3] >= 13]
print(f"con alguna coordenada >= 13 (no pueden ser de 13x13): {len(mayores)}")