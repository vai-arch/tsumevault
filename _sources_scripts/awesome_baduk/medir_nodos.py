import json, glob, collections
from analyze_all import parse_edn

def nodos(children):
    for ch in children or ():
        yield ch
        yield from nodos(ch.get(":children"))

def vacio(v):
    if not v:
        return True
    if isinstance(v, dict):
        return not any(v.values())
    return False

problemas = con_algo = 0
nodos_tot = n_marks = n_labels = 0
tipos = collections.Counter()
ejemplos = []
for f in glob.glob("problems_raw/*.json"):
    d = json.load(open(f, encoding="utf-8"))
    try:
        t = parse_edn(d["variations"])
    except Exception:
        continue
    problemas += 1
    hay = False
    for n in nodos(t.get(":children")):
        nodos_tot += 1
        m, lab = n.get(":marks"), n.get(":labels")
        if not vacio(m):
            n_marks += 1
            hay = True
            tipos[("marks", type(m).__name__)] += 1
        if not vacio(lab):
            n_labels += 1
            hay = True
            tipos[("labels", type(lab).__name__)] += 1
        if (not vacio(m) or not vacio(lab)) and len(ejemplos) < 4:
            ejemplos.append((d["id"][:8], n.get(":move"), m, lab))
    con_algo += hay
print(f"problemas leídos: {problemas} | nodos de variante: {nodos_tot}")
print(f"nodos con marcas reales: {n_marks} | con labels reales: {n_labels}")
print(f"problemas con alguna anotación en variantes: {con_algo}")
print("tipos:", dict(tipos))
for e in ejemplos:
    print("ejemplo:", e)