#!/usr/bin/env python3
"""
Baja y convierte los problemas de las lecciones de Awesome Baduk a la source `awesome_lessons`.

Estructura de salida (carpeta salida_awesome_lessons):
    <coleccion por nivel 0-5> / <capitulo = titulo del curso> / difficulty-<valor>
                                                              / NN_id8.sgf

Uso (PowerShell, desde la carpeta de los scripts de awesome_baduk):
    python lecciones_problemas.py plan          # solo plan, no descarga nada, no hace login
    python lecciones_problemas.py               # todos los niveles
    python lecciones_problemas.py 3             # solo el nivel 3
    python lecciones_problemas.py 0,1 plan      # plan de los niveles 0 y 1

Necesita en la misma carpeta: lesson_problems.json, awesome_to_player.py, niveles_academia.py,
list_inventory.py, analyze_all.py, convert_problems.py y el token awesomebaduk_rt (solo al descargar).
Es reanudable: lo que ya esta en problems_raw no se vuelve a bajar.
"""
import os, re, sys, json, shutil, collections

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from analyze_all import parse_edn
from convert_problems import problem_to_sgf
from niveles_academia import descargar, ya_descargado, CACHE
import awesome_to_player as A

# ── Config ─────────────────────────────────────────────────────────────
ENTRADA = "lesson_problems.json"
DST = "salida_awesome_lessons"
ENLACES = "awesome_lessons_links.json"       # lessonId -> capitulo y ficheros
PLAN = "plan_awesome_lessons.txt"
INFORME = "informe_awesome_lessons.txt"

# Longitud maxima del nombre de capitulo (niveles_academia usa 60, que corta numeros de serie)
LIMITE_NOMBRE = 120

# Nombre de la coleccion de cada nivel (0 = group-all ... 5 = group-a)
COLECCION = {
    0: "Lessons 0 - All levels",
    1: "Lessons 1 - Beginners",
    2: "Lessons 2 - Group D",
    3: "Lessons 3 - Group C",
    4: "Lessons 4 - Group B",
    5: "Lessons 5 - Group A",
}
# Marcador de dificultad por capitulo (grupo D 10K-15K, C 6K-9K, B 1K-5K, A 1D-5D)
DIFFICULTY = {0: "30k", 1: "20k", 2: "12k", 3: "8k", 4: "3k", 5: "3d"}

# Curso duplicado con audio incompleto: se descarta (nos quedamos con Ejwk2Z...)
DESCARTAR = {"f8SCiKxyZ2lEGDARMP1H"}

# Cursos sin target-group: nivel del primero de su serie, o 0 si no hay serie
SIN_GRUPO = {
    "6ZiN1rVHraGZKTUrSQ5g": 3,   # Choosing the perfect Jeong-Seock 4
    "DBdyuG5BkhH70GaTzYZC": 2,   # Tips for best 50 moves ... level 2
    "bOYvsYWZ8rlYhv2BjbIh": 2,   # Tips for best 50 moves ... level 3
    "ND462hwtmPAFAYCbU2EY": 4,   # Let's master 3-3 invasion ... 3
    "U08kQVWQL95D4QO98l0h": 4,   # Let's master 3-3 invasion ... 2
    "VKXX9XE2LT1LsVjOfawO": 3,   # Don't Be Afraid Giving Your Stones! - Avoid Bad Shape 3
    "m53s3mbjnaSyrE08fBRz": 5,   # The hidden truth of Jeong-Seock 3
    "uNj7nGORubCAD6ZmySgn": 0,   # Game Review - 1st Fujitsu Cup Final (sin serie)
    "HAQWWQbxZApmALv6Kidz": 0,   # New course (sin serie)
}
# ───────────────────────────────────────────────────────────────────────


