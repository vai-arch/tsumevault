"""
analizar_sgf_guojuan.py — Analiza todos los SGFs de guo_juan/problems_*/
y clasifica su formato para determinar compatibilidad y necesidad de transformación.

Uso:
    python analizar_sgf_guojuan.py [ruta_guo_juan]

Por defecto busca en:
    guo_juan/   (relativo al script)

Salida:
    analizar_sgf_guojuan_informe.txt   — informe detallado por categoría
    analizar_sgf_guojuan_unknown.txt   — SGFs con formato no reconocido
"""

import os
import re
import sys
import json
from collections import defaultdict, Counter

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(SCRIPT_DIR, 'guo_juan', 'problems')
REPORT_FILE  = os.path.join(SCRIPT_DIR, 'analizar_sgf_guojuan_informe.txt')
UNKNOWN_FILE = os.path.join(SCRIPT_DIR, 'analizar_sgf_guojuan_unknown.txt')
# ─────────────────────────────────────────────────────────────────────────────

GUO_JUAN_ROOT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT


# ═══════════════════════════════════════════════════════════════════════════
# SGF PARSER — mínimo, robusto
# ═══════════════════════════════════════════════════════════════════════════

def parse_sgf(text):
    """
    Devuelve root node: { 'props': {KEY:[val,...]}, 'children': [...] }
    Soporta \\ y \] dentro de valores, claves multiletter.
    """
    pos = [0]

    def skip_ws():
        while pos[0] < len(text) and text[pos[0]] in ' \t\r\n':
            pos[0] += 1

    def read_prop_value():
        assert text[pos[0]] == '[', f"Expected '[' at {pos[0]}"
        pos[0] += 1
        val = []
        while pos[0] < len(text):
            c = text[pos[0]]
            if c == '\\':
                pos[0] += 1
                if pos[0] < len(text):
                    val.append(text[pos[0]])
                    pos[0] += 1
            elif c == ']':
                pos[0] += 1
                break
            else:
                val.append(c)
                pos[0] += 1
        return ''.join(val)

    def read_props():
        """Lee las propiedades de un nodo (KEY[val]...) hasta ; ( )"""
        props = {}
        while pos[0] < len(text):
            skip_ws()
            c = text[pos[0]]
            if c in '(;)':
                break
            if c.isupper():
                key = []
                while pos[0] < len(text) and text[pos[0]].isupper():
                    key.append(text[pos[0]])
                    pos[0] += 1
                key = ''.join(key)
                vals = []
                skip_ws()
                while pos[0] < len(text) and text[pos[0]] == '[':
                    vals.append(read_prop_value())
                    skip_ws()
                props[key] = vals
            else:
                pos[0] += 1
        return props

    def read_node():
        skip_ws()
        assert text[pos[0]] == ';', f"Expected ';' at {pos[0]}"
        pos[0] += 1
        props = read_props()
        children = []
        skip_ws()
        while pos[0] < len(text):
            c = text[pos[0]]
            if c == ';':
                # Nodo siguiente en secuencia lineal — hijo único
                pos[0] += 1
                child_props = read_props()
                child_node = {'props': child_props, 'children': []}
                # Leer recursivamente los hijos de este hijo
                skip_ws()
                while pos[0] < len(text):
                    cc = text[pos[0]]
                    if cc == '(':
                        pos[0] += 1
                        grandchild = read_node()
                        child_node['children'].append(grandchild)
                        skip_ws()
                        if pos[0] < len(text) and text[pos[0]] == ')':
                            pos[0] += 1
                    elif cc == ';':
                        # Otro nodo en secuencia — envolver en hijo
                        pos[0] += 1
                        next_props = read_props()
                        next_node = {'props': next_props, 'children': []}
                        child_node['children'].append(next_node)
                        child_node = next_node
                    else:
                        break
                children.append(child_node)
                break
            elif c == '(':
                pos[0] += 1
                child = read_node()
                children.append(child)
                skip_ws()
                if pos[0] < len(text) and text[pos[0]] == ')':
                    pos[0] += 1
            else:
                break
        return {'props': props, 'children': children}

    def read_tree():
        skip_ws()
        if pos[0] >= len(text) or text[pos[0]] != '(':
            raise ValueError(f"Expected '(' at {pos[0]}, got '{text[pos[0]:pos[0]+10]}'")
        pos[0] += 1
        node = read_node()
        skip_ws()
        if pos[0] < len(text) and text[pos[0]] == ')':
            pos[0] += 1
        return node

    return read_tree()


