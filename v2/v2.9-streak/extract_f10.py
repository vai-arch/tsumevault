#!/usr/bin/env python3
"""Extrae, del cliente real, las funciones F10 (racha + predicción de
reaparición) para probarlas en Node contra un sql.js real. Mismo patrón que
extract_bundle.py / extract_futureload.py."""
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
    depth = 0
    out = []
    started = False
    for i in range(start_idx, len(lines)):
        line = lines[i]
        out.append(line)
        for ch in line:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        if started and depth == 0:
            return "\n".join(out), i
    raise SystemExit(f"bloque sin cerrar desde línea {start_idx}")


chunks = []


def grab(marker, label=None):
    i = find_line(marker)
    block, _ = extract_block(i)
    chunks.append(f"// ── {label or marker} ──\n" + block)


grab("function dbExec(")
grab("function dbQuery(")
grab("function dbQueryOne(")
grab("function localGetStreak(")
grab("function predictNextInterval(")

bundle = "\n\n".join(chunks)
io.open("f10_bundle.js", "w", encoding="utf-8", newline="").write(bundle)
print(f"f10_bundle: {len(bundle)} chars, {len(chunks)} bloques")
