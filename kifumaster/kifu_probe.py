#!/usr/bin/env python3
"""AR1.0 (WORKPLAN_ARCHIVO.md): baja unas pocas muestras públicas de kifumaster.org para fijar
el formato exacto antes de escribir el descargador. Una petición cada ~6-8 s, de una en una.

    python kifumaster/kifu_probe.py            (o kifu_probe.bat desde la raíz)

Deja en kifumaster/data/probe/ el cuerpo de cada respuesta, sus cabeceras y un resumen.txt.
Es reanudable: lo ya descargado con éxito no se vuelve a pedir. Ante 429 o 5xx se para.
"""
import json, os, random, sys, time, urllib.error, urllib.request

BASE = os.environ.get("KIFU_BASE", "https://kifumaster.org/")
UA = "TsumeVault-archive/0.1 (estudio personal; +https://github.com/vai-arch/tsumevault)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "probe")
DELAY = (6.0, 8.0) if "KIFU_BASE" not in os.environ else (0.0, 0.0)   # sin pausa solo en los tests locales

SAMPLES = [
    "seo/g/04.json",                        # índice: un reparto de los 256
    "seo/te/d3.json",                       # evento -> torneo/edición
    "seo/te/00.json",                       # ¿hay 256 repartos de te?
    "seo/te/ff.json",
    "tournament/meijin",                    # página del torneo (lista de ediciones)
    "tournament/meijin/52",                 # edición con fases (principal, Preliminary B/C)
    "tournament/korean-baduk-league/2017",  # edición de una liga por temporadas
]

def fname(path):
    return path.replace("/", "_")

def fetch(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""

def summarize(path, status, headers, body):
    h = {k.lower(): v for k, v in headers.items()}
    parts = [f"{status}", path, f"{len(body)} B", h.get("content-type", "?")]
    parts.append("ETag" if "etag" in h else "sin ETag")
    parts.append("Last-Modified" if "last-modified" in h else "sin Last-Modified")
    if status == 200 and path.endswith(".json"):
        try:
            j = json.loads(body)
            parts.append(f"{len(j)} claves" if isinstance(j, dict) else f"{type(j).__name__} de {len(j)}")
        except ValueError:
            parts.append("JSON no válido")
    return " | ".join(parts)

def main():
    os.makedirs(OUT, exist_ok=True)
    lines = []
    for i, path in enumerate(SAMPLES):
        body_f = os.path.join(OUT, fname(path) + ".body")
        head_f = os.path.join(OUT, fname(path) + ".headers.json")
        if os.path.exists(body_f) and os.path.exists(head_f):
            with open(head_f, encoding="utf-8") as f:
                meta = json.load(f)
            with open(body_f, "rb") as f:
                line = summarize(path, meta["status"], meta["headers"], f.read()) + " (ya descargado)"
            print(line); lines.append(line)
            continue
        if i and DELAY[1]:
            time.sleep(random.uniform(*DELAY))
        status, headers, body = fetch(path)
        line = summarize(path, status, headers, body)
        print(line, flush=True); lines.append(line)
        if status == 200:
            with open(body_f, "wb") as f:
                f.write(body)
            with open(head_f, "w", encoding="utf-8") as f:
                json.dump({"status": status, "headers": headers}, f, ensure_ascii=False, indent=1)
        elif status == 429 or status >= 500:
            lines.append(f"PARADO: el servidor respondió {status}; no se sigue pidiendo nada.")
            print(lines[-1]); break
    with open(os.path.join(OUT, "resumen.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nResumen en {os.path.join(OUT, 'resumen.txt')}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