# ═══════════════════════════════════════════════════════════════════════════
# ANÁLISIS DE UN SGF
# ═══════════════════════════════════════════════════════════════════════════

def get_leaf_comments(node, depth=0):
    """Recoge todos los C[] de nodos hoja."""
    if not node['children']:
        return [('leaf', depth, node['props'].get('C', [''])[0].strip())]
    results = []
    for child in node['children']:
        results.extend(get_leaf_comments(child, depth + 1))
    return results


def get_all_comments(node, depth=0):
    """Recoge todos los C[] de todos los nodos."""
    results = []
    c = node['props'].get('C', None)
    if c:
        results.append((depth, c[0].strip()))
    for child in node['children']:
        results.extend(get_all_comments(child, depth + 1))
    return results


def get_first_move(node):
    """Devuelve ('B'|'W'|None, coord) del primer nodo con B[] o W[].
    Si no hay moves, usa PL[] del nodo raíz como fallback."""
    def search(n, visited=0):
        if visited > 5:
            return None, None
        props = n['props']
        # Solo contar B/W si la coordenada no es jj (placeholder)
        if 'B' in props:
            coord = props['B'][0] if props['B'] else ''
            if coord.lower() != 'jj':
                return 'B', coord
        if 'W' in props:
            coord = props['W'][0] if props['W'] else ''
            if coord.lower() != 'jj':
                return 'W', coord
        for child in n['children']:
            color, coord = search(child, visited + 1)
            if color:
                return color, coord
        return None, None

    color, coord = search(node)
    if color:
        return color, coord
    # Fallback: leer PL[] del nodo raíz
    pl = node['props'].get('PL', None)
    if pl:
        val = pl[0].strip().upper()
        if val == 'B':
            return 'B', None
        if val == 'W':
            return 'W', None
    return None, None


def has_pass_move(node):
    """Detecta B[jj] o W[jj] (placeholder/pass) en cualquier nodo."""
    props = node['props']
    for key in ('B', 'W'):
        if key in props and props[key] and props[key][0].lower() == 'jj':
            return True
    for child in node['children']:
        if has_pass_move(child):
            return True
    return False


def count_branches(node):
    """Cuenta ramas en el primer nivel de variación (hijos del root)."""
    if not node['children']:
        return 1
    return len(node['children'])


