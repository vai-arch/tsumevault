#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
census_draw.py - Censo de los draw-events (dibujo a mano) de los clips.

Uso:
    python census_draw.py lessons.json
    python census_draw.py lessons.json --out census_draw.json

Solo LEE lessons.json; no modifica nada.

Responde a tres preguntas:
  1. Que tipos de evento hay en draw-events y con que forma de argumentos
     (por si hay alguno que no conocemos).
  2. Rango de coordenadas de los puntos con tinta (entre start-drawing y
     stop-drawing) y de los puntos sin tinta, para confirmar el tamano del
     lienzo original (hipotesis ~600 px).
  3. Anomalias: trazos sin stop, eventos desordenados, colores raros...
"""
import argparse
import json
import sys
from collections import Counter, defaultdict


# ---------------------------------------------------------------- EDN minimo
class EdnError(Exception):
    pass


def parse_edn(s):
    """Parser EDN minimo: vectores, mapas, strings, numeros, keywords, nil."""
    pos = 0
    n = len(s)

    def skip():
        nonlocal pos
        while pos < n and (s[pos].isspace() or s[pos] == ','):
            pos += 1

    def value():
        nonlocal pos
        skip()
        if pos >= n:
            raise EdnError("fin inesperado")
        c = s[pos]
        if c == '[':
            pos += 1
            out = []
            while True:
                skip()
                if pos >= n:
                    raise EdnError("vector sin cerrar")
                if s[pos] == ']':
                    pos += 1
                    return out
                out.append(value())
        if c == '{':
            pos += 1
            out = []
            while True:
                skip()
                if pos >= n:
                    raise EdnError("mapa sin cerrar")
                if s[pos] == '}':
                    pos += 1
                    return {"__map__": out}
                out.append(value())
        if c == '"':
            pos += 1
            buf = []
            while pos < n and s[pos] != '"':
                if s[pos] == '\\' and pos + 1 < n:
                    pos += 1
                buf.append(s[pos])
                pos += 1
            pos += 1
            return "".join(buf)
        # atomo
        start = pos
        while pos < n and not s[pos].isspace() and s[pos] not in ',[]{}"':
            pos += 1
        tok = s[start:pos]
        if tok == 'nil':
            return None
        if tok == 'true':
            return True
        if tok == 'false':
            return False
        try:
            return int(tok)
        except ValueError:
            pass
        try:
            return float(tok)
        except ValueError:
            pass
        return tok  # keyword (:foo) u otro simbolo

    v = value()
    return v


def parse_events(raw):
    """raw puede ser 'nil', None, un string EDN o ya una lista."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        if raw.strip() in ("", "nil"):
            return []
        v = parse_edn(raw)
        return v if isinstance(v, list) else []
    return []


