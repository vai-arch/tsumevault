"""
descargar_ogs.py — Descarga puzzles de OGS y los convierte a SGF estándar.

Uso:
    python descargar_ogs.py <puzzle_id>

Donde <puzzle_id> es cualquier puzzle de la colección que quieres descargar.

El script obtiene el listado completo de la colección y para cada puzzle:
  1. Si JSON y SGF existen → skip
  2. Si JSON existe pero no SGF → solo convierte
  3. Si ninguno existe → descarga JSON y convierte

Salida:
    ogs/<collection_name>/json/<id>.json
    ogs/<collection_name>/sgf/<id>.sgf
"""

import os
import sys
import json
import time
import random
import re
import requests

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════

BASE_URL   = "https://online-go.com/api/v1/puzzles"
DELAY_BASE = 0.8   # segundos mínimo entre descargas
DELAY_RAND = 0.6   # segundos extra aleatorios


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def sanitize(name):
    if not name:
        return ''
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip().rstrip('.')
    return name

def human_delay():
    time.sleep(DELAY_BASE + random.uniform(0, DELAY_RAND))


# ═══════════════════════════════════════════════════════════════════════════
# DESCARGA
# ═══════════════════════════════════════════════════════════════════════════

def fetch_json(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSIÓN: initial_state → AB/AW
# ═══════════════════════════════════════════════════════════════════════════

def decode_stones(encoded):
    """
    Decodifica el string de piedras de OGS.
    Pares de letras: primera = fila (a=0 → rank 19), segunda = columna (a=0 → file A).
    Devuelve lista de coordenadas SGF en formato 'xy' (col-first, a-based).
    """
    coords = []
    s = encoded.strip()
    for i in range(0, len(s) - 1, 2):
        row = ord(s[i])   - ord('a')   # 0 = top (rank 19)
        col = ord(s[i+1]) - ord('a')   # 0 = left (file A)
        # SGF coord: first char = column, second char = row
        sgf_coord = chr(ord('a') + col) + chr(ord('a') + row)
        coords.append(sgf_coord)
    return coords

def build_setup(initial_state, width, height):
    """Devuelve string SGF con SZ, AB, AW, y la propiedad de turno."""
    parts = [f'SZ[{width}]']
    black = decode_stones(initial_state.get('black', ''))
    white = decode_stones(initial_state.get('white', ''))
    if black:
        parts.append('AB' + ''.join(f'[{c}]' for c in black))
    if white:
        parts.append('AW' + ''.join(f'[{c}]' for c in white))
    return ''.join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSIÓN: move_tree → SGF
# ═══════════════════════════════════════════════════════════════════════════

# OGS color alternates starting from initial_player.
# We track whose turn it is as we recurse.

def coord_to_sgf(x, y):
    """OGS x=col (0=A), y=row (0=top rank). Returns SGF 'col row' chars."""
    return chr(ord('a') + x) + chr(ord('a') + y)

def marks_to_sgf(marks):
    """Convierte lista de marks de OGS a propiedades SGF."""
    trs, sqs, crs = [], [], []
    for m in (marks or []):
        coord = coord_to_sgf(m['x'], m['y'])
        ms = m.get('marks', {})
        if ms.get('triangle'):
            trs.append(coord)
        if ms.get('square'):
            sqs.append(coord)
        if ms.get('circle'):
            crs.append(coord)
    result = ''
    if trs:
        result += 'TR' + ''.join(f'[{c}]' for c in trs)
    if sqs:
        result += 'SQ' + ''.join(f'[{c}]' for c in sqs)
    if crs:
        result += 'CR' + ''.join(f'[{c}]' for c in crs)
    return result

def escape_sgf(val):
    return val.replace('\\', '\\\\').replace(']', '\\]')

def build_comment(node_data, is_terminal, result):
    """
    Construye el valor de C[].
    - Nodos terminales: C[RIGHT] o C[WRONG] (+ texto original si existe)
    - Nodos intermedios: texto original si existe, nada si no
    """
    raw_text = node_data.get('text', '') or ''
    # Limpiar HTML básico
    clean = re.sub(r'<[^>]+>', '', raw_text).strip()

    if is_terminal:
        if result == 'RIGHT':
            return 'RIGHT\n' + clean if clean else 'RIGHT'
        else:
            return 'WRONG\n' + clean if clean else 'WRONG'
    else:
        return clean  # puede ser vacío

def convert_tree(node_data, color):
    """
    Convierte recursivamente un nodo del move_tree de OGS a SGF.
    color: 'B' o 'W' — color que mueve en este nodo.
    Devuelve string SGF del nodo y sus descendientes, o None si es raíz ficticia.

    Detiene la recursión en nodos wrong_answer (no baja más).
    """
    x = node_data.get('x', -1)
    y = node_data.get('y', -1)

    is_correct = node_data.get('correct_answer', False)
    is_wrong   = node_data.get('wrong_answer', False)
    branches   = node_data.get('branches', []) or []

    # Nodo raíz ficticio (x=-1, y=-1): no genera nodo SGF, solo procesa ramas
    if x == -1 and y == -1:
        return convert_branches(branches, color)

    # Determinar si es terminal (para SGF)
    # Terminal si: es correct/wrong, o no tiene ramas
    is_terminal = is_correct or is_wrong or not branches

    result = 'RIGHT' if is_correct else ('WRONG' if is_wrong else None)

    # Construir el nodo SGF
    move_prop = f'{color}[{coord_to_sgf(x, y)}]'
    comment   = build_comment(node_data, is_terminal, result)
    markup    = marks_to_sgf(node_data.get('marks', []))

    node_str = ';' + move_prop
    if markup:
        node_str += markup
    if comment:
        node_str += f'C[{escape_sgf(comment)}]'

    # Si es wrong → no bajamos más
    if is_wrong:
        return node_str

    # Si es correct o sin ramas → terminal
    if is_correct or not branches:
        return node_str

    # Nodo intermedio: recursar en ramas con color alternado
    next_color = 'W' if color == 'B' else 'B'
    children_sgf = convert_branches(branches, next_color)

    if not children_sgf:
        return node_str

    return node_str + children_sgf

def convert_branches(branches, color):
    """Convierte una lista de ramas al formato SGF."""
    if not branches:
        return ''

    valid = []
    for b in branches:
        s = convert_tree(b, color)
        if s:
            valid.append(s)

    if not valid:
        return ''
    if len(valid) == 1:
        return valid[0]
    # Múltiples ramas: cada una entre paréntesis
    return ''.join(f'({v})' for v in valid)


# ═══════════════════════════════════════════════════════════════════════════
# SGF COMPLETO
# ═══════════════════════════════════════════════════════════════════════════

def puzzle_to_sgf(data):
    """Convierte el JSON completo de un puzzle OGS a SGF estándar."""
    puzzle = data['puzzle']
    width  = data.get('width', 19)
    height = data.get('height', 19)
    name   = data.get('name', '')
    rank   = data.get('rank', '')
    ptype  = data.get('type', '')

    initial_player = puzzle.get('initial_player', 'black')
    first_color    = 'B' if initial_player == 'black' else 'W'

    # Cabecera
    setup   = build_setup(puzzle.get('initial_state', {}), width, height)
    pl_prop = f'PL[{first_color}]'
    gn_prop = f'GN[{escape_sgf(name)}]'
    rk_prop = f'GC[{escape_sgf(ptype)} rank {rank}]' if rank else ''

    root_props = ';' + setup + pl_prop + gn_prop
    if rk_prop:
        root_props += rk_prop

    # Árbol de movimientos
    move_tree = puzzle.get('move_tree', {})
    tree_sgf  = convert_tree(move_tree, first_color)

    if tree_sgf:
        # Si hay una sola rama, va inline; si hay múltiples ya vienen con ()
        # convert_tree del root ficticio devuelve las ramas directamente
        return f'({root_props}{tree_sgf})'
    else:
        return f'({root_props})'


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Uso: python descargar_ogs.py <puzzle_id>")
        sys.exit(1)

    seed_id = sys.argv[1]

    # 1. Obtener colección
    print(f"Obteniendo colección desde puzzle {seed_id}...")
    summary = fetch_json(f"{BASE_URL}/{seed_id}/collection_summary")
    if not summary:
        print("Error: colección vacía o puzzle no encontrado.")
        sys.exit(1)

    # Obtener nombre de la colección del primer puzzle
    first_data   = fetch_json(f"{BASE_URL}/{summary[0]['id']}")
    col_name     = sanitize(first_data.get('collection', {}).get('name', f'collection_{seed_id}'))
    human_delay()

    print(f"Colección: {col_name}  ({len(summary)} puzzles)")

    # Carpetas
    json_dir = os.path.join('ogs', col_name, 'json')
    sgf_dir  = os.path.join('ogs', col_name, 'sgf')
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(sgf_dir,  exist_ok=True)

    ok_dl = ok_conv = skip = err = 0

    for i, entry in enumerate(summary):
        pid   = entry['id']
        pname = sanitize(entry.get('name', str(pid)))

        json_path = os.path.join(json_dir, f'{pid}.json')
        sgf_path  = os.path.join(sgf_dir,  f'{pid}.sgf')

        # Skip si ambos existen
        if os.path.exists(json_path) and os.path.exists(sgf_path):
            skip += 1
            continue

        print(f"[{i+1}/{len(summary)}] {pname} (ID {pid})", end='')

        # Descargar JSON si no existe
        if not os.path.exists(json_path):
            try:
                data = fetch_json(f"{BASE_URL}/{pid}")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(' → JSON ok', end='')
                ok_dl += 1
                human_delay()
            except Exception as e:
                print(f' → ERROR descarga: {e}')
                err += 1
                continue
        else:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(' → JSON cached', end='')

        # Convertir a SGF
        try:
            sgf = puzzle_to_sgf(data)
            with open(sgf_path, 'w', encoding='utf-8') as f:
                f.write(sgf)
            print(' → SGF ok')
            ok_conv += 1
        except Exception as e:
            print(f' → ERROR conversión: {e}')
            err += 1

    print()
    print('=' * 60)
    print(f'Completado.')
    print(f'  Descargados : {ok_dl}')
    print(f'  Convertidos : {ok_conv}')
    print(f'  Saltados    : {skip}')
    print(f'  Errores     : {err}')
    print(f'  Carpeta     : ogs/{col_name}/')


if __name__ == '__main__':
    main()
