"""
analizar_sgf_101weiqi.py — Analiza y limpia SGFs de 101_weiqi/problems/{book_id}/{chapter_id}/

Modos:
    python analizar_sgf_101weiqi.py [ruta_problems]
        → Analiza y genera informe (dry-run por defecto)

    python analizar_sgf_101weiqi.py [ruta_problems] --delete
        → Borra ficheros no estándar y carpetas vacías resultantes

Por defecto busca en:
    101_weiqi/problems/   (relativo al script)

Salida:
    analizar_sgf_101weiqi_informe.txt   — informe detallado por categoría
    analizar_sgf_101weiqi_unknown.txt   — SGFs con formato no reconocido
"""

import os
import sys
from collections import defaultdict, Counter

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.join(SCRIPT_DIR, '101_weiqi', 'problems_std')
REPORT_FILE  = os.path.join(SCRIPT_DIR, 'analizar_sgf_101weiqi_informe.txt')
UNKNOWN_FILE = os.path.join(SCRIPT_DIR, 'analizar_sgf_101weiqi_unknown.txt')

STANDARD_CATS = ('RIGHT_WRONG', 'RIGHT_ONLY')
# ─────────────────────────────────────────────────────────────────────────────

args         = [a for a in sys.argv[1:] if not a.startswith('--')]
flags        = [a for a in sys.argv[1:] if a.startswith('--')]
PROBLEMS_ROOT = args[0] if args else DEFAULT_ROOT
DO_DELETE     = '--delete' in flags

def cleanup_empty_chapters(root, do_delete):
    """Borra carpetas chapter (nivel 2) que no contienen ningún SGF."""
    label = "BORRAR" if do_delete else "DRY-RUN"
    deleted = 0
    for book in os.scandir(root):
        if not book.is_dir():
            continue
        for chap in os.scandir(book.path):
            if not chap.is_dir():
                continue
            sgfs = [f for f in os.listdir(chap.path) if f.lower().endswith(".sgf")]
            if not sgfs:
                print(f"  [{label}] carpeta vacía: {chap.path}")
                if do_delete:
                    import shutil
                    shutil.rmtree(chap.path)
                deleted += 1
    print(f"[{label}] Carpetas chapter vacías: {deleted}")
    
def distribution_stats(values, percentiles=(10, 25, 50, 75, 90, 95, 99)):
    if not values:
        return {}
    s = sorted(values)
    n = len(s)
    result = {'min': s[0], 'max': s[-1], 'mean': sum(s) / n}
    for p in percentiles:
        idx = max(0, int(n * p / 100) - 1)
        result[f'p{p}'] = s[idx]
    return result

def cleanup_empty_books(root, do_delete):
    """Borra carpetas book (nivel 1) que no contienen ninguna carpeta chapter con SGFs."""
    import shutil
    label = "BORRAR" if do_delete else "DRY-RUN"
    deleted = 0
    for book in os.scandir(root):
        if not book.is_dir():
            continue
        subdirs = [e for e in os.scandir(book.path) if e.is_dir()]
        if not subdirs:
            print(f"  [{label}] book vacío: {book.path}")
            if do_delete:
                shutil.rmtree(book.path)
            deleted += 1
    print(f"[{label}] Carpetas book vacías: {deleted}")

