"""
convertir_sgf_tsumego.py — Convierte SGFs de tsumego_hero al formato estándar.

Formato estándar:
  - Hoja correcta : C[RIGHT] (o C[RIGHT\nTexto original] si había comentario)
  - Hoja incorrecta: C[WRONG] (o C[WRONG\nTexto original] si había comentario)

Reglas de conversión por categoría detectada:
  TH_PLUS     : hoja con C que empieza por '+' → RIGHT, resto → WRONG
  TH_S_STATUS : hoja con S que contiene '+' o es ALIVE/LIVE → RIGHT,
                S=DEAD → WRONG
  MIXED       : aplica ambas reglas (C tiene prioridad sobre S)
  IGS_RIGHTW  : no se toca
  DIAGRAM     : se omite (no se copia al destino)
  UNKNOWN/1   : S[KO+] → tratado como TH_S_STATUS

Uso:
  python convertir_sgf_tsumego.py [origen] [destino]

Por defecto:
  origen  : tsumego_hero\problems\   (relativo al script)
  destino : tsumego_hero\problems_std\  (relativo al script)

Los SGFs se copian manteniendo la estructura de carpetas.
Los DIAGRAM se omiten y se listan en convertir_sgf_tsumego_omitidos.txt
"""

import os
import sys
from collections import Counter

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC   = os.path.join(SCRIPT_DIR, 'tsumego_hero', 'problems')
DEFAULT_DST   = os.path.join(SCRIPT_DIR, 'tsumego_hero', 'problems_std')
OMITTED_FILE  = os.path.join(SCRIPT_DIR, 'convertir_sgf_tsumego_omitidos.txt')
REPORT_FILE   = os.path.join(SCRIPT_DIR, 'convertir_sgf_tsumego_informe.txt')

SRC = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
DST = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DST

RESULT_PROPS = ('C', 'S', 'GC', 'N')


# ═══════════════════════════════════════════════════════════════════════════
# PARSER (mismo que analizador)
# ═══════════════════════════════════════════════════════════════════════════

def parse_sgf(text):
    pos = [0]
    n = len(text)

    def skip_ws():
        while pos[0] < n and text[pos[0]] in ' \t\r\n':
            pos[0] += 1

    def read_value():
        pos[0] += 1
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
# SERIALIZER — escribe el árbol de vuelta a SGF
# ═══════════════════════════════════════════════════════════════════════════

def escape_sgf(val):
    """Escapa ] y \ dentro de valores SGF."""
    return val.replace('\\', '\\\\').replace(']', '\\]')

def serialize_node(node):
    """Serializa un nodo y sus hijos a texto SGF."""
    parts = [';']
    for key, vals in node['props'].items():
        parts.append(key)
        for v in vals:
            parts.append(f'[{escape_sgf(v)}]')

    children = node['children']
    if not children:
        return ''.join(parts)

    # Un solo hijo inline (secuencia), múltiples hijos entre paréntesis
    # Reconstruimos: si el primer hijo es el "inline" (secuencia lineal),
    # lo ponemos inline; el resto como ramas.
    # Para simplicidad y seguridad, ponemos SIEMPRE ramas entre paréntesis
    # cuando hay más de un hijo, e inline cuando hay exactamente uno.
    if len(children) == 1:
        return ''.join(parts) + serialize_node(children[0])
    else:
        result = ''.join(parts)
        for child in children:
            result += '(' + serialize_node(child) + ')'
        return result

def to_sgf(root):
    return '(' + serialize_node(root) + ')'


# ═══════════════════════════════════════════════════════════════════════════
# CLASIFICACIÓN (simplificada — solo lo necesario para conversión)
# ═══════════════════════════════════════════════════════════════════════════

def has_move(node):
    return 'B' in node['props'] or 'W' in node['props']

def all_nodes(node, acc=None):
    if acc is None: acc = []
    acc.append(node)
    for c in node['children']: all_nodes(c, acc)
    return acc

def is_diagram_only(root):
    return not any(has_move(n) for n in all_nodes(root))

def is_leaf(node):
    return not node['children']

def result_marker_c(val):
    """Evalúa propiedad C."""
    v = val.strip()
    if not v: return None
    u = v.upper()
    if v.startswith('+'): return 'RIGHT'
    if u.startswith('RIGHT'): return 'RIGHT'
    if u.startswith('WRONG'): return 'WRONG'
    return None

def result_marker_s(val):
    """Evalúa propiedad S."""
    v = val.strip().upper()
    if not v: return None
    if '+' in v: return 'RIGHT'       # SEKI+, KO+, ALIVE+, etc.
    if v in ('ALIVE', 'LIVE'): return 'RIGHT'
    if v == 'DEAD': return 'WRONG'
    return None

