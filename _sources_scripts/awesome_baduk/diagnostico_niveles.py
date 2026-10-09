import os, re, json, glob, collections
from analyze_all import parse_edn

def nodos(children):
    for ch in children or ():
        yield ch
        yield from nodos(ch.get(":children"))

# id8 -> carpeta del capítulo, a partir de lo ya generado
donde = {}
for ruta in glob.glob("salida_academia/*/*/*.sgf"):
    partes = ruta.replace("\\", "/").split("/")
    m = re.match(r"\d+_(\w{8})\.sgf$", partes[-1])
    if m:
        donde[m.group(1)] = (partes[-3], partes[-2])

sin_tablero, sin_hijos = [], []
stones_por_nivel = collections.Counter()
probs_stones = collections.Counter()
claves_sin_tablero = collections.Counter()
claves_sin_hijos = collections.Counter()
ejemplos_hijos, ejemplo_stones = [], None
errores = leidos = 0
for f in glob.glob("problems_raw/*.json"):
    d = json.load(open(f, encoding="utf-8"))
    id8 = d.get("id", "")[:8]
    if id8 not in donde:
        continue
    nivel, cap = donde[id8]
    try:
        t = parse_edn(d["variations"])
    except Exception:
        errores += 1
        continue
    leidos += 1
    if t.get(":board-size") is None:
        sin_tablero.append((nivel, cap, id8))
        claves_sin_tablero.update(t.keys())
    if not t.get(":children"):
        sin_hijos.append((nivel, cap, id8))
        claves_sin_hijos.update(t.keys())
        if len(ejemplos_hijos) < 2:
            ejemplos_hijos.append((cap, id8, d["variations"][:450]))
    hay = False
    for n in nodos(t.get(":children")):
        if n.get(":stones"):
            stones_por_nivel[nivel] += 1
            hay = True
            if ejemplo_stones is None:
                ejemplo_stones = (cap, id8, n.get(":move"), n.get(":stones"))
    probs_stones[nivel] += hay

print(f"problemas Level leídos: {leidos} | errores al leer EDN: {errores}")
print(f"\n1) SIN ÁRBOL de soluciones: {len(sin_hijos)}")
print("   claves de su EDN:", dict(claves_sin_hijos))
print(f"2) SIN tamaño de tablero: {len(sin_tablero)}")
print("   claves de su EDN:", dict(claves_sin_tablero))
solapan = {x[2] for x in sin_hijos} & {x[2] for x in sin_tablero}
print(f"   de ellos, también sin árbol: {len(solapan)}")
print(f"3) nodos con :stones: {sum(stones_por_nivel.values())} "
      f"| problemas afectados: {sum(probs_stones.values())}")
print("   problemas afectados por nivel:",
      dict(sorted((k, v) for k, v in probs_stones.items() if v)))
if ejemplo_stones:
    print("   ejemplo de nodo:", ejemplo_stones)
for cap, id8, txt in ejemplos_hijos:
    print(f"\nejemplo sin árbol: {cap} / {id8}\n   {txt!r}")
if os.path.exists("informe_niveles.txt"):
    print("\n--- informe_niveles.txt ---")
    print(open("informe_niveles.txt", encoding="utf-8").read())