def write_size_report(results, lines):
    # Agrupar
    chapter_counts = defaultdict(int)   # (book_id, chapter_id) -> count
    book_counts    = defaultdict(int)   # book_id -> count

    for r in results:
        key = (r['book_id'], r['chapter_id'])
        chapter_counts[key] += 1
        book_counts[r['book_id']] += 1

    # Distribución chapters
    chap_sizes = list(chapter_counts.values())
    chap_stats = distribution_stats(chap_sizes)

    lines.append("── DISTRIBUCIÓN TAMAÑO CHAPTERS (nº problemas) ─────────────────────")
    lines.append(f"  Total chapters : {len(chap_sizes)}")
    lines.append(f"  Min            : {chap_stats['min']}")
    lines.append(f"  Max            : {chap_stats['max']}")
    lines.append(f"  Media          : {chap_stats['mean']:.1f}")
    for p in (10, 25, 50, 75, 90, 95, 99):
        lines.append(f"  p{p:<3}           : {chap_stats[f'p{p}']}")
    lines.append("")

    CHAPTER_THRESHOLD = 5
    small_chapters = sorted(
        [(k, v) for k, v in chapter_counts.items() if v < CHAPTER_THRESHOLD],
        key=lambda x: x[1]
    )
    if small_chapters:
        lines.append(f"── CHAPTERS CON < {CHAPTER_THRESHOLD} PROBLEMAS ({len(small_chapters)}) ──────────────────────────")
        for (book_id, chapter_id), count in small_chapters:
            lines.append(f"  book={book_id} chapter={chapter_id}  → {count} problema(s)")
        lines.append("")

    # Distribución books
    book_sizes = list(book_counts.values())
    book_stats = distribution_stats(book_sizes)

    lines.append("── DISTRIBUCIÓN TAMAÑO BOOKS (nº problemas) ────────────────────────")
    lines.append(f"  Total books    : {len(book_sizes)}")
    lines.append(f"  Min            : {book_stats['min']}")
    lines.append(f"  Max            : {book_stats['max']}")
    lines.append(f"  Media          : {book_stats['mean']:.1f}")
    for p in (10, 25, 50, 75, 90, 95, 99):
        lines.append(f"  p{p:<3}           : {book_stats[f'p{p}']}")
    lines.append("")

    BOOK_THRESHOLD = 10
    small_books = sorted(
        [(k, v) for k, v in book_counts.items() if v < BOOK_THRESHOLD],
        key=lambda x: x[1]
    )
    if small_books:
        lines.append(f"── BOOKS CON < {BOOK_THRESHOLD} PROBLEMAS ({len(small_books)}) ─────────────────────────────")
        for book_id, count in small_books:
            lines.append(f"  book={book_id}  → {count} problema(s)")
        lines.append("")
        
def cleanup_small_chapters(results, root, do_delete, threshold=5):
    """Borra chapters con menos de threshold problemas y books que queden vacíos."""
    label = "BORRAR" if do_delete else "DRY-RUN"

    from collections import defaultdict
    chapter_problems = defaultdict(list)  # (book_id, chapter_id) -> [result, ...]
    for r in results:
        chapter_problems[(r['book_id'], r['chapter_id'])].append(r)

    small = {k: v for k, v in chapter_problems.items() if len(v) < threshold}
    if not small:
        print("No hay chapters pequeños. Nada que limpiar.")
        return

    print(f"\n[{label}] Chapters con < {threshold} problemas: {len(small)}")

    deleted_files    = 0
    deleted_chapters = 0
    deleted_books    = 0
    books_touched    = set()

    for (book_id, chapter_id), chapter_results in sorted(small.items()):
        chap_path = os.path.join(root, book_id, chapter_id)
        print(f"  [{label}] chapter {chapter_id} (book={book_id}, {len(chapter_results)} problema(s))")
        if do_delete and os.path.isdir(chap_path):
            import shutil
            shutil.rmtree(chap_path)
        deleted_chapters += 1
        books_touched.add(book_id)
        deleted_files += len(chapter_results) * 2  # sgf + json

    # Limpiar books vacíos resultantes
    for book_id in sorted(books_touched):
        book_path = os.path.join(root, book_id)
        if not os.path.isdir(book_path):
            continue
        remaining = [d for d in os.listdir(book_path) if os.path.isdir(os.path.join(book_path, d))]
        if not remaining:
            print(f"  [{label}] book vacío tras limpieza: {book_path}")
            if do_delete:
                import shutil
                shutil.rmtree(book_path)
            deleted_books += 1

    print(f"\n[{label}] Resumen chapters pequeños:")
    print(f"  Chapters eliminados : {deleted_chapters}")
    print(f"  Ficheros estimados  : {deleted_files}")
    print(f"  Books eliminados    : {deleted_books}")
    if not do_delete:
        print(f"\n  ⚠️  Dry-run — usa --delete para borrar de verdad.")
        
            
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
                pos[0] += 1
                child_props = read_props()
                child_node = {'props': child_props, 'children': []}
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
        c_vals = node['props'].get('C', [])
        comment = c_vals[0].strip() if c_vals else ''
        return [('leaf', depth, comment)]
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
        if 'B' in props:
            coord = props['B'][0] if props['B'] else ''
            return 'B', coord
        if 'W' in props:
            coord = props['W'][0] if props['W'] else ''
            return 'W', coord
        for child in n['children']:
            color, coord = search(child, visited + 1)
            if color:
                return color, coord
        return None, None

    color, coord = search(node)
    if color:
        return color, coord
    pl = node['props'].get('PL', None)
    if pl:
        val = pl[0].strip().upper()
        if val == 'B':
            return 'B', None
        if val == 'W':
            return 'W', None
    return None, None