def classify_simple(root):
    """Devuelve 'DIAGRAM', 'IGS_RIGHTW', 'CONVERTIBLE'."""
    if is_diagram_only(root):
        return 'DIAGRAM'
    ns = all_nodes(root)
    has_right = any(
        (p in n['props'] and n['props'][p][0].strip().upper().startswith('RIGHT'))
        for n in ns for p in ('C',)
    )
    has_wrong = any(
        (p in n['props'] and n['props'][p][0].strip().upper().startswith('WRONG'))
        for n in ns for p in ('C',)
    )
    has_plus = any(
        ('C' in n['props'] and n['props']['C'][0].strip().startswith('+'))
        or ('S' in n['props'] and '+' in n['props']['S'][0].upper())
        or ('S' in n['props'] and n['props']['S'][0].strip().upper() in ('ALIVE','LIVE'))
        for n in ns
    )
    # IGS puro: tiene RIGHT/WRONG pero no tiene marcadores TH
    if (has_right or has_wrong) and not has_plus:
        return 'IGS_RIGHTW'
    return 'CONVERTIBLE'


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSIÓN DEL ÁRBOL
# ═══════════════════════════════════════════════════════════════════════════

def convert_node(node):
    """
    Recorre el árbol en profundidad. En cada hoja determina si es
    RIGHT o WRONG y actualiza la propiedad C.
    No modifica nodos intermedios.
    """
    if not is_leaf(node):
        for child in node['children']:
            convert_node(child)
        return

    # Es hoja — determinar resultado
    result = None

    # Prioridad: C > S
    if 'C' in node['props']:
        result = result_marker_c(node['props']['C'][0])

    if result is None and 'S' in node['props']:
        result = result_marker_s(node['props']['S'][0])

    # Si no hay marcador en la hoja → WRONG por defecto
    if result is None:
        result = 'WRONG'

    # Aplicar: actualizar C, eliminar S
    old_c = node['props'].get('C', [''])[0].strip()

    # Construir nuevo valor de C
    if result == 'RIGHT':
        # Preservar texto original tras el marcador
        if old_c.startswith('+'):
            extra = old_c[1:].strip()
        elif old_c.upper().startswith('RIGHT'):
            extra = old_c[5:].strip().lstrip('\n').strip()
        else:
            extra = old_c if old_c else ''
        new_c = 'RIGHT\n' + extra if extra else 'RIGHT'
    else:
        if old_c.upper().startswith('WRONG'):
            extra = old_c[5:].strip().lstrip('\n').strip()
        elif old_c.startswith('-'):
            extra = old_c[1:].strip()
        else:
            extra = old_c if old_c else ''
        new_c = 'WRONG\n' + extra if extra else 'WRONG'

    node['props']['C'] = [new_c]

    # Eliminar S (ya procesado)
    node['props'].pop('S', None)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if not os.path.isdir(SRC):
        print(f"Error: origen '{SRC}' no existe.")
        sys.exit(1)

    os.makedirs(DST, exist_ok=True)

    sgf_files = []
    for dirpath, _, filenames in os.walk(SRC):
        for fname in filenames:
            if fname.lower().endswith('.sgf'):
                sgf_files.append(os.path.join(dirpath, fname))

    total = len(sgf_files)
    print(f"SGFs encontrados: {total}")
    print(f"Origen:  {SRC}")
    print(f"Destino: {DST}\n")

    stats    = Counter()
    omitted  = []
    errors   = []

    for i, fpath in enumerate(sorted(sgf_files)):
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{total}...")
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()

            root = parse_sgf(text)
            if root is None:
                errors.append((fpath, 'parse returned None'))
                stats['error'] += 1
                continue

            cat = classify_simple(root)

            if cat == 'DIAGRAM':
                omitted.append(fpath)
                stats['diagram_omitted'] += 1
                continue

            if cat == 'IGS_RIGHTW':
                # Copiar sin modificar
                out_text = text
                stats['igs_copied'] += 1
            else:
                # Convertir
                convert_node(root)
                out_text = to_sgf(root)
                stats['converted'] += 1

            # Escribir en destino manteniendo estructura
            rel      = os.path.relpath(fpath, SRC)
            out_path = os.path.join(DST, rel)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(out_text)

        except Exception as e:
            errors.append((fpath, str(e)))
            stats['error'] += 1

    # ── Informe ──────────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 60)
    lines.append("CONVERSIÓN SGF — tsumego_hero")
    lines.append("=" * 60)
    lines.append(f"Total SGFs      : {total}")
    lines.append(f"Convertidos     : {stats['converted']}")
    lines.append(f"IGS (copiados)  : {stats['igs_copied']}")
    lines.append(f"DIAGRAM omitidos: {stats['diagram_omitted']}")
    lines.append(f"Errores         : {stats['error']}")
    lines.append("")
    lines.append(f"Destino: {DST}")

    report = '\n'.join(lines)
    print('\n' + report)

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)

    if omitted:
        with open(OMITTED_FILE, 'w', encoding='utf-8') as f:
            f.write('\n'.join(os.path.relpath(p, SRC) for p in omitted))
        print(f"\n→ Omitidos (DIAGRAM): {OMITTED_FILE}")

    if errors:
        print(f"\nERRORES ({len(errors)}):")
        for fpath, err in errors:
            print(f"  {os.path.relpath(fpath, SRC)}: {err}")

    print(f"\n→ Informe: {REPORT_FILE}")
    print("Completado.")


if __name__ == '__main__':
    main()