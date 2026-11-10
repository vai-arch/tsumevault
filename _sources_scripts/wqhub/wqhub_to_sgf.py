#!/usr/bin/env python3
"""
wqhub_to_sgf.py — Convierte las colecciones de problemas de WeiqiHub
(wqhub_tasks.db + collections.json) en el arbol de carpetas que espera
import_my_collection.py:

    <salida>/<fuente>/<Coleccion>/<NN-Capitulo>/<NNN>.sgf
    <salida>/<fuente>/<Coleccion>/<NN-Capitulo>/difficulty-<valor>

Cada <salida>/<fuente> es la raiz que se pasa al importador.

Reglas (acordadas):
  - Fuente: las colecciones de MY_COLLECTIONS (las que tienen capitulos por
    tema concreto) van a "my_collections"; el resto, a la fuente generica
    GENERIC_SOURCE.
  - Colecciones sin capitulos -> un unico capitulo con el nombre de la coleccion.
  - Niveles intermedios -> se aplanan en el nombre del capitulo
    ("01-Part 1 - 1 - Life").
  - Rangos desplazados SHIFT posiciones hacia abajo (el 10k de WeiqiHub es 15k).
  - Una carpeta tiene como maximo PART_MAX problemas, mas un resto de menos de
    TAIL_MIN (es decir, hasta PART_MAX + TAIL_MIN - 1). Un capitulo que no
    cabe se parte:
      1. En bandas de dificultad: se acumulan rangos completos de facil a
         dificil hasta PART_MIN problemas; un resto final de menos de
         TAIL_MIN se une a la banda anterior. Nombre: "<capitulo> - 12k-10k".
      2. Una banda que sigue sin caber se trocea en el orden del libro en
         trozos de PART_MAX; un resto de menos de TAIL_MIN se une al ultimo.
         Nombre: "<capitulo> - 12k (1)", "(2)"...
    Dentro de cada carpeta se conserva el orden del libro.
  - Ficheros numerados con ceros a la izquierda en el orden del libro.
  - Toda hoja del arbol lleva C[RIGHT] o C[WRONG] explicito.
  - Cada SGF lleva su propio rango en la propiedad DI[] de la raiz.
  - difficulty-<valor> de cada capitulo = media redondeada de sus problemas.

Formato WeiqiHub (lib/train/variation_tree.dart, lib/wq/rank.dart):
  - piedras: pares SGF concatenados ("qaraoa...")
  - first: 0 = negras, 1 = blancas
  - rank: indice 0 = 30k ... 29 = 1k, 30 = 1d ...
  - variation_tree: nodo = '0' (correcto) | '1' (incorrecto)
                         | (punto subarbol)* '<'

Uso:
    python wqhub_to_sgf.py <wqhub_tasks.db> <collections.json> <carpeta_salida>

La carpeta de salida no debe existir o debe estar vacia. Si sgf_lib.py esta
junto a este script, cada SGF generado se valida con validate_problem().
"""
import json
import os
import re
import sqlite3
import sys

COORDS = 'abcdefghijklmnopqrstuvwxyz'
SHIFT = 5
PART_MIN = 50
PART_MAX = 50
TAIL_MIN = 25
FITS = PART_MAX + TAIL_MIN - 1   # tamano maximo de una carpeta (74)

GENERIC_SOURCE = 'wqhub'
MY_SOURCE = 'my_collections'
# Titulos exactos del JSON (ojo: "Lee Changho’s Endgame Skills" lleva apostrofo tipografico)
MY_COLLECTIONS = {
    'All About Life and Death',
    'Gokyo Shumyo',
    'How to Improve on a 5x5 board',
    'Lee Changho\'s Selected Tesuji',
    'Lee Changho’s Endgame Skills',
    'Life and Death Dictionary - Segoe Kensaku',
    'Tesuji Dictionary - Segoe Kensaku, Go Seigen',
    'Weiqi Life and Death 1000 Problems',
}


# ── rangos ────────────────────────────────────────────────────────────────────

def shifted(idx):
    """Indice WeiqiHub (0 = 30k) -> indice desplazado, sin bajar de 30k."""
    return max(idx - SHIFT, 0)


def label(r):
    """Indice (ya desplazado, puede ser fraccionario) -> '14k' / '2d'."""
    r = int(r + 0.5)
    return f'{30 - r}k' if r <= 29 else f'{r - 29}d'


def num(r):
    """Indice -> escala de TsumeVault (inversa de kyu_dan_to_num)."""
    return 100 * int(r + 0.5) - 900


# ── variation_tree ────────────────────────────────────────────────────────────

class TreeError(Exception):
    pass


def parse_tree(s):
    """Devuelve el nodo raiz: {'status': 'RIGHT'|'WRONG'|None,
    'children': [(punto, nodo), ...]}."""
    node, i = _parse_node(s, 0)
    if i != len(s):
        raise TreeError(f'texto sobrante en la posicion {i}')
    return node


