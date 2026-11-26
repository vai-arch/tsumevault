#!/usr/bin/env python3
"""AR2: rutas /archive/* del servidor (server/archive_api.py) y subida kifumaster/kifu_upload.py.

Construye un archive.db pequeño con kifu_build.py (desde un raw/ falso), arranca tsumevault_server.py
con token y lo consulta. La subida se prueba con un ssh/scp falsos que ejecutan sobre una carpeta local.

    python tests/test_archive_server.py
"""
import gzip, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(ROOT, "server")
FAILS = []
PORT = 3489
TOKEN = "tok-archive"


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def gid(prefix, n):
    return (prefix + f"{n:x}" * 32)[:32]


TMP = tempfile.mkdtemp(prefix="ar2_")
RAW = os.path.join(TMP, "data", "raw")
A = [gid("4c", i) for i in range(1, 6)]        # 52nd Meijin: 2 principal, 2 Preliminary B, 1 Preliminary C
TM = gid("ab", 1)                               # 52nd Meijin Title Match
OT = [gid("e1", 1), gid("e2", 2), gid("e3", 3)] # otros eventos: 2nd/1st Lanke Cup y sin evento
raw = {
    "database/aliases.csv": "canonical,alias,script,nationality\nSeto Taiki,瀬戸大樹,japanese,JP\nIyama Yuta,井山裕太,japanese,JP\n",
    "database/aliasesevent.csv": "canonical,,alias\n", "database/aliasesrank.csv": "variant,canonical\n九段,9p\n",
    "database/event_families.csv": "base,numbering,variants,keys,year_map,ord_map,rows\n",
    "seo/te/00.json": {"52nd Meijin": "meijin/52", "52nd Meijin Title Match": "meijin/52"},
    "seo/t/00.json": {"meijin": {"n": "Meijin", "l": "名人戦", "ll": "ja", "t": ["x"], "g": 6, "y": "2025-2026",
                                 "s": [{"k": "52nd", "u": "52", "n": 6, "a": "2025-11-06", "z": "2026-09-30", "p": 8}]}},
    "seo/ts/00.json": {"meijin/52": {"c": [
        {"a": "52nd Meijin Title Match", "g": [[TM, "Iyama Yuta", "Seto Taiki", "2026-09-30", "B+R"]]},
        {"a": "52nd Meijin", "t": [["Preliminary B", 2], ["Preliminary C", 1]], "g": [
            [A[0], "Iyama Yuta", "Seto Taiki", "2026-09-17", "B+R"], [A[1], "Seto Taiki", "Iyama Yuta", "2026-08-01", "W+0.5"],
            [A[2], "Hane Naoki", "Seto Taiki", "2025-12-07", "B+R"], [A[3], "Seto Taiki", "Hane Naoki", "2025-12-01", "W+R"],
            [A[4], "Hane Naoki", "Iyama Yuta", "2025-11-06", "B+2.5"]]}]}},
    "seo/g/00.json": {**{x: {"b": "?", "w": "?", "e": "52nd Meijin", "d": "2026-01-01", "r": "?"} for x in A + [TM]},
                      OT[0]: {"b": "Iyama Yuta", "w": "Hane Naoki", "e": "2nd Lanke Cup", "d": "2020-05-01", "r": "Black wins"},
                      OT[1]: {"b": "Hane Naoki", "w": "Iyama Yuta", "e": "1st Lanke Cup", "d": "2019-05-01", "r": "White wins"},
                      OT[2]: {"b": "Iyama Yuta", "w": "Seto Taiki", "d": "1990-03-03", "r": "Jigo"},
                      gid("e4", 4): {"b": "Solo Otros", "w": "Nadie Mas", "e": "Castle Games", "d": "1850-01-01", "r": "B+R"}},
}
for path, v in raw.items():
    p = os.path.join(RAW, *path.split("/")); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
REPO = os.path.join(TMP, "repo")
def put_at(d, g, text):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, g + ".sgf"), "w", encoding="utf-8") as f:
        f.write(text)
LISTS = os.path.join(TMP, "data", "lists")
put_at(os.path.join(LISTS, "meijin", "52"), A[0], "(;GM[1]SZ[19]PB[井山裕太]PW[瀬戸大樹];B[pd])")
def put_sgf(root, g, text, rel="meijin/52"):          # en el servidor: archive/sgf/<torneo>/<edición>/
    put_at(os.path.join(root, "archive", "sgf", *rel.split("/")), g, text)
