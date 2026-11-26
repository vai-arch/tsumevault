#!/usr/bin/env python3
"""AR1: pruebas de kifumaster/kifu_crawl.py y kifumaster/kifu_build.py contra un servidor HTTP falso
local (sin red): ETag/304, gzip, 404, 429 con espera, JSON roto, reanudación, ciclos, y el catálogo
(torneo → edición → sección → fase), alias, listas games.txt / games_pendientes.txt.

    python tests/test_kifu.py
"""
import gzip, hashlib, http.server, io, json, os, shutil, sqlite3, subprocess, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CRAWL = os.path.join(ROOT, "kifumaster", "kifu_crawl.py")
BUILD = os.path.join(ROOT, "kifumaster", "kifu_build.py")
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


# ── datos falsos con la forma real (comprobada en kifumaster el 26-nov-2026) ──
G04 = "04" + "a" * 30
IDS = {k: k * 16 if len(k) == 2 else k for k in ["4c", "51", "87", "0a", "2f", "ef", "ab", "cd"]}
M = [IDS[k] for k in ["4c", "51", "87", "0a", "2f", "ef"]]          # 6 partidas del "52nd Meijin"
TM = IDS["ab"]                                                       # 1 de "52nd Meijin Title Match"
LOOSE_TE = IDS["cd"]                                                 # en el índice y en te, pero en ninguna sección
LOOSE = G04                                                          # en el índice, sin te: sin clasificar
FILES = {
    "database/aliases.csv": "canonical,alias,script,nationality\nSeto Taiki,瀬戸大樹,japanese,JP\nSeto Taiki,세토 다이키,korean,JP\nHane Naoki,羽根直樹,japanese,JP\nNadie,Nadie,latin,0\n",
    "database/aliasesevent.csv": "canonical,,alias\n52nd Meijin,,第52期名人戦予選\n",
    "database/aliasesrank.csv": "variant,canonical\n九段,9p\n四段,4p\n",
    "database/event_families.csv": "base,numbering,variants,keys,year_map,ord_map,rows\nMeijin,ord,League,名人戦,,,405\n",
    "seo/te/d3.json": {"52nd Meijin": "meijin/52", "52nd Meijin Title Match": "meijin/52", "51st Meijin": "meijin/51"},
    "seo/t/9f.json": {"meijin": {"n": "Meijin", "l": "名人戦", "ll": "ja", "t": ["Historia."], "g": 4189, "y": "1974-2026",
                                 "s": [{"k": "52nd", "u": "52", "n": 7, "a": "2025-11-06", "z": "2026-09-17", "p": 9},
                                       {"k": "51st", "u": "51", "n": 1, "a": "2025-02-06", "z": "2026-10-29", "p": 2}]}},
    "seo/ts/77.json": {"meijin/52": {"c": [
        {"a": "52nd Meijin Title Match", "g": [[TM, "Shibano Toramaru", "Ichiriki Ryo", "2026-09-30", "B+R"]]},
        {"a": "52nd Meijin", "t": [["Preliminary B", 2], ["Preliminary C", 1]], "g": [
            [M[0], "Hane Naoki", "Kōno Rin", "2026-09-17", "B+R"], [M[1], "Hirata Tomoya", "Seto Taiki", "2026-09-07", "B+R"],
            [M[2], "Fujii Shuya", "Suzuki Shinji", "2026-08-20", "B+2.5"], [M[3], "Hon Akiyoshi", "Seto Taiki", "2026-07-23", "W+R"],
            [M[4], "Omote Yuto", "U Boi", "2026-07-15", "W+R"], [M[5], "Tanaka Koyu", "Yuki Satoshi", "2026-07-08", "W+R"]]}]}},
    "seo/g/4c.json": {gid: {"b": "X", "w": "Y", "e": "52nd Meijin", "d": "2026-01-01", "r": "Black wins by resignation"} for gid in M + [TM]},
    "seo/g/cd.json": {LOOSE_TE: {"b": "Seto Taiki", "w": "Hane Naoki", "e": "51st Meijin", "d": "2025-03-01", "r": "White wins by 0.5 points"}},
    "seo/g/04.json": {LOOSE: {"b": "Nadie", "w": "Hane Naoki", "e": "Evento suelto", "d": "1999-01-01", "r": "Jigo"},
                      **{f"{i:02x}" + "e" * 30: {"b": "A", "w": "B", "e": ev, "d": d, "r": "Jigo"} for i, (ev, d) in enumerate([
                          ("1st Lanke Cup", "2019-05-01"), ("2nd Lanke Cup", "2020-05-01"), ("2nd Lanke Cup", "2020-06-01"), ("4th Lanke Cup", "2022-05-01"),
                          ("2016 National League", "2016-04-01"), ("2017-2018 Pro-Ama League", "2017-09-01"), ("Jubango (10-Game Match)", "1939-01-01"),
                          (None, "1980-02-02"), (None, "1980-03-03"), (None, ""), ("Lanke Cup", "2018-01-01"), ("第3回テスト杯", "2001-01-01")])}},
}


