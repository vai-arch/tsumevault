"""archive_api.py — AR2 (docs/WORKPLAN_ARCHIVO.md): consultas de SOLO LECTURA al archivo de partidas.

El catálogo (archive/archive.db) lo genera kifumaster/kifu_build.py en el portátil y lo sube
kifumaster/kifu_upload.py (sustitución atómica con mv). Los SGF viven en archive/sgf/<torneo>/<edición>/
<id>.sgf (la misma estructura que kifumaster/data/lists/ en el portátil) y la verdad sobre cuáles hay es
el disco del servidor, no la columna has_sgf de la base.

Se despacha SIN DB_LOCK (no toca tsumeVault.db). Rutas, todas GET y con el mismo token que el resto:
    /archive/tree                     torneos → ediciones → secciones (con fases) y recuentos
    /archive/games?…                  lista filtrada y paginada (ver handle_games)
    /archive/players?q=texto          autocompletado por nombre o alias (también en japonés, coreano…)
    /archive/game?id=<32 hex>         ficha de una partida
    /archive/sgf?id=<32 hex>          {id, sgf}: el SGF, solo con token (no se publican en abierto)
"""
import json
import os
import re
import sqlite3
import threading
import time

ARCHIVE_DIR = os.environ.get("TSUMEVAULT_ARCHIVE_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive")
_ID = re.compile(r"^[0-9a-f]{32}$")
_LOCK = threading.Lock()
_SGF_CACHE = {"key": None, "ids": {}}
_TREE_CACHE = {"key": None, "tree": None}
MAX_LIMIT = 500
COUNTRY_ORDER = ("japan", "korea", "china", "taiwan", "international", "other")
SGF_MAX_BYTES = 2 * 1024 * 1024


class Unavailable(Exception):
    """archive.db no está (aún no se ha subido)."""


def db_path():
    return os.path.join(ARCHIVE_DIR, "archive.db")


def sgf_dir():
    return os.path.join(ARCHIVE_DIR, "sgf")


