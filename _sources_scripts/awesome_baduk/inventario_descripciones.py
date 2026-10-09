import json
import os
import re
import sys
from collections import defaultdict

RAIZ = sys.argv[1] if len(sys.argv) > 1 else "problems_raw"
SALIDA = "informe_descripciones.txt"
SOLO_TURNO = re.compile(
    r"^\s*(black|white)\s+to\s+(play|move)\s*[.!]?\s*$", re.I)
SEP = re.compile(r"\s*/\s*|\r?\n")


def problemas(obj):
    if isinstance(obj, dict):
        if "description" in obj or "variations" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from problemas(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from problemas(v)


def analizar(desc):
    segs = [s.strip() for s in SEP.split(desc or "") if s.strip()]
    color = None
    resto = []
    for s in segs:
        m = SOLO_TURNO.match(s)
        if m:
            color = m.group(1).lower()
        else:
            resto.append(s)
    return color, "\n".join(resto)


def main():
    vistos = set()
    n_json = n_malos = 0
    total = sin_desc = solo_turno = 0
    incoherentes = []
    grupos = defaultdict(list)
    for base, _, ficheros in os.walk(RAIZ):
        for f in ficheros:
            if not f.lower().endswith(".json"):
                continue
            n_json += 1
            ruta = os.path.join(base, f)
            try:
                with open(ruta, encoding="utf-8") as fh:
                    datos = json.load(fh)
            except Exception:
                n_malos += 1
                continue
            for p in problemas(datos):
                pid = str(p.get("id") or f)
                if pid in vistos:
                    continue
                vistos.add(pid)
                total += 1
                desc = p.get("description")
                if not (desc or "").strip():
                    sin_desc += 1
                    continue
                color, resto = analizar(desc)
                turno = (p.get("to-play") or "").lower()
                if color and turno and color != turno:
                    incoherentes.append(pid[:8])
                if resto:
                    grupos[resto].append(pid[:8])
                else:
                    solo_turno += 1

    lineas = [
        "Ficheros JSON leidos: %d (ilegibles: %d)" % (n_json, n_malos),
        "Problemas unicos: %d" % total,
        "Sin descripcion: %d" % sin_desc,
        "Solo 'X to play': %d" % solo_turno,
        "Con texto restante: %d" % sum(len(v) for v in grupos.values()),
        "Descripciones distintas restantes: %d" % len(grupos),
        "Color de la descripcion distinto de to-play: %d" % len(incoherentes),
    ]
    if incoherentes:
        lineas.append("  ids: " + ", ".join(incoherentes[:20]))
    lineas.append("")
    orden = sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for texto, ids in orden:
        una = texto.replace("\n", " | ")
        lineas.append("%5d  %s" % (len(ids), una))
        lineas.append("       ej: " + ", ".join(ids[:3]))
    informe = "\n".join(lineas)
    with open(SALIDA, "w", encoding="utf-8") as fh:
        fh.write(informe + "\n")
    print("\n".join(lineas[:60]))
    print("\nInforme completo en", SALIDA)


main()