class Fake:
    def __init__(self):
        self.files = {k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)).encode("utf-8") for k, v in FILES.items()}
        self.fail = {}          # ruta -> lista de códigos a devolver antes del contenido real
        self.log = []           # (ruta, cabeceras)
        self.gzip = set()


FAKE = Fake()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.lstrip("/")
        import time as _t
        FAKE.log.append((path, dict(self.headers), _t.monotonic()))
        if FAKE.fail.get(path):
            code = FAKE.fail[path].pop(0)
            self.send_response(code); self.send_header("Retry-After", "0"); self.end_headers(); return
        body = FAKE.files.get(path)
        if body is None:
            self.send_response(404); self.end_headers(); self.wfile.write(b"<html>404</html>"); return
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304); self.send_header("ETag", etag); self.end_headers(); return
        out = body
        self.send_response(200)
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", "Wed, 25 Nov 2026 22:32:47 GMT")
        self.send_header("Content-Type", "application/json" if path.endswith(".json") else "text/csv")
        if path in FAKE.gzip and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            out = gzip.compress(body); self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}/"
TMP = tempfile.mkdtemp(prefix="kifu_test_")
DATA = os.path.join(TMP, "data")
REPO = os.path.join(TMP, "repo")
ENV = dict(os.environ, KIFU_BASE=BASE, KIFU_DATA=DATA, KIFU_REPO=REPO, KIFU_DELAY="0", KIFU_BACKOFF="0.01,0.01,0.01", PYTHONIOENCODING="utf-8")


