#!/usr/bin/env python3
"""
wqhub_analisis.py — Analisis de dificultad de las colecciones de WeiqiHub.
Usa exactamente la misma estructura que genera wqhub_to_sgf.py (aplanado,
desplazamiento de rangos por coleccion y particion por bandas), asi que cada fila
corresponde a una carpeta de capitulo generada.

Genera dos CSV (separador ';', UTF-8 con BOM para Excel en espanol):

  wqhub_capitulos.csv — una fila por capitulo
    fuente, coleccion, capitulo, problemas,
    media, min, p25, mediana, p75, max     rangos ya desplazados (p.ej. 14k)
    media_num, min_num, max_num            escala TsumeVault (1k=2000, 1d=2100)
    dispersion                             desviacion tipica, en rangos
    correl_orden    correlacion (Spearman) entre el orden del libro y la
                    dificultad: ~1 = va de facil a dificil, ~0 = mezclado
    tipos           reparto por tipo de problema (vida y muerte, tesuji...)
    blancas_juegan  problemas con blancas a jugar
    jugadas_sol     media de jugadas de la linea correcta mas corta

  wqhub_problemas.csv — una fila por problema, para tablas dinamicas
    fuente, coleccion, capitulo, posicion, task_id, rango, rango_num, tipo, juega,
    jugadas_sol, variantes (hojas del arbol)

Uso (en la misma carpeta que wqhub_to_sgf.py):
    python wqhub_analisis.py <wqhub_tasks.db> <collections.json>
"""
import csv
import json
import sqlite3
import statistics
import sys
from collections import Counter

from wqhub_to_sgf import label, num, parse_tree, plan

TYPES = ['Vida y muerte', 'Tesuji', 'Captura', 'Carrera de libertades',
         'Apertura', 'Joseki', 'Medio juego', 'Yose', 'Teoria', 'Apreciacion']


def shortest_right(node, depth=0):
    """Jugadas de la linea correcta mas corta (None si no hay ninguna)."""
    if node['status'] == 'RIGHT':
        return depth
    if node['status'] == 'WRONG':
        return None
    best = None
    for _, child in node['children']:
        d = shortest_right(child, depth + 1)
        if d is not None and (best is None or d < best):
            best = d
    return best


def leaves(node):
    if node['status']:
        return 1
    return sum(leaves(c) for _, c in node['children'])


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda k: v[k])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    if len(xs) < 3:
        return ''
    try:
        return round(statistics.correlation(ranks(xs), ranks(ys)), 2)
    except statistics.StatisticsError:
        return ''  # todos los rangos iguales


def dec(x):
    """Decimal con coma para Excel en espanol."""
    return str(x).replace('.', ',')


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    db_path, json_path = sys.argv[1:]
    with open(json_path, encoding='utf-8') as fh:
        meta = json.load(fh)
    warnings = []
    structure = plan(sqlite3.connect(db_path), meta, warnings)

    cap_rows, prob_rows = [], []
    for source, col_name, chapters in structure:
        for chap_name, rows in chapters:
            ranks, sols, types = [], [], Counter()
            white = 0
            for pos, row in enumerate(rows, start=1):
                r = row['srank']
                tree = parse_tree(row['variation_tree'])
                sol = shortest_right(tree)
                tname = TYPES[row['type']] if row['type'] < len(TYPES) else str(row['type'])
                ranks.append(r)
                types[tname] += 1
                if sol is not None:
                    sols.append(sol)
                if row['first'] == 1:
                    white += 1
                prob_rows.append([source, col_name, chap_name, pos, row['task_id'],
                                  label(r), num(r), tname,
                                  'B' if row['first'] == 0 else 'W',
                                  '' if sol is None else sol, leaves(tree)])

            if len(ranks) >= 2:
                q = statistics.quantiles(ranks, n=4, method='inclusive')
            else:
                q = [ranks[0]] * 3
            mean = statistics.fmean(ranks)
            tipos = ' / '.join(f'{t} {100 * c // len(rows)}%'
                               for t, c in types.most_common())
            cap_rows.append([
                source, col_name, chap_name, len(rows),
                label(mean), label(min(ranks)), label(q[0]), label(q[1]),
                label(q[2]), label(max(ranks)),
                num(mean), num(min(ranks)), num(max(ranks)),
                dec(round(statistics.pstdev(ranks), 1)),
                dec(spearman(list(range(len(ranks))), ranks)),
                tipos, white,
                dec(round(statistics.fmean(sols), 1)) if sols else '',
            ])

    with open('wqhub_capitulos.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['fuente', 'coleccion', 'capitulo', 'problemas', 'media', 'min', 'p25',
                    'mediana', 'p75', 'max', 'media_num', 'min_num', 'max_num',
                    'dispersion', 'correl_orden', 'tipos', 'blancas_juegan',
                    'jugadas_sol'])
        w.writerows(cap_rows)
    with open('wqhub_problemas.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['fuente', 'coleccion', 'capitulo', 'posicion', 'task_id', 'rango',
                    'rango_num', 'tipo', 'juega', 'jugadas_sol', 'variantes'])
        w.writerows(prob_rows)

    print(f'wqhub_capitulos.csv: {len(cap_rows)} capitulos')
    print(f'wqhub_problemas.csv: {len(prob_rows)} problemas')
    for line in warnings:
        print(f'AVISO: {line}')


if __name__ == '__main__':
    main()
