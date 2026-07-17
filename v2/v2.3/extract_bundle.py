#!/usr/bin/env python3
"""Extrae del cliente MODIFICADO las funciones de sync para probarlas en Node.

Extracción por emparejamiento de llaves desde la línea de inicio de cada
función/bloque. Si algo no se encuentra, aborta: el arnés debe probar el
código real, no una copia divergente.
"""
import io, sys

import re as _re
_html = io.open("tsumevault.html", encoding="utf-8", newline="").read()
src = max(_re.findall(r"<script>(.*?)</script>", _html, _re.S), key=len)
io.open("client_script.js", "w", encoding="utf-8", newline="").write(src)
lines = src.split("\r\n")

def find_line(startswith, from_line=0):
    for i in range(from_line, len(lines)):
        if lines[i].strip().startswith(startswith):
            return i
    raise SystemExit(f"no encontrado: {startswith!r}")

def extract_block(start_idx):
    """Desde la línea start_idx, devuelve el bloque hasta cerrar llaves."""
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

# Orden de dependencias
grab("const SYNC_TOKEN_KEY")            # solo la const (línea única)
grab("function syncFetch(")
grab("function localDateStr(")
grab("function localCountReviewPending(")
grab("function makeUUID(")
grab("function dbExec(")
grab("function dbQuery(")
grab("function dbQueryOne(")
grab("async function saveDB(")
# bloque de debounce: desde 'let saveDBTimer' hasta el listener de pagehide
i0 = find_line("let saveDBTimer")
i1 = find_line("window.addEventListener('pagehide'")
chunks.append("// ── debounce saveDB ──\n" + "\n".join(lines[i0:i1 + 1]))
grab("function getSyncMeta(")
grab("function setSyncMeta(")
grab("function migrateSyncMeta(")
grab("function migrateSyncColumns(")
grab("function createSchema(")
grab("function localInsertAttempt(")
grab("function updateSm2(")
grab("function localInsertRun(")
grab("function localUpdateRunStatus(")
grab("async function purgeEmptyRuns(")
grab("async function tryAutoSync(")
grab("async function doSync(")
grab("async function syncDeletedRuns(")
grab("async function deleteRun(")
grab("function localGetRunItems(")
grab("async function resumeRun(")

bundle = "\n\n".join(chunks)

# La const de SYNC_TOKEN_KEY es una línea sin llaves: extract_block habrá
# devorado de más; corregimos extrayéndola a mano.
tok_line = lines[find_line("const SYNC_TOKEN_KEY")]
assert "sync_token" in tok_line
# Reconstruimos: el primer chunk es erróneo (una const no abre llaves y el
# extractor siguió hasta la primera función con llaves). Lo sustituimos.
chunks[0] = "// ── SYNC_TOKEN_KEY ──\n" + tok_line
bundle = "\n\n".join(chunks)

io.open("harness_bundle.js", "w", encoding="utf-8", newline="").write(bundle)
print(f"bundle: {len(bundle)} chars, {len(chunks)} bloques")