def count_branches(node):
    """Cuenta ramas en el primer punto de ramificación del árbol."""
    if not node['children']:
        return 0
    if len(node['children']) > 1:
        return len(node['children'])
    # Nodo lineal — bajar al siguiente
    return count_branches(node['children'][0])


def parse_gc(gc_value):
    """
    Extrae metadatos del campo GC[] de 101weiqi.
    Ejemplo: 'Type: Endgame | Level: 5K | Rating: 4.2/5 | Correct: 68% | First move: Black'
    """
    meta = {}
    if not gc_value:
        return meta
    for part in gc_value.split('|'):
        part = part.strip()
        if ':' in part:
            key, _, val = part.partition(':')
            meta[key.strip()] = val.strip()
    return meta


def classify_sgf(sgf_path):
    """
    Analiza un SGF de 101weiqi y devuelve un dict con toda la información relevante.
    """
    result = {
        'path': sgf_path,
        'parse_error': None,
        'color_to_play': None,
        'first_move_coord': None,
        'num_branches': 0,
        'leaf_comments': [],
        'all_comments': [],
        'gc_meta': {},
        'category': None,
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

    # Metadatos GC[]
    gc_raw = tree['props'].get('GC', [''])[0]
    result['gc_meta'] = parse_gc(gc_raw)

    # Color to play y primer movimiento
    color, coord = get_first_move(tree)
    result['color_to_play'] = color
    result['first_move_coord'] = coord

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

    has_right     = any('RIGHT' in c.upper() for c in leaf_comments)
    has_wrong     = any('WRONG' in c.upper() for c in leaf_comments)
    has_right_any = any('RIGHT' in c.upper() for c in all_comments)
    has_wrong_any = any('WRONG' in c.upper() for c in all_comments)

    if result['parse_error']:
        pass
    elif has_right and has_wrong:
        result['category'] = 'RIGHT_WRONG'
    elif has_right and not has_wrong:
        result['category'] = 'RIGHT_ONLY'
    elif has_wrong and not has_right:
        result['category'] = 'WRONG_ONLY'
    elif has_right_any or has_wrong_any:
        result['category'] = 'RIGHT_WRONG_NOT_LEAF'
        result['notes'].append('markers_not_in_leaf')
    elif not any(c for c in leaf_comments):
        result['category'] = 'NO_COMMENTS'
    else:
        result['category'] = 'UNKNOWN'

    return result


# ═══════════════════════════════════════════════════════════════════════════
# ESCANEO
# ═══════════════════════════════════════════════════════════════════════════

def scan_101weiqi(root):
    """
    Recorre problems/{book_id}/{chapter_id}/ y analiza cada SGF.
    Devuelve lista de resultados y stats por libro.
    """
    results = []
    book_stats = defaultdict(Counter)

    if not os.path.isdir(root):
        print(f"ERROR: No se encuentra el directorio: {root}")
        sys.exit(1)

    book_dirs = sorted([
        d for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d))
    ])

    if not book_dirs:
        print(f"ERROR: No se encontraron carpetas de libros en: {root}")
        sys.exit(1)

    total_books = len(book_dirs)
    total_sgfs  = 0
    print(f"Encontrados {total_books} libros")

    for book_id in book_dirs:
        book_path = os.path.join(root, book_id)
        chapter_dirs = sorted([
            d for d in os.listdir(book_path)
            if os.path.isdir(os.path.join(book_path, d))
        ])

        for chapter_id in chapter_dirs:
            chapter_path = os.path.join(book_path, chapter_id)
            sgf_files = sorted([
                f for f in os.listdir(chapter_path)
                if f.lower().endswith('.sgf')
            ])

            for sgf_name in sgf_files:
                sgf_path = os.path.join(chapter_path, sgf_name)
                r = classify_sgf(sgf_path)
                r['book_id']    = book_id
                r['chapter_id'] = chapter_id
                r['filename']   = sgf_name
                results.append(r)
                book_stats[book_id][r['category']] += 1
                total_sgfs += 1

        print(f"  Libro {book_id}: {sum(book_stats[book_id].values())} SGFs")

    print(f"Total SGFs procesados: {total_sgfs}")
    return results, book_stats


# ═══════════════════════════════════════════════════════════════════════════
# LIMPIEZA
# ═══════════════════════════════════════════════════════════════════════════