def _connect():
    p = db_path()
    if not os.path.isfile(p):
        raise Unavailable()
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def sgf_map():
    """id → ruta de los SGF en disco (sgf/<torneo>/<edición>/<id>.sgf; también el antiguo sgf/<xx>/<id>.sgf).
    Recorrer ~6.000 carpetas en cada petición sería caro: se recalcula cuando cambia sgf/.stamp (lo toca
    kifu_upload.py al subir o mover) o la propia carpeta sgf/, y como red de seguridad cada 5 minutos."""
    d = sgf_dir()
    try:
        st_root = os.stat(d).st_mtime_ns
    except FileNotFoundError:
        return {}
    try:
        st_stamp = os.stat(os.path.join(d, ".stamp")).st_mtime_ns
    except FileNotFoundError:
        st_stamp = 0
    key = (st_root, st_stamp, int(time.time() // 300))
    with _LOCK:
        if _SGF_CACHE["key"] == key:
            return _SGF_CACHE["ids"]
    found = {}
    for root, _, files in os.walk(d):
        for n in files:
            if n.endswith(".sgf") and _ID.match(n[:-4]):
                found.setdefault(n[:-4], os.path.join(root, n))
    with _LOCK:
        _SGF_CACHE.update(key=key, ids=found)
    return found


def sgf_ids():
    return sgf_map().keys()


def _one(qs, name, default=None):
    v = qs.get(name, [default])[0]
    return v if v != "" else default


def _int(qs, name, default=None, lo=None, hi=None):
    v = _one(qs, name)
    if v is None:
        return default
    n = int(v)                      # ValueError → 400
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise ValueError(f"{name} fuera de rango")
    return n


def _gid(qs):
    gid = (_one(qs, "id") or "").lower()
    if not _ID.match(gid):
        raise ValueError("id no válido")
    return gid


# ── /archive/tree ──
def handle_tree(qs):
    con = _connect()
    try:
        built = con.execute("SELECT value FROM ar_meta WHERE key='built_at'").fetchone()
        have = sgf_ids()
        key = (os.stat(db_path()).st_mtime_ns, built[0] if built else None, len(have), hash(frozenset(have)))
        with _LOCK:
            if _TREE_CACHE["key"] == key:
                return _TREE_CACHE["tree"]
        sgf_by_section = {}
        if have:
            for sid, gid in con.execute("SELECT section_id, id FROM ar_games WHERE section_id IS NOT NULL"):
                if gid in have:
                    sgf_by_section[sid] = sgf_by_section.get(sid, 0) + 1
        n_by_section = dict(con.execute("SELECT section_id, COUNT(*) FROM ar_games WHERE section_id IS NOT NULL GROUP BY section_id"))
        sections = {}
        for r in con.execute("SELECT id, edition_id, event_name, phases FROM ar_sections ORDER BY edition_id, ord"):
            sections.setdefault(r["edition_id"], []).append({
                "id": r["id"], "event": r["event_name"], "phases": json.loads(r["phases"]) if r["phases"] else None,
                "games": n_by_section.get(r["id"], 0), "sgf": sgf_by_section.get(r["id"], 0)})
        editions = {}
        for r in con.execute("SELECT id, tournament_slug, slug, label, date_from, date_to FROM ar_editions ORDER BY tournament_slug, ord"):
            secs = sections.get(r["id"], [])
            editions.setdefault(r["tournament_slug"], []).append({
                "id": r["id"], "slug": r["slug"], "label": r["label"], "from": r["date_from"], "to": r["date_to"],
                "games": sum(s["games"] for s in secs), "sgf": sum(s["sgf"] for s in secs), "sections": secs})
        tournaments = []
        # los torneos 'otros' están ocultos (solo se ven los de kifumaster y los promocionados)
        for r in con.execute("SELECT slug, name, name_local, kind, years, country, history FROM ar_tournaments WHERE kind <> 'otros'"):
            eds = editions.get(r["slug"], [])
            tournaments.append({"slug": r["slug"], "name": r["name"], "local": r["name_local"], "kind": r["kind"], "years": r["years"],
                                "country": r["country"] or "other",
                                "history": json.loads(r["history"]) if r["history"] else [],   # párrafos de kifumaster (ficha del torneo)
                                "games": sum(e["games"] for e in eds), "sgf": sum(e["sgf"] for e in eds), "editions": eds})
        # por país (Japón, Corea, China, Taiwán, internacionales, otros) y dentro, por nº de partidas
        order = {c: i for i, c in enumerate(COUNTRY_ORDER)}
        tournaments.sort(key=lambda t: (order.get(t["country"], len(order)), -t["games"], t["name"].lower()))
        tree = {"version": f"{built[0] if built else ''}|{len(have)}", "tournaments": tournaments}
        with _LOCK:
            _TREE_CACHE.update(key=key, tree=tree)
        return tree
    finally:
        con.close()


# ── /archive/games ──
_GAME_COLS = """g.id, g.date, g.result, g.result_text, g.event_name, g.phase, g.edition_id, g.section_id,
    pb.id AS black_id, pb.name AS black, pw.id AS white_id, pw.name AS white,
    e.tournament_slug AS tournament, e.label AS edition, e.slug AS edition_slug, t.name AS tournament_name, t.kind AS kind"""
_GAME_FROM = """FROM ar_games g LEFT JOIN ar_players pb ON pb.id = g.black_id LEFT JOIN ar_players pw ON pw.id = g.white_id
    LEFT JOIN ar_editions e ON e.id = g.edition_id LEFT JOIN ar_tournaments t ON t.slug = e.tournament_slug"""


def handle_games(qs):
    """Filtros (todos opcionales, se combinan con Y):
    tournament=slug · edition=id · section=id · phase=texto ('' = tabla principal; ausente = todas)
    player=id [&color=b|w] · player2=id (enfrentamientos de player contra player2, cualquier color)
    year_from=AAAA · year_to=AAAA · has_sgf=1 · offset · limit (≤ 500; 200 por defecto)
    Orden: fecha descendente. Devuelve {total, offset, limit, games: [...]}."""
    where, args = ["g.visible = 1"], []          # las partidas de torneos 'otros' no se muestran
    t = _one(qs, "tournament")
    if t is not None:
        where.append("e.tournament_slug = ?"); args.append(t)
    for name, col in (("edition", "g.edition_id"), ("section", "g.section_id")):
        v = _int(qs, name)
        if v is not None:
            where.append(f"{col} = ?"); args.append(v)
    if "phase" in qs:
        where.append("COALESCE(g.phase, '') = ?"); args.append(qs["phase"][0])
    p1, p2 = _int(qs, "player"), _int(qs, "player2")
    color = (_one(qs, "color") or "any").lower()
    if color not in ("any", "b", "w"):
        raise ValueError("color no válido")
    if p2 is not None and p1 is None:
        raise ValueError("player2 sin player")
    if p1 is not None and p2 is not None:
        where.append("((g.black_id = ? AND g.white_id = ?) OR (g.black_id = ? AND g.white_id = ?))"); args += [p1, p2, p2, p1]
    elif p1 is not None:
        if color == "b":
            where.append("g.black_id = ?"); args.append(p1)
        elif color == "w":
            where.append("g.white_id = ?"); args.append(p1)
        else:
            where.append("(g.black_id = ? OR g.white_id = ?)"); args += [p1, p1]
    yf, yt = _int(qs, "year_from", lo=1000, hi=3000), _int(qs, "year_to", lo=1000, hi=3000)
    if yf is not None:
        where.append("g.date >= ?"); args.append(f"{yf:04d}")
    if yt is not None:
        where.append("g.date < ?"); args.append(f"{yt + 1:04d}")
    only_sgf = _one(qs, "has_sgf") in ("1", "true")
    offset = _int(qs, "offset", 0, lo=0)
    limit = _int(qs, "limit", 200, lo=1, hi=MAX_LIMIT)
    w = (" WHERE " + " AND ".join(where)) if where else ""
    order = " ORDER BY g.date DESC, g.id DESC"   # NULL queda al final; usa el índice ix_g_date (date, id)
    have = sgf_ids()
    con = _connect()
    try:
        if only_sgf:
            # la verdad está en el disco: se filtra en Python (para el uso personal sobra)
            ids = [r[0] for r in con.execute(f"SELECT g.id {_GAME_FROM}{w}{order}", args) if r[0] in have]
            total, page = len(ids), ids[offset:offset + limit]
            rows = []
            if page:
                rows = con.execute(f"SELECT {_GAME_COLS} {_GAME_FROM} WHERE g.id IN ({','.join('?' * len(page))}){order}", page).fetchall()
        else:
            # el recuento solo necesita los JOIN si se filtra por torneo (e.*); sin ellos va mucho más rápido
            count_from = _GAME_FROM if "e." in w else "FROM ar_games g"
            total = con.execute(f"SELECT COUNT(*) {count_from}{w}", args).fetchone()[0]
            rows = con.execute(f"SELECT {_GAME_COLS} {_GAME_FROM}{w}{order} LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
        games = []
        for r in rows:
            d = dict(r)
            d["has_sgf"] = d["id"] in have
            games.append(d)
        return {"total": total, "offset": offset, "limit": limit, "games": games}
    finally:
        con.close()


# ── /archive/players ──
def handle_players(qs):
    q = (_one(qs, "q") or "").strip()
    if len(q) < 2:
        return {"players": []}
    like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    con = _connect()
    try:
        rows = con.execute("""
            SELECT p.id, p.name, p.nationality,
                   (SELECT COUNT(*) FROM ar_games WHERE black_id = p.id AND visible = 1) + (SELECT COUNT(*) FROM ar_games WHERE white_id = p.id AND visible = 1) AS games,
                   MIN(CASE WHEN a.alias = ? THEN 0 WHEN a.alias LIKE ? ESCAPE '\\' THEN 1 ELSE 2 END) AS rank
            FROM ar_player_aliases a JOIN ar_players p ON p.id = a.player_id
            WHERE a.alias LIKE ? ESCAPE '\\'
            GROUP BY p.id HAVING games > 0 ORDER BY rank, games DESC, p.name LIMIT 20""", (q, like + "%", "%" + like + "%")).fetchall()
        return {"players": [{"id": r["id"], "name": r["name"], "nationality": r["nationality"], "games": r["games"]} for r in rows]}
    finally:
        con.close()


# ── /archive/game y /archive/sgf ──
def handle_game(qs):
    gid = _gid(qs)
    con = _connect()
    try:
        r = con.execute(f"SELECT {_GAME_COLS}, s.event_name AS section_event {_GAME_FROM} LEFT JOIN ar_sections s ON s.id = g.section_id WHERE g.id = ?", (gid,)).fetchone()
        if r is None:
            return {"error": "not found"}, 404
        d = dict(r)
        d["has_sgf"] = gid in sgf_ids()
        d["kifumaster_url"] = f"https://kifumaster.org/game/{gid}"
        # dónde guardarlo en el portátil: la carpeta de su edición
        d["sgf_path"] = (f"kifumaster/data/lists/{d['tournament']}/{d['edition_slug']}/{gid}.sgf" if d.get("tournament") else None)
        return d
    finally:
        con.close()


def handle_sgf(qs):
    gid = _gid(qs)
    p = sgf_map().get(gid)
    if not p or not os.path.isfile(p):
        return {"error": "not found"}, 404
    if os.path.getsize(p) > SGF_MAX_BYTES:
        return {"error": "sgf too large"}, 413
    with open(p, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "gb18030", "shift_jis", "euc-kr", "latin-1"):
        try:
            return {"id": gid, "sgf": raw.decode(enc)}
        except UnicodeDecodeError:
            continue
    return {"id": gid, "sgf": raw.decode("utf-8", "replace")}


def guarded(fn):
    """Sin archive.db → 503 (el resto de la app sigue funcionando)."""
    def run(qs):
        try:
            return fn(qs)
        except Unavailable:
            return {"error": "archive not available"}, 503
    run.__name__ = fn.__name__
    return run


GET_ROUTES = {
    "/archive/tree": guarded(handle_tree),
    "/archive/games": guarded(handle_games),
    "/archive/players": guarded(handle_players),
    "/archive/game": guarded(handle_game),
    "/archive/sgf": guarded(handle_sgf),
}
