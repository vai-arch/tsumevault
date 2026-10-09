import sys, re, os, zipfile, collections, shutil
import xml.etree.ElementTree as ET

XH = "{http://www.w3.org/1999/xhtml}"
SV = "{http://www.w3.org/2000/svg}"
XL = "{http://www.w3.org/1999/xlink}href"
GV = "{https://gobooks.com}v"

# ── Config ─────────────────────────────────────────────
COLECCION = "Mastering Basic Corner Shapes"
DST = "salida_sgf"
DIFFICULTY = None      # p.ej. "20k" crea difficulty-20k en cada chapter
N = 19                 # tamaño del tablero
USAR_TITULOS = True    # True: carpeta "04-<título>"; False: "04-Chapter 4"
# ───────────────────────────────────────────────────────

def cargar(texto):
    try:
        return ET.fromstring(texto.encode("utf-8"))
    except ET.ParseError:
        texto = texto.replace("&nbsp;", "&#160;")
        return ET.fromstring(texto.encode("utf-8"))

# ── Mini motor de Go (capturas, sin regla de ko) ───────
def vecinos(p):
    c, r = p
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if 0 <= c + dc < N and 0 <= r + dr < N:
            yield (c + dc, r + dr)

def grupo(tab, p):
    col, vis, pila, libres = tab[p], {p}, [p], set()
    while pila:
        q = pila.pop()
        for v in vecinos(q):
            if v not in tab:
                libres.add(v)
            elif tab[v] == col and v not in vis:
                vis.add(v)
                pila.append(v)
    return vis, libres

def jugar(tab, color, p):
    if p in tab:
        return None
    t = dict(tab)
    t[p] = color
    for v in vecinos(p):
        if v in t and t[v] != color:
            g, lib = grupo(t, v)
            if not lib:
                for q in g:
                    del t[q]
    if p in t:
        _, lib = grupo(t, p)
        if not lib:
            return None   # suicidio
    return t

def aplicar(tab, jugadas):
    for p, c in jugadas:
        tab = jugar(tab, c, p)
        if tab is None:
            return None
    return tab

# ── Lectura de figuras ─────────────────────────────────
def texto_leyenda(cap):
    if cap is None:
        return ""
    partes = []
    def rec(e):
        if e.text and not e.tag.endswith("svg"):
            partes.append(e.text)
        for h in e:
            if h.tag == SV + "svg":
                circ = h.find(SV + "circle")
                negro = circ is not None and circ.get("fill") == "black"
                partes.append("●" if negro else "○")
            elif h.tag == XH + "br":
                partes.append(" ")
            else:
                rec(h)
            if h.tail:
                partes.append(h.tail)
    rec(cap)
    return re.sub(r"\s+", " ", "".join(partes)).strip()

def figura(fig, pm):
    svg = fig.find(SV + "svg")
    xs, ys, gruesas_v, gruesas_h = set(), set(), [], []
    for p in svg.iter(SV + "path"):
        d = p.get("d", "")
        grueso = p.get("stroke-width", "").startswith("2")
        for m in re.finditer(r"M([\d.]+),([\d.]+)V", d):
            xs.add(round(float(m.group(1))))
            if grueso:
                gruesas_v.append(round(float(m.group(1))))
        for m in re.finditer(r"M([\d.]+),([\d.]+)H", d):
            ys.add(round(float(m.group(2))))
            if grueso:
                gruesas_h.append(round(float(m.group(2))))
    if not xs or not ys:
        return None
    x0, y0 = min(xs), min(ys)
    cols, rows = len(xs), len(ys)
    izq = any(x == x0 for x in gruesas_v)
    der = any(x != x0 for x in gruesas_v)
    arr = any(y == y0 for y in gruesas_h)
    aba = any(y != y0 for y in gruesas_h)
    if izq == der or arr == aba:
        return {"error": "bordes no claros"}
    ox = 0 if izq else N - cols
    oy = 0 if arr else N - rows
    def pt(x, y):
        return (round((x - x0) / 24) + ox, round((y - y0) / 24) + oy)
    def oculto(e):
        while e is not None:
            if e.get("visibility") == "hidden":
                return True
            e = pm.get(e)
        return False
    vb = svg.get("viewBox").split()
    es_problema = float(vb[3]) > float(vb[2])
    fijas, jugadas, textos, turno = {}, [], [], None
    colores = {}
    for e in svg.iter(SV + "use"):
        ref = e.get(XL, "")
        if ref not in ("#b", "#w"):
            continue
        x, y = float(e.get("x")), float(e.get("y"))
        if y >= y0 - 6:
            colores.setdefault(pt(x, y), set()).add(ref[1])
        if oculto(e):
            continue
        if y < y0 - 6:
            turno = ref[1]
            continue
        p = pm.get(e)
        con_gv = p is not None and p.get(GV) is not None
        if con_gv and not es_problema:
            jugadas.append((pt(x, y), ref[1]))
        else:
            fijas[pt(x, y)] = ref[1]
    textos_todos = []
    for e in svg.iter(SV + "text"):
        if float(e.get("y")) < y0 - 6:
            continue
        t = (e.text or "").strip()
        p_t = pt(float(e.get("x")), float(e.get("y")))
        textos_todos.append((t, p_t))
        if not oculto(e):
            textos.append((t, p_t))
    lado = ("i" if izq else "d") + ("a" if arr else "b")
    leyenda = texto_leyenda(fig.find(XH + "figcaption"))
    return {"fijas": fijas, "jugadas": jugadas, "textos": textos,
            "textos_todos": textos_todos, "colores": colores,
            "turno": turno, "lado": lado, "cap": leyenda,
            "es_problema": es_problema}