def touch_stamp():
    with open(os.path.join(SRV, "archive", "sgf", ".stamp"), "w") as f:
        f.write(str(time.time()))
ENV = dict(os.environ, KIFU_DATA=os.path.join(TMP, "data"), KIFU_REPO=REPO, PYTHONIOENCODING="utf-8")
b = subprocess.run([sys.executable, os.path.join(ROOT, "kifumaster", "kifu_build.py")], env=ENV, capture_output=True, text=True, encoding="utf-8")
check("kifu_build del fixture", b.returncode == 0, b.stdout + b.stderr)

# servidor: tsumeVault.db mínima + archive/ con archive.db y un SGF
SRV = os.path.join(TMP, "srv")
os.makedirs(SRV)
for f in ("tsumevault_server.py", "ai_engines.py", "archive_api.py"):
    shutil.copy(os.path.join(SERVER, f), SRV)
con = sqlite3.connect(os.path.join(SRV, "tsumeVault.db"))
con.executescript(open(os.path.join(SERVER, "db_schema.sql"), encoding="utf-8", errors="replace").read().replace("CREATE TABLE sqlite_sequence(name,seq);", ""))
con.close()
os.makedirs(os.path.join(SRV, "archive"))
shutil.copy(os.path.join(TMP, "data", "archive.db"), os.path.join(SRV, "archive", "archive.db"))
put_sgf(SRV, A[0], "(;GM[1]SZ[19]PB[井山裕太]PW[瀬戸大樹];B[pd])")


def req(path, token=TOKEN, gz=False):
    h = {"X-Auth-Token": token} if token else {}
    if gz:
        h["Accept-Encoding"] = "gzip"
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", headers=h)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw_ = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw_ = gzip.decompress(raw_)
            return resp.status, json.loads(raw_), dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw_ = e.read()
        return e.code, (json.loads(raw_) if raw_ else {}), dict(e.headers)


env = dict(os.environ, TSUMEVAULT_TOKEN=TOKEN)
env.pop("TSUMEVAULT_ARCHIVE_DIR", None)
p = subprocess.Popen([sys.executable, os.path.join(SRV, "tsumevault_server.py"), str(PORT)], cwd=SRV, env=env,
                     stdout=open(os.path.join(TMP, "srv.log"), "w"), stderr=subprocess.STDOUT)
