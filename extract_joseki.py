#!/usr/bin/env python3
"""J3: extrae del cliente real las funciones PURAS del modo aprender de josekis
(jsXform, jsXformInv, jsMarkInfo, jsOptions, jsIsEndpoint, jsSignal,
jsNamePath, jsGhostsVisible) para probarlas en Node con test_joseki.js, y el módulo J3 completo
(joseki_ui_bundle.js) para su prueba de humo de UI. Mismo patrón que
extract_tags.py: si algo no se encuentra, aborta.

    python3 extract_joseki.py && node test_joseki.js
"""
import io, re
_html = io.open("tsumevault.html", encoding="utf-8", newline="").read()
src = max(re.findall(r"<script>(.*?)</script>", _html, re.S), key=len)
lines = src.split("\r\n")
def find_line(startswith, from_line=0):
    for i in range(from_line, len(lines)):
        if lines[i].strip().startswith(startswith):
            return i
    raise SystemExit(f"no encontrado: {startswith!r}")
def extract_block(start_idx):
    depth = 0; out = []; started = False
    for i in range(start_idx, len(lines)):
        line = lines[i]; out.append(line)
        for ch in line:
            if ch == "{": depth += 1; started = True
            elif ch == "}": depth -= 1
        if started and depth == 0:
            return "\n".join(out), i
    raise SystemExit(f"bloque sin cerrar desde línea {start_idx}")
chunks = []
def grab(marker):
    i = find_line(marker); block, _ = extract_block(i)
    chunks.append(f"// ── {marker} ──\n" + block)
for m in ("function jsXform(", "function jsXformInv(", "function jsMarkInfo(", "function jsOptions(",
          "function jsIsEndpoint(", "function jsSignal(", "function jsNamePath(", "function jsGhostsVisible("):
    grab(m)
bundle = "\n\n".join(chunks)
io.open("joseki_bundle.js", "w", encoding="utf-8", newline="").write(bundle)
print(f"joseki_bundle: {len(bundle)} chars, {len(chunks)} bloques")

# Bloque completo J3 (puras + UI) para la prueba de humo de UI con DOM/WGo
# simulados: desde la cabecera del módulo hasta justo antes de switchTab.
i0 = find_line("// ══ J3: JOSEKIS")
i1 = find_line("function switchTab(")
ui = "\n".join(lines[i0:i1])
io.open("joseki_ui_bundle.js", "w", encoding="utf-8", newline="").write(ui)
print(f"joseki_ui_bundle: {len(ui)} chars")
