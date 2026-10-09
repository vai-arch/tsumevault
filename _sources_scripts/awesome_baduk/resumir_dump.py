import json, re

ARCHIVO = "find_chapters_dump.json"
CLAVES = ["chapter", "l-shape", "tripod", "l+1", "book", "libro"]
PREFIJOS = ["49d27623", "62859d32", "a57b04c5", "cc64a241", "e5f151d4"]
MAX_COINCIDENCIAS = 12

def aplanar(v, ruta=""):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from aplanar(x, f"{ruta}.{k}" if ruta else k)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from aplanar(x, f"{ruta}[{i}]")
    else:
        yield ruta, v

def forma(v):
    if isinstance(v, dict):
        return "dict{" + ", ".join(list(v)[:8]) + ("…" if len(v) > 8 else "") + "}"
    if isinstance(v, list):
        return f"list[{len(v)}]" + (f" de {forma(v[0])}" if v else "")
    if isinstance(v, str):
        return f"str({len(v)})"
    return type(v).__name__

def main():
    datos = json.load(open(ARCHIVO, encoding="utf-8"))
    por_col = {}
    for k in datos:
        por_col.setdefault(k.split("/")[0], []).append(k)
    print("documentos por colección:", {c: len(v) for c, v in por_col.items()})
    for k, doc in datos.items():
        tit = doc.get("title") or doc.get("name") or ""
        print(f"\n### {k[:40]} | {str(tit)[:70]}")
        print("   campos:", {c: forma(v) for c, v in doc.items()})
        hallazgos = []
        for ruta, val in aplanar(doc):
            s = str(val)
            low = s.lower()
            if any(p in s for p in PREFIJOS) or any(c in low for c in CLAVES):
                hallazgos.append(f"{ruta} = {s[:100]!r}")
        if hallazgos:
            print(f"   coincidencias ({len(hallazgos)}):")
            for h in hallazgos[:MAX_COINCIDENCIAS]:
                print("     ", h)
            if len(hallazgos) > MAX_COINCIDENCIAS:
                print(f"      … {len(hallazgos) - MAX_COINCIDENCIAS} más")

if __name__ == "__main__":
    main()