try:
    for _ in range(60):
        try:
            req("/sync/static_version"); break
        except Exception:
            time.sleep(0.1)
    q = lambda s, **kw: req("/archive/games?" + s, **kw)

    # ── seguridad ──
    st, body, _ = req("/archive/tree", token=None)
    check("sin token: 401", st == 401)
    st, body, _ = req("/archive/sgf?id=../../tsumeVault.db")
    check("id que no es de 32 hex: 400 (sin path traversal)", st == 400)
    st, body, _ = req("/archive/games?limit=99999")
    check("limit fuera de rango: 400", st == 400)
    st, body, _ = req("/archive/games?player2=1")
    check("player2 sin player: 400", st == 400)

    # ── árbol ──
    st, tree, hd = req("/archive/tree", gz=True)
    check("tree: 200", st == 200, f"{st}")
    ts = {t["slug"]: t for t in tree.get("tournaments", [])}
    check("tree: el Meijin primero (kifumaster antes que otros)", tree["tournaments"][0]["slug"] == "meijin" and ts["meijin"]["kind"] == "kifumaster")
    m52 = ts["meijin"]["editions"][0]
    check("tree: edición 52 con 6 partidas, 1 con SGF y 2 secciones", m52["games"] == 6 and m52["sgf"] == 1 and len(m52["sections"]) == 2, json.dumps(m52)[:300])
    check("tree: la historia del torneo viaja con el árbol (ficha)", ts["meijin"]["history"] == ["x"] and all(isinstance(t["history"], list) for t in ts.values()))
    check("tree: fases de la sección principal", m52["sections"][1]["phases"] == [["Preliminary B", 2], ["Preliminary C", 1]])
    check("tree: los otros eventos no aparecen (ocultos)", list(ts) == ["meijin"], str(list(ts)))

    # ── lista y filtros ──
    st, r, _ = q("tournament=meijin")
    check("games: todo el Meijin (6), por fecha descendente", st == 200 and r["total"] == 6 and [g["id"] for g in r["games"]] == [TM] + A, str([g["date"] for g in r.get("games", [])]))
    sec = m52["sections"][1]["id"]
    st, r, _ = q(f"section={sec}&phase=")
    check("games: tabla principal ('' ) de la sección", [g["id"] for g in r["games"]] == A[:2])
    st, r, _ = q(f"section={sec}&phase=Preliminary%20B")
    check("games: fase Preliminary B", [g["id"] for g in r["games"]] == A[2:4] and all(g["phase"] == "Preliminary B" for g in r["games"]))
    st, pl, _ = req("/archive/players?q=" + urllib.request.quote("瀬戸"))
    check("players: alias japonés → Seto Taiki", st == 200 and pl["players"] and pl["players"][0]["name"] == "Seto Taiki", str(pl))
    seto = pl["players"][0]["id"]
    st, pl, _ = req("/archive/players?q=iya")
    iyama = pl["players"][0]["id"] if pl["players"] else None
    check("players: por trozo del nombre, con nº de partidas", pl["players"] and pl["players"][0]["name"] == "Iyama Yuta" and pl["players"][0]["games"] == 4, str(pl))
    st, r, _ = q(f"player={seto}")
    check("games: Seto con cualquier color (5; la de otros eventos no cuenta)", r["total"] == 5, str(r["total"]))
    st, r, _ = q(f"player={seto}&color=b")
    check("games: Seto solo con negras (2)", r["total"] == 2 and all(g["black"] == "Seto Taiki" for g in r["games"]))
    st, r, _ = q(f"player={iyama}&player2={seto}")
    check("games: enfrentamientos Iyama-Seto en los dos colores (3)", r["total"] == 3 and {g["id"] for g in r["games"]} == {TM, A[0], A[1]}, str([g["id"] for g in r["games"]]))
    st, r, _ = q("year_from=2025&year_to=2025")
    check("games: año 2025 (3)", r["total"] == 3 and all(g["date"].startswith("2025") for g in r["games"]))
    st, r, _ = q("has_sgf=1")
    check("games: solo con SGF (1, según el disco)", r["total"] == 1 and r["games"][0]["id"] == A[0] and r["games"][0]["has_sgf"] is True)
    st, r, _ = q("tournament=meijin&limit=2&offset=2")
    check("games: paginación (total 6, página de 2 desde la 3ª)", r["total"] == 6 and [g["id"] for g in r["games"]] == A[1:3])
    st, r, _ = q("tournament=otros-lanke-cup")
    check("games: los otros eventos no salen ni pidiéndolos", st == 200 and r["total"] == 0)
    st, r, _ = q("")
    check("games: sin filtros, solo las 6 visibles", r["total"] == 6)
    st, pl, _ = req("/archive/players?q=Hane")
    check("players: el recuento solo cuenta partidas visibles", pl["players"] and pl["players"][0]["games"] == 3, str(pl))
    st, pl, _ = req("/archive/players?q=Solo")
    check("players: no sugiere jugadores que solo tienen partidas ocultas", st == 200 and pl["players"] == [], str(pl))

    # ── ficha y SGF ──
    st, g, _ = req(f"/archive/game?id={A[0]}")
    check("game: ficha con edición, fase, enlace a kifumaster y ruta", st == 200 and g["edition"] == "52nd" and g["phase"] == "" and g["has_sgf"]
          and g["kifumaster_url"].endswith(A[0]) and g["sgf_path"] == f"kifumaster/data/lists/meijin/52/{A[0]}.sgf", str(g))
    st, s, _ = req(f"/archive/sgf?id={A[0]}")
    check("sgf: devuelve el texto (UTF-8 con japonés)", st == 200 and "井山裕太" in s.get("sgf", ""))
    st, s, _ = req(f"/archive/sgf?id={A[1]}")
    check("sgf: 404 si no está en disco", st == 404)
    st, g, _ = req(f"/archive/game?id={'f' * 32}")
    check("game: 404 si no existe", st == 404)

    # ── el disco manda: un SGF nuevo aparece sin reiniciar ni reconstruir ──
    time.sleep(0.02)
    put_sgf(SRV, A[2], "(;GM[1])")          # en una carpeta que ya existía: la raíz no cambia
    st0, r0, _ = q("has_sgf=1")
    check("sin tocar .stamp un fichero nuevo aún no se ve (caché: no recorre miles de carpetas en cada petición)", r0.get("total") == 1, str(r0.get("total")))
    put_sgf(SRV, TM, "(;GM[1])", rel="4c")  # el antiguo sgf/<xx>/ también se encuentra (varias carpetas)
    touch_stamp()
    st, r, _ = q("has_sgf=1")
    st2, tree2, _ = req("/archive/tree")
    m = ([t for t in tree2.get("tournaments", []) if t["slug"] == "meijin"] or [{"editions": [{"sgf": None}]}])[0]["editions"][0]
    check("SGF subidos en caliente y .stamp tocado (dos carpetas): aparecen en la lista y en los recuentos del árbol", st == 200 and r.get("total") == 3 and m["sgf"] == 3 and tree2.get("version") != tree["version"], f"{st} {r}")

    time.sleep(0.02)
    put_sgf(SRV, A[3], "(;GM[1])")          # carpeta existente + solo .stamp: tiene que verse
    touch_stamp()
    st, r, _ = q("has_sgf=1")
    check(".stamp basta para ver un SGF nuevo en una carpeta existente", r.get("total") == 4, str(r.get("total")))

    # ── promocionar Lanke Cup y subir la base nueva: aparece al momento ──
    promo = os.path.join(TMP, "promocionados.txt")
    with open(promo, "w", encoding="utf-8") as f:
        f.write("otros-lanke-cup\n")
    b = subprocess.run([sys.executable, os.path.join(ROOT, "kifumaster", "kifu_build.py")], env=dict(ENV, KIFU_PROMO=promo), capture_output=True, text=True, encoding="utf-8")
    shutil.copy(os.path.join(TMP, "data", "archive.db"), os.path.join(SRV, "archive", "archive.db.new"))
    os.replace(os.path.join(SRV, "archive", "archive.db.new"), os.path.join(SRV, "archive", "archive.db"))
    st, tree3, _ = req("/archive/tree")
    ts3 = {t["slug"]: t for t in tree3.get("tournaments", [])}
    check("promocionado: aparece tras los de kifumaster, sin «otros-» y con sus 2 ediciones", b.returncode == 0 and [t["slug"] for t in tree3["tournaments"]] == ["meijin", "lanke-cup"]
          and ts3["lanke-cup"]["kind"] == "promocionado" and [e["slug"] for e in ts3["lanke-cup"]["editions"]] == ["2", "1"], str(list(ts3)))
    check("tree: país de cada torneo (Meijin japan, el promocionado other)", ts3["meijin"]["country"] == "japan" and ts3["lanke-cup"]["country"] == "other")
    st, r, _ = q("tournament=lanke-cup")
    check("promocionado: sus partidas se ven", r["total"] == 2 and r["games"][0]["tournament_name"] == "Lanke Cup")

    # ── sin archive.db: 503 y el resto de la app sigue ──
    os.rename(os.path.join(SRV, "archive", "archive.db"), os.path.join(SRV, "archive", "x.db"))
    st, body, _ = req("/archive/tree")
    st2, body2, _ = req("/sync/static_version")
    check("sin archive.db: 503 y el resto del servidor responde", st == 503 and st2 == 200, f"{st} {st2}")
    os.rename(os.path.join(SRV, "archive", "x.db"), os.path.join(SRV, "archive", "archive.db"))