def cleanup_invalid(results, root, do_delete):
    """
    Borra (o muestra en dry-run) los ficheros de problemas no estándar
    y las carpetas/JSONs que queden vacíos.

    Por cada problema no estándar:
      - Borra {id}.sgf y {id}.json en la carpeta del capítulo

    Después, por cada capítulo afectado:
      - Si no quedan SGFs → borra chapter.json y la carpeta

    Después, por cada libro afectado:
      - Si no quedan subcarpetas de capítulo → borra book.json y la carpeta
    """
    label = "BORRAR" if do_delete else "DRY-RUN"

    invalid = [r for r in results if r['category'] not in STANDARD_CATS]
    if not invalid:
        print("No hay problemas no estándar. Nada que limpiar.")
        return

    # Archivos de problema a borrar
    files_to_delete  = []
    chapters_touched = set()  # (book_id, chapter_id)
    books_touched    = set()  # book_id

    for r in invalid:
        base       = os.path.splitext(r['filename'])[0]
        chap_path  = os.path.join(root, r['book_id'], r['chapter_id'])
        sgf_path   = os.path.join(chap_path, r['filename'])
        json_path  = os.path.join(chap_path, base + '.json')
        files_to_delete.append(sgf_path)
        files_to_delete.append(json_path)
        chapters_touched.add((r['book_id'], r['chapter_id']))
        books_touched.add(r['book_id'])

    print(f"\n[{label}] Problemas no estándar a eliminar: {len(invalid)}")
    print(f"[{label}] Ficheros a borrar (sgf+json): {len(files_to_delete)}")

    deleted_files   = 0
    missing_files   = 0
    deleted_chapters = 0
    deleted_books   = 0

    # 1. Borrar ficheros de problema
    for fpath in files_to_delete:
        if os.path.exists(fpath):
            print(f"  [{label}] {fpath}")
            if do_delete:
                os.remove(fpath)
            deleted_files += 1
        else:
            missing_files += 1

    # 2. Limpiar capítulos vacíos
    print(f"\n[{label}] Comprobando {len(chapters_touched)} capítulos afectados...")
    for book_id, chapter_id in sorted(chapters_touched):
        chap_path = os.path.join(root, book_id, chapter_id)
        if not os.path.isdir(chap_path):
            continue
        remaining_sgfs = [
            f for f in os.listdir(chap_path)
            if f.lower().endswith('.sgf')
        ]
        if not remaining_sgfs:
            chapter_json = os.path.join(chap_path, 'chapter.json')
            if os.path.exists(chapter_json):
                print(f"  [{label}] (chapter vacío) {chapter_json}")
                if do_delete:
                    os.remove(chapter_json)
            print(f"  [{label}] (chapter vacío) rmdir {chap_path}")
            if do_delete:
                # Borrar ficheros restantes (solo chapter.json ya borrado)
                for f in os.listdir(chap_path):
                    os.remove(os.path.join(chap_path, f))
                os.rmdir(chap_path)
            deleted_chapters += 1

    # 3. Limpiar libros vacíos
    print(f"\n[{label}] Comprobando {len(books_touched)} libros afectados...")
    for book_id in sorted(books_touched):
        book_path = os.path.join(root, book_id)
        if not os.path.isdir(book_path):
            continue
        remaining_chapters = [
            d for d in os.listdir(book_path)
            if os.path.isdir(os.path.join(book_path, d))
        ]
        if not remaining_chapters:
            book_json = os.path.join(book_path, 'book.json')
            if os.path.exists(book_json):
                print(f"  [{label}] (book vacío) {book_json}")
                if do_delete:
                    os.remove(book_json)
            print(f"  [{label}] (book vacío) rmdir {book_path}")
            if do_delete:
                for f in os.listdir(book_path):
                    os.remove(os.path.join(book_path, f))
                os.rmdir(book_path)
            deleted_books += 1

    print(f"\n[{label}] Resumen limpieza:")
    print(f"  Ficheros eliminados  : {deleted_files}")
    print(f"  Ficheros no hallados : {missing_files}")
    print(f"  Capítulos eliminados : {deleted_chapters}")
    print(f"  Libros eliminados    : {deleted_books}")
    if not do_delete:
        print(f"\n  ⚠️  Modo dry-run — no se ha borrado nada.")
        print(f"  Ejecuta con --delete para borrar de verdad.")


# ═══════════════════════════════════════════════════════════════════════════
# INFORME
# ═══════════════════════════════════════════════════════════════════════════

