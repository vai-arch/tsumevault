#!/usr/bin/env python3
"""
wqhub_carpetas.py — Estadisticas leidas directamente de las carpetas
generadas (no de la base de datos): sirve para comprobar lo que realmente
se va a importar.

Espera la estructura <carpeta>/<fuente>/<coleccion>/<capitulo>/.
Por cada capitulo lee el marcador difficulty-<valor> y el DI[] de cada SGF.
Genera wqhub_carpetas.csv (separador ';', UTF-8 con BOM) con:
  fuente, coleccion, capitulo, problemas, dificultad (marcador), dificultad_num,
  media_DI, min_DI, max_DI, sin_DI (SGF sin la propiedad DI)
y muestra en consola los totales por fuente y coleccion.

Uso:
    python wqhub_carpetas.py <carpeta_wqhub_sgf>
"""
import csv
import os
import re
import sys

DIFF_RE = re.compile(r'^difficulty-(\d+)([kd])$', re.IGNORECASE)
DI_RE = re.compile(r'DI\[(\d+)([kd])\]', re.IGNORECASE)


def to_num(n, kind):
    # Igual que kyu_dan_to_num() de import_my_collection.py
    return 2100 - 100 * n if kind.lower() == 'k' else 2000 + 100 * n


def to_label(v):
    v = int(round(v / 100.0)) * 100
    return f'{(2100 - v) // 100}k' if v <= 2000 else f'{(v - 2000) // 100}d'


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        print(__doc__)
        sys.exit(2)
    root = sys.argv[1]

    rows, totals = [], []
    for source in sorted(os.listdir(root)):
        src_dir = os.path.join(root, source)
        if os.path.isdir(src_dir):
            scan_source(source, src_dir, rows, totals)

    with open('wqhub_carpetas.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['fuente', 'coleccion', 'capitulo', 'problemas', 'dificultad',
                    'dificultad_num', 'media_DI', 'min_DI', 'max_DI', 'sin_DI'])
        w.writerows(rows)

    width = max(len(c) for _, c, _, _ in totals)
    for source in sorted({s for s, _, _, _ in totals}):
        sub = [t for t in totals if t[0] == source]
        print(f'\n[{source}] {len(sub)} colecciones, {sum(t[2] for t in sub)} problemas')
        print(f'  {"Coleccion".ljust(width)}  Problemas  Media')
        for _, col, n, avg in sub:
            print(f'  {col.ljust(width)}  {n:9d}  {avg}')
    print(f'\nwqhub_carpetas.csv: {len(rows)} capitulos, '
          f'{sum(t[2] for t in totals)} problemas')
    if any(r[-1] for r in rows):
        print('AVISO: hay SGF sin DI[] (columna sin_DI)')


def scan_source(source, src_dir, rows, totals):
    for col in sorted(os.listdir(src_dir)):
        col_dir = os.path.join(src_dir, col)
        if not os.path.isdir(col_dir):
            continue
        col_n, col_di = 0, []
        for chap in sorted(os.listdir(col_dir)):
            chap_dir = os.path.join(col_dir, chap)
            if not os.path.isdir(chap_dir):
                continue
            marker, marker_num = '', ''
            di, missing, n = [], 0, 0
            for f in os.listdir(chap_dir):
                m = DIFF_RE.match(f)
                if m:
                    marker = f'{m.group(1)}{m.group(2).lower()}'
                    marker_num = to_num(int(m.group(1)), m.group(2))
                elif f.lower().endswith('.sgf'):
                    n += 1
                    with open(os.path.join(chap_dir, f), encoding='utf-8') as fh:
                        d = DI_RE.search(fh.read(300))
                    if d:
                        di.append(to_num(int(d.group(1)), d.group(2)))
                    else:
                        missing += 1
            stats = ([to_label(sum(di) / len(di)), to_label(min(di)), to_label(max(di))]
                     if di else ['', '', ''])
            rows.append([source, col, chap, n, marker, marker_num, *stats, missing])
            col_n += n
            col_di += di
        avg = to_label(sum(col_di) / len(col_di)) if col_di else '-'
        totals.append((source, col, col_n, avg))


if __name__ == '__main__':
    main()
