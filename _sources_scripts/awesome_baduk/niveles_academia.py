import os, re, sys, json, time, shutil, collections, requests
from list_inventory import login, listar
from analyze_all import parse_edn
from convert_problems import problem_to_sgf

# ── Config ─────────────────────────────────────────────────────────────
# Beginner 1-3 pasan a ser Level 01-03; Level 4-12 siguen igual.
PATRON = r"^(?:Beginner|Level)\s+(\d+)\s*-\s*(\d+)"
NIVELES = [1]                  # [1] = prueba; None = todos; o p.ej. [1, 2, 3]
DST = "salida_academia"        # carpeta de salida (no toca my_collections)
DIFFICULTY_POR_NIVEL = {n: f"{16 - n}k" for n in range(1, 13)}   # Level 01=15k ... Level 12=4k
CACHE = "problems_raw"         # caché compartida con la otra cadena
TIMEOUT, REINTENTOS, PAUSA = 30, 3, 0.3
BASE = ("https://firestore.googleapis.com/v1/projects/badol-online-academy"
        "/databases/(default)/documents")
# ───────────────────────────────────────────────────────────────────────

def plain(v):
    k, x = next(iter(v.items()))
    if k == "mapValue":
        return {a: plain(b) for a, b in x.get("fields", {}).items()}
    if k == "arrayValue":
        return [plain(i) for i in x.get("values", [])]
    if k == "integerValue":
        return int(x)
    if k == "nullValue":
        return None
    return x

