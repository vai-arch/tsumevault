#!/usr/bin/env python3
"""import_games.py — Escanea la carpeta 'games/' y sincroniza game_collections
y games en el servidor de TsumeVault vía HTTP (POST /admin/import_games).

Sustituye al antiguo script que escribía directamente en SQLite: ahora habla
con el servidor, que es quien tiene la autoridad sobre la DB.

El import es un REEMPLAZO COMPLETO: el servidor borra todo lo que tenga en
game_collections/games e inserta exactamente lo que este script encuentra en
disco. Esto es seguro porque esas tablas nunca se editan desde tsumevault.html
(son de solo lectura para el cliente) y ninguna otra tabla las referencia.
Por eso el script es idempotente: se puede relanzar cuando se quiera (p. ej.
tras añadir/quitar SGFs o carpetas) y siempre deja el servidor igual que el
disco.

Selección de servidor (salvo que se use --server-url, que fija uno fijo y
desactiva el fallback): primero se comprueba si el servidor LOCAL responde
(pensado para cuando se ejecuta en el propio Hetzner, junto al proceso del
servidor); si no responde en poco tiempo, se usa el servidor REAL (el mismo
https://tsumevault.duckdns.org al que apunta tsumevault.html por defecto).

Uso:
    python3 import_games.py
    python3 import_games.py --server-url http://localhost:3002   # fuerza uno, sin fallback
    python3 import_games.py --games-dir /ruta/a/games

Variables de entorno:
    TSUMEVAULT_LOCAL_URL    URL del servidor local (por defecto http://localhost:3002)
    TSUMEVAULT_REAL_URL     URL del servidor real  (por defecto https://tsumevault.duckdns.org)
    TSUMEVAULT_TOKEN        Si está definida, se envía como header X-Auth-Token
                            (solo hace falta si el servidor tiene auth activada)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOCAL_URL = os.environ.get("TSUMEVAULT_LOCAL_URL", "http://localhost:3002")
DEFAULT_REAL_URL = os.environ.get("TSUMEVAULT_REAL_URL", "https://tsumevault.duckdns.org")
DEFAULT_TIMEOUT = 30
PROBE_TIMEOUT = 3  # comprobación rápida de "¿está vivo el local?"


def scan_games(games_dir):
    """Recorre games/<coleccion>/*.sgf y devuelve (game_collections, games)
    en el formato que espera POST /admin/import_games."""
    if not os.path.isdir(games_dir):
        print(f"[games] Carpeta '{games_dir}' no encontrada.")
        return [], []

    collection_names = sorted(e.name for e in os.scandir(games_dir) if e.is_dir())
    if not collection_names:
        print(f"[games] Sin subcarpetas en '{games_dir}'.")
        return [], []

    game_collections = []
    games = []
    for col_name in collection_names:
        col_path = os.path.join(games_dir, col_name)
        game_collections.append({"name": col_name, "folder": col_name})
        sgf_files = sorted(
            f for f in os.listdir(col_path) if f.lower().endswith(".sgf")
        )
        for filename in sgf_files:
            sgf_rel = f"games/{col_name}/{filename}".replace("\\", "/")
            games.append(
                {
                    "collection_name": col_name,
                    "name": filename,
                    "sgf_path": sgf_rel,
                }
            )
    return game_collections, games


def server_is_alive(server_url, timeout=PROBE_TIMEOUT):
    """Comprobación ligera y de solo lectura (no toca datos): GET a un
    endpoint barato que ya existe (/sync/static_version)."""
    url = server_url.rstrip("/") + "/sync/static_version"
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def pick_server_url(local_url, real_url):
    """Elige local si responde; si no, real. Un solo intento de escritura
    después, contra la URL ya elegida (la comprobación es de solo lectura,
    así que probar ambas no tiene efectos secundarios)."""
    print(f"[games] Comprobando servidor local ({local_url})...")
    if server_is_alive(local_url):
        print("[games] Servidor local responde, se usa ese.")
        return local_url
    print(f"[games] Servidor local no responde, probando el real ({real_url})...")
    if server_is_alive(real_url, timeout=DEFAULT_TIMEOUT):
        print("[games] Servidor real responde, se usa ese.")
        return real_url
    print("[error] Ni el servidor local ni el real responden.", file=sys.stderr)
    sys.exit(1)


def post_import(server_url, game_collections, games, token=None, timeout=DEFAULT_TIMEOUT):
    url = server_url.rstrip("/") + "/admin/import_games"
    payload = json.dumps(
        {"game_collections": game_collections, "games": games}
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Auth-Token"] = token
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[error] HTTP {e.code} desde el servidor: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[error] No se pudo conectar a {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server-url",
        default=None,
        help="Fuerza una URL de servidor concreta y desactiva el fallback local→real",
    )
    parser.add_argument(
        "--local-url",
        default=DEFAULT_LOCAL_URL,
        help=f"URL del servidor local a probar primero (por defecto: {DEFAULT_LOCAL_URL})",
    )
    parser.add_argument(
        "--real-url",
        default=DEFAULT_REAL_URL,
        help=f"URL del servidor real, usada si el local no responde (por defecto: {DEFAULT_REAL_URL})",
    )
    parser.add_argument(
        "--games-dir",
        default=os.path.join(SCRIPT_DIR, "games"),
        help="Carpeta 'games/' a escanear (por defecto: junto a este script)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo muestra lo que se enviaría, sin hacer el POST",
    )
    args = parser.parse_args()

    token = os.environ.get("TSUMEVAULT_TOKEN", "").strip() or None

    print(f"[games] Escaneando '{args.games_dir}'...")
    game_collections, games = scan_games(args.games_dir)
    print(f"[games] {len(game_collections)} colecciones, {len(games)} partidas encontradas en disco")

    if not game_collections and not games:
        print("[games] Nada que importar, abortando (no se toca ningún servidor).")
        return

    if args.dry_run:
        print(json.dumps({"game_collections": game_collections, "games": games}, indent=2, ensure_ascii=False))
        return

    server_url = args.server_url or pick_server_url(args.local_url, args.real_url)

    print(f"[games] Enviando a {server_url} (reemplazo completo)...")
    result, status = post_import(server_url, game_collections, games, token=token)
    if status != 200 or "error" in result:
        print(f"[error] Respuesta inesperada del servidor: {result}", file=sys.stderr)
        sys.exit(1)

    print(f"  Colecciones cargadas : {result.get('collections')}")
    print(f"  Partidas cargadas    : {result.get('games')}")
    skipped = result.get("skipped_games", 0)
    if skipped:
        print(f"  Partidas OMITIDAS    : {skipped} (colección no encontrada — revisa nombres)")
    print("[games] OK")


if __name__ == "__main__":
    main()