def write_report(results, book_stats, report_path, unknown_path):
    total = len(results)
    cat_counter = Counter(r['category'] for r in results)

    lines = []
    lines.append("=" * 70)
    lines.append("ANÁLISIS SGF — 101WEIQI")
    lines.append("=" * 70)
    lines.append(f"Total SGFs analizados : {total}")
    lines.append(f"Libros                : {len(book_stats)}")
    lines.append("")

    lines.append("── RESUMEN POR CATEGORÍA ──────────────────────────────────────────")
    cat_descriptions = {
        'RIGHT_WRONG'          : 'Formato estándar (C[RIGHT] y C[WRONG] en hojas)  ✅ compatible',
        'RIGHT_ONLY'           : 'Solo C[RIGHT] en hojas                            ✅ compatible',
        'WRONG_ONLY'           : 'Solo C[WRONG] en hojas (sin C[RIGHT])             ❌ incompatible',
        'RIGHT_WRONG_NOT_LEAF' : 'C[RIGHT]/C[WRONG] existen pero no en hojas        ❌ incompatible',
        'NO_COMMENTS'          : 'Sin comentarios en hojas                          ❌ incompatible',
        'UNKNOWN'              : 'Comentarios en hojas no reconocidos               ❌ incompatible',
        'PARSE_ERROR'          : 'Error de parseo SGF                               ❌ incompatible',
        'READ_ERROR'           : 'Error de lectura de fichero                       ❌ incompatible',
        'EMPTY'                : 'Fichero vacío                                     ❌ incompatible',
    }
    for cat, count in sorted(cat_counter.items(), key=lambda x: -x[1]):
        pct = 100 * count / total if total else 0
        desc = cat_descriptions.get(cat, cat)
        lines.append(f"  {cat:<30} {count:>6}  ({pct:5.1f}%)  {desc}")
    lines.append("")

    # Color to play
    colors = Counter(r['color_to_play'] for r in results)
    lines.append("── COLOR TO PLAY ───────────────────────────────────────────────────")
    for color, count in sorted(colors.items(), key=lambda x: -x[1]):
        label = color if color else 'None/unknown'
        lines.append(f"  {label:<10} {count:>6}")
    lines.append("")

    # Ramas
    branch_counter = Counter(r['num_branches'] for r in results)
    lines.append("── DISTRIBUCIÓN DE RAMAS (primer punto de variación) ───────────────")
    for nb, count in sorted(branch_counter.items()):
        lines.append(f"  {nb} rama(s): {count}")
    lines.append("")

    # Tipos (GC[Type: ...])
    type_counter = Counter(r['gc_meta'].get('Type', 'unknown') for r in results)
    lines.append("── TIPOS DE PROBLEMA (GC[Type]) ────────────────────────────────────")
    for ptype, count in sorted(type_counter.items(), key=lambda x: -x[1]):
        pct = 100 * count / total if total else 0
        lines.append(f"  {ptype:<30} {count:>6}  ({pct:5.1f}%)")
    lines.append("")

    # Niveles (GC[Level: ...])
    level_counter = Counter(r['gc_meta'].get('Level', 'unknown') for r in results)
    lines.append("── NIVELES (GC[Level]) ─────────────────────────────────────────────")
    for level, count in sorted(level_counter.items(), key=lambda x: -x[1]):
        lines.append(f"  {level:<10} {count:>6}")
    lines.append("")

    # Libros con problemas no estándar
    non_standard_books = {
        book_id: stats for book_id, stats in book_stats.items()
        if any(cat not in STANDARD_CATS for cat in stats)
    }
    if non_standard_books:
        lines.append("── LIBROS CON PROBLEMAS NO ESTÁNDAR ────────────────────────────────")
        for book_id in sorted(non_standard_books):
            stats = book_stats[book_id]
            issues = {k: v for k, v in stats.items() if k not in STANDARD_CATS}
            lines.append(f"  book {book_id}: {dict(issues)}")
        lines.append("")

    # Errores
    errors = [r for r in results if r['category'] in ('PARSE_ERROR', 'READ_ERROR', 'EMPTY')]
    if errors:
        lines.append("── ERRORES ─────────────────────────────────────────────────────────")
        for r in errors:
            lines.append(f"  book={r['book_id']} chapter={r['chapter_id']} {r['filename']}: {r['parse_error']}")
        lines.append("")

    lines.append("=" * 70)

    write_size_report(results, lines)

    report_text = '\n'.join(lines)
    print("\n" + report_text)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"\nInforme guardado: {report_path}")

    # Fichero no-estándar detallado
    non_standard = [r for r in results if r['category'] not in STANDARD_CATS]
    if non_standard:
        with open(unknown_path, 'w', encoding='utf-8') as f:
            for r in non_standard:
                f.write(f"book={r['book_id']} chapter={r['chapter_id']} {r['filename']}\n")
                f.write(f"  category      : {r['category']}\n")
                f.write(f"  color_to_play : {r['color_to_play']}\n")
                f.write(f"  gc_meta       : {r['gc_meta']}\n")
                f.write(f"  leaf_comments : {r['leaf_comments']}\n")
                f.write(f"  all_comments  : {r['all_comments'][:5]}\n")
                f.write(f"  notes         : {r['notes']}\n")
                f.write("\n")
        print(f"No estándar guardados: {unknown_path}")


