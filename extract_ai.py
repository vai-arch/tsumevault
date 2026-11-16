#!/usr/bin/env python3
"""IA3: extrae de tsumevault.html el bloque de funciones puras de la partida contra
la IA (entre sus marcadores) a ai_bundle.js, para probarlo en Node con test_ai.js.
Aborta si no encuentra los marcadores: se prueba el código real, no una copia."""
import io
import re

html = io.open("tsumevault.html", encoding="utf-8", newline="").read()
src = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
a = src.find("// ── IA3: funciones puras")
b = src.find("// ── fin IA3 funciones puras ──")
if a < 0 or b < 0 or b < a:
    raise SystemExit("marcadores IA3 no encontrados")
io.open("ai_bundle.js", "w", encoding="utf-8", newline="").write(src[a:b])
print(f"ai_bundle: {b - a} chars")
