#!/usr/bin/env python3
"""LP1: pruebas de /sync/chapter_mostrar_by_name contra tsumevault_server.py.

Uso:  python test_lp1.py   (necesita tsumevault_server.py y db_schema.sql al lado)
"""
import json, os, shutil, sqlite3, subprocess, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
TESTDIR = os.path.join(HERE, "t_lp1")
DB = os.path.join(TESTDIR, "tsumeVault.db")
PORT = 3478
BASE = f"http://127.0.0.1:{PORT}"
URL = "/sync/chapter_mostrar_by_name"
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def req(path, method="GET", body=None, origin=None):
    h = {"Content-Type": "application/json"}
    if origin:
        h["Origin"] = origin
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {}


def make_db():
    if os.path.isdir(TESTDIR):
        shutil.rmtree(TESTDIR)
    os.makedirs(TESTDIR)
    shutil.copy(os.path.join(HERE, "tsumevault_server.py"), TESTDIR)
    con = sqlite3.connect(DB)
    with open(os.path.join(HERE, "db_schema.sql"), encoding="utf-8", errors="replace") as f:
        sql = f.read().replace("CREATE TABLE sqlite_sequence(name,seq);", "")
    con.executescript(sql)
    con.executescript("""
        INSERT INTO collections (source,set_id,name,folder) VALUES
            ('awesome_lessons',1,'Lessons 3 - Group C','f'),
            ('awesome_lessons',2,'Lessons 4 - Group B','f'),
            ('otra_source',1,'Lessons 3 - Group C','f');
        INSERT INTO chapters (id,source,set_id,chapter_num,name,mostrar) VALUES
            (501,'awesome_lessons',1,1,'Which way',0),
            (502,'awesome_lessons',1,2,'Trick joseki',1),
            (503,'awesome_lessons',2,1,'Which way',0),
            (504,'otra_source',1,1,'Which way',0);
    """)
    con.commit()
    con.close()


def start_server():
    p = subprocess.Popen([sys.executable, os.path.join(TESTDIR, "tsumevault_server.py"), str(PORT)],
                         cwd=TESTDIR, stdout=open(os.path.join(TESTDIR, "out.log"), "a"),
                         stderr=subprocess.STDOUT, env=dict(os.environ, TSUMEVAULT_TOKEN=""))
    for _ in range(80):
        try:
            req("/sync/static_version")
            break
        except Exception:
            time.sleep(0.1)
    return p


def mostrar_db(cid):
    con = sqlite3.connect(DB)
    v = con.execute("SELECT mostrar FROM chapters WHERE id=?", (cid,)).fetchone()[0]
    con.close()
    return v


make_db()
p = start_server()
try:
    # GET
    st, body = req(URL + "?source=awesome_lessons")
    rows = body.get("chapters", [])
    check("GET devuelve solo los capitulos de la source pedida", st == 200 and len(rows) == 3, f"st={st} {body}")
    check("GET trae collection/chapter/mostrar",
          {"collection": "Lessons 3 - Group C", "chapter": "Trick joseki", "mostrar": 1} in rows, f"{rows}")
    st, _ = req(URL)
    check("GET sin source -> 400", st == 400, f"st={st}")

    # PUT encender
    k = {"source": "awesome_lessons", "collection": "Lessons 3 - Group C", "chapter": "Which way"}
    st, body = req(URL, "PUT", dict(k, mostrar=1))
    check("PUT mostrar=1 responde el estado final", st == 200 and body.get("mostrar") == 1, f"st={st} {body}")
    check("PUT mostrar=1 cambia SOLO el capitulo de esa coleccion",
          mostrar_db(501) == 1 and mostrar_db(503) == 0 and mostrar_db(504) == 0,
          f"{mostrar_db(501)} {mostrar_db(503)} {mostrar_db(504)}")
    st, body = req(URL + "?source=awesome_lessons")
    check("GET refleja el cambio",
          {"collection": "Lessons 3 - Group C", "chapter": "Which way", "mostrar": 1} in body.get("chapters", []),
          f"{body}")
    st, body = req(URL, "PUT", dict(k, mostrar=1))
    check("PUT repetido es idempotente", st == 200 and body.get("mostrar") == 1 and mostrar_db(501) == 1, f"{body}")

    # PUT apagar
    st, body = req(URL, "PUT", dict(k, mostrar=0))
    check("PUT mostrar=0 apaga", st == 200 and body.get("mostrar") == 0 and mostrar_db(501) == 0, f"{body}")

    # Visto tambien por el sync T34 (el que usa tsumevault.html)
    req(URL, "PUT", dict(k, mostrar=1))
    st, body = req("/sync/chapter_visibility", "PUT", {"chapters": []})
    srv = {c["id"]: c["mostrar"] for c in body.get("chapters", [])}
    check("T34 /sync/chapter_visibility ve el cambio", st == 200 and srv.get(501) == 1, f"st={st} {srv}")

    # No encontrado / invalidos
    st, _ = req(URL, "PUT", dict(k, chapter="No existe", mostrar=1))
    check("PUT capitulo inexistente -> 404", st == 404, f"st={st}")
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    con.close()
    check("PUT inexistente no crea filas", n == 4, f"n={n}")
    st, _ = req(URL, "PUT", dict(k, collection="Lessons 9 - Nada", mostrar=1))
    check("PUT coleccion inexistente -> 404", st == 404, f"st={st}")
    for label, bad in (("mostrar=2", dict(k, mostrar=2)),
                       ("mostrar=true", dict(k, mostrar=True)),
                       ("sin chapter", {"source": "awesome_lessons", "collection": "x", "mostrar": 1}),
                       ("chapter vacio", dict(k, chapter="", mostrar=1))):
        st, _ = req(URL, "PUT", bad)
        check(f"PUT con {label} -> 400", st == 400, f"st={st}")
    st, _ = req(URL, "PUT", dict(k, mostrar=0), origin="https://evil.example")
    check("PUT con Origin ajeno -> 403", st == 403, f"st={st}")
    check("anti-vacio: tras el 403 el capitulo sigue encendido", mostrar_db(501) == 1, f"{mostrar_db(501)}")
finally:
    p.terminate()
    p.wait(timeout=5)

print()
print("RESULTADO:", "TODO OK" if not FAILS else f"{len(FAILS)} FALLOS: {FAILS}")
sys.exit(1 if FAILS else 0)
