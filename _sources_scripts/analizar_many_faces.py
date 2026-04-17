import os
import sys
from collections import Counter, defaultdict

# ── Config ─────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(SCRIPT_DIR, "many_faces")
REPORT_FILE = os.path.join(SCRIPT_DIR, "analizar_many_faces.txt")
# ───────────────────────────────────────────────────────

ROOT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT


# ═══════════════════════════════════════════════════════
# PARSER SGF (igual que tus scripts)
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


def has_move(node):
    return "B" in node["props"] or "W" in node["props"]


def is_diagram(root):
    return not any(has_move(n) for n in all_nodes(root))


def count_depth(node, d=0):
    if not node["children"]:
        return d
    return max(count_depth(c, d + 1) for c in node["children"])


def branch_has_TE(node):
    if "TE" in node["props"]:
        return True
    return any(branch_has_TE(c) for c in node["children"])


# ═══════════════════════════════════════════════════════
# ANÁLISIS
# ═══════════════════════════════════════════════════════


def analyze(root):
    nodes = all_nodes(root)
    leaves = collect_leaves(root)

    te_nodes = [n for n in nodes if "TE" in n["props"]]
    te_in_leaf = sum(1 for n in leaves if "TE" in n["props"])
    te_total = len(te_nodes)

    branches_with_te = 0
    for child in root["children"]:
        if branch_has_TE(child):
            branches_with_te += 1

    return {
        "num_nodes": len(nodes),
        "num_leaves": len(leaves),
        "depth": count_depth(root),
        "root_branches": len(root["children"]),
        "te_total": te_total,
        "te_in_leaf": te_in_leaf,
        "branches_with_te": branches_with_te,
        "has_comments": any("C" in n["props"] for n in nodes),
        "is_diagram": is_diagram(root),
    }


def classify(a):
    if a["is_diagram"]:
        return "DIAGRAM"

    if a["te_total"] == 0:
        return "NO_TE"

    if a["branches_with_te"] == 1:
        return "ONE_SOLUTION"

    if a["branches_with_te"] > 1:
        return "MULTI_SOLUTION"

    if a["te_total"] > 0 and a["te_in_leaf"] == 0:
        return "TE_NOT_IN_LEAF"

    return "UNKNOWN"


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════


def main():
    if not os.path.isdir(ROOT):
        print(f"No existe: {ROOT}")
        return

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
            print(f"{i + 1}...")

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

            root = parse_sgf(text)
            if not root:
                stats["parse_error"] += 1
                continue

            a = analyze(root)
            cat = classify(a)

            categories[cat].append((path, a))
            stats[cat] += 1

        except Exception:
            stats["error"] += 1

    # ── REPORT ─────────────────────────────────────────

    lines = []
    lines.append("=" * 60)
    lines.append("ANALISIS MANY FACES")
    lines.append("=" * 60)
    lines.append(f"Total: {len(sgfs)}\n")

    for k, v in stats.most_common():
        lines.append(f"{k:20} {v}")

    lines.append("\n--- EJEMPLOS RAROS ---\n")

    for cat in ["NO_TE", "MULTI_SOLUTION", "TE_NOT_IN_LEAF", "UNKNOWN"]:
        items = categories.get(cat, [])
        if not items:
            continue
        lines.append(f"\n[{cat}] ({len(items)})")
        for path, a in items[:20]:
            rel = os.path.relpath(path, ROOT)
            lines.append(f"  {rel} | {a}")

    report = "\n".join(lines)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"\n→ {REPORT_FILE}")


if __name__ == "__main__":
    main()
