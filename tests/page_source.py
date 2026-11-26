"""AR3a: reconstruye tsumevault.html TAL COMO ERA antes de mover código a js/board_core.js y js/ai_pure.js.

Cada bloque movido deja en la página una línea "    // ⇢ js/<f>.js #N" y en el .js empieza con "// ⇠ #N …".
page_source() sustituye cada marca por su bloque (con la sangría de 4 espacios que tenía) y quita las dos
<script src> de esos ficheros, de modo que los extractores de tests ven exactamente la página de siempre.
test_page_source.py comprueba que el resultado es idéntico byte a byte al original guardado en git.
"""
import io, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ("board_core", "ai_pure")
_MARK = re.compile(r"^    // ⇢ js/(\w+)\.js #(\d+)$")
_HEAD = re.compile(r"^// ⇠ #(\d+) ")
_TAGS = "".join(f'  <script src="js/{f}.js"></script>\n' for f in FILES)


def _blocks(f, root):
    p = os.path.join(root, "js", f + ".js")
    if not os.path.exists(p):
        return {}
    lines = io.open(p, encoding="utf-8", newline="").read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    out, cur = {}, None
    for l in lines:
        m = _HEAD.match(l)
        if m:
            cur = int(m.group(1)); out[cur] = []; continue
        if cur is not None:
            out[cur].append("" if l == "" else "    " + l)
    return out


def page_source(root=ROOT, newline_crlf=None):
    raw = io.open(os.path.join(root, "tsumevault.html"), encoding="utf-8", newline="").read()
    crlf = "\r\n" in raw if newline_crlf is None else newline_crlf
    src = raw.replace("\r\n", "\n")
    blocks = {f: _blocks(f, root) for f in FILES}
    for f in FILES:
        for k in blocks[f]:
            blocks[f][k] = [l.replace("\r", "") for l in blocks[f][k]]
    out, used = [], set()
    for l in src.split("\n"):
        m = _MARK.match(l)
        if m:
            f, k = m.group(1), int(m.group(2))
            if (f, k) in used or k not in blocks.get(f, {}):
                raise SystemExit(f"page_source: marca sin bloque o repetida: {l.strip()}")
            used.add((f, k)); out.extend(blocks[f][k]); continue
        out.append(l)
    for f in FILES:
        for k in blocks[f]:
            if (f, k) not in used:
                raise SystemExit(f"page_source: bloque #{k} de js/{f}.js sin marca en la página")
    text = "\n".join(out).replace(_TAGS, "")
    return text.replace("\n", "\r\n") if crlf else text


if __name__ == "__main__":
    import sys
    sys.stdout.write(page_source())