def limpiar_nombre(s, limite=LIMITE_NOMBRE):
    """Igual que limpiar() de niveles_academia, pero con limite propio."""
    s = s.replace("/", " - ")
    s = re.sub(r'[<>:"\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limite].strip(" .-")


def nivel_de(cid, grupo):
    """Misma regla que el conversor de lecciones (difficulty_from_group); si el curso
    no tiene grupo, la tabla SIN_GRUPO. None = sin nivel."""
    v = A.difficulty_from_group(grupo)
    if v != "":
        return int(v)
    return SIN_GRUPO.get(cid)


def cargar():
    with open(ENTRADA, encoding="utf-8") as f:
        datos = json.load(f)
    cursos = collections.OrderedDict()
    descartados = []
    for e in datos:
        cid = e["courseId"]
        if cid in DESCARTAR:
            descartados.append(e)
            continue
        c = cursos.setdefault(cid, {"id": cid, "titulo": (e.get("course") or "").strip(),
                                    "grupo": e.get("targetGroup") or "", "entradas": []})
        c["entradas"].append(e)
    for c in cursos.values():
        c["entradas"].sort(key=lambda e: e["clip"])
        c["nivel"] = nivel_de(c["id"], c["grupo"])
        c["problemas"] = [pid for e in c["entradas"] for pid in e["problems"]]
    return cursos, descartados


def planificar(cursos, niveles):
    sin_nivel = [c for c in cursos.values() if c["nivel"] is None]
    unidades = [c for c in cursos.values()
                if c["nivel"] is not None and (niveles is None or c["nivel"] in niveles)]
    unidades.sort(key=lambda c: (c["nivel"], c["titulo"].lower()))
    usados = collections.defaultdict(set)
    for c in unidades:
        base = limpiar_nombre(c["titulo"]) or f"Course {c['id'][:6]}"
        nombre, k = base, 2
        while nombre.lower() in usados[c["nivel"]]:
            nombre = f"{base} ({k})"
            k += 1
        usados[c["nivel"]].add(nombre.lower())
        c["capitulo"] = nombre
        c["renombrado"] = nombre != base
        c["coleccion"] = COLECCION[c["nivel"]]
    return unidades, sin_nivel


def mostrar_plan(unidades, sin_nivel, descartados):
    por_nivel = collections.OrderedDict()
    for c in unidades:
        por_nivel.setdefault(c["nivel"], []).append(c)
    lineas = []
    for nivel, cs in por_nivel.items():
        total = sum(len(c["problemas"]) for c in cs)
        cache = sum(1 for c in cs for p in c["problemas"] if ya_descargado(os.path.join(CACHE, p + ".json")))
        lineas.append(f"{COLECCION[nivel]} (difficulty-{DIFFICULTY[nivel]}): "
                      f"{len(cs)} capitulos, {total} problemas, {cache} ya en la cache")
        for c in cs:
            marca = "  (nombre repetido, se renombra)" if c["renombrado"] else ""
            lineas.append(f"     {c['capitulo']}  [{len(c['problemas'])}]{marca}")
    cambiados = [c for c in unidades if c["capitulo"] != c["titulo"]]
    recortados = [c["titulo"] for c in unidades if len(limpiar_nombre(c["titulo"], 10**6)) > LIMITE_NOMBRE]
    sin_lesson = sum(1 for c in unidades for e in c["entradas"] if e.get("lessonId") is None)
    renombrados = [c["capitulo"] for c in unidades if c["renombrado"]]
    lineas.append("")
    lineas.append(f"TOTAL: {len(por_nivel)} colecciones, {len(unidades)} capitulos, "
                  f"{sum(len(c['problemas']) for c in unidades)} problemas")
    lineas.append(f"cursos descartados: {sorted({e['courseId'] for e in descartados})} "
                  f"({sum(len(e['problems']) for e in descartados)} problemas)")
    lineas.append(f"cursos SIN nivel (no se generan): {[(c['id'], c['titulo']) for c in sin_nivel]}")
    lineas.append(f"capitulos renombrados por llamarse igual: {renombrados}")
    lineas.append(f"capitulos cuyo nombre difiere del titulo del curso (recortado o con signos quitados): "
                  f"{len(cambiados)}")
    for c in cambiados:
        lineas.append(f"     {c['titulo']!r}  ->  {c['capitulo']!r}")
    lineas.append(f"capitulos recortados por LONGITUD (limite {LIMITE_NOMBRE}): {len(recortados)} {recortados}")
    lineas.append(f"clips sin lessonId (se generan, pero sin enlace a leccion): {sin_lesson}")
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    return lineas


def main():
    tokens = [a.lower() for a in sys.argv[1:]]
    solo_plan = "plan" in tokens
    resto = [t for t in tokens if t != "plan"]
    niveles = None
    if resto and resto[0] != "todos":
        niveles = [int(x) for x in resto[0].split(",")]

    cursos, descartados = cargar()
    unidades, sin_nivel = planificar(cursos, niveles)
    if not unidades:
        print("Ningun curso coincide con el filtro de niveles.")
        return
    lineas = mostrar_plan(unidades, sin_nivel, descartados)
    resumen = [l for l in lineas if not l.startswith("     ")]
    print("\n".join(resumen[:40]))
    print(f"\nPlan completo en {PLAN}")
    if solo_plan:
        print("(no se ha descargado nada)")
        return
    if sin_nivel:
        print("\nHay cursos sin nivel; no se generan. Revisa SIN_GRUPO antes de seguir.")

    from list_inventory import login
    H = login()
    ids = [pid for c in unidades for pid in c["problemas"]]
    print(f"\nproblemas a revisar: {len(ids)} ({len(set(ids))} distintos)")
    nuevos, errores = descargar(H, ids)
    print(f"descargados ahora: {nuevos} | errores: {errores}")

    for col in {c["coleccion"] for c in unidades}:
        destino = os.path.join(DST, col)
        if os.path.isdir(destino):
            shutil.rmtree(destino)

    informe, sin_right, omitidos, enlaces = [], [], [], []
    tablero, hojas = collections.Counter(), collections.Counter()
    ficheros = noascii = 0
    for c in unidades:
        carpeta = os.path.join(DST, c["coleccion"], c["capitulo"])
        os.makedirs(carpeta, exist_ok=True)
        open(os.path.join(carpeta, f"difficulty-{DIFFICULTY[c['nivel']]}"), "a").close()
        ancho = max(2, len(str(len(c["problemas"]))))
        pos = 0
        clips = []
        for e in c["entradas"]:
            lista = []
            for pid in e["problems"]:
                pos += 1
                path = os.path.join(CACHE, pid + ".json")
                if not ya_descargado(path):
                    informe.append(f"{c['capitulo']}: problema {pid[:8]} sin descargar")
                    lista.append({"id": pid, "file": None})
                    continue
                d = json.load(open(path, encoding="utf-8"))
                try:
                    sgf, avisos = problem_to_sgf(d)
                    t = parse_edn(d["variations"])
                except Exception as ex:
                    informe.append(f"{c['capitulo']}/{pid[:8]}: NO CONVERTIDO ({str(ex)[:60]})")
                    lista.append({"id": pid, "file": None})
                    continue
                r, w = sgf.count("C[RIGHT"), sgf.count("C[WRONG")
                if r == 0:
                    # sin ninguna hoja RIGHT no se puede resolver nunca: diagrama sin soluciones
                    # o solo respuestas incorrectas
                    motivo = "diagrama sin soluciones" if w == 0 else "sin ninguna hoja RIGHT"
                    omitidos.append(f"{c['capitulo']}/{pid[:8]}")
                    informe.append(f"{c['capitulo']}/{pid[:8]}: OMITIDO, {motivo}")
                    lista.append({"id": pid, "file": None})
                    continue
                sgf = sgf.replace("(;GM[1]FF[4]", "(;GM[1]FF[4]CA[UTF-8]", 1)
                for a in avisos:
                    informe.append(f"{c['capitulo']}/{pid[:8]}: {a}")
                tablero[t.get(":board-size") or "sin dato (19)"] += 1
                hojas["RIGHT"] += r
                hojas["WRONG"] += w
                if r == 0:
                    sin_right.append(f"{c['capitulo']}/{pid[:8]}")
                if any(ord(ch) > 127 for ch in sgf):
                    noascii += 1
                nombre = f"{pos:0{ancho}d}_{pid[:8]}.sgf"
                with open(os.path.join(carpeta, nombre), "w", encoding="utf-8", newline="\n") as f:
                    f.write(sgf)
                ficheros += 1
                lista.append({"id": pid, "file": "/".join([c["coleccion"], c["capitulo"], nombre])})
            clips.append({"clip": e["clip"], "lessonId": e.get("lessonId"),
                          "vimeoId": e.get("vimeoId"), "problems": lista})
        enlaces.append({"courseId": c["id"], "course": c["titulo"], "level": c["nivel"],
                        "collection": c["coleccion"], "chapter": c["capitulo"], "clips": clips})

    with open(ENLACES, "w", encoding="utf-8") as f:
        json.dump(enlaces, f, indent=1, ensure_ascii=False)
    with open(INFORME, "w", encoding="utf-8") as f:
        f.write("\n".join(informe))
    print(f"\nficheros escritos: {ficheros} en {DST}")
    print("tamanos de tablero:", dict(tablero), "| hojas:", dict(hojas))
    print(f"con texto no ASCII: {noascii} | omitidos (sin soluciones o sin hoja RIGHT): {len(omitidos)}")
    print("problemas sin ninguna hoja RIGHT:", sin_right)
    print(f"avisos en {INFORME}: {len(informe)} | enlaces en {ENLACES}")


if __name__ == "__main__":
    main()