def opuesto(c):
    return "w" if c == "b" else "b"

def base_de(d):
    """Posición de partida: piedras fijas + piedras de jugada sin número."""
    numerados = {p for t, p in d["textos"] if t.isdigit()}
    base = dict(d["fijas"])
    for p, c in d["jugadas"]:
        if p not in numerados:
            base[p] = c
    return base

def mover_visibles(d):
    """Jugadas en orden, según los números visibles y las notas 'N at M'."""
    num = {}
    for t, p in d["textos"]:
        if t.isdigit():
            num[int(t)] = p
    notas = re.findall(r"(\d+)\s+at\s+(\d+)", d["cap"])
    implicitas = {int(n): int(m) for n, m in notas}
    if not num and not implicitas:
        return [], None
    col_en = {p: c for p, c in d["jugadas"]}
    for p, c in d["fijas"].items():
        col_en.setdefault(p, c)
    K = max(list(num) + list(implicitas))
    pts = {}
    for n in range(1, K + 1):
        if n in num:
            pts[n] = num[n]
        elif n in implicitas and implicitas[n] in pts:
            pts[n] = pts[implicitas[n]]
        else:
            return None, "numeración incompleta (falta %d)" % n
    c1 = None
    for n in sorted(pts):
        c = col_en.get(pts[n])
        if c:
            c1 = c if n % 2 == 1 else opuesto(c)
            break
    if c1 is None:
        return None, "no se sabe quién empieza"
    seq = []
    for n in range(1, K + 1):
        c = c1 if n % 2 == 1 else opuesto(c1)
        visto = col_en.get(pts[n]) if n in num else None
        if visto and visto != c:
            return None, "colores no alternan"
        seq.append((pts[n], c))
    return seq, None

def mover_con_ocultos(d):
    """Segundo intento: usa todos los números del SVG, también los ocultos."""
    num = {}
    for t, p in d["textos_todos"]:
        if t.isdigit() and int(t) not in num:
            num[int(t)] = p
    if not num:
        return None, "sin números"
    K = max(num)
    faltan = [n for n in range(1, K + 1) if n not in num]
    if faltan:
        return None, "numeración incompleta (falta %d)" % faltan[0]
    c1 = None
    for n in sorted(num):
        propios = {c for p, c in d["jugadas"] if p == num[n]}
        vis = propios or d["colores"].get(num[n], set())
        if len(vis) == 1:
            c = next(iter(vis))
            c1 = c if n % 2 == 1 else opuesto(c)
            break
    if c1 is None:
        return None, "no se sabe quién empieza"
    seq = []
    for n in range(1, K + 1):
        seq.append((num[n], c1 if n % 2 == 1 else opuesto(c1)))
    return seq, None

def mover(d):
    seq, aviso = mover_visibles(d)
    if seq is not None:
        return seq, None
    if aviso and aviso.startswith("numeración incompleta"):
        seq2, aviso2 = mover_con_ocultos(d)
        if seq2 is not None:
            return seq2, None
    return None, aviso