def crawl(*args):
    n0 = len(FAKE.log)
    p = subprocess.run([sys.executable, CRAWL, *args], env=ENV, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr, FAKE.log[n0:]


def build():
    p = subprocess.run([sys.executable, BUILD], env=ENV, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout + p.stderr


def state():
    with open(os.path.join(DATA, "raw", "_estado.json"), encoding="utf-8") as f:
        return json.load(f)


N_TARGETS = 4 + 4 * 256
try:
    # ── 1. primer ciclo, en dos tandas (reanudación) ──
    FAKE.gzip.add("seo/g/4c.json")
    FAKE.fail["seo/te/00.json"] = [429, 503]                # dos errores y luego 404 (no existe)
    rc, out, reqs = crawl("--limite", "10")
    check("tanda 1: termina bien y para en el límite", rc == 0 and len([r for r in reqs if not r[0].startswith("x")]) == 12, f"rc={rc} n={len(reqs)}\n{out[-600:]}")
    check("tanda 1: 429/503 se reintentan tras esperar (10 ficheros + 2 reintentos)", sum(1 for r in reqs if r[0] == "seo/te/00.json") == 3)
    check("User-Agent identificable", all("TsumeVault-archive" in r[1].get("User-Agent", "") for r in reqs))
    check("nunca pide ?step=", all("?step=" not in r[0] for r in reqs))
    st = state()
    check("estado guardado: 10 ficheros del ciclo 1, ciclo sin terminar", sum(1 for v in st["files"].values() if v["cycle"] == 1) == 10 and not st["cycle_finished"])
    rc, out, reqs2 = crawl()
    paths = [r[0] for r in reqs + reqs2]
    check("tanda 2: completa el ciclo sin repetir nada", rc == 0 and len(set(paths)) == N_TARGETS and len(reqs2) == N_TARGETS - 10, f"{len(set(paths))} {len(reqs2)}")
    st = state()
    check("ciclo 1 completo", st["cycle"] == 1 and bool(st["cycle_finished"]))
    check("404 apuntado y no guardado", st["files"]["seo/g/ff.json"]["status"] == 404 and not os.path.exists(os.path.join(DATA, "raw", "seo", "g", "ff.json")))
    raw4c = os.path.join(DATA, "raw", "seo", "g", "4c.json")
    check("gzip descomprimido y guardado tal cual", os.path.exists(raw4c) and json.load(open(raw4c, encoding="utf-8")) == FILES["seo/g/4c.json"])
    check("CSV guardado tal cual", open(os.path.join(DATA, "raw", "database", "aliases.csv"), encoding="utf-8").read() == FILES["database/aliases.csv"])
    check("ETag guardado", (st["files"]["seo/ts/77.json"].get("etag") or "").startswith('"'))
    check("orden: CSV, te, t, ts y el índice g al final", paths.index("database/aliases.csv") < paths.index("seo/te/00.json") < paths.index("seo/t/00.json") < paths.index("seo/ts/00.json") < paths.index("seo/g/00.json"))

    # ── 2. relanzar con el ciclo completo no pide nada ──
    rc, out, reqs = crawl()
    check("ciclo completo: relanzar no hace ninguna petición", rc == 0 and len(reqs) == 0 and "--nuevo-ciclo" in out)

    # ── 3. ciclo nuevo: condicional (304) y detecta el cambio ──
    FAKE.files["seo/ts/77.json"] = FAKE.files["seo/ts/77.json"].replace(b'"B+2.5"', b'"B+3.5"')
    rc, out, reqs = crawl("--nuevo-ciclo")
    existing = [r for r in reqs if r[0] in FAKE.files]
    check("ciclo 2: manda If-None-Match en lo que ya tiene", existing and all(r[1].get("If-None-Match") for r in existing))
    st = state()
    check("ciclo 2: lo cambiado se baja de nuevo", st["files"]["seo/ts/77.json"]["cycle"] == 2 and b"B+3.5" in open(os.path.join(DATA, "raw", "seo", "ts", "77.json"), "rb").read())
    check("ciclo 2: resumen con 1 cambiado y el resto igual", "cambiado 1" in out and f"igual {len(FILES) - 1}" in out, out[-300:])

    # ── 4. errores que paran ──
    FAKE.fail["seo/te/d3.json"] = [503] * 10
    rc, out, reqs = crawl("--nuevo-ciclo")
    check("503 persistente: se para con código 2 tras 3 esperas", rc == 2 and sum(1 for r in reqs if r[0] == "seo/te/d3.json") == 4, f"rc={rc}")
    st = state()
    check("…y el estado queda guardado a medias (ciclo 3 sin terminar)", st["cycle"] == 3 and not st["cycle_finished"])
    FAKE.fail.pop("seo/te/d3.json")
    good = FAKE.files["seo/t/9f.json"]
    FAKE.files["seo/t/9f.json"] = b"{roto"
    rc, out, reqs = crawl()
    check("JSON roto: se para con código 3 y no lo guarda", rc == 3 and json.load(open(os.path.join(DATA, "raw", "seo", "t", "9f.json"), encoding="utf-8")) == FILES["seo/t/9f.json"], f"rc={rc}")
    FAKE.files["seo/t/9f.json"] = good
    rc, out, reqs = crawl()
    check("tras arreglarse, sigue donde lo dejó y termina el ciclo 3", rc == 0 and state()["cycle_finished"] and "seo/te/00.json" not in [r[0] for r in reqs])

    # ── 4b. pausa entre peticiones (la regla de cortesía principal) ──
    rc, out, reqs = (lambda e: (lambda p: (p.returncode, p.stdout, FAKE.log[-3:]))(
        subprocess.run([sys.executable, CRAWL, "--nuevo-ciclo", "--limite", "3"], env=e, capture_output=True, text=True, encoding="utf-8")))(dict(ENV, KIFU_DELAY="0.3"))
    gaps = [b[2] - a[2] for a, b in zip(reqs, reqs[1:])]
    check("pausa entre peticiones respetada (≥ 0,3 s con KIFU_DELAY=0.3)", rc == 0 and len(gaps) == 2 and min(gaps) >= 0.29, str(gaps))
    rc, out, reqs = crawl()
    check("…y el ciclo 4 se completa", rc == 0 and state()["cycle_finished"])

    # ── 5. catálogo ──
    # SGF: uno en el antiguo archive/sgf/<xx>/ y otro en una edición equivocada → kifu_build los mueve
    os.makedirs(os.path.join(REPO, "archive", "sgf", "4c"))
    open(os.path.join(REPO, "archive", "sgf", "4c", M[0] + ".sgf"), "w").write("(;GM[1])")
    os.makedirs(os.path.join(DATA, "lists", "meijin", "51"))
    open(os.path.join(DATA, "lists", "meijin", "51", M[1] + ".sgf"), "w").write("(;GM[1])")
    # carpeta vieja (torneo que ya no existe) con su lista y un SGF de una partida desconocida
    os.makedirs(os.path.join(DATA, "lists", "viejo", "1"))
    open(os.path.join(DATA, "lists", "viejo", "1", "games.txt"), "w").write("x\n")
    open(os.path.join(DATA, "lists", "viejo", "1", "f" * 32 + ".sgf"), "w").write("(;GM[1])")
    rc, out = build()
    check("kifu_build termina bien", rc == 0, out[-800:])
    db = sqlite3.connect(os.path.join(DATA, "archive.db"))
    q = lambda s, *a: db.execute(s, a).fetchall()
    check("torneo con nombre local e historia", q("SELECT name, name_local, years, game_count FROM ar_tournaments WHERE kind='kifumaster'") == [("Meijin", "名人戦", "1974-2026", 4189)])
    check("ediciones en el orden de kifumaster", q("SELECT slug, label, ord FROM ar_editions WHERE tournament_slug='meijin' ORDER BY ord") == [("52", "52nd", 0), ("51", "51st", 1)])
    check("dos secciones en la 52: Title Match y principal", q("SELECT s.event_name, s.ord FROM ar_sections s JOIN ar_editions e ON e.id=s.edition_id WHERE e.tournament_slug='meijin' AND e.slug='52' ORDER BY s.ord") == [("52nd Meijin Title Match", 0), ("52nd Meijin", 1)])
    ph = dict(q("SELECT id, phase FROM ar_games WHERE section_id IS NOT NULL"))
    check("fases: las 3 primeras principal, luego 2 Preliminary B y 1 Preliminary C",
          [ph[x] for x in M] == ["", "", "", "Preliminary B", "Preliminary B", "Preliminary C"], str([ph[x] for x in M]))
    check("la del Title Match en su sección y sin fase", q("SELECT s.event_name, g.phase FROM ar_games g JOIN ar_sections s ON s.id=g.section_id WHERE g.id=?", TM) == [("52nd Meijin Title Match", "")])
    check("resultado corto (ts) y largo (g)", q("SELECT result, result_text FROM ar_games WHERE id=?", M[2]) == [("B+3.5", "Black wins by resignation")])
    check("jugadores con el nombre de ts (no el del índice)", q("SELECT p.name FROM ar_games g JOIN ar_players p ON p.id=g.black_id WHERE g.id=?", M[0]) == [("Hane Naoki",)])
    check("sin sección pero con te: edición 51 asignada", q("SELECT e.slug, g.section_id FROM ar_games g JOIN ar_editions e ON e.id=g.edition_id WHERE g.id=?", LOOSE_TE) == [("51", None)])
    check("ya no queda ninguna partida sin edición", q("SELECT COUNT(*) FROM ar_games WHERE edition_id IS NULL") == [(0,)])
    oe = lambda gid: q("SELECT t.name, t.kind, e.slug, e.label, s.event_name, g.phase FROM ar_games g JOIN ar_editions e ON e.id=g.edition_id "
                       "JOIN ar_tournaments t ON t.slug=e.tournament_slug JOIN ar_sections s ON s.id=g.section_id WHERE g.id=?", gid)
    E = lambda i: f"{i:02x}" + "e" * 30
    check("otros: evento sin número = torneo de una sola edición", oe(LOOSE) == [("Evento suelto", "otros", "unica", None, "Evento suelto", "")], str(oe(LOOSE)))
    check("otros: «2nd Lanke Cup» → Lanke Cup, edición 2", oe(E(1)) == [("Lanke Cup", "otros", "2", "2", "2nd Lanke Cup", "")], str(oe(E(1))))
    check("otros: «2016 National League» → National League, 2016", oe(E(4))[0][:3] == ("National League", "otros", "2016"))
    check("otros: «2017-2018 Pro-Ama League» → Pro-Ama League, 2017-2018", oe(E(5))[0][:3] == ("Pro-Ama League", "otros", "2017-2018"))
    check("otros: paréntesis y caracteres japoneses se quedan como nombre", oe(E(6))[0][0] == "Jubango (10-Game Match)" and oe(E(11))[0][0] == "第3回テスト杯")
    check("otros: sin evento → «Sin evento» por año (y sin fecha, edición única)", oe(E(7))[0][:3] == ("Sin evento", "otros", "1980") and oe(E(9))[0][:3] == ("Sin evento", "otros", "unica"))
    check("otros: Lanke Cup con ediciones 4, 2, 1 y la sin número al final", q("SELECT e.slug FROM ar_editions e JOIN ar_tournaments t ON t.slug=e.tournament_slug WHERE t.name='Lanke Cup' ORDER BY e.ord") == [("4",), ("2",), ("1",), ("unica",)])
    check("otros: recuento y años del torneo", q("SELECT game_count, years FROM ar_tournaments WHERE name='Lanke Cup'") == [(5, "2018-2022")])
    check("kifumaster: el Meijin sigue siendo kind=kifumaster", q("SELECT kind FROM ar_tournaments WHERE slug='meijin'") == [("kifumaster",)])
    check("alias japonés → jugador", q("SELECT p.name FROM ar_player_aliases a JOIN ar_players p ON p.id=a.player_id WHERE a.alias=?", "瀬戸大樹") == [("Seto Taiki",)])
    check("nacionalidad del CSV; 0 se ignora", q("SELECT nationality FROM ar_players WHERE name IN ('Seto Taiki','Nadie') ORDER BY name") == [(None,), ("JP",)])
    check("rangos y alias de evento cargados", q("SELECT canonical FROM ar_rank_aliases WHERE variant='九段'") == [("9p",)] and q("SELECT canonical FROM ar_event_aliases") == [("52nd Meijin",)])
    L52 = os.path.join(DATA, "lists", "meijin", "52")
    check("SGF del antiguo archive/sgf/4c movido a lists/meijin/52", os.path.exists(os.path.join(L52, M[0] + ".sgf")) and not os.path.exists(os.path.join(REPO, "archive", "sgf", "4c", M[0] + ".sgf")) and "sgf_movidos: 2" in out, out[-500:])
    check("SGF en una edición equivocada (51) movido a la suya (52)", os.path.exists(os.path.join(L52, M[1] + ".sgf")) and not os.path.exists(os.path.join(DATA, "lists", "meijin", "51", M[1] + ".sgf")))
    check("has_sgf y sgf_path según el fichero en su edición", q("SELECT id, sgf_path FROM ar_games WHERE has_sgf=1 ORDER BY id") == sorted([(M[0], f"meijin/52/{M[0]}.sgf"), (M[1], f"meijin/52/{M[1]}.sgf")]))
    check("sgf_path también para las que aún no tienen SGF", q("SELECT sgf_path FROM ar_games WHERE id=?", LOOSE_TE) == [(f"meijin/51/{LOOSE_TE}.sgf",)])
    lst = lambda *p: open(os.path.join(DATA, "lists", *p), encoding="utf-8").read().splitlines()
    g52 = lst("meijin", "52", "games.txt")
    check("games.txt de la 52: un id por línea, 7, en el orden de la página", g52 == [TM] + M, "\n".join(g52))
    check("games_pendientes.txt sin las que ya están", lst("meijin", "52", "games_pendientes.txt") == [x for x in [TM] + M if x not in (M[0], M[1])])
    check("lista de la 51", lst("meijin", "51", "games.txt") == [LOOSE_TE])
    lanke = q("SELECT slug FROM ar_tournaments WHERE name='Lanke Cup'")[0][0]
    check("listas de otros: otros-lanke-cup/2 con sus 2 partidas, la más reciente primero", lanke == "otros-lanke-cup" and lst(lanke, "2", "games.txt") == [E(2), E(1)])
    check("carpeta vieja: se quita su games.txt pero el SGF desconocido no se toca (y se avisa)",
          not os.path.exists(os.path.join(DATA, "lists", "viejo", "1", "games.txt")) and os.path.exists(os.path.join(DATA, "lists", "viejo", "1", "f" * 32 + ".sgf")) and "no está en el catálogo" in out, out[-600:])
    check("ya no hay carpeta _sin_clasificar", not os.path.exists(os.path.join(DATA, "lists", "_sin_clasificar")))
    fs = dict(q("SELECT id, first_seen FROM ar_games"))
    db.close()
    # Windows no deja sustituir un fichero abierto: kifu_build no debe dejar abierta la base anterior
    src = open(BUILD, encoding="utf-8").read()
    check("kifu_build cierra la base anterior antes de sustituirla (Windows)", "with sqlite3.connect(" not in src and "old.close()" in src)
    rc, out = build()
    db = sqlite3.connect(os.path.join(DATA, "archive.db"))
    check("reconstruir conserva first_seen y no cuenta nuevas", rc == 0 and dict(db.execute("SELECT id, first_seen FROM ar_games")) == fs and "nuevas: 0" in out, out[-300:])
    check("reconstruir no borra los SGF de las carpetas", os.path.exists(os.path.join(L52, M[0] + ".sgf")) and os.path.exists(os.path.join(L52, M[1] + ".sgf")) and "sgf_movidos: 0" in out)
    db.close()
finally:
    srv.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'TODO OK' if not FAILS else str(len(FAILS)) + ' FALLOS'}")
sys.exit(1 if FAILS else 0)