def classify_sgf(sgf_path):
    """
    Analiza un SGF y devuelve un dict con toda la información relevante.
    """
    result = {
        'path': sgf_path,
        'parse_error': None,
        'has_pass_move': False,
        'color_to_play': None,
        'first_move_coord': None,
        'num_branches': 0,
        'leaf_comments': [],       # lista de strings en hojas
        'all_comments': [],        # lista de strings en todos los nodos
        'category': None,          # clasificación final
        'notes': [],
    }

    try:
        with open(sgf_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read().strip()
    except Exception as e:
        result['parse_error'] = f"Read error: {e}"
        result['category'] = 'READ_ERROR'
        return result

    if not text:
        result['parse_error'] = 'Empty file'
        result['category'] = 'EMPTY'
        return result

    try:
        tree = parse_sgf(text)
    except Exception as e:
        result['parse_error'] = str(e)
        result['category'] = 'PARSE_ERROR'
        return result

    # Color to play y primer movimiento
    color, coord = get_first_move(tree)
    result['color_to_play'] = color
    result['first_move_coord'] = coord

    # Pass moves
    result['has_pass_move'] = has_pass_move(tree)

    # Ramas
    result['num_branches'] = count_branches(tree)

    # Comentarios en hojas
    leaf_data = get_leaf_comments(tree)
    result['leaf_comments'] = [c for (_, _, c) in leaf_data]

    # Todos los comentarios
    all_data = get_all_comments(tree)
    result['all_comments'] = [c for (_, c) in all_data]

    # ── Clasificación ────────────────────────────────────────────────────
    leaf_comments = result['leaf_comments']
    all_comments  = result['all_comments']

    has_right  = any('RIGHT' in c.upper() for c in leaf_comments)
    has_wrong  = any('WRONG' in c.upper() for c in leaf_comments)
    has_right_any = any('RIGHT' in c.upper() for c in all_comments)
    has_wrong_any = any('WRONG' in c.upper() for c in all_comments)

    # Patrón reveal: tiene jj placeholder Y C[RIGHT] en algún nodo (no necesariamente hoja)
    is_reveal = result['has_pass_move'] and has_right_any

    # DONOTSWAP en el comentario raíz
    root_comment = tree['props'].get('C', [''])[0]
    has_donotswap = 'DONOTSWAP' in root_comment.upper()

    if result['has_pass_move']:
        result['notes'].append('has_pass_move')
    if has_donotswap:
        result['notes'].append('donotswap')
    if is_reveal:
        result['notes'].append('reveal_pattern')

    if result['parse_error']:
        pass  # ya clasificado
    elif is_reveal:
        result['category'] = 'RIGHT_ONLY'         # reveal con C[RIGHT] — compatible
    elif has_right and has_wrong:
        result['category'] = 'RIGHT_WRONG'        # formato estándar GJ
    elif has_right and not has_wrong:
        result['category'] = 'RIGHT_ONLY'         # solo RIGHT, sin WRONG
    elif has_wrong and not has_right:
        result['category'] = 'WRONG_ONLY'         # solo WRONG, sin RIGHT
    elif has_right_any or has_wrong_any:
        result['category'] = 'RIGHT_WRONG_NOT_LEAF'  # marcadores fuera de hojas
        result['notes'].append('markers_not_in_leaf')
    elif has_donotswap:
        result['category'] = 'DONOTSWAP_NO_RIGHT' # DONOTSWAP sin C[RIGHT]
    elif result['has_pass_move'] and not has_right and not has_wrong:
        result['category'] = 'PASS_ONLY'
    elif not any(c for c in leaf_comments):
        result['category'] = 'NO_COMMENTS'        # sin comentarios en hojas
    else:
        result['category'] = 'UNKNOWN'            # comentarios pero no reconocidos

    return result


# ═══════════════════════════════════════════════════════════════════════════
# ESCANEO
# ═══════════════════════════════════════════════════════════════════════════

def scan_guo_juan(root):
    """
    Recorre guo_juan/problems_*/ y analiza cada SGF.
    Devuelve lista de resultados y stats por carpeta.
    """
    results = []
    folder_stats = defaultdict(Counter)  # folder -> category -> count

    if not os.path.isdir(root):
        print(f"ERROR: No se encuentra el directorio: {root}")
        sys.exit(1)

    problem_dirs = sorted([
        d for d in os.listdir(root)
        if d.startswith('problems_') and os.path.isdir(os.path.join(root, d))
    ])

    if not problem_dirs:
        print(f"ERROR: No se encontraron carpetas problems_* en: {root}")
        sys.exit(1)

    total_dirs = len(problem_dirs)
    print(f"Encontradas {total_dirs} carpetas problems_*")

    for i, folder in enumerate(problem_dirs, 1):
        lesson_id = folder.replace('problems_', '')
        folder_path = os.path.join(root, folder)
        sgf_files = sorted([
            f for f in os.listdir(folder_path) if f.lower().endswith('.sgf')
        ])

        if i % 50 == 0 or i == total_dirs:
            print(f"  Procesando {i}/{total_dirs}: {folder} ({len(sgf_files)} SGFs)")

        for sgf_name in sgf_files:
            sgf_path = os.path.join(folder_path, sgf_name)
            r = classify_sgf(sgf_path)
            r['lesson_id'] = lesson_id
            r['folder'] = folder
            r['filename'] = sgf_name
            results.append(r)
            folder_stats[folder][r['category']] += 1

    return results, folder_stats


# ═══════════════════════════════════════════════════════════════════════════
# INFORME
# ═══════════════════════════════════════════════════════════════════════════

def write_report(results, folder_stats, report_path, unknown_path):
    total = len(results)
    cat_counter = Counter(r['category'] for r in results)

    lines = []
    lines.append("=" * 70)
    lines.append("ANÁLISIS SGF — GUO JUAN")
    lines.append("=" * 70)
    lines.append(f"Total SGFs analizados : {total}")
    lines.append(f"Carpetas problems_*   : {len(folder_stats)}")
    lines.append("")

    lines.append("── RESUMEN POR CATEGORÍA ──────────────────────────────────────────")
    cat_descriptions = {
        'RIGHT_WRONG'          : 'Formato estándar GJ (C[RIGHT] y C[WRONG] en hojas)',
        'RIGHT_ONLY'           : 'Solo C[RIGHT] — incluye reveal con jj placeholder',
        'WRONG_ONLY'           : 'Solo C[WRONG] en hojas (sin C[RIGHT])',
        'RIGHT_WRONG_NOT_LEAF' : 'C[RIGHT]/C[WRONG] existen pero no en hojas',
        'NO_COMMENTS'          : 'Sin comentarios en hojas',
        'PASS_ONLY'            : 'Contiene pass move B[jj]/W[jj], sin marcadores',
        'DONOTSWAP_NO_RIGHT'   : 'DONOTSWAP sin C[RIGHT] — revisar manualmente',
        'UNKNOWN'              : 'Comentarios en hojas no reconocidos',
        'PARSE_ERROR'          : 'Error de parseo SGF',
        'READ_ERROR'           : 'Error de lectura de fichero',
        'EMPTY'                : 'Fichero vacío',
    }
    for cat, count in sorted(cat_counter.items(), key=lambda x: -x[1]):
        pct = 100 * count / total if total else 0
        desc = cat_descriptions.get(cat, cat)
        lines.append(f"  {cat:<30} {count:>6}  ({pct:5.1f}%)  {desc}")
    lines.append("")

    # Color to play stats
    colors = Counter(r['color_to_play'] for r in results)
    lines.append("── COLOR TO PLAY ───────────────────────────────────────────────────")
    for color, count in sorted(colors.items(), key=lambda x: -x[1]):
        label = color if color else 'None/unknown'
        lines.append(f"  {label:<10} {count:>6}")
    lines.append("")

    # Pass moves
    pass_count = sum(1 for r in results if r['has_pass_move'])
    lines.append("── PASS MOVES (B[jj]/W[jj]) ────────────────────────────────────────")
    lines.append(f"  SGFs con pass move: {pass_count}")
    lines.append("")

    # Ramas
    branch_counter = Counter(r['num_branches'] for r in results)
    lines.append("── DISTRIBUCIÓN DE RAMAS (primer nivel) ────────────────────────────")
    for nb, count in sorted(branch_counter.items()):
        lines.append(f"  {nb} rama(s): {count}")
    lines.append("")

    STANDARD_CATS = ('RIGHT_WRONG', 'RIGHT_ONLY')
    non_standard_folders = {
        folder: stats for folder, stats in folder_stats.items()
        if any(cat not in STANDARD_CATS for cat in stats)
    }
    if non_standard_folders:
        lines.append("── CARPETAS CON PROBLEMAS NO ESTÁNDAR ──────────────────────────────")
        for folder in sorted(non_standard_folders):
            stats = folder_stats[folder]
            issues = {k: v for k, v in stats.items() if k not in STANDARD_CATS}
            lines.append(f"  {folder}: {dict(issues)}")
        lines.append("")

    # Muestra de UNKNOWN
    unknown_results = [r for r in results if r['category'] == 'UNKNOWN']
    donotswap_results = [r for r in results if r['category'] == 'DONOTSWAP_NO_RIGHT']
    if unknown_results:
        lines.append("── MUESTRA UNKNOWN (primeros 10) ───────────────────────────────────")
        for r in unknown_results[:10]:
            lines.append(f"  {r['folder']}/{r['filename']}")
            lines.append(f"    Comentarios hojas: {r['leaf_comments'][:3]}")
        lines.append("")
    if donotswap_results:
        lines.append("── DONOTSWAP SIN C[RIGHT] (primeros 5) ─────────────────────────────")
        for r in donotswap_results[:5]:
            lines.append(f"  {r['folder']}/{r['filename']}")
            lines.append(f"    Comentarios hojas: {r['leaf_comments'][:2]}")
        lines.append("")

    # Errores
    errors = [r for r in results if r['category'] in ('PARSE_ERROR', 'READ_ERROR', 'EMPTY')]
    if errors:
        lines.append("── ERRORES ─────────────────────────────────────────────────────────")
        for r in errors:
            lines.append(f"  {r['folder']}/{r['filename']}: {r['parse_error']}")
        lines.append("")

    lines.append("=" * 70)

    report_text = '\n'.join(lines)
    print("\n" + report_text)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"\nInforme guardado: {report_path}")

    # Fichero unknown detallado
    non_standard = [r for r in results if r['category'] in ('UNKNOWN', 'DONOTSWAP_NO_RIGHT')]
    if non_standard:
        with open(unknown_path, 'w', encoding='utf-8') as f:
            for r in non_standard:
                f.write(f"{r['folder']}/{r['filename']}\n")
                f.write(f"  category      : {r['category']}\n")
                f.write(f"  color_to_play : {r['color_to_play']}\n")
                f.write(f"  leaf_comments : {r['leaf_comments']}\n")
                f.write(f"  all_comments  : {r['all_comments'][:5]}\n")
                f.write(f"  notes         : {r['notes']}\n")
                f.write("\n")
        print(f"Unknowns guardados: {unknown_path}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"Analizando: {GUO_JUAN_ROOT}")
    results, folder_stats = scan_guo_juan(GUO_JUAN_ROOT)
    write_report(results, folder_stats, REPORT_FILE, UNKNOWN_FILE)
    print("Listo.")