# ---------------------------------------------------------- recorrer el JSON
def iter_courses(node, path=""):
    """Devuelve (path, dict) de cada dict que tenga una lista 'clips'."""
    if isinstance(node, dict):
        if isinstance(node.get("clips"), list):
            yield path, node
        else:
            for k, v in node.items():
                yield from iter_courses(v, f"{path}/{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_courses(v, f"{path}[{i}]")


def shape(args):
    """Descripcion corta de la forma de los argumentos de un evento."""
    out = []
    for a in args:
        if isinstance(a, bool):
            out.append("bool")
        elif isinstance(a, (int, float)):
            out.append("num")
        elif isinstance(a, str):
            out.append("str")
        elif a is None:
            out.append("nil")
        elif isinstance(a, list):
            out.append("vec%d" % len(a))
        else:
            out.append(type(a).__name__)
    return "(" + ",".join(out) + ")"


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, int(round(p / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[i]


# ------------------------------------------------------------------- censo
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("--out", default="census_draw.json")
    args = ap.parse_args()

    with open(args.json_file, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    n_courses = n_clips = 0
    courses_with_draw = set()
    clips_with_draw = clips_with_ink = 0
    parse_errors = []

    ev_types = Counter()
    ev_shapes = defaultdict(Counter)
    colors = Counter()

    ink_x, ink_y = [], []
    hov_x, hov_y = [], []
    max_ink = []   # (valor, curso, clip, titulo)

    strokes_per_clip = []
    stroke_durs = []
    stroke_pts = []
    n_strokes = n_deletes = 0
    anomalies = defaultdict(list)

    for path, course in iter_courses(data):
        n_courses += 1
        title = course.get("title", "")
        clips = course.get("clips") or []
        for ci, clip in enumerate(clips):
            n_clips += 1
            raw = clip.get("draw-events")
            try:
                evs = parse_events(raw)
            except EdnError as e:
                parse_errors.append((path, ci, str(e)))
                continue
            if not evs:
                continue
            clips_with_draw += 1
            courses_with_draw.add(path)

            last_t = -1
            drawing = False
            cur = None
            clip_strokes = 0
            had_ink = False
            for ev in evs:
                if not (isinstance(ev, list) and len(ev) == 2 and isinstance(ev[1], list) and ev[1]):
                    anomalies["evento_malformado"].append((path, ci))
                    continue
                t, body = ev
                kind = body[0]
                a = body[1:]
                ev_types[kind] += 1
                ev_shapes[kind][shape(a)] += 1

                if isinstance(t, (int, float)) and t < last_t:
                    anomalies["tiempo_desordenado"].append((path, ci, t))
                if isinstance(t, (int, float)):
                    last_t = t

                if kind == ":set-color":
                    colors[str(a[0]) if a else "?"] += 1
                elif kind == ":start-drawing":
                    if drawing:
                        anomalies["start_sin_stop"].append((path, ci, t))
                    drawing = True
                    had_ink = True
                    clip_strokes += 1
                    n_strokes += 1
                    cur = {"t0": t, "pts": 0}
                    if a and isinstance(a[0], list) and len(a[0]) == 2:
                        x, y = a[0]
                        ink_x.append(x); ink_y.append(y)
                        max_ink.append((max(x, y), path, ci, title))
                        cur["pts"] += 1
                elif kind == ":stop-drawing":
                    if not drawing:
                        anomalies["stop_sin_start"].append((path, ci, t))
                    else:
                        stroke_durs.append(t - cur["t0"])
                        stroke_pts.append(cur["pts"])
                    drawing = False
                    cur = None
                elif kind == ":draw-move":
                    if a and isinstance(a[0], list) and len(a[0]) == 2:
                        x, y = a[0]
                        if drawing:
                            ink_x.append(x); ink_y.append(y)
                            max_ink.append((max(x, y), path, ci, title))
                            cur["pts"] += 1
                        else:
                            hov_x.append(x); hov_y.append(y)
                elif kind == ":delete-drawing":
                    n_deletes += 1
            if drawing:
                anomalies["trazo_abierto_al_final"].append((path, ci))
            if had_ink:
                clips_with_ink += 1
            strokes_per_clip.append(clip_strokes)

    # ------------------------------------------------------------ informe
    def rng(xs):
        if not xs:
            return None
        s = sorted(xs)
        return {"min": s[0], "p1": pct(s, 1), "p50": pct(s, 50),
                "p99": pct(s, 99), "max": s[-1], "n": len(s)}

    max_ink.sort(reverse=True)
    report = {
        "cursos_totales": n_courses,
        "clips_totales": n_clips,
        "cursos_con_draw_events": len(courses_with_draw),
        "clips_con_draw_events": clips_with_draw,
        "clips_con_tinta": clips_with_ink,
        "trazos": n_strokes,
        "borrados": n_deletes,
        "tipos_de_evento": dict(ev_types),
        "formas_de_argumentos": {k: dict(v) for k, v in ev_shapes.items()},
        "colores": dict(colors),
        "tinta_x": rng(ink_x),
        "tinta_y": rng(ink_y),
        "sin_tinta_x": rng(hov_x),
        "sin_tinta_y": rng(hov_y),
        "trazos_por_clip_max": max(strokes_per_clip) if strokes_per_clip else 0,
        "duracion_trazo_ms": rng(stroke_durs),
        "puntos_por_trazo": rng(stroke_pts),
        "top_mayores_coordenadas_tinta": [
            {"valor": v, "curso": p, "clip": c, "titulo": t}
            for v, p, c, t in max_ink[:10]
        ],
        "anomalias": {k: v[:15] for k, v in anomalies.items()},
        "anomalias_conteo": {k: len(v) for k, v in anomalies.items()},
        "errores_de_parseo": parse_errors[:15],
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # ------------------------------------------------------- resumen en pantalla
    print("==== CENSO DE DRAW-EVENTS ====")
    print(f"Cursos: {n_courses}  (con dibujo: {len(courses_with_draw)})")
    print(f"Clips : {n_clips}  (con draw-events: {clips_with_draw}, con tinta: {clips_with_ink})")
    print(f"Trazos: {n_strokes}   Borrados: {n_deletes}")
    print("\nTipos de evento:")
    for k, v in ev_types.most_common():
        print(f"  {k:18} {v:8}   formas: {dict(ev_shapes[k])}")
    print("\nColores:", dict(colors) or "-")
    print("\nCoordenadas CON tinta:")
    print("  x:", report["tinta_x"])
    print("  y:", report["tinta_y"])
    print("Coordenadas SIN tinta (movimiento con el boton arriba):")
    print("  x:", report["sin_tinta_x"])
    print("  y:", report["sin_tinta_y"])
    print("\nDuracion del trazo (ms):", report["duracion_trazo_ms"])
    print("Puntos por trazo       :", report["puntos_por_trazo"])
    print("Trazos por clip (max)  :", report["trazos_por_clip_max"])
    print("\nMayores coordenadas con tinta (posibles valores atipicos):")
    for r in report["top_mayores_coordenadas_tinta"][:5]:
        print(f"  {r['valor']:.1f}  clip {r['clip']}  {r['curso']}  {r['titulo'][:50]}")
    print("\nAnomalias:", report["anomalias_conteo"] or "ninguna")
    if parse_errors:
        print(f"Errores de parseo: {len(parse_errors)} (ver {args.out})")
    print(f"\nDetalle completo en {args.out}")


if __name__ == "__main__":
    sys.exit(main())