# ═══════════════════════════════════════════════════════════════════════════
# DEDUPLICACIÓN DE QIDs
# ═══════════════════════════════════════════════════════════════════════════

def cleanup_duplicate_qids(root, do_delete):
    """
    Detecta qids (problem_id) que aparecen en más de un book y elimina
    las copias extra, conservando la del book con más SGFs totales.
    En empate, conserva el de mayor book_id.
    """
    from collections import defaultdict

    label = "BORRAR" if do_delete else "DRY-RUN"

    # Contar SGFs por book
    book_size = {}
    for book in os.scandir(root):
        if not book.is_dir():
            continue
        try:
            book_id = int(book.name)
        except ValueError:
            continue
        count = sum(
            1
            for chap in os.scandir(book.path) if chap.is_dir()
            for f in os.listdir(chap.path) if f.lower().endswith(".sgf")
        )
        book_size[int(book.name)] = count

    # Escanear todos los SGFs
    qid_locations = defaultdict(list)  # qid -> [(book_id_int, chap_name)]
    for book in os.scandir(root):
        if not book.is_dir():
            continue
        try:
            book_id = int(book.name)
        except ValueError:
            continue
        for chap in os.scandir(book.path):
            if not chap.is_dir():
                continue
            for f in os.listdir(chap.path):
                if f.lower().endswith(".sgf"):
                    try:
                        qid = int(os.path.splitext(f)[0])
                        qid_locations[qid].append((book_id, chap.name))
                    except ValueError:
                        pass

    duplicates = {qid: locs for qid, locs in qid_locations.items() if len(locs) > 1}
    extra_copies = sum(len(v) - 1 for v in duplicates.values())

    print(f"\n[{label}] QIDs duplicados  : {len(duplicates)}")
    print(f"[{label}] Copias extra     : {extra_copies}")

    if not duplicates:
        print("No hay duplicados. Nada que hacer.")
        return

    deleted_files = 0
    missing_files = 0

    for qid, locs in sorted(duplicates.items()):
        # Conservar la copia del book con más SGFs; en empate, mayor book_id
        winner = max(locs, key=lambda x: (book_size.get(x[0], 0), x[0]))
        for book_id, chap_name in locs:
            if (book_id, chap_name) == winner:
                continue
            chap_path = os.path.join(root, str(book_id), chap_name)
            for ext in (".sgf", ".json"):
                fpath = os.path.join(chap_path, f"{qid}{ext}")
                if os.path.isfile(fpath):
                    if do_delete:
                        os.remove(fpath)
                    deleted_files += 1
                else:
                    missing_files += 1

    print(f"[{label}] Ficheros eliminados  : {deleted_files}")
    print(f"[{label}] Ficheros no hallados : {missing_files}")
    if not do_delete:
        print(f"\n  ⚠️  Dry-run — usa --delete para borrar de verdad.")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print(f"Analizando: {PROBLEMS_ROOT}")
    if DO_DELETE:
        print("Modo: BORRADO REAL (--delete)")
    else:
        print("Modo: dry-run (usa --delete para borrar de verdad)")

    results, book_stats = scan_101weiqi(PROBLEMS_ROOT)
    write_report(results, book_stats, REPORT_FILE, UNKNOWN_FILE)
    cleanup_invalid(results, PROBLEMS_ROOT, DO_DELETE)
    cleanup_small_chapters(results, PROBLEMS_ROOT, DO_DELETE, threshold=5)
    cleanup_empty_chapters(PROBLEMS_ROOT, DO_DELETE)
    cleanup_empty_books(PROBLEMS_ROOT, DO_DELETE)
    cleanup_duplicate_qids(PROBLEMS_ROOT, DO_DELETE)
    print("\nListo.")