def es_fallo(cap):
    m = re.match(r"Dia\.\s*[\d–\-]+\s*(.*)", cap)
    return bool(m and m.group(1).lower().startswith("failure"))

# ── Problema → diagramas resueltos ─────────────────────
def procesar(ruta_nombre, texto, info):
    root = cargar(texto)
    pm = {c: p for p in root.iter() for c in p}
    figs = []
    for f in root.iter(XH + "figure"):
        if f.find(SV + "svg") is not None:
            figs.append(figura(f, pm))
    if not figs or figs[0] is None or "error" in figs[0]:
        return None, "figura inicial no válida"
    if not figs[0]["es_problema"]:
        return None, "figura inicial no válida"
    ini = figs[0]
    inicial = dict(ini["fijas"])
    lineas, resumen = [], collections.Counter()
    problemas = []
    resueltos = []   # secuencias completas de diagramas ya resueltos
    for i, d in enumerate(figs[1:], 1):
        if d is None or "error" in d:
            resumen["figura ilegible"] += 1
            continue
        cap = d["cap"][:40]
        if not d["cap"].startswith("Dia."):
            resumen["no es solución (sin 'Dia.')"] += 1
            continue
        if d["lado"] != ini["lado"]:
            problemas.append((cap, "orientación distinta"))
            continue
        seq, aviso = mover(d)
        if seq is None:
            problemas.append((cap, aviso))
            resumen["sin resolver: " + aviso] += 1
            continue
        base = base_de(d)
        if base == inicial:
            prefijo, via = (), "inicial"
        else:
            cands, vistos = [], set()
            for L in resueltos:
                tab = dict(inicial)
                for k in range(1, len(L) + 1):
                    tab = jugar(tab, L[k - 1][1], L[k - 1][0])
                    if tab is None:
                        break
                    if tab == base and tuple(L[:k]) not in vistos:
                        vistos.add(tuple(L[:k]))
                        cands.append(tuple(L[:k]))
            if not cands:
                problemas.append((cap, "no coincide con ninguna posición previa"))
                resumen["sin resolver: sin padre"] += 1
                continue
            prefijo = cands[0]
            via = "exacto" if len(cands) == 1 else "equivalente"
        linea = tuple(prefijo) + tuple(seq)
        if aplicar(dict(inicial), linea) is None:
            problemas.append((cap, "jugada ilegal en la simulación"))
            resumen["sin resolver: ilegal"] += 1
            continue
        resumen["diagrama " + via] += 1
        resueltos.append(linea)
        if seq:
            lineas.append((linea, d["cap"], es_fallo(d["cap"])))
    res = {"inicial": inicial, "turno": ini["turno"], "lineas": lineas,
           "resumen": resumen, "problemas": problemas, "figs": len(figs) - 1}
    return res, None

# ── Árbol y SGF ────────────────────────────────────────
def coord(p):
    return chr(97 + p[0]) + chr(97 + p[1])

def esc(v):
    return v.replace("\\", "\\\\").replace("]", "\\]")

def construir_sgf(res):
    arbol = {"hijos": collections.OrderedDict(), "caps": []}
    for linea, cap, fallo in res["lineas"]:
        n = arbol
        for mv in linea:
            nuevo = {"hijos": collections.OrderedDict(), "caps": []}
            n = n["hijos"].setdefault(mv, nuevo)
        n["caps"].append((cap, fallo))
    stats = collections.Counter()
    def ser(n, mv, previo):
        s = ";" + ("B" if mv[1] == "b" else "W") + "[" + coord(mv[0]) + "]"
        propio = any(f for _, f in n["caps"])
        fallo = previo or propio
        textos = " | ".join(c for c, _ in n["caps"])
        if not n["hijos"]:
            todos_fallo = all(f for _, f in n["caps"])
            if n["caps"] and propio and not todos_fallo:
                stats["hoja con leyendas contradictorias"] += 1
            if previo and not propio:
                stats["hoja WRONG por pasar bajo un Failure"] += 1
            r = "WRONG" if fallo else "RIGHT"
            stats[r] += 1
            s += "C[" + esc((r + "\n" + textos).rstrip()) + "]"
        elif textos:
            s += "C[" + esc(textos) + "]"
        hijos = [ser(h, m, fallo) for m, h in n["hijos"].items()]
        if len(hijos) == 1:
            return s + hijos[0]
        return s + "".join("(" + h + ")" for h in hijos)
    turno = res["turno"]
    ab = sorted(coord(p) for p, c in res["inicial"].items() if c == "b")
    aw = sorted(coord(p) for p, c in res["inicial"].items() if c == "w")
    raiz = "(;GM[1]FF[4]CA[UTF-8]SZ[%d]PL[%s]" % (N, "B" if turno == "b" else "W")
    if ab:
        raiz += "AB" + "".join("[%s]" % x for x in ab)
    if aw:
        raiz += "AW" + "".join("[%s]" % x for x in aw)
    hijos = [ser(h, m, False) for m, h in arbol["hijos"].items()]
    if len(hijos) == 1:
        cuerpo = hijos[0]
    else:
        cuerpo = "".join("(" + h + ")" for h in hijos)
    return raiz + cuerpo + ")", stats

