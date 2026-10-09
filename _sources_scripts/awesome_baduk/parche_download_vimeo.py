#!/usr/bin/env python3
"""
Parche de download_vimeo_batch.py: anade la opcion --skip-catalog RUTA.

Con ella, el script salta los audios cuyo id de Vimeo ya figura como sourceVimeoId en el catalogo de
lecciones (awesome_baduk_lessons.json): son audios ya convertidos y publicados, asi que no hace falta
conservar los .m4a viejos para no volver a bajarlos. Sin la opcion, el comportamiento no cambia.

Uso (desde la carpeta de los scripts):
    python parche_download_vimeo.py                 # parchea download_vimeo_batch.py
    python parche_download_vimeo.py otro_script.py

Cada sustitucion exige exactamente 1 coincidencia; si no, no se escribe nada. Hace copia .bak antes
y comprueba la sintaxis despues (si falla, restaura la copia).
"""
import py_compile
import re
import shutil
import sys
from pathlib import Path

ruta = Path(sys.argv[1] if len(sys.argv) > 1 else "download_vimeo_batch.py")
orig = ruta.read_bytes()
crlf = b"\r\n" in orig
NL = "\r\n" if crlf else "\n"
txt = orig.decode("utf-8")

if "--skip-catalog" in txt:
    raise SystemExit("Ya esta parcheado (contiene --skip-catalog). No se hace nada.")


def una_vez(patron, desc):
    n = len(re.findall(patron, txt, flags=re.M))
    if n != 1:
        raise SystemExit(f"ERROR: '{desc}' aparece {n} veces (se esperaba 1). No se ha escrito nada.")


# 1) opcion nueva, justo despues de --pause (mismo sangrado que esa linea)
P1 = r'^([ \t]*)ap\.add_argument\("--pause", type=float, default=1\.0\)[ \t]*(?=\r?$)'
una_vez(P1, 'ap.add_argument("--pause" ...)')
NUEVA_OPCION = (
    '{i}ap.add_argument("--skip-catalog", default=None,{n}'
    '{i}                help="catalogo de lecciones (awesome_baduk_lessons.json): se saltan los audios "{n}'
    '{i}                     "cuyo id de Vimeo ya figura como sourceVimeoId")'
)
txt = re.sub(P1, lambda m: m.group(0) + NL + NUEVA_OPCION.format(i=m.group(1), n=NL), txt, count=1, flags=re.M)

# 2) funcion auxiliar justo antes de run_one
P2 = r'^def run_one\(args, vid, mode, outdir\):[ \t]*(?=\r?$)'
una_vez(P2, "def run_one(args, vid, mode, outdir):")
AUX = NL.join([
    "_SKIP_IDS = None",
    "",
    "",
    "def skip_ids(args):",
    '    """Ids de Vimeo ya publicados segun --skip-catalog (se carga una sola vez)."""',
    "    global _SKIP_IDS",
    "    if _SKIP_IDS is None:",
    "        _SKIP_IDS = set()",
    '        ruta_cat = getattr(args, "skip_catalog", None)',
    "        if ruta_cat:",
    '            rows = json.loads(Path(ruta_cat).read_text(encoding="utf-8-sig"))["rows"]',
    '            _SKIP_IDS = {str(r["sourceVimeoId"]) for r in rows if r.get("sourceVimeoId")}',
    '            log.info("Catalogo %s: %d audios ya publicados se saltan", ruta_cat, len(_SKIP_IDS))',
    "    return _SKIP_IDS",
    "",
    "",
    "",
])
txt = re.sub(P2, lambda m: AUX + m.group(0), txt, count=1, flags=re.M)

# 3) el salto, justo despues de calcular target dentro de run_one
P3 = r'^([ \t]+)target = outdir / f"\{vid\}\.\{ext\}"[ \t]*(?=\r?$)'
una_vez(P3, 'target = outdir / f"{vid}.{ext}"')
SALTO = (
    '{i}if mode == "audio" and not args.force and str(vid) in skip_ids(args):{n}'
    '{i}    return True, "skipped (ya en catalogo)"'
)
txt = re.sub(P3, lambda m: m.group(0) + NL + SALTO.format(i=m.group(1), n=NL), txt, count=1, flags=re.M)

copia = ruta.with_name(ruta.name + ".bak")
shutil.copy2(ruta, copia)
ruta.write_bytes(txt.encode("utf-8"))
try:
    py_compile.compile(str(ruta), doraise=True)
except py_compile.PyCompileError as e:
    shutil.copy2(copia, ruta)
    raise SystemExit(f"ERROR de sintaxis tras el parche; restaurado el original.\n{e}")
print(f"Parcheado {ruta} ({'CRLF' if crlf else 'LF'}). Copia: {copia.name}")