finally:
    p.terminate(); p.wait(timeout=5)

# ── subida (kifu_upload.py) con ssh/scp falsos sobre una carpeta local ──
if shutil.which("bash"):
    FAKE = os.path.join(TMP, "fake"); os.makedirs(FAKE)
    with open(os.path.join(FAKE, "fake_ssh.py"), "w") as f:
        f.write("import subprocess,sys,os\nopen(os.environ['FAKE_SSH_LOG'],'a').write(sys.argv[-1]+'\\n')\nsys.exit(subprocess.run(['bash','-c',sys.argv[-1]]).returncode)\n")
    with open(os.path.join(FAKE, "fake_scp.py"), "w") as f:
        f.write("import shutil,sys,os\nargs=[a for a in sys.argv[1:]]\nfiles=[]\ni=0\n"
                "while i<len(args):\n    if args[i]=='-o': i+=2; continue\n    files.append(args[i]); i+=1\n"
                "dest=files.pop().split(':',1)[1]\nfor x in files:\n    shutil.copy(x, dest if dest.endswith('/') else dest)\n")
    REMOTE = os.path.join(TMP, "remote")
    UENV = dict(ENV, KIFU_SSH=f"{sys.executable} {os.path.join(FAKE, 'fake_ssh.py')}", KIFU_SCP=f"{sys.executable} {os.path.join(FAKE, 'fake_scp.py')}",
                KIFU_HOST="fake", KIFU_REMOTE_DIR=REMOTE, FAKE_SSH_LOG=os.path.join(TMP, "ssh.log"))
    up = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "kifumaster", "kifu_upload.py"), *a], env=UENV, capture_output=True, text=True, encoding="utf-8")
    put_at(os.path.join(LISTS, "meijin", "52"), A[3], "﻿  (;GM[1]SZ[19])")
    put_at(os.path.join(LISTS, "meijin", "unica-prueba"), gid("5a", 5), "(;GM[1])")   # otra carpeta: tiene que ir en el mismo tar
    put_at(os.path.join(LISTS, "meijin", "52"), gid("77", 1), "no soy un sgf")
    put_at(os.path.join(REMOTE, "sgf", "4c"), A[0], "(;GM[1])")          # en el servidor en la ruta antigua: se mueve, no se sube
    r = up("--simular")
    check("subir --simular: no copia ni mueve nada", r.returncode == 1 and os.listdir(os.path.join(REMOTE, "sgf")) == ["4c"] and not os.path.exists(os.path.join(REMOTE, "archive.db")), r.stdout + r.stderr)
    r = up()
    R52 = os.path.join(REMOTE, "sgf", "meijin", "52")
    check("subir: 2 SGF nuevos, 1 movido de la ruta antigua, archive.db; salta el que no es SGF (código 1)", r.returncode == 1 and "2 por subir, 1 por mover" in r.stdout and "no parece un SGF" in r.stdout
          and os.path.exists(os.path.join(R52, A[3] + ".sgf")) and os.path.exists(os.path.join(R52, A[0] + ".sgf"))
          and not os.path.exists(os.path.join(REMOTE, "sgf", "4c", A[0] + ".sgf")) and not os.path.exists(os.path.join(R52, gid("77", 1) + ".sgf"))
          and os.path.exists(os.path.join(REMOTE, "sgf", ".stamp"))
          and os.path.exists(os.path.join(REMOTE, "archive.db")), r.stdout + r.stderr)
    check("subir: comprueba que el servidor lee la base nueva (10 partidas)", "el servidor la lee: 10 partidas" in r.stdout, r.stdout)
    tars = [l for l in open(os.path.join(TMP, "ssh.log"), encoding="utf-8") if "tar -xf" in l]
    check("subir: todos los SGF nuevos (dos carpetas) en una sola conexión con tar", len(tars) == 1 and os.path.exists(os.path.join(REMOTE, "sgf", "meijin", "unica-prueba", gid("5a", 5) + ".sgf")), str(len(tars)))
    check("subir: la base sustituida es idéntica y no queda .new", open(os.path.join(REMOTE, "archive.db"), "rb").read() == open(os.path.join(TMP, "data", "archive.db"), "rb").read()
          and not os.path.exists(os.path.join(REMOTE, "archive.db.new")))
    os.remove(os.path.join(LISTS, "meijin", "52", gid("77", 1) + ".sgf"))
    r = up()
    check("subir otra vez: nada nuevo ni base distinta", r.returncode == 0 and "0 por subir, 0 por mover" in r.stdout and "igual que la del servidor" in r.stdout, r.stdout + r.stderr)
    with sqlite3.connect(os.path.join(TMP, "data", "archive.db")) as c:
        c.execute("UPDATE ar_meta SET value='x' WHERE key='built_at'")
    c.close()
    r = up()
    check("subir tras cambiar la base: solo la base", r.returncode == 0 and "0 por subir" in r.stdout and "sustituida" in r.stdout, r.stdout)
else:
    print("(sin bash: se saltan las pruebas de kifu_upload)")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TODO OK' if not FAILS else str(len(FAILS)) + ' FALLOS'}")
sys.exit(1 if FAILS else 0)
