"""
analizar_sgf_tsumego.py v2 — Analiza todos los SGFs de tsumego_hero\problems\
y clasifica su formato para determinar el estándar de conversión.

Detecta: C[...], S[...], GC[...], N[...] y cualquier otra propiedad con valores
de resultado en nodos hoja.

Uso:
    python analizar_sgf_tsumego.py [ruta_tsumego_hero]

Por defecto busca en:
    tsumego_hero\problems\   (relativo al script)

Salida:
    analizar_sgf_tsumego_informe.txt
    analizar_sgf_tsumego_informe.json
    analizar_sgf_tsumego_unknown.txt
"""

import os
import sys
import json
from collections import defaultdict, Counter

# ── Config ───────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(SCRIPT_DIR, 'tsumego_hero', 'problems')
REPORT_FILE  = os.path.join(SCRIPT_DIR, 'analizar_sgf_tsumego_informe.txt')
UNKNOWN_FILE = os.path.join(SCRIPT_DIR, 'analizar_sgf_tsumego_unknown.txt')
# ─────────────────────────────────────────────────────────────────────────────

PROBLEMS_ROOT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT

# Propiedades que pueden contener marcadores de resultado
RESULT_PROPS = ('C', 'S', 'GC', 'N')


# ═══════════════════════════════════════════════════════════════════════════
# SGF PARSER
# ═══════════════════════════════════════════════════════════════════════════

def parse_sgf(text):
    pos = [0]
    n = len(text)

    def skip_ws():
        while pos[0] < n and text[pos[0]] in ' \t\r\n':
            pos[0] += 1

    def read_value():
        pos[0] += 1  # consume '['
        val = []
        while pos[0] < n:
            c = text[pos[0]]
            if c == '\\':
                pos[0] += 1
                if pos[0] < n:
                    val.append(text[pos[0]])
                    pos[0] += 1
            elif c == ']':
                pos[0] += 1
                break
            else:
                val.append(c)
                pos[0] += 1
        return ''.join(val)

    def read_node():
        skip_ws()
        if pos[0] >= n or text[pos[0]] != ';':
            return None
        pos[0] += 1

        props = {}
        skip_ws()
        while pos[0] < n and text[pos[0]] not in ';()':
            if not text[pos[0]].isupper():
                pos[0] += 1
                continue
            key = []
            while pos[0] < n and text[pos[0]].isupper():
                key.append(text[pos[0]])
                pos[0] += 1
            key = ''.join(key)
            vals = []
            skip_ws()
            while pos[0] < n and text[pos[0]] == '[':
                vals.append(read_value())
                skip_ws()
            if vals:
                props[key] = vals
            skip_ws()

        node = {'props': props, 'children': []}

        skip_ws()
        while pos[0] < n and text[pos[0]] == '(':
            pos[0] += 1
            child = read_node()
            if child:
                node['children'].append(child)
            skip_ws()
            if pos[0] < n and text[pos[0]] == ')':
                pos[0] += 1
            skip_ws()

        skip_ws()
        if pos[0] < n and text[pos[0]] == ';':
            sibling = read_node()
            if sibling:
                node['children'].insert(0, sibling)

        return node

    skip_ws()
    if pos[0] < n and text[pos[0]] == '(':
        pos[0] += 1
    return read_node()


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def is_leaf(node):
    return len(node['children']) == 0

def has_move(node):
    return 'B' in node['props'] or 'W' in node['props']

def board_size(node):
    return node['props'].get('SZ', ['19'])[0]

def first_move_color(node):
    for child in node['children']:
        if 'B' in child['props']: return 'B'
        if 'W' in child['props']: return 'W'
    return None

def all_nodes(node, acc=None):
    if acc is None:
        acc = []
    acc.append(node)
    for child in node['children']:
        all_nodes(child, acc)
    return acc

def collect_leaves(node, acc=None):
    if acc is None:
        acc = []
    if is_leaf(node):
        acc.append(node)
    else:
        for child in node['children']:
            collect_leaves(child, acc)
    return acc

def count_depth(node, d=0):
    if not node['children']:
        return d
    return max(count_depth(c, d+1) for c in node['children'])

def is_diagram_only(root):
    """Sin movimientos en ningún nodo del árbol."""
    return not any(has_move(n) for n in all_nodes(root))

def result_marker(val_str):
    """Clasifica un valor de propiedad de resultado."""
    v = val_str.strip()
    if not v:                    return ''
    u = v.upper()
    if v.startswith('+'):        return 'PLUS'
    if v.startswith('-'):        return 'MINUS'
    if u.startswith('RIGHT'):    return 'RIGHT'
    if u.startswith('WRONG'):    return 'WRONG'
    if u == 'DEAD':              return 'DEAD'
    if u in ('ALIVE', 'LIVE'):   return 'ALIVE'
    if 'SEKI' in u:              return 'SEKI_PLUS' if '+' in v else 'SEKI'
    if '+' in u:  return 'PLUS'   # KO+, SEKI+, cualquier variante con +
    return 'OTHER'

