import os
import sys
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(SCRIPT_DIR, "go_problems", "problems_clean")
REPORT_FILE = os.path.join(SCRIPT_DIR, "analizar_go_problems.txt")

ROOT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT


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


def all_nodes(node, acc=None):
    if acc is None:
        acc = []
    acc.append(node)
    for c in node["children"]:
        all_nodes(c, acc)
    return acc


def collect_leaves(node, acc=None):
    if acc is None:
        acc = []
    if not node["children"]:
        acc.append(node)
    else:
        for c in node["children"]:
            collect_leaves(c, acc)
    return acc


def comment_flags(node):
    c = " ".join(node["props"].get("C", [])).upper()
    has_right = "RIGHT" in c
    has_correct = "CORRECT" in c
    has_wrong = "WRONG" in c
    has_choice = "CHOICE" in c
    return has_right, has_correct, has_wrong, has_choice


def classify_leaf(node):
    has_right, has_correct, has_wrong, has_choice = comment_flags(node)
    if has_right or has_correct:
        if has_wrong:
            return "RIGHT+WRONG"  # conflicto
        return "RIGHT"
    if has_wrong:
        return "WRONG"
    if has_choice:
        return "CHOICE"
    return "SILENT"  # sin comentario de resultado


def has_move(node):
    return "B" in node["props"] or "W" in node["props"]


def count_depth(node, d=0):
    if not node["children"]:
        return d
    return max(count_depth(c, d + 1) for c in node["children"])


def analyze(root):
    nodes = all_nodes(root)
    leaves = collect_leaves(root)

    leaf_types = Counter(classify_leaf(l) for l in leaves)

    # comentarios en nodos NO hoja
    inner_flags = Counter()
    for n in nodes:
        if n in leaves:
            continue
        hr, hc, hw, hch = comment_flags(n)
        if hr or hc:
            inner_flags["RIGHT_in_inner"] += 1
        if hw:
            inner_flags["WRONG_in_inner"] += 1

    return {
        "num_nodes": len(nodes),
        "num_leaves": len(leaves),
        "depth": count_depth(root),
        "leaf_RIGHT": leaf_types["RIGHT"],
        "leaf_WRONG": leaf_types["WRONG"],
        "leaf_CHOICE": leaf_types["CHOICE"],
        "leaf_SILENT": leaf_types["SILENT"],
        "leaf_CONFLICT": leaf_types["RIGHT+WRONG"],
        "inner_RIGHT": inner_flags["RIGHT_in_inner"],
        "inner_WRONG": inner_flags["WRONG_in_inner"],
    }


def classify_problem(a):
    if a["leaf_RIGHT"] == 0 and a["leaf_WRONG"] == 0 and a["leaf_CHOICE"] == 0:
        return "NO_MARKERS"
    if a["leaf_CONFLICT"] > 0:
        return "CONFLICT"
    if a["leaf_RIGHT"] == 0:
        return "NO_RIGHT"  # solo WRONG y/o CHOICE
    if a["inner_RIGHT"] > 0:
        return "RIGHT_IN_INNER"  # el RIGHT no está en hoja
    return "OK"


def main():
    sgfs = []
    for d, _, files in os.walk(ROOT):
        for f in files:
            if f.lower().endswith(".sgf"):
                sgfs.append(os.path.join(d, f))

    print(f"SGFs encontrados: {len(sgfs)}")

    categories = defaultdict(list)
    stats = Counter()

    for i, path in enumerate(sgfs):
        if (i + 1) % 1000 == 0:
            print(f"  {i + 1}...")
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
            root = parse_sgf(text)
            if not root:
                stats["parse_error"] += 1
                continue
            a = analyze(root)
            cat = classify_problem(a)
            categories[cat].append((path, a))
            stats[cat] += 1
        except Exception:
            stats["error"] += 1

    lines = []
    lines.append("=" * 60)
    lines.append("ANALISIS GO_PROBLEMS")
    lines.append("=" * 60)
    lines.append(f"Total: {len(sgfs)}\n")
    for k, v in stats.most_common():
        lines.append(f"  {k:20} {v}")

    for cat in ["NO_MARKERS", "CONFLICT", "NO_RIGHT", "RIGHT_IN_INNER"]:
        items = categories.get(cat, [])
        if not items:
            continue
        lines.append(f"\n--- {cat} ({len(items)}) ---")
        for path, a in items[:15]:
            rel = os.path.relpath(path, ROOT)
            lines.append(f"  {rel}")
            lines.append(f"    {a}")

    report = "\n".join(lines)
    print(report)
    open(REPORT_FILE, "w", encoding="utf-8").write(report)
    print(f"\n→ {REPORT_FILE}")


if __name__ == "__main__":
    main()
