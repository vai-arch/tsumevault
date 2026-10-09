#!/usr/bin/env python3
"""
Parche del catalogo de lecciones de Awesome Baduk (awesome_baduk_lessons.json):
  1) fija lessonDifficulty en las lecciones de cursos sin target-group (misma tabla que usa
     lecciones_problemas.py para las colecciones de problemas), y
  2) quita del catalogo cursos sobrantes (Test, New course vacios) y el curso duplicado
     f8SCiK... con audio incompleto (lecciones 900359 y 900361). Los ficheros de esas lecciones NO se tocan.

Es idempotente: se puede ejecutar de nuevo (por ejemplo tras regenerar el catalogo desde
all_lessons.new.json). Solo rellena dificultades que estan vacias; si una fila ya tiene OTRO valor,
avisa y no la toca. Hace copia con fecha antes de escribir.

Uso (PowerShell, desde _sources_scripts\\awesome_baduk):
    python parchear_catalogo.py --dry-run     # cuenta lo que haria, sin escribir
    python parchear_catalogo.py               # aplica el parche
    python parchear_catalogo.py otro.json     # otro catalogo

Despues: python merge_lessons.py ... (ver merge_lessons.bat) para regenerar all_lessons.json.
"""
import argparse
import collections
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

CATALOGO = r"..\..\player\lessons_sources\awesome_baduk_lessons.json"

# courseId -> dificultad. El 0 va como TEXTO "0": el player trata el numero 0 como "sin dificultad".
DIFICULTAD = {
    "6ZiN1rVHraGZKTUrSQ5g": 3,    # Choosing the perfect Jeong-Seock 4
    "VKXX9XE2LT1LsVjOfawO": 3,    # Don't Be Afraid Giving Your Stones! ... Avoid Bad Shape 3
    "DBdyuG5BkhH70GaTzYZC": 2,    # Tips for best 50 moves ... level 2
    "bOYvsYWZ8rlYhv2BjbIh": 2,    # Tips for best 50 moves ... level 3
    "ND462hwtmPAFAYCbU2EY": 4,    # Let's master 3-3 invasion ... 3
    "U08kQVWQL95D4QO98l0h": 4,    # Let's master 3-3 invasion ... 2
    "m53s3mbjnaSyrE08fBRz": 5,    # The hidden truth of Jeong-Seock 3
    "uNj7nGORubCAD6ZmySgn": "0",  # Game Review - 1st Fujitsu Cup Final
    "HAQWWQbxZApmALv6Kidz": "0",  # New course (con problemas)
    "E0cQMcCDhw9wkpSa5H57": "0",  # 14th Chunlan Cup Final Game 1
    "RalenloSZoxgwtkCgi2S": "0",  # Shin Jinseo Won the 9th Ing Cup
    "KFXxJgO1Dd66aGbxnlqD": "0",  # Wang Xinghao 9 dan won the 5th Nie Weiping Cup
}

# Cursos que se quitan enteros del catalogo
QUITAR_CURSOS = {
    "4FMUbz3OOMUipXZ9v6gl": "Test",
    "1mN2oDp7QXiVE0KH89IX": "New course (sin problemas)",
    "luwirvB0TxmtvSNuFoxh": "New course (sin problemas)",
    "f8SCiKxyZ2lEGDARMP1H": "Where are my Ko threats? (duplicado con audio incompleto)",
}

# Lecciones sueltas que se quitan: lessonId -> courseId que deben tener (comprobacion).
# Vacio: el curso duplicado f8SCiK... se quita entero (en el catalogo estan 900359 y 900361;
# la 900360 existe en el registro de IDs pero no tiene fila).
QUITAR_LECCIONES = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("catalogo", nargs="?", default=CATALOGO)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ruta = Path(args.catalogo)
    data = json.loads(ruta.read_text(encoding="utf-8-sig"))
    if not (isinstance(data, dict) and isinstance(data.get("rows"), list)):
        raise SystemExit(f"{ruta}: no tiene el formato {{\"rows\": [...]}}")
    filas = data["rows"]
    antes = len(filas)

    nuevas, quitadas = [], collections.Counter()
    fijadas = collections.Counter()
    ya_bien = distintas = 0
    vistos = set()
    for r in filas:
        cid, lid = r.get("sourceCourseId"), r.get("lessonId")
        if cid in QUITAR_CURSOS:
            quitadas[f"curso {cid} ({QUITAR_CURSOS[cid]})"] += 1
            continue
        if lid in QUITAR_LECCIONES:
            if cid != QUITAR_LECCIONES[lid]:
                print(f"AVISO: la leccion {lid} es del curso {cid}, no del esperado; NO se quita")
            else:
                quitadas[f"leccion {lid}"] += 1
                continue
        if cid in DIFICULTAD:
            vistos.add(cid)
            nuevo, actual = DIFICULTAD[cid], r.get("lessonDifficulty")
            if actual in ("", None):
                r["lessonDifficulty"] = nuevo
                fijadas[cid] += 1
            elif str(actual) == str(nuevo):
                ya_bien += 1
            else:
                distintas += 1
                print(f"AVISO: leccion {lid} ({cid}) ya tiene dificultad {actual!r}, no la cambio (tabla: {nuevo!r})")
        nuevas.append(r)

    sin_dif = [r for r in nuevas if r.get("lessonDifficulty") in ("", None)]
    print(f"filas antes: {antes} | despues: {len(nuevas)} | quitadas: {sum(quitadas.values())}")
    for k, n in quitadas.items():
        print(f"   quitada: {k} x{n}")
    print(f"dificultades fijadas: {sum(fijadas.values())} lecciones en {len(fijadas)} cursos"
          f" | ya correctas: {ya_bien} | con otro valor (sin tocar): {distintas}")
    faltan = [c for c in DIFICULTAD if c not in vistos]
    if faltan:
        print(f"cursos de la tabla que no estan (ya parcheado o no existen): {faltan}")
    print(f"lecciones que siguen sin dificultad: {len(sin_dif)}")
    for r in sin_dif[:10]:
        print(f"   {r.get('lessonId')} {r.get('collectionName')!r} ({r.get('sourceCourseId')})")

    if args.dry_run:
        print("\n(--dry-run: no se ha escrito nada)")
        return
    if len(nuevas) == antes and not fijadas:
        print("\nNada que cambiar; no se escribe.")
        return
    copia = ruta.with_name(ruta.name + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(ruta, copia)
    data["rows"] = nuevas
    ruta.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nEscrito {ruta}  (copia: {copia.name})")
    print("Siguiente paso: python merge_lessons.py ... --dry-run  y luego sin --dry-run (merge_lessons.bat).")


if __name__ == "__main__":
    main()