def get_markers_in_node(node):
    """Devuelve lista de (prop, raw_val, marker) para el nodo."""
    out = []
    for p in RESULT_PROPS:
        if p in node['props']:
            raw = node['props'][p][0].strip()
            out.append((p, raw, result_marker(raw)))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# CLASIFICADOR
# ═══════════════════════════════════════════════════════════════════════════

def classify(root):
    all_ns  = all_nodes(root)
    leaves  = collect_leaves(root)

    # Acumular marcadores en hojas y en todo el árbol
    leaf_markers = Counter()
    all_markers  = Counter()
    props_seen   = Counter()

    for n in all_ns:
        for p, raw, m in get_markers_in_node(n):
            props_seen[p] += 1
            all_markers[m] += 1

    for leaf in leaves:
        for p, raw, m in get_markers_in_node(leaf):
            leaf_markers[m] += 1
        # contar hojas vacías
        if not get_markers_in_node(leaf):
            leaf_markers[''] += 1

    num_leaves = len(leaves)

    has_plus   = leaf_markers['PLUS'] > 0 or all_markers['PLUS'] > 0
    has_right  = all_markers['RIGHT'] > 0
    has_wrong  = all_markers['WRONG'] > 0
    has_s      = 'S' in props_seen
    has_dead   = all_markers['DEAD'] > 0
    has_alive  = all_markers['ALIVE'] > 0
    has_seki   = all_markers['SEKI'] > 0 or all_markers['SEKI_PLUS'] > 0
    all_empty  = (leaf_markers.get('', 0) == num_leaves
                  and sum(v for k, v in leaf_markers.items() if k != '') == 0)

    details = {
        'num_leaves':    num_leaves,
        'depth':         count_depth(root),
        'board_size':    board_size(root),
        'first_move':    first_move_color(root),
        'root_branches': len(root['children']),
        'leaf_markers':  dict(leaf_markers),
        'all_markers':   dict(all_markers),
        'props_in_tree': dict(props_seen.most_common(20)),
    }

    if is_diagram_only(root):
        return 'DIAGRAM', details

    if has_right or has_wrong:
        if has_plus or (has_s and (has_dead or has_alive or has_seki)):
            return 'MIXED', details
        return 'IGS_RIGHTW', details

    if has_s and (has_dead or has_alive or has_seki):
        if has_plus or has_right:
            return 'MIXED', details
        return 'TH_S_STATUS', details

    if has_plus:
        return 'TH_PLUS', details

    if all_empty:
        if num_leaves == 1:
            return 'SINGLE_LINE', details
        return 'LEAF_EMPTY', details

    return 'UNKNOWN', details


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if not os.path.isdir(PROBLEMS_ROOT):
        print(f"Error: '{PROBLEMS_ROOT}' no existe.")
        sys.exit(1)

    print(f"Analizando SGFs en: {PROBLEMS_ROOT}")

    sgf_files = []
    for dirpath, _, filenames in os.walk(PROBLEMS_ROOT):
        for fname in filenames:
            if fname.lower().endswith('.sgf'):
                sgf_files.append(os.path.join(dirpath, fname))

    total = len(sgf_files)
    print(f"  SGFs encontrados: {total}  — procesando...")

    categories   = defaultdict(list)
    parse_errors = []

    for i, fpath in enumerate(sorted(sgf_files)):
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{total}...")
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            root = parse_sgf(text)
            if root is None:
                parse_errors.append((fpath, 'parse returned None'))
                continue
            cat, details = classify(root)
            categories[cat].append((fpath, details))
        except Exception as e:
            parse_errors.append((fpath, str(e)))

    print(f"  Completado.\n")

    # ── INFORME ───────────────────────────────────────────────────────────
    DESCRIPTIONS = {
        'TH_PLUS':     'C[+...] correcto, sin marcador = incorrecto  ← CONVERTIBLE',
        'TH_S_STATUS': 'S[SEKI+/DEAD/ALIVE]  ← CONVERTIBLE',
        'IGS_RIGHTW':  'C[RIGHT]/C[WRONG]  ← YA EN FORMATO',
        'MIXED':       'Mezcla de convenciones  ← REVISAR',
        'SINGLE_LINE': 'Un camino sin marcador  ← REVEAL',
        'LEAF_EMPTY':  'Múltiples variantes sin marcar  ← REVEAL',
        'DIAGRAM':     'Solo posición, sin movimientos  ← DESCARTAR',
        'UNKNOWN':     'Formato no reconocido  ← REVISAR MANUALMENTE',
    }
    CONVERTIBLE = {'TH_PLUS', 'TH_S_STATUS', 'IGS_RIGHTW'}
    REVEAL      = {'SINGLE_LINE', 'LEAF_EMPTY'}
    DISCARD     = {'DIAGRAM'}

    lines = []
    lines.append("=" * 72)
    lines.append("INFORME DE ANÁLISIS DE SGFs v2 — tsumego_hero")
    lines.append("=" * 72)
    lines.append(f"\nTotal SGFs:     {total}")
    lines.append(f"Errores parseo: {len(parse_errors)}")
    lines.append("")
    lines.append("─" * 72)
    lines.append("RESUMEN")
    lines.append("─" * 72)

    tc = tr = td = tu = 0
    for cat in sorted(categories, key=lambda c: -len(categories[c])):
        count = len(categories[cat])
        pct   = count / total * 100
        desc  = DESCRIPTIONS.get(cat, cat)
        lines.append(f"  {cat:<16}  {count:5d}  ({pct:5.1f}%)  {desc}")
        if cat in CONVERTIBLE: tc += count
        elif cat in REVEAL:    tr += count
        elif cat in DISCARD:   td += count
        else:                  tu += count

    if parse_errors:
        lines.append(f"  {'PARSE_ERROR':<16}  {len(parse_errors):5d}")

    lines.append("")
    lines.append(f"  ✓ CONVERTIBLES (interactivo) : {tc:5d}  ({tc/total*100:.1f}%)")
    lines.append(f"  ~ REVEAL                     : {tr:5d}  ({tr/total*100:.1f}%)")
    lines.append(f"  ✗ DESCARTAR                  : {td:5d}  ({td/total*100:.1f}%)")
    lines.append(f"  ? REVISAR                    : {tu:5d}  ({tu/total*100:.1f}%)")

    # Detalle para categorías no triviales
    for cat in ['TH_S_STATUS', 'MIXED', 'UNKNOWN', 'LEAF_EMPTY', 'DIAGRAM']:
        items = categories.get(cat, [])
        if not items:
            continue
        lines.append("")
        lines.append("─" * 72)
        lines.append(f"DETALLE — {cat}  ({len(items)} ficheros)")
        lines.append("─" * 72)
        for fpath, det in items[:60]:
            rel = os.path.relpath(fpath, PROBLEMS_ROOT)
            lines.append(f"\n  {rel}")
            lines.append(f"    leaves={det['num_leaves']}  depth={det['depth']}  "
                         f"size={det['board_size']}  first_move={det['first_move']}")
            lines.append(f"    leaf_markers : {det['leaf_markers']}")
            lines.append(f"    all_markers  : {det['all_markers']}")
            lines.append(f"    props_in_tree: {det['props_in_tree']}")
        if len(items) > 60:
            lines.append(f"\n  ... y {len(items)-60} más (ver unknown.txt)")

    # Ejemplos
    lines.append("")
    lines.append("─" * 72)
    lines.append("EJEMPLOS (1 fichero por categoría)")
    lines.append("─" * 72)
    for cat in sorted(categories):
        fpath, det = categories[cat][0]
        rel = os.path.relpath(fpath, PROBLEMS_ROOT)
        lines.append(f"  [{cat}] {rel}  "
                     f"leaves={det['num_leaves']} depth={det['depth']} "
                     f"size={det['board_size']} first={det['first_move']}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("FIN DEL INFORME")
    lines.append("=" * 72)

    report_text = '\n'.join(lines)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(report_text)
    print(f"\n→ Informe:  {REPORT_FILE}")

    # Unknown/Mixed detallado
    unk_lines = []
    for cat in ['UNKNOWN', 'MIXED', 'LEAF_EMPTY', 'DIAGRAM']:
        for fpath, det in categories.get(cat, []):
            rel = os.path.relpath(fpath, PROBLEMS_ROOT)
            unk_lines.append(f"[{cat}] {rel}")
            unk_lines.append(f"  leaf_markers={det['leaf_markers']}")
            unk_lines.append(f"  all_markers ={det['all_markers']}")
            unk_lines.append(f"  props       ={det['props_in_tree']}")
            unk_lines.append("")
    if unk_lines:
        with open(UNKNOWN_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(unk_lines))
        print(f"→ Unknowns: {UNKNOWN_FILE}")

    # JSON
    json_out = {
        'total': total,
        'parse_errors': len(parse_errors),
        'summary': {
            'convertible': tc, 'reveal': tr, 'discard': td, 'review': tu
        },
        'categories': {
            cat: {'count': len(items), 'pct': round(len(items)/total*100, 1)}
            for cat, items in categories.items()
        }
    }
    json_path = REPORT_FILE.replace('.txt', '.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2)
    print(f"→ JSON:     {json_path}")

    if parse_errors:
        print(f"\nERRORES DE PARSEO ({len(parse_errors)}):")
        for fpath, err in parse_errors[:20]:
            print(f"  {fpath}: {err}")


if __name__ == '__main__':
    main()