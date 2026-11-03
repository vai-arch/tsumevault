#!/usr/bin/env python3
"""FC2: extrae del cliente real la API local de Focus (y lo que necesita) para
probarla en Node contra un sql.js real. Mismo patrón que extract_tags.py.
Uso: python3 extract_focus.py && node test_focus.js"""
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
for m in ("function dbExec(", "function dbQuery(", "function dbQueryOne(", "function createSchema(",
          "function makeUUID(", "function localDateStr(", "function localInsertAttempt(", "function setChapterMostrar(",
          "function focusNorm(", "function focusStamp(", "function localFocusGet(", "function localFocusList(",
          "function localFocusNameTaken(", "function focusTouch(", "function focusSetChapterRow(",
          "function localFocusCreate(", "function localFocusRename(", "function localFocusDelete(",
          "function localFocusOfChapter(", "function localFocusChapterMap(", "function localFocusAddChapter(",
          "function localFocusRemoveChapter(", "function localChapterHasCompletedRun(", "function focusChapterState(",
          "function localFocusSetPromoted(", "function localFocusChapters(", "function localFocusArchiveCheck(",
          "function localFocusArchive(", "function localFocusReopen(", "function localFocusSessionProblems(",
          "function localFocusSessionStart(", "function localFocusSessionComplete(", "function focusFirstAttempts(",
          "function focusPct(", "function localFocusSessionStats(", "function localFocusProgress(",
          "function localFocusTodayStatus("):
    grab(m)
bundle = "\n\n".join(chunks)
io.open("focus_bundle.js", "w", encoding="utf-8", newline="").write(bundle)
print(f"focus_bundle: {len(bundle)} chars, {len(chunks)} bloques")