def limpiar(s):
    s = s.replace("/", " - ")
    s = re.sub(r'[<>:"\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:60].strip(" .-")

def parsear(titulo):
    m = re.search(PATRON, titulo)
    if not m:
        return None
    tema = re.sub(PATRON + r"\s*[-:]?\s*", "", titulo, count=1)
    return int(m.group(1)), int(m.group(2)), limpiar(tema)

def ids_de(f):
    out = []
    for p in f.get("problems") or []:
        pid = p.get("id") if isinstance(p, dict) else p
        if pid:
            out.append(pid)
    return out

def planificar(cols, niveles):
    unidades = []
    for cid, f in cols:
        titulo = f.get("title") or ""
        r = parsear(titulo)
        if r is None:
            continue
        nivel, sub, tema = r
        if niveles is not None and nivel not in niveles:
            continue
        unidades.append({"nivel": nivel, "sub": sub, "tema": tema,
                         "titulo": titulo, "problemas": ids_de(f)})
    unidades.sort(key=lambda u: (u["nivel"], u["sub"], u["tema"]))
    usados = collections.defaultdict(set)
    for u in unidades:
        base = f"Level {u['nivel']:02d}-{u['sub']:02d}"
        if u["tema"]:
            base += f" - {u['tema']}"
        nombre, k = base, 2
        while nombre.lower() in usados[u["nivel"]]:
            nombre = f"{base} ({k})"
            k += 1
        usados[u["nivel"]].add(nombre.lower())
        u["capitulo"] = nombre
        u["coleccion"] = f"Level {u['nivel']:02d}"
        u["renombrado"] = nombre != base
    return unidades

def ya_descargado(path):
    if not os.path.exists(path):
        return False
    try:
        d = json.load(open(path, encoding="utf-8"))
        return "variations" in d and "id" in d
    except Exception:
        return False

def descargar(H, ids):
    S = requests.Session()
    S.headers.update(H)
    os.makedirs(CACHE, exist_ok=True)
    nuevos = errores = 0
    for i, pid in enumerate(ids, 1):
        path = os.path.join(CACHE, pid + ".json")
        if ya_descargado(path):
            continue
        rr, ultimo = None, ""
        for intento in range(1, REINTENTOS + 1):
            try:
                rr = S.get(f"{BASE}/problems/{pid}", timeout=TIMEOUT)
                if rr.status_code == 200:
                    break
                ultimo = f"HTTP {rr.status_code}"
                if rr.status_code not in (429, 500, 502, 503, 504):
                    break
            except requests.RequestException as e:
                ultimo = type(e).__name__
            rr = None
            print(f"   reintento {intento}/{REINTENTOS} ({ultimo})", flush=True)
            time.sleep(2 * intento)
        if rr is None or rr.status_code != 200:
            print(f"error {pid[:8]}: {ultimo}", flush=True)
            errores += 1
            continue
        doc = {k: plain(v) for k, v in rr.json()["fields"].items()}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        nuevos += 1
        if nuevos % 10 == 0:
            print(f"  {nuevos} descargados ({i}/{len(ids)})", flush=True)
        time.sleep(PAUSA)
    return nuevos, errores

def claves_nodo(children, acc):
    for ch in children or ():
        acc.update(ch.keys())
        claves_nodo(ch.get(":children"), acc)

def mostrar_plan(unidades):
    por_col = collections.OrderedDict()
    for u in unidades:
        por_col.setdefault(u["coleccion"], []).append(u)
    lineas = []
    for col, us in por_col.items():
        total = sum(len(u["problemas"]) for u in us)
        lineas.append(f"{col}: {len(us)} capítulos, {total} problemas")
        for u in us:
            marca = "  (nombre repetido, se renombra)" if u["renombrado"] else ""
            lineas.append(f"     {u['capitulo']}  [{len(u['problemas'])}]{marca}")
    renombrados = [u["capitulo"] for u in unidades if u["renombrado"]]
    cuenta = collections.Counter((u["nivel"], u["sub"]) for u in unidades)
    mismo_num = [f"Level {n:02d}-{s:02d} x{c}" for (n, s), c in cuenta.items() if c > 1]
    vacios = [u["capitulo"] for u in unidades if not u["problemas"]]
    largos = [u["titulo"] for u in unidades if len(u["tema"]) >= 60]
    lineas.append("")
    lineas.append(f"TOTAL: {len(por_col)} colecciones, {len(unidades)} capítulos, "
                  f"{sum(len(u['problemas']) for u in unidades)} problemas")
    lineas.append(f"números repetidos en la academia (se distinguen por el tema): {mismo_num}")
    lineas.append(f"capítulos renombrados por llamarse exactamente igual: {renombrados}")
    lineas.append(f"capítulos sin problemas: {vacios}")
    lineas.append(f"temas recortados a 60 caracteres: {len(largos)}")
    with open("plan_niveles.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    return lineas

def main():
    niveles = NIVELES
    if len(sys.argv) > 1:
        a = sys.argv[1].lower()
        niveles = None if a == "todos" else [int(x) for x in a.split(",")]
    solo_plan = len(sys.argv) > 2 and sys.argv[2].lower() == "plan"
    H = login()
    cols, est = listar(H, "problem-collections", ["title", "problems"])
    unidades = planificar(cols, niveles)
    if not unidades:
        print(f"Ninguna colección coincide (de {len(cols)} leídas).")
        return
    lineas = mostrar_plan(unidades)
    if solo_plan:
        print("\n".join(lineas[:12]), "\n...")
        print("\n".join(lineas[-5:]))
        print("\nPlan completo en plan_niveles.txt (no se ha descargado nada).")
        return
    print("\n".join(lineas[-5:]))
    ids = [pid for u in unidades for pid in u["problemas"]]
    print(f"\nproblemas a revisar: {len(ids)} ({len(set(ids))} distintos)")
    nuevos, errores = descargar(H, ids)
    print(f"descargados ahora: {nuevos} | errores: {errores}")

    for col in {u["coleccion"] for u in unidades}:
        destino = os.path.join(DST, col)
        if os.path.isdir(destino):
            shutil.rmtree(destino)
    informe, sin_right, omitidos = [], [], []
    tablero, claves, hojas = collections.Counter(), set(), collections.Counter()
    ficheros = marcas = noascii = 0
    for u in unidades:
        carpeta = os.path.join(DST, u["coleccion"], u["capitulo"])
        os.makedirs(carpeta, exist_ok=True)
        valor = DIFFICULTY_POR_NIVEL.get(u["nivel"])
        if valor:
            open(os.path.join(carpeta, f"difficulty-{valor}"), "a").close()
        for pos, pid in enumerate(u["problemas"], 1):
            path = os.path.join(CACHE, pid + ".json")
            if not ya_descargado(path):
                informe.append(f"{u['capitulo']}: problema {pid[:8]} sin descargar")
                continue
            d = json.load(open(path, encoding="utf-8"))
            try:
                sgf, avisos = problem_to_sgf(d)
                t = parse_edn(d["variations"])
            except Exception as e:
                informe.append(f"{u['capitulo']}/{pid[:8]}: NO CONVERTIDO ({str(e)[:60]})")
                continue
            r, w = sgf.count("C[RIGHT"), sgf.count("C[WRONG")
            if r + w == 0:
                omitidos.append(f"{u['capitulo']}/{pid[:8]}")
                informe.append(f"{u['capitulo']}/{pid[:8]}: OMITIDO, diagrama sin soluciones")
                continue
            sgf = sgf.replace("(;GM[1]FF[4]", "(;GM[1]FF[4]CA[UTF-8]", 1)
            for a in avisos:
                informe.append(f"{u['capitulo']}/{pid[:8]}: {a}")
            tablero[t.get(":board-size") or "sin dato (19)"] += 1
            claves_nodo(t.get(":children"), claves)
            m = t.get(":marks") or {}
            if any(m.get(k) for k in (":circle", ":square", ":triangle")) or t.get(":labels"):
                marcas += 1
            hojas["RIGHT"] += r
            hojas["WRONG"] += w
            if r == 0:
                sin_right.append(f"{u['capitulo']}/{pid[:8]}")
            if any(ord(ch) > 127 for ch in sgf):
                noascii += 1
            fich = os.path.join(carpeta, f"{pos:02d}_{pid[:8]}.sgf")
            with open(fich, "w", encoding="utf-8", newline="\n") as f:
                f.write(sgf)
            ficheros += 1
    print(f"\nficheros escritos: {ficheros} en {DST}")
    print("tamaños de tablero:", dict(tablero), "| hojas:", dict(hojas))
    print("claves de nodo vistas:", sorted(claves))
    print(f"problemas con marcas o labels: {marcas} | con texto no ASCII: {noascii}")
    print(f"omitidos por no ser ejercicios (diagramas sin soluciones): {len(omitidos)}")
    print("problemas sin ninguna hoja RIGHT:", sin_right)
    with open("informe_niveles.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(informe))
    print(f"avisos en informe_niveles.txt: {len(informe)}")

if __name__ == "__main__":
    main()