def _parse_node(s, i):
    if i >= len(s):
        raise TreeError('fin inesperado')
    c = s[i]
    if c == '0':
        return {'status': 'RIGHT', 'children': []}, i + 1
    if c == '1':
        return {'status': 'WRONG', 'children': []}, i + 1
    children = []
    while True:
        if i >= len(s):
            raise TreeError('falta "<" de cierre')
        if s[i] == '<':
            if not children:
                raise TreeError(f'nodo vacio en la posicion {i}')
            return {'status': None, 'children': children}, i + 1
        pt = s[i:i + 2]
        if len(pt) != 2 or not pt.isalpha() or not pt.islower():
            raise TreeError(f'punto invalido {pt!r} en la posicion {i}')
        child, i = _parse_node(s, i + 2)
        children.append((pt, child))


# ── SGF ───────────────────────────────────────────────────────────────────────

def split_stones(s):
    if len(s) % 2:
        raise TreeError(f'lista de piedras con longitud impar: {s!r}')
    return [s[k:k + 2] for k in range(0, len(s), 2)]


def check_point(pt, size, stats):
    if pt == 'tt' and size <= 19:
        stats['passes'] += 1
        return ''  # pase en FF4
    if COORDS.index(pt[0]) >= size or COORDS.index(pt[1]) >= size:
        raise TreeError(f'punto {pt} fuera de un tablero {size}x{size}')
    return pt


def node_to_sgf(color, pt, node, size, stats):
    """Serializa una jugada y todo su subarbol."""
    out = f';{color}[{check_point(pt, size, stats)}]'
    if node['status']:
        return out + f"C[{node['status']}]"
    nxt = 'W' if color == 'B' else 'B'
    kids = [node_to_sgf(nxt, p, n, size, stats) for p, n in node['children']]
    if len(kids) == 1:
        return out + kids[0]
    return out + ''.join(f'({k})' for k in kids)


def build_sgf(row, stats):
    size = row['board_size']
    tree = parse_tree(row['variation_tree'])
    if tree['status']:
        raise TreeError('el arbol no tiene ninguna jugada')
    first = 'B' if row['first'] == 0 else 'W'
    black = [check_point(p, size, stats) for p in split_stones(row['black_stones'])]
    white = [check_point(p, size, stats) for p in split_stones(row['white_stones'])]
    root = (f'GM[1]FF[4]CA[UTF-8]SZ[{size}]PL[{first}]'
            f"DI[{label(shifted(row['rank']))}]")
    if black:
        root += 'AB' + ''.join(f'[{p}]' for p in black)
    if white:
        root += 'AW' + ''.join(f'[{p}]' for p in white)
    kids = [node_to_sgf(first, p, n, size, stats) for p, n in tree['children']]
    body = kids[0] if len(kids) == 1 else ''.join(f'({k})' for k in kids)
    return f'(;{root}{body})\n'


# ── estructura de colecciones y capitulos ─────────────────────────────────────