def limpiar(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:60].strip(" .")

def titulo_capitulo(z, ch):
    for n in z.namelist():
        if re.search(r"/ch%d\.xhtml$" % ch, n):
            try:
                r = cargar(z.read(n).decode("utf-8", "replace"))
                for tag in ("h1", "h2", "h3"):
                    for e in r.iter(XH + tag):
                        partes = [x.strip() for x in e.itertext() if x.strip()]
                        t = " ".join(partes)
                        t = re.sub(r"^Chapter\s*\d+\s*[:\-–.]*\s*", "", t,
                                   flags=re.I)
                        t = limpiar(t)
                        if t:
                            return t
            except Exception:
                pass
    return ""

def main(ruta):
    z = zipfile.ZipFile(ruta)
    probs = [n for n in z.namelist() if re.search(r"/prob\d+-\d+\.xhtml$", n)]
    probs.sort(key=lambda n: tuple(map(int, re.findall(r"\d+", os.path.basename(n)))))
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    total, hojas = collections.Counter(), collections.Counter()
    informe, sin_right, ficheros = [], [], 0
    titulos = {}
    for n in probs:
        nombre = os.path.basename(n)
        ch, k = map(int, re.findall(r"\d+", nombre))
        res, err = None, None
        try:
            res, err = procesar(n, z.read(n).decode("utf-8", "replace"), None)
        except Exception as e:
            err = "excepción: %s" % str(e)[:80]
        if res is None:
            informe.append(f"{nombre}: NO CONVERTIDO ({err})")
            total["problemas no convertidos"] += 1
            continue
        for kx, v in res["resumen"].items():
            total[kx] += v
        total["diagramas de respuesta"] += res["figs"]
        for cap, aviso in res["problemas"]:
            informe.append(f"{nombre}: {cap!r} -> {aviso}")
        sgf, st = construir_sgf(res)
        for kx, v in st.items():
            hojas[kx] += v
        if not st["RIGHT"]:
            sin_right.append(nombre)
        if ch not in titulos:
            titulos[ch] = titulo_capitulo(z, ch) if USAR_TITULOS else ""
        nom_cap = f"{ch:02d}-" + (titulos[ch] or f"Chapter {ch}")
        carpeta = os.path.join(DST, COLECCION, nom_cap)
        try:
            os.makedirs(carpeta, exist_ok=True)
            if DIFFICULTY:
                open(os.path.join(carpeta, f"difficulty-{DIFFICULTY}"), "a").close()
            fichero = os.path.join(carpeta, f"{k:02d}_prob{ch}-{k}.sgf")
            with open(fichero, "w", encoding="utf-8", newline="\n") as f:
                f.write(sgf)
            ficheros += 1
        except OSError as e:
            informe.append(f"{nombre}: NO ESCRITO ({e})")
            total["no escritos"] += 1
    print(f"problemas: {len(probs)} | ficheros escritos: {ficheros}")
    print("diagramas:", dict(total))
    print("hojas:", dict(hojas))
    print("problemas sin ninguna hoja RIGHT:", sin_right)
    print("capítulos (carpetas):", dict(sorted(titulos.items())[:6]), "…")
    with open("informe_libro.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(informe))
    print(f"avisos en informe_libro.txt: {len(informe)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python convertir_libro.py libro.epub")
    else:
        main(sys.argv[1])