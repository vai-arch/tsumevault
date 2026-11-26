#!/usr/bin/env python3
"""AR1 (WORKPLAN_ARCHIVO.md): construye kifumaster/data/archive.db y las listas games.txt a partir de
lo que kifu_crawl.py dejó en kifumaster/data/raw/. No usa la red: se puede repetir cuando se quiera.

    python kifumaster/kifu_build.py

Estructura: torneo → edición → sección (evento: "8th Kisei Title Match", "8th Kisei"…) → fase
("" = tabla principal, "Preliminary B"…) → partida. Las fases salen del campo t de cada sección de
seo/ts: [[fase, nº de partidas], …]; esas partidas son bloques consecutivos al FINAL de la lista de la
sección, en ese orden, y las primeras son la tabla principal (comprobado con el Meijin 52: 30+16+39).

Carpeta por edición (decidido por Victor el 26-nov): data/lists/<torneo>/<edición>/ contiene games.txt
(un id por línea, en el orden de la página), games_pendientes.txt (los ids cuyo SGF aún no está) y los
propios SGF, guardados a mano como <id>.sgf en esa misma carpeta. Si un SGF aparece en otra carpeta (la
partida cambió de edición, o está en el antiguo archive/sgf/<xx>/), kifu_build lo mueve a la suya y avisa. Las partidas de eventos que kifumaster no organiza en torneos (~37 %) se agrupan en "otros eventos"
(kind='otros', slug otros-…) por la regla de otros_family: el número o año del principio es la edición.
"""
import csv, datetime, hashlib, io, json, os, re, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("KIFU_DATA", os.path.join(HERE, "data"))
RAW = os.path.join(DATA, "raw")
REPO = os.environ.get("KIFU_REPO", os.path.dirname(HERE))      # raíz del repo: allí estaba el antiguo archive/sgf/
DB = os.path.join(DATA, "archive.db")
LISTS = os.path.join(DATA, "lists")
SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE ar_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE ar_tournaments (
  slug TEXT PRIMARY KEY, name TEXT NOT NULL, name_local TEXT, lang TEXT, years TEXT,
  game_count INTEGER NOT NULL DEFAULT 0, history TEXT,             -- JSON: lista de párrafos
  kind TEXT NOT NULL DEFAULT 'kifumaster',                         -- 'kifumaster' | 'otros' (ocultos) | 'promocionado' (de otros, ver promocionados.txt)
  country TEXT                                                      -- japan | korea | china | taiwan | international | other (idioma + paises.txt)
);
CREATE TABLE ar_editions (
  id INTEGER PRIMARY KEY, tournament_slug TEXT NOT NULL REFERENCES ar_tournaments(slug),
  slug TEXT NOT NULL, label TEXT, game_count INTEGER, player_count INTEGER,
  date_from TEXT, date_to TEXT, ord INTEGER NOT NULL,              -- ord: orden de kifumaster (la más reciente primero)
  UNIQUE (tournament_slug, slug)
);
CREATE TABLE ar_sections (
  id INTEGER PRIMARY KEY, edition_id INTEGER NOT NULL REFERENCES ar_editions(id),
  event_name TEXT NOT NULL, ord INTEGER NOT NULL,
  phases TEXT                                                       -- JSON tal cual: [["Preliminary B",16],…] o NULL
);
CREATE TABLE ar_players (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, nationality TEXT);
CREATE TABLE ar_player_aliases (
  alias TEXT NOT NULL, player_id INTEGER NOT NULL REFERENCES ar_players(id), script TEXT,
  PRIMARY KEY (alias, player_id)
);
CREATE TABLE ar_event_aliases (alias TEXT NOT NULL, canonical TEXT NOT NULL, PRIMARY KEY (alias, canonical));
CREATE TABLE ar_rank_aliases (variant TEXT PRIMARY KEY, canonical TEXT NOT NULL);
CREATE TABLE ar_games (
  id TEXT PRIMARY KEY,                                              -- 32 hex de kifumaster
  event_name TEXT, date TEXT,
  black_id INTEGER REFERENCES ar_players(id), white_id INTEGER REFERENCES ar_players(id),
  result TEXT,                                                      -- corto (B+R), de seo/ts
  result_text TEXT,                                                 -- largo, de seo/g
  edition_id INTEGER REFERENCES ar_editions(id),
  section_id INTEGER REFERENCES ar_sections(id),
  phase TEXT,                                                       -- '' = tabla principal; NULL = sin sección
  ord INTEGER,                                                      -- posición dentro de la sección
  has_sgf INTEGER NOT NULL DEFAULT 0,
  sgf_path TEXT,                                                    -- <torneo>/<edición>/<id>.sgf (relativo a lists/ y al sgf/ del servidor); NULL si está oculta
  visible INTEGER NOT NULL DEFAULT 1,                               -- 0 = de un torneo 'otros' (no se muestra en la página)
  first_seen TEXT NOT NULL                                          -- se conserva entre reconstrucciones
);
CREATE INDEX ix_g_edition ON ar_games(edition_id, section_id, ord);
CREATE INDEX ix_g_black ON ar_games(black_id, date);
CREATE INDEX ix_g_white ON ar_games(white_id, date);
CREATE INDEX ix_g_date ON ar_games(date, id);
CREATE INDEX ix_g_visible ON ar_games(visible, date, id);
CREATE INDEX ix_alias ON ar_player_aliases(alias);
"""


# "2nd Lanke Cup" → ("Lanke Cup", "2"); "2016 National League" → ("National League", "2016");
# "2017-2018 Pro-Ama League" → ("Pro-Ama League", "2017-2018"); sin número → (evento, ""); sin evento → ("Sin evento", año)
_ORD = re.compile(r"^(\d{1,3})(?:st|nd|rd|th)\s+(\S.*)$")
_YEAR = re.compile(r"^((?:1[89]|20)\d\d(?:[-–/](?:\d\d){1,2})?)\s+(\S.*)$")


def otros_family(event, date):
    """(torneo, edición, número para ordenar las ediciones) de un evento que kifumaster no organiza."""
    ev = (event or "").strip()
    if not ev:
        y = (date or "")[:4]
        return "Sin evento", y if y.isdigit() else "", int(y) if y.isdigit() else None
    m = _ORD.match(ev)
    if m:
        return m.group(2), m.group(1), int(m.group(1))
    m = _YEAR.match(ev)
    if m:
        return m.group(2), m.group(1), int(m.group(1)[:4])
    return ev, "", None


PROMO = os.environ.get("KIFU_PROMO", os.path.join(HERE, "promocionados.txt"))
COUNTRIES_FILE = os.environ.get("KIFU_PAISES", os.path.join(HERE, "paises.txt"))
COUNTRIES = ("japan", "korea", "china", "taiwan", "international", "other")
LANG_COUNTRY = {"ja": "japan", "ko": "korea", "zh-Hans": "china", "zh-Hant": "taiwan"}


def read_countries(warn):
    """paises.txt: "<torneo> <país>" por línea (# comenta). Solo las excepciones al idioma."""
    out = {}
    if not os.path.exists(COUNTRIES_FILE):
        return out
    with open(COUNTRIES_FILE, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2 or parts[1] not in COUNTRIES:
                warn(f"paises.txt línea {n}: se espera '<torneo> <{'|'.join(COUNTRIES)}>'; se ignora"); continue
            out[parts[0]] = parts[1]
    return out


def read_promotions(warn):
    """promocionados.txt: "<torneo-otros> [carpeta-nueva] [nombre para mostrar]" por línea; # comenta.
    Sin carpeta nueva, se le quita el "otros-" del principio."""
    out = {}
    if not os.path.exists(PROMO):
        return out
    with open(PROMO, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split(None, 2)
            old = parts[0]
            new = parts[1] if len(parts) > 1 else (old[6:] if old.startswith("otros-") else old)
            if not re.match(r"^[\w-]+$", new, re.UNICODE):
                warn(f"promocionados.txt línea {n}: carpeta {new!r} no válida (solo letras, números y -); se ignora la línea"); continue
            out[old] = (new, parts[2].strip() if len(parts) > 2 else None)
    return out


def slugify(name):
    s = re.sub(r"[^\w]+", "-", name.lower(), flags=re.UNICODE).strip("-_")
    return s[:60] or hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


_IDRE = re.compile(r"^[0-9a-f]{32}$")


def edition_dir(tslug, eslug):
    return f"{tslug}/{eslug}"


def find_sgf():
    """id → [rutas] de todos los SGF que hay: en lists/<torneo>/<edición>/ y en el antiguo archive/sgf/<xx>/."""
    found = {}
    for root in (LISTS, os.path.join(REPO, "archive", "sgf")):
        if not os.path.isdir(root):
            continue
        for d, _, files in os.walk(root):
            for n in files:
                if n.lower().endswith(".sgf") and _IDRE.match(n[:-4].lower()):
                    found.setdefault(n[:-4].lower(), []).append(os.path.join(d, n))
    return found


def load_family(fam, warn):
    """Une los 256 ficheros seo/<fam>/xx.json. Los que no existan (404) se saltan."""
    out, n = {}, 0
    d = os.path.join(RAW, "seo", fam)
    for i in range(256):
        p = os.path.join(d, f"{i:02x}.json")
        if not os.path.exists(p):
            continue
        n += 1
        with open(p, encoding="utf-8") as f:
            part = json.load(f)
        for k, v in part.items():
            if k in out and out[k] != v:
                warn(f"seo/{fam}: clave {k!r} repetida en dos repartos con valores distintos; me quedo con la primera")
                continue
            out[k] = v
    return out, n


def read_csv(name):
    p = os.path.join(RAW, "database", name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(io.StringIO(f.read())))


def main():
    os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
    warnings = []
    warn = warnings.append
    g, ng = load_family("g", warn)
    te, nte = load_family("te", warn)
    t, nt = load_family("t", warn)
    ts, nts = load_family("ts", warn)
    if not g:
        print("No hay índice (seo/g) en data/raw/: ejecuta antes kifu_crawl.py.")
        return 1
    print(f"Leído: seo/g {ng} ficheros ({len(g)} partidas), seo/te {nte} ({len(te)} eventos), "
          f"seo/t {nt} ({len(t)} torneos), seo/ts {nts} ({len(ts)} ediciones)")

    # first_seen de la base anterior, para no perderlo al reconstruir
    first_seen = {}
    if os.path.exists(DB):
        old = None
        try:   # ojo: usar connect() como gestor de contexto NO cierra la conexión, y en Windows un fichero abierto no se puede sustituir
            old = sqlite3.connect(DB)
            first_seen = dict(old.execute("SELECT id, first_seen FROM ar_games"))
        except sqlite3.Error:
            pass
        finally:
            if old is not None:
                old.close()
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    tmp = DB + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO ar_meta VALUES ('schema_version', ?), ('built_at', ?)", (str(SCHEMA_VERSION), now))

    # ── alias (CSV) ──
    nat = {}
    alias_rows = read_csv("aliases.csv")[1:]
    for r in alias_rows:
        if len(r) >= 4 and r[3] not in ("", "0", "?") and r[0] not in nat:
            nat[r[0]] = r[3]
    for r in read_csv("aliasesevent.csv")[1:]:
        if len(r) >= 3 and r[0] and r[2]:
            con.execute("INSERT OR IGNORE INTO ar_event_aliases VALUES (?,?)", (r[2], r[0]))
    for r in read_csv("aliasesrank.csv")[1:]:
        if len(r) >= 2 and r[0] and r[1]:
            con.execute("INSERT OR IGNORE INTO ar_rank_aliases VALUES (?,?)", (r[0], r[1]))

    players = {}
    def pid(name):
        if not name:
            return None
        if name not in players:
            cur = con.execute("INSERT INTO ar_players (name, nationality) VALUES (?,?)", (name, nat.get(name)))
            players[name] = cur.lastrowid
        return players[name]

    # ── torneos y ediciones (seo/t) ──
    ed_id = {}
    for slug in sorted(t):
        v = t[slug]
        con.execute("INSERT INTO ar_tournaments VALUES (?,?,?,?,?,?,?,'kifumaster',NULL)",
                    (slug, v.get("n") or slug, v.get("l"), v.get("ll"), v.get("y"), v.get("g") or 0,
                     json.dumps(v.get("t") or [], ensure_ascii=False)))
        for o, s in enumerate(v.get("s") or []):
            cur = con.execute("INSERT INTO ar_editions (tournament_slug, slug, label, game_count, player_count, date_from, date_to, ord) "
                              "VALUES (?,?,?,?,?,?,?,?)", (slug, str(s.get("u")), s.get("k"), s.get("n"), s.get("p"), s.get("a"), s.get("z"), o))
            ed_id[f"{slug}/{s.get('u')}"] = cur.lastrowid

    # ── partidas: primero el índice completo (seo/g) ──
    games = {}
    for gid, v in g.items():
        games[gid] = {"event_name": v.get("e"), "date": v.get("d"), "b": v.get("b"), "w": v.get("w"),
                      "result": None, "result_text": v.get("r"), "edition_id": None, "section_id": None, "phase": None, "ord": None}

    # ── secciones y fases (seo/ts) ──
    for key in sorted(ts):
        e = ed_id.get(key)
        if e is None:
            slug = key.split("/")[0]
            if slug not in t:
                warn(f"seo/ts {key}: el torneo {slug!r} no está en seo/t; se crea sin datos")
                con.execute("INSERT OR IGNORE INTO ar_tournaments (slug, name) VALUES (?,?)", (slug, slug))
            cur = con.execute("INSERT INTO ar_editions (tournament_slug, slug, label, ord) VALUES (?,?,?,?)",
                              (slug, key.split("/", 1)[1], key.split("/", 1)[1], 9999))
            e = ed_id[key] = cur.lastrowid
            warn(f"seo/ts {key}: edición que no figura en la lista del torneo; añadida al final")
        for so, sec in enumerate(ts[key].get("c") or []):
            rows = sec.get("g") or []
            phases = sec.get("t")
            cur = con.execute("INSERT INTO ar_sections (edition_id, event_name, ord, phases) VALUES (?,?,?,?)",
                              (e, sec.get("a") or "", so, json.dumps(phases, ensure_ascii=False) if phases else None))
            sid = cur.lastrowid
            # fase de cada posición: bloques al final, en el orden de t; el resto, tabla principal ("")
            labels = [""] * len(rows)
            if phases:
                total = sum(int(n) for _, n in phases)
                if total > len(rows):
                    warn(f"seo/ts {key} «{sec.get('a')}»: las fases suman {total} pero hay {len(rows)} partidas; sin fases")
                else:
                    pos = len(rows) - total
                    for name, n in phases:
                        for k in range(pos, pos + int(n)):
                            labels[k] = name
                        pos += int(n)
            for o, r in enumerate(rows):
                gid, b, w, d, res = (list(r) + [None] * 5)[:5]
                gm = games.get(gid)
                if gm is None:
                    gm = games[gid] = {"event_name": sec.get("a"), "date": d, "b": b, "w": w, "result_text": None}
                elif gm.get("section_id") is not None:
                    warn(f"partida {gid} en dos secciones ({key}); me quedo con la primera")
                    continue
                gm.update(result=res, edition_id=e, section_id=sid, phase=labels[o], ord=o)
                # manda la edición (es lo que pinta la página); el índice solo rellena lo que falte
                gm.update({k: val for k, val in (("b", b), ("w", w), ("date", d)) if val})
                if not gm.get("event_name"):
                    gm["event_name"] = sec.get("a")

    # partidas del índice que no están en ninguna sección: edición por el mapa evento → edición (seo/te)
    for gid, gm in games.items():
        if gm.get("edition_id") is None and gm.get("event_name") in te:
            gm["edition_id"] = ed_id.get(te[gm["event_name"]])

    # el resto (eventos que kifumaster no organiza en torneos): "otros eventos", agrupados por nombre
    otros = {}
    for gid, gm in games.items():
        if gm.get("edition_id") is None:
            fam, ed, num = otros_family(gm.get("event_name"), gm.get("date"))
            otros.setdefault(fam, {}).setdefault(ed, []).append(gid)
            gm["_otros"] = (fam, ed, num)
    used = set(r[0] for r in con.execute("SELECT slug FROM ar_tournaments"))
    # primero los slugs "otros-…" de todos (estables), y luego las promociones, que pueden renombrar
    fam_slug = {}
    for fam in sorted(otros):
        base = "otros-" + slugify(fam)
        slug, k = base, 2
        while slug in used:
            slug, k = f"{base}-{k}", k + 1
        used.add(slug)
        fam_slug[fam] = slug
    promo = read_promotions(warn)
    by_slug = {v: f for f, v in fam_slug.items()}
    final = {}                                     # fam -> (slug, nombre, kind)
    for fam, slug in fam_slug.items():
        final[fam] = (slug, fam, "otros")
    for old, (new, name) in promo.items():
        fam = by_slug.get(old)
        if fam is None:
            warn(f"promocionados.txt: {old!r} no es ningún torneo de otros eventos; se ignora"); continue
        if new != old and new in used:
            warn(f"promocionados.txt: {old!r} → {new!r} choca con un torneo que ya existe; se promociona sin cambiar el nombre de carpeta")
            new = old
        used.discard(old); used.add(new)
        final[fam] = (new, name or fam, "promocionado")
    for fam in sorted(otros):
        slug, tname, kind = final[fam]
        eds = otros[fam]
        dates = [games[x].get("date") for e in eds.values() for x in e if games[x].get("date")]
        years = f"{min(dates)[:4]}-{max(dates)[:4]}" if dates else None
        con.execute("INSERT INTO ar_tournaments (slug, name, years, game_count, kind) VALUES (?,?,?,?,?)",
                    (slug, tname, years, sum(len(v) for v in eds.values()), kind))
        # ediciones: la más reciente primero (como kifumaster); la edición sin número, al final
        order = sorted(eds, key=lambda e: (-games[eds[e][0]]["_otros"][2] if games[eds[e][0]]["_otros"][2] is not None else float("inf"), e))
        for o, ed in enumerate(order):
            ids = sorted(eds[ed], key=lambda x: (games[x].get("date") or "", x), reverse=True)
            ds = [games[x].get("date") for x in ids if games[x].get("date")]
            cur = con.execute("INSERT INTO ar_editions (tournament_slug, slug, label, game_count, date_from, date_to, ord) VALUES (?,?,?,?,?,?,?)",
                              (slug, ed or "unica", ed or None, len(ids), min(ds) if ds else None, max(ds) if ds else None, o))
            e = cur.lastrowid
            ev = games[ids[0]].get("event_name")
            sid = con.execute("INSERT INTO ar_sections (edition_id, event_name, ord) VALUES (?,?,0)", (e, ev or "")).lastrowid
            for k2, x in enumerate(ids):
                games[x].update(edition_id=e, section_id=sid, phase="", ord=k2)

    # SGF: cada uno en la carpeta de su edición; los que estén en otro sitio se mueven
    # solo los torneos visibles tienen carpeta; los SGF de los ocultos se dejan donde estén
    ed_dir = {r[0]: edition_dir(r[1], r[2]) for r in con.execute(
        "SELECT e.id, e.tournament_slug, e.slug FROM ar_editions e JOIN ar_tournaments t ON t.slug = e.tournament_slug WHERE t.kind <> 'otros'")}
    hidden_ed = {r[0] for r in con.execute(
        "SELECT e.id FROM ar_editions e JOIN ar_tournaments t ON t.slug = e.tournament_slug WHERE t.kind = 'otros'")}
    found = find_sgf()
    n_sgf, moved = 0, []
    for gid, gm in games.items():
        rel = f"{ed_dir[gm['edition_id']]}/{gid}.sgf" if gm.get("edition_id") in ed_dir else None
        has = False
        if rel:
            want = os.path.join(LISTS, *rel.split("/"))
            here = [p for p in found.get(gid, []) if os.path.normcase(os.path.abspath(p)) != os.path.normcase(os.path.abspath(want))]
            if os.path.exists(want):
                has = True
                for p in here:
                    warn(f"SGF repetido de {gid}: se queda {rel}; sobra {p} (no lo borro)")
            elif here:
                os.makedirs(os.path.dirname(want), exist_ok=True)
                os.replace(here[0], want)
                moved.append((here[0], rel)); has = True
                for p in here[1:]:
                    warn(f"SGF repetido de {gid}: movido {here[0]} → {rel}; sobra {p} (no lo borro)")
        elif gm.get("edition_id") in hidden_ed and found.get(gid):
            has = True                                 # oculta: el SGF cuenta, pero no se mueve
        n_sgf += has
        con.execute("INSERT INTO ar_games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (gid, gm.get("event_name"), gm.get("date"), pid(gm.get("b")), pid(gm.get("w")), gm.get("result"),
                     gm.get("result_text"), gm.get("edition_id"), gm.get("section_id"), gm.get("phase"), gm.get("ord"),
                     int(has), rel, int(gm.get("edition_id") not in hidden_ed), first_seen.get(gid, now)))
    for gid in found:
        if gid not in games:
            warn(f"SGF de una partida que no está en el catálogo: {found[gid][0]} (no lo toco)")
    for src, rel in moved:
        print(f"  movido: {src} → lists/{rel}")

    # alias de los jugadores que aparecen en alguna partida
    for r in alias_rows:
        if len(r) >= 2 and r[0] in players and r[1]:
            con.execute("INSERT OR IGNORE INTO ar_player_aliases VALUES (?,?,?)", (r[1], players[r[0]], r[2] if len(r) > 2 else None))
    for name, p in players.items():
        con.execute("INSERT OR IGNORE INTO ar_player_aliases VALUES (?,?,?)", (name, p, "canonical"))

    # país de cada torneo visible: excepción de paises.txt o, si no, el idioma de su nombre original
    overrides = read_countries(warn)
    known = {r[0] for r in con.execute("SELECT slug FROM ar_tournaments")}
    for slug in overrides:
        if slug not in known:
            warn(f"paises.txt: {slug!r} no es ningún torneo; se ignora")
    for slug, lang, kind in con.execute("SELECT slug, lang, kind FROM ar_tournaments").fetchall():
        c = overrides.get(slug) or (LANG_COUNTRY.get(lang) if kind == "kifumaster" else None) or "other"
        con.execute("UPDATE ar_tournaments SET country=? WHERE slug=?", (c, slug))

    # recuentos reales por torneo/edición (los de kifumaster se guardan aparte en game_count de seo/t)
    con.commit()
    stats = dict(
        torneos=con.execute("SELECT COUNT(*) FROM ar_tournaments WHERE kind='kifumaster'").fetchone()[0],
        promocionados=con.execute("SELECT COUNT(*) FROM ar_tournaments WHERE kind='promocionado'").fetchone()[0],
        otros_eventos=con.execute("SELECT COUNT(*) FROM ar_tournaments WHERE kind='otros'").fetchone()[0],
        partidas_visibles=con.execute("SELECT COUNT(*) FROM ar_games WHERE visible=1").fetchone()[0],
        partidas_en_otros=con.execute("SELECT COUNT(*) FROM ar_games g JOIN ar_editions e ON e.id=g.edition_id JOIN ar_tournaments t ON t.slug=e.tournament_slug WHERE t.kind='otros'").fetchone()[0],
        ediciones=con.execute("SELECT COUNT(*) FROM ar_editions e JOIN ar_tournaments t ON t.slug=e.tournament_slug WHERE t.kind='kifumaster'").fetchone()[0],
        secciones=con.execute("SELECT COUNT(*) FROM ar_sections").fetchone()[0],
        partidas=len(games),
        en_seccion=con.execute("SELECT COUNT(*) FROM ar_games WHERE section_id IS NOT NULL").fetchone()[0],
        con_fase=con.execute("SELECT COUNT(*) FROM ar_games WHERE phase <> ''").fetchone()[0],
        sin_edicion=con.execute("SELECT COUNT(*) FROM ar_games WHERE edition_id IS NULL").fetchone()[0],
        jugadores=len(players),
        con_sgf=n_sgf,
        sgf_movidos=len(moved),
        nuevas=sum(1 for gid in games if gid not in first_seen) if first_seen else 0,
    )
    write_lists(con)
    con.close()
    try:
        os.replace(tmp, DB)
    except PermissionError:
        print(f"No puedo sustituir {DB}: otro programa lo tiene abierto (¿DB Browser, el servidor, otra consola?).\n"
              f"Ciérralo y vuelve a lanzar kifu_build. El catálogo nuevo está en {tmp}.")
        return 5

    lines = [f"{k}: {v}" for k, v in stats.items()] + [f"AVISO: {w}" for w in warnings]
    with open(os.path.join(DATA, "logs", "build_" + datetime.date.today().strftime("%Y%m%d") + ".log"), "a", encoding="utf-8") as f:
        f.write(f"── {now}\n" + "\n".join(lines) + "\n")
    print("\n".join(lines[:len(stats)]))
    if warnings:
        print(f"{len(warnings)} avisos (ver data/logs/). Primeros:")
        for w in warnings[:5]:
            print("  " + w)
    print(f"Catálogo: {DB}\nListas: {LISTS}")
    return 0


def write_lists(con):
    """Una carpeta por edición con games.txt y games_pendientes.txt (un id por línea, en el orden de la
    página). NO se borra nada: en estas carpetas viven también los SGF. Las listas de carpetas que ya no
    son ediciones (torneo renombrado…) se quitan para que no confundan; sus SGF ya los movió main()."""
    current = set()
    q = """SELECT e.tournament_slug, e.slug, g.id, g.has_sgf FROM ar_games g
           JOIN ar_editions e ON e.id = g.edition_id
           LEFT JOIN ar_sections s ON s.id = g.section_id
           WHERE g.visible = 1
           ORDER BY e.tournament_slug, e.slug, COALESCE(s.ord, 999999), COALESCE(g.ord, 999999), g.date DESC, g.id"""
    groups = {}
    for tslug, eslug, gid, has in con.execute(q):
        groups.setdefault((tslug, eslug), []).append((gid, has))
    for (tslug, eslug), rows in groups.items():
        d = os.path.join(LISTS, tslug, eslug)
        current.add(os.path.normcase(os.path.abspath(d)))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "games.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.writelines(f"{gid}\n" for gid, _ in rows)
        with open(os.path.join(d, "games_pendientes.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.writelines(f"{gid}\n" for gid, has in rows if not has)
    for d, _, files in os.walk(LISTS, topdown=False):
        if os.path.normcase(os.path.abspath(d)) not in current:
            for n in ("games.txt", "games_pendientes.txt"):
                if n in files:
                    os.remove(os.path.join(d, n))
            if d != LISTS and not os.listdir(d):
                os.rmdir(d)                            # solo carpetas que se han quedado vacías (sin SGF)


if __name__ == "__main__":
    sys.exit(main())