def safe_name(name):
    name = name.replace(':', ' -')
    name = re.sub(r'[<>"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip().rstrip('.')
    return name


def chapters_of(collection):
    """Hojas de la coleccion como [(id, nombre_aplanado, taskCount)]."""
    if not collection.get('children'):
        return [(collection['id'], collection['title'], collection['taskCount'])]
    out = []

    def walk(node, prefix):
        title = node['title'] if not prefix else f"{prefix} - {node['title']}"
        if node.get('children'):
            for ch in node['children']:
                walk(ch, title)
        else:
            out.append((node['id'], title, node['taskCount']))

    for ch in collection['children']:
        walk(ch, '')
    return out


def split_by_rank(rows):
    """Parte los problemas en bandas de rangos completos (PART_MIN / TAIL_MIN).
    Devuelve [(etiqueta_banda, filas_en_orden_del_libro)]."""
    counts = {}
    for row in rows:
        r = shifted(row['rank'])
        counts[r] = counts.get(r, 0) + 1
    bands, cur = [], []
    for r in sorted(counts):
        cur.append(r)
        if sum(counts[x] for x in cur) >= PART_MIN:
            bands.append(cur)
            cur = []
    if cur:
        if bands and sum(counts[x] for x in cur) < TAIL_MIN:
            bands[-1] += cur
        else:
            bands.append(cur)
    out = []
    for band in bands:
        name = label(band[0]) if len(band) == 1 else f'{label(band[0])}-{label(band[-1])}'
        members = set(band)
        out.append((name, [row for row in rows if shifted(row['rank']) in members]))
    return out


def chunk(rows):
    """Trozos de PART_MAX en orden del libro; resto < TAIL_MIN al ultimo."""
    out = [rows[k:k + PART_MAX] for k in range(0, len(rows), PART_MAX)]
    if len(out) > 1 and len(out[-1]) < TAIL_MIN:
        tail = out.pop()
        out[-1] = out[-1] + tail
    return out


def split_chapter(title, rows):
    """[(titulo_carpeta, filas)] para un capitulo, segun PART_MIN/MAX/TAIL."""
    if len(rows) <= FITS:
        return [(title, rows)]
    out = []
    for band, part in split_by_rank(rows):
        pieces = chunk(part) if len(part) > FITS else [part]
        if len(pieces) == 1:
            out.append((f'{title} - {band}', pieces[0]))
        else:
            out += [(f'{title} - {band} ({k})', p)
                    for k, p in enumerate(pieces, start=1)]
    return out


def plan(con, meta, warnings):
    """Estructura final: [(fuente, carpeta_coleccion, [(carpeta_capitulo, filas)])].
    Las filas van en el orden del libro."""
    con.row_factory = sqlite3.Row
    titles = {col['title'] for col in meta['children']}
    for missing in sorted(MY_COLLECTIONS - titles):
        warnings.append(f'MY_COLLECTIONS: "{missing}" no existe en el JSON')
    result = []
    for col in meta['children']:
        source = MY_SOURCE if col['title'] in MY_COLLECTIONS else GENERIC_SOURCE
        chapters, n = [], 0
        for leaf_id, chap_title, expected in chapters_of(col):
            ctx = f"{col['title']} / {chap_title}"
            rows = con.execute(
                'SELECT ct.idx, t.rank, t.type, t.id AS task_id, t.first, '
                't.board_size, t.black_stones, t.white_stones, t.variation_tree '
                'FROM collection_tasks ct JOIN tasks t '
                'ON t.rank = ct.rank AND t.type = ct.type AND t.id = ct.task_id '
                'WHERE ct.id = ? ORDER BY ct.idx', (leaf_id,)).fetchall()
            if len(rows) != expected:
                warnings.append(f'{ctx}: {len(rows)} problemas en la BD, '
                                f'el JSON dice {expected}')
            if not rows:
                warnings.append(f'{ctx}: sin problemas, capitulo omitido')
                continue
            parts = split_chapter(chap_title, rows)
            got = [r['task_id'] for _, part in parts for r in part]
            if sorted(got) != sorted(r['task_id'] for r in rows):
                raise RuntimeError(f'{ctx}: la particion no conserva los problemas')
            for title, part in parts:
                n += 1
                chapters.append((f'{n:02d}-{safe_name(title)}', part))
        if chapters:
            result.append((source, safe_name(col['title']), chapters))
    return result


# ── principal ─────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    db_path, json_path, out_root = sys.argv[1:]

    if os.path.exists(out_root) and os.listdir(out_root):
        print(f'La carpeta de salida no esta vacia: {out_root}')
        sys.exit(2)

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from sgf_lib import parse_sgf, validate_problem
    except ImportError:
        parse_sgf = validate_problem = None
        print('AVISO: sgf_lib.py no encontrado junto al script; no se validara.\n')

    with open(json_path, encoding='utf-8') as fh:
        meta = json.load(fh)

    errors, warnings = [], []
    sev_count = {'ERROR': 0, 'BROKEN': 0, 'WARNING': 0, 'COSMETIC': 0}
    stats = {'passes': 0}
    total = n_chapters = 0
    per_source = {}

    structure = plan(sqlite3.connect(db_path), meta, warnings)
    for source, col_name, chapters in structure:
        for chap_name, rows in chapters:
            chap_dir = os.path.join(out_root, source, col_name, chap_name)
            os.makedirs(chap_dir)
            n_chapters += 1
            per_source[source] = per_source.get(source, 0) + len(rows)
            width = max(3, len(str(len(rows))))
            for k, row in enumerate(rows, start=1):
                pctx = f"{source} / {col_name} / {chap_name} #{k} (task {row['task_id']})"
                try:
                    sgf = build_sgf(row, stats)
                except (TreeError, ValueError) as e:
                    errors.append(f'{pctx}: {e} -- no generado')
                    continue
                if validate_problem:
                    res = validate_problem(parse_sgf(sgf))
                    for sev, msg in res['issues']:
                        sev_count[sev] += 1
                        if sev in ('ERROR', 'BROKEN'):
                            errors.append(f'{pctx}: {sev} {msg}')
                with open(os.path.join(chap_dir, f'{k:0{width}d}.sgf'),
                          'w', encoding='utf-8', newline='') as fh:
                    fh.write(sgf)
                total += 1

            avg = sum(shifted(r['rank']) for r in rows) / len(rows)
            open(os.path.join(chap_dir, f'difficulty-{label(avg)}'), 'w').close()

    print(f'{total} problemas generados en {len(structure)} colecciones '
          f'y {n_chapters} capitulos.')
    for source in sorted(per_source):
        n_cols = sum(1 for s, _, _ in structure if s == source)
        print(f'  {source}: {n_cols} colecciones, {per_source[source]} problemas')
    if stats['passes']:
        print(f'{stats["passes"]} jugadas de pase encontradas (escritas como B[]/W[]).')
    if validate_problem:
        print('Validacion sgf_lib: ' +
              ', '.join(f'{k} {v}' for k, v in sev_count.items()))
    for title, items in (('ERRORES', errors), ('AVISOS', warnings)):
        print(f'\n=== {title}: {len(items)} ===')
        for line in items:
            print(f'  - {line}')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
