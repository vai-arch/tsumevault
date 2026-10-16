#!/usr/bin/env python3
"""
import_joseki.py — Valida y compila los ficheros de josekis de TsumeVault
(fase J1, ver WORKPLAN_JOSEKI_J1.md).

Lee <carpeta>/*.sgf (sin subcarpetas), imprime por cada fichero el informe
del árbol con las tarjetas resultantes y los avisos, y escribe junto a cada
SGF válido su <nombre>.json compilado, más <carpeta>/manifest.json con el
hash de cada JSON (el cliente lo usa para descachear solo lo que cambia).

No habla con el servidor: el despliegue es el .bat habitual.

Uso:
    python import_joseki.py [carpeta] [--validate-only] [--no-tree]

    carpeta          por defecto: joseki
    --validate-only  solo valida e informa; no escribe nada
    --no-tree        no imprime el árbol (solo avisos y resumen)

Reglas de escritura:
  - Fichero con ERROR: no se escribe; se conservan su JSON y su entrada de
    manifiesto anteriores (si existían).
  - SGF borrado: su entrada sale del manifiesto con un aviso; el JSON
    huérfano NO se borra (puedes borrarlo a mano).

Códigos de salida:
    0 - sin errores
    1 - algún fichero con ERROR (los válidos se escriben igualmente)
    2 - error de uso (carpeta inexistente, etc.)
"""
import argparse
import json
import os
import sys

from joseki_lib import ERROR, FORMAT, compile_joseki, content_hash, serialize

MANIFEST = "manifest.json"


def _setup_console():
    # La consola de Windows puede no ser UTF-8: nunca fallar por un acento.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def load_manifest(folder):
    path = os.path.join(folder, MANIFEST)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8"))
        return {e["file"]: e for e in data.get("files", [])}
    except (ValueError, KeyError, TypeError):
        print("AVISO: %s ilegible; se regenera desde cero." % path)
        return {}


def write_atomic(path, blob):
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(blob)
    os.replace(tmp, path)


def main():
    _setup_console()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", default="joseki")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--no-tree", action="store_true")
    args = ap.parse_args()

    folder = args.folder
    if not os.path.isdir(folder):
        print("ERROR: carpeta no encontrada: %s" % folder)
        sys.exit(2)

    sgfs = sorted(f for f in os.listdir(folder)
                  if f.lower().endswith(".sgf") and os.path.isfile(os.path.join(folder, f)))
    if not sgfs:
        print("No hay ficheros .sgf en %s" % folder)

    old = load_manifest(folder)
    new = {}
    n_ok, n_err, n_cards, n_warn = 0, 0, 0, 0

    for fname in sgfs:
        stem = os.path.splitext(fname)[0]
        with open(os.path.join(folder, fname), "rb") as fh:
            raw = fh.read()
        res = compile_joseki(raw, stem)

        print("\n" + "=" * 72)
        print(fname)
        print("=" * 72)
        if res["ok"] and not args.no_tree:
            for line in res["tree"]:
                print(line)

        errs = [i for i in res["issues"] if i[0] == ERROR]
        warns = [i for i in res["issues"] if i[0] != ERROR]
        n_warn += len(warns)
        if errs:
            print("\n  ERRORES (%d) — fichero NO compilado:" % len(errs))
            for _, path, msg in errs:
                print("    - [%s] %s" % (path, msg))
        if warns:
            print("\n  AVISOS (%d):" % len(warns))
            for _, path, msg in warns:
                print("    - [%s] %s" % (path, msg))

        if res["ok"]:
            n_ok += 1
            n_cards += res["cards"]
            blob = serialize(res["data"])
            entry = {"file": stem, "json": stem + ".json",
                     "hash": content_hash(blob), "cards": res["cards"]}
            prev = old.get(stem)
            if prev and prev.get("hash") == entry["hash"]:
                state = "sin cambios"
            elif prev:
                state = "actualizado"
            else:
                state = "nuevo"
            print("\n  %d tarjetas — %s" % (res["cards"], state))
            if not args.validate_only:
                write_atomic(os.path.join(folder, entry["json"]), blob)
            new[stem] = entry
        else:
            n_err += 1
            if stem in old and os.path.isfile(os.path.join(folder, old[stem]["json"])):
                new[stem] = old[stem]
                print("\n  Se conserva el JSON anterior de este fichero.")
            else:
                print("\n  No hay JSON anterior: este fichero no estará disponible en la app.")

    for stem in sorted(set(old) - {os.path.splitext(f)[0] for f in sgfs}):
        n_warn += 1
        print("\nAVISO: %s.sgf ya no existe; se quita del manifiesto "
              "(el JSON %s no se borra)." % (stem, old[stem].get("json")))

    manifest = {"format": FORMAT, "files": [new[k] for k in sorted(new)]}
    if not args.validate_only:
        blob = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        write_atomic(os.path.join(folder, MANIFEST), blob)

    print("\n" + "=" * 72)
    print("RESUMEN: %d fichero(s) OK, %d con errores, %d tarjetas, %d aviso(s)"
          % (n_ok, n_err, n_cards, n_warn))
    if args.validate_only:
        print("(--validate-only: no se ha escrito nada)")
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
