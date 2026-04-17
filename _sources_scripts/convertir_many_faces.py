import os

# ── Config ─────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(SCRIPT_DIR, "many_faces", "problems")
DST = os.path.join(SCRIPT_DIR, "many_faces", "problems_std")
# ───────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════
# PARSER (igual que tus scripts)
# ═══════════════════════════════════════════════════════


def parse_sgf(text):
    pos = [0]
    n = len(text)

    def skip_ws():
        while pos[0] < n and text[pos[0]] in " \t\r\n":
            pos[0] += 1

    def read_value():
        pos[0] += 1
        val = []
        while pos[0] < n:
            c = text[pos[0]]
            if c == "\\":
                pos[0] += 1
                if pos[0] < n:
                    val.append(text[pos[0]])
                    pos[0] += 1
            elif c == "]":
                pos[0] += 1
                break
            else:
                val.append(c)
                pos[0] += 1
        return "".join(val)

    def read_node():
        skip_ws()
        if pos[0] >= n or text[pos[0]] != ";":
            return None
        pos[0] += 1

        props = {}
        skip_ws()
        while pos[0] < n and text[pos[0]] not in ";()":
            if not text[pos[0]].isupper():
                pos[0] += 1
                continue
            key = []
            while pos[0] < n and text[pos[0]].isupper():
                key.append(text[pos[0]])
                pos[0] += 1
            key = "".join(key)

            vals = []
            skip_ws()
            while pos[0] < n and text[pos[0]] == "[":
                vals.append(read_value())
                skip_ws()

            if vals:
                props[key] = vals

            skip_ws()

        node = {"props": props, "children": []}

        skip_ws()
        while pos[0] < n and text[pos[0]] == "(":
            pos[0] += 1
            child = read_node()
            if child:
                node["children"].append(child)
            skip_ws()
            if pos[0] < n and text[pos[0]] == ")":
                pos[0] += 1
            skip_ws()

        skip_ws()
        if pos[0] < n and text[pos[0]] == ";":
            sibling = read_node()
            if sibling:
                node["children"].insert(0, sibling)

        return node

    skip_ws()
    if pos[0] < n and text[pos[0]] == "(":
        pos[0] += 1
    return read_node()


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════


def is_leaf(node):
    return not node["children"]


def branch_has_TE(node):
    if "TE" in node["props"]:
        return True
    return any(branch_has_TE(c) for c in node["children"])


# ═══════════════════════════════════════════════════════
# CONVERSIÓN
# ═══════════════════════════════════════════════════════


def convert_node(node, has_te_in_path=False):
    current_has_te = has_te_in_path or ("TE" in node["props"])

    if is_leaf(node):
        result = "RIGHT" if current_has_te else "WRONG"

        old_c = node["props"].get("C", [""])[0].strip()

        if old_c:
            new_c = result + "\n" + old_c
        else:
            new_c = result

        node["props"]["C"] = [new_c]

        # limpiar TE en salida
        node["props"].pop("TE", None)
        return

    for child in node["children"]:
        convert_node(child, current_has_te)

    # limpiar TE en nodos intermedios
    node["props"].pop("TE", None)


# ═══════════════════════════════════════════════════════
# SERIALIZER
# ═══════════════════════════════════════════════════════


def escape(val):
    return val.replace("\\", "\\\\").replace("]", "\\]")


def serialize(node):
    parts = [";"]
    for k, vals in node["props"].items():
        parts.append(k)
        for v in vals:
            parts.append(f"[{escape(v)}]")

    if not node["children"]:
        return "".join(parts)

    if len(node["children"]) == 1:
        return "".join(parts) + serialize(node["children"][0])

    out = "".join(parts)
    for c in node["children"]:
        out += "(" + serialize(c) + ")"
    return out


def to_sgf(root):
    return "(" + serialize(root) + ")"


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════


def main():
    if not os.path.isdir(SRC):
        print(f"No existe: {SRC}")
        return

    for dirpath, _, files in os.walk(SRC):
        for fname in files:
            if not fname.lower().endswith(".sgf"):
                continue

            src_path = os.path.join(dirpath, fname)
            rel = os.path.relpath(src_path, SRC)
            dst_path = os.path.join(DST, rel)

            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            try:
                with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()

                root = parse_sgf(text)
                if not root:
                    continue

                convert_node(root)

                out = to_sgf(root)

                with open(dst_path, "w", encoding="utf-8") as f:
                    f.write(out)

            except Exception as e:
                print(f"ERROR: {rel} -> {e}")

    print("Conversión completada.")


if __name__ == "__main__":
    main()
