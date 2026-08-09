#!/usr/bin/env python3
"""Batería de pruebas Fase 1 contra tsumevault_server.py.

Prueba: compatibilidad sin token, auth con token, Origin/CORS, límites de body,
JSON malformado, dedup por uuid en push, resolución run_uuid, delete por
ids (viejo) y uuids (nuevo), validaciones 400, migración de duplicados.
"""
import json, os, sqlite3, subprocess, sys, time, urllib.request, urllib.error, gzip

HERE = os.path.dirname(os.path.abspath(__file__))
TESTDIR = os.path.join(HERE, "t_run")
DB = os.path.join(TESTDIR, "tsumeVault.db")
PORT = 3477
BASE = f"http://127.0.0.1:{PORT}"
FAILS = []

def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)

def req(path, method="GET", body=None, headers=None, origin=None, token=None):
    h = {"Content-Type": "application/json"}
    if headers: h.update(headers)
    if origin: h["Origin"] = origin
    if token: h["X-Auth-Token"] = token
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return resp.status, json.loads(raw) if raw else {}, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            if e.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {}
        return e.code, parsed, dict(e.headers)

def make_db():
    os.makedirs(TESTDIR, exist_ok=True)
    import shutil; shutil.copy(os.path.join(HERE, "tsumevault_server.py"), TESTDIR)
    if os.path.exists(DB): os.remove(DB)
    con = sqlite3.connect(DB)
    with open(os.path.join(HERE, "db_schema.sql"), encoding="utf-8", errors="replace") as f:
        sql = f.read()
    # el dump trae sqlite_sequence; crearla vía tabla dummy autoincrement ya está en schema
    sql = sql.replace("CREATE TABLE sqlite_sequence(name,seq);", "")
    # Fixture LEGACY: sin los índices únicos de Fase 1, para poder insertar los
    # duplicados históricos que la migración del servidor debe resolver.
    sql = "\n".join(l for l in sql.splitlines()
                    if "idx_attempts_uuid" not in l and "idx_runs_uuid" not in l
                    and not l.strip().startswith("-- Fase 1"))
    con.executescript(sql)
    # datos previos con DUPLICADOS por uuid para probar la migración
    con.execute("INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES (1,'tsumego_hero','chapter','closed',2,2,'2026-07-01T10:00:00Z','run-dup')")
    con.execute("INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES (2,'tsumego_hero','chapter','closed',2,2,'2026-07-01T10:00:00Z','run-dup')")
    con.execute("INSERT INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (1,'tsumego_hero',11,0,'correct')")
    con.execute("INSERT INTO run_items (run_id,source,problem_id,order_in_run,result) VALUES (2,'tsumego_hero',11,0,'correct')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (1,'tsumego_hero',11,1,'correct',900,'2026-07-01T10:00:01Z','att-dup')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (2,'tsumego_hero',11,2,'correct',900,'2026-07-01T10:00:01Z','att-dup')")
    con.execute("INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at) VALUES ('tsumego_hero','11','2026-07-10',3,2.5,2,'2026-07-05T09:00:00Z')")
    con.commit(); con.close()

def start_server(env_extra=None):
    env = dict(os.environ)
    if env_extra: env.update(env_extra)
    p = subprocess.Popen([sys.executable, os.path.join(TESTDIR, "tsumevault_server.py"), str(PORT)],
                         cwd=TESTDIR, stdout=open(os.path.join(TESTDIR, "out.log"), "a"),
                         stderr=subprocess.STDOUT, env=env)
    for _ in range(50):
        try:
            req("/sync/static_version"); break
        except Exception: time.sleep(0.1)
    return p

def stop(p):
    p.terminate(); p.wait(timeout=5)

GH = "https://vai-arch.github.io"

# ══ FASE A: sin token (modo compatibilidad) ══
make_db()
p = start_server()
try:
    # Migración: duplicados fusionados + índices únicos
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    n_att = con.execute("SELECT COUNT(*) c FROM attempts WHERE uuid='att-dup'").fetchone()["c"]
    n_run = con.execute("SELECT COUNT(*) c FROM runs WHERE uuid='run-dup'").fetchone()["c"]
    att_run = con.execute("SELECT run_id FROM attempts WHERE uuid='att-dup'").fetchone()["run_id"]
    idx = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    check("migración dedup attempts por uuid", n_att == 1, f"n={n_att}")
    check("migración dedup runs por uuid", n_run == 1, f"n={n_run}")
    check("migración repunta attempts al run conservado", att_run == 1, f"run_id={att_run}")
    check("índices únicos uuid creados", {"idx_attempts_uuid", "idx_runs_uuid"} <= idx, str(idx))
    con.close()

    # Protocolo viejo sin token ni origin → funciona (compatibilidad)
    st, body, _ = req("/sync/pull?since_attempt_id=0&since_run_id=0")
    check("pull sin token (compat)", st == 200 and "attempts" in body)

    # push protocolo viejo (sin run_uuid en attempts) — dedup por uuid
    run = {"id": 100, "uuid": "run-new-1", "source": "tsumego_hero", "set_id": None, "chapter_id": None,
           "vc_id": None, "type": "chapter", "status": "closed", "total": 1, "done": 1,
           "started_at": "2026-07-11T09:00:00Z", "closed_at": "2026-07-11T09:05:00Z",
           "run_items": [{"run_id": 100, "source": "tsumego_hero", "problem_id": 21, "order_in_run": 0, "result": "correct"}]}
    att = {"id": 100, "client_id": 100, "uuid": "att-new-1", "source": "tsumego_hero", "problem_id": 21,
           "run_id": 100, "result": "correct", "time_ms": 1200, "created_at": "2026-07-11T09:01:00Z"}
    st, body, _ = req("/sync/push", "POST", {"attempts": [att], "runs": [run]})
    check("push v. antigua ok", st == 200 and body.get("ok"), f"{st} {body}")
    st, body, _ = req("/sync/push", "POST", {"attempts": [att], "runs": [run]})
    check("push repetido ok (dedup)", st == 200, f"{st} {body}")
    con = sqlite3.connect(DB)
    c1 = con.execute("SELECT COUNT(*) FROM attempts WHERE uuid='att-new-1'").fetchone()[0]
    c2 = con.execute("SELECT COUNT(*) FROM runs WHERE uuid='run-new-1'").fetchone()[0]
    check("push repetido no duplica attempt", c1 == 1, f"c={c1}")
    check("push repetido no duplica run", c2 == 1, f"c={c2}")
    srv_run_id = con.execute("SELECT id FROM runs WHERE uuid='run-new-1'").fetchone()[0]
    a_run = con.execute("SELECT run_id FROM attempts WHERE uuid='att-new-1'").fetchone()[0]
    check("attempt mapeado a run del servidor", a_run == srv_run_id, f"{a_run} vs {srv_run_id}")
    con.close()

    # push protocolo nuevo: attempt con run_uuid de run YA sincronizado, sin el run en el payload
    att2 = {"uuid": "att-new-2", "run_uuid": "run-new-1", "source": "tsumego_hero", "problem_id": 21,
            "run_id": 999999, "result": "wrong", "time_ms": 800, "created_at": "2026-07-11T09:02:00Z", "client_id": 101, "id": 101}
    st, body, _ = req("/sync/push", "POST", {"attempts": [att2], "runs": []})
    con = sqlite3.connect(DB)
    a_run = con.execute("SELECT run_id FROM attempts WHERE uuid='att-new-2'").fetchone()[0]
    check("run_uuid resuelve run_id sin run en payload", st == 200 and a_run == srv_run_id, f"{st} run_id={a_run}")
    con.close()

    # delete por ids (viejo) y uuids (nuevo)
    st, _, _ = req("/db/runs/delete", "POST", {"ids": [srv_run_id]})
    con = sqlite3.connect(DB)
    gone = con.execute("SELECT COUNT(*) FROM runs WHERE id=?", (srv_run_id,)).fetchone()[0]
    check("delete por ids (compat) funciona", st == 200 and gone == 0)
    con.close()
    st, _, _ = req("/db/runs/delete", "POST", {"uuids": ["run-dup"]})
    con = sqlite3.connect(DB)
    gone = con.execute("SELECT COUNT(*) FROM runs WHERE uuid='run-dup'").fetchone()[0]
    check("delete por uuids funciona", st == 200 and gone == 0)
    con.close()

    # check_runs
    st, body, _ = req("/sync/check_runs", "POST", {"uuids": ["run-new-1", "no-existe"]})
    check("check_runs missing correcto", st == 200 and set(body.get("missing", [])) == {"run-new-1", "no-existe"} - set(), f"{body}")

    # Validaciones 400
    st, _, _ = req("/sync/push", "POST", {"attempts": [{"uuid": "x"}], "runs": []})
    check("push attempt inválido → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/push", "POST", {"attempts": "no-list", "runs": []})
    check("push attempts no-lista → 400", st == 400, f"st={st}")
    st, _, _ = req("/db/run", "PUT", {"id": 1})
    check("put_run sin status → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/sm2/push", "POST", {"sm2_state": [{"source": "x"}]})
    check("sm2 push inválido → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/chapters_mostrar", "PUT", {"chapters": [{"id": 1}]})
    check("chapters_mostrar inválido → 400", st == 400, f"st={st}")

    # ── T13: /sync/problems_hidden (borrado lógico, merge) ──
    # Sembrar catálogo mínimo directamente en la DB (conexión concurrente
    # legítima: WAL). El fixture legacy no trae filas en problems.
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO problems (source,problem_id,set_id,sgf_path) VALUES ('th','hx1',1,'a.sgf')")
    con.execute("INSERT INTO problems (source,problem_id,set_id,sgf_path) VALUES ('th','hx2',1,'b.sgf')")
    con.commit(); con.close()
    st, body, _ = req("/sync/problems_hidden", "PUT", {"problems": [{"source": "th", "problem_id": "hx1"}]})
    check("problems_hidden: push oculta y responde lista", st == 200 and body.get("updated") == 1
          and any(r["problem_id"] == "hx1" for r in body.get("hidden", [])), f"st={st} body={body}")
    st, body, _ = req("/sync/problems_hidden", "PUT", {"problems": []})
    check("problems_hidden: push vacío NO des-oculta (unión)", st == 200
          and any(r["problem_id"] == "hx1" for r in body.get("hidden", [])), f"body={body}")
    st, body, _ = req("/sync/problems_hidden", "PUT",
                      {"problems": [{"source": "th", "problem_id": "no-existe"}]})
    check("problems_hidden: problem inexistente ignorado (no crea filas)", st == 200
          and body.get("updated") == 0
          and not any(r["problem_id"] == "no-existe" for r in body.get("hidden", [])), f"body={body}")
    con = sqlite3.connect(DB)
    n_rows = con.execute("SELECT COUNT(*) FROM problems WHERE problem_id='no-existe'").fetchone()[0]
    con.execute("UPDATE problems SET hidden=0 WHERE problem_id='hx1'")  # unhide manual (procedimiento real de Victor)
    con.commit(); con.close()
    check("problems_hidden: sin filas fantasma en catálogo", n_rows == 0, f"n={n_rows}")
    st, body, _ = req("/sync/problems_hidden", "PUT", {"problems": []})
    check("problems_hidden: unhide manual en BD se refleja en la respuesta", st == 200
          and not any(r["problem_id"] == "hx1" for r in body.get("hidden", [])), f"body={body}")
    st, _, _ = req("/sync/problems_hidden", "PUT", {"problems": [{"source": "th"}]})
    check("problems_hidden: entrada inválida → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/problems_hidden", "PUT", {"problems": "no-list"})
    check("problems_hidden: no-lista → 400", st == 400, f"st={st}")

    # ── T13: filtrado de lecturas — un problema oculto desaparece de /db/problems
    # y no entra en runs nuevos. Guardia anti-test-vacuo: primero con todo
    # visible (hx1 fue des-ocultado arriba; hx2 nunca se ocultó).
    st, body, _ = req("/db/problems?source=th")
    ids = sorted(p["problem_id"] for p in body.get("problems", []))
    check("filtrado: baseline con hx1 y hx2 visibles", st == 200 and ids == ["hx1", "hx2"], f"ids={ids}")
    st, body, _ = req("/db/run", "POST", {"source": "th", "type": "collection", "set_id": 1})
    check("filtrado: run baseline con 2 problemas", st == 200 and body.get("total") == 2, f"body={body}")
    st, _, _ = req("/sync/problems_hidden", "PUT", {"problems": [{"source": "th", "problem_id": "hx2"}]})
    st, body, _ = req("/db/problems?source=th")
    ids = sorted(p["problem_id"] for p in body.get("problems", []))
    check("filtrado: hx2 oculto desaparece de /db/problems", st == 200 and ids == ["hx1"], f"ids={ids}")
    st, body, _ = req("/db/run", "POST", {"source": "th", "type": "collection", "set_id": 1})
    check("filtrado: run nuevo excluye el oculto (total=1)", st == 200 and body.get("total") == 1, f"body={body}")

    # ── T13/F5: contadores visibles — visible_problems computado dinámico;
    # la columna almacenada problem_count NO se toca. Estado: hx1 visible,
    # hx2 oculto (del bloque anterior).
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO collections (source,set_id,name,folder,num_problems) VALUES ('th',1,'ThCol','f',2)")
    con.execute("INSERT INTO chapters (id,source,set_id,chapter_num,problem_count) VALUES (901,'th',1,1,2)")
    con.execute("UPDATE problems SET chapter_id=901 WHERE source='th'")
    con.commit(); con.close()
    st, body, _ = req("/db/collections?source=th")
    col = next((c for c in body.get("collections", []) if c["set_id"] == 1), None)
    check("F5: visible_problems=1 en /db/collections (hx2 oculto)", st == 200 and col
          and col.get("visible_problems") == 1 and col.get("num_problems") == 2, f"col={col}")
    st, body, _ = req("/db/chapters?source=th&set_id=1")
    ch = next((c for c in body.get("chapters", []) if c["id"] == 901), None)
    check("F5: visible_problems=1 en /db/chapters con problem_count intacto", st == 200 and ch
          and ch.get("visible_problems") == 1 and ch.get("problem_count") == 2, f"ch={ch}")
    st, _, _ = req("/sync/push", "POST", b"{esto no es json")
    check("JSON malformado → 400", st == 400, f"st={st}")
    big = b'{"attempts": "' + b"x" * (10 * 1024 * 1024 + 100) + b'"}'
    try:
        st, _, _ = req("/sync/push", "POST", big)
        ok_413 = st == 413
    except Exception:
        # El servidor responde 413 sin leer el body y cierra: el cliente puede
        # ver la conexión cortada antes de leer la respuesta. Ambas cosas
        # significan que el límite funciona.
        ok_413 = True
    check("body >10MB rechazado", ok_413)

    # pull incluye run_uuid en attempts (para remapeo de ids en clientes nuevos)
    st, body, _ = req("/sync/pull?since_attempt_id=0&since_run_id=0")
    atts = body.get("attempts", [])
    check("pull attempts incluyen run_uuid", st == 200 and atts and all("run_uuid" in a for a in atts), f"n={len(atts)}")

    # T11-A: schema_version formal sellado tras las migraciones
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    con.close()
    # T13: la migracion v2 (problems.hidden) sella ahora schema_version=2.
    check("user_version sellado a 2 tras migrar DB legacy", uv == 2, f"uv={uv}")

    # T11-D: query params no numericos → 400 (no 500)
    st, _, _ = req("/sync/pull?since_attempt_id=abc&since_run_id=0")
    check("since_attempt_id no numerico → 400", st == 400, f"st={st}")
    st, _, _ = req("/db/last_run_stats?source=tsumego_hero&set_id=abc")
    check("set_id no numerico → 400", st == 400, f"st={st}")

    # sm2 pull con >= (registro frontera incluido)
    st, body, _ = req("/sync/sm2/pull?since=2026-07-05T09:00:00Z")
    check("sm2 pull incluye registro frontera (>=)", st == 200 and len(body.get("sm2_state", [])) == 1, f"{body}")

    # Origin no permitido en escritura → 403 (aunque no haya token)
    st, _, _ = req("/sync/check_runs", "POST", {"uuids": []}, origin="https://evil.example")
    check("Origin no permitido → 403", st == 403, f"st={st}")
    st, _, _ = req("/sync/check_runs", "POST", {"uuids": []}, origin=GH)
    check("Origin permitido → 200", st == 200, f"st={st}")

    # CORS: refleja solo orígenes permitidos
    st, _, h = req("/sync/static_version", origin=GH)
    check("CORS refleja origin permitido", h.get("Access-Control-Allow-Origin") == GH, str(h.get("Access-Control-Allow-Origin")))
    st, _, h = req("/sync/static_version", origin="https://evil.example")
    check("CORS no refleja origin ajeno", "Access-Control-Allow-Origin" not in h, str(h.get("Access-Control-Allow-Origin")))
finally:
    stop(p)

# ══ FASE B: con token ══
p = start_server({"TSUMEVAULT_TOKEN": "tok-test"})
try:
    st, _, _ = req("/sync/pull?since_attempt_id=0&since_run_id=0")
    check("GET sin token → 401", st == 401, f"st={st}")
    st, _, _ = req("/sync/pull?since_attempt_id=0&since_run_id=0", token="mal")
    check("token incorrecto → 401", st == 401, f"st={st}")
    st, body, _ = req("/sync/pull?since_attempt_id=0&since_run_id=0", token="tok-test")
    check("token correcto → 200", st == 200 and "attempts" in body, f"st={st}")
    st, _, _ = req("/sync/push", "POST", {"attempts": [], "runs": []}, token="tok-test", origin=GH)
    check("escritura con token+origin ok", st == 200, f"st={st}")
    # OPTIONS (preflight) no exige token
    r = urllib.request.Request(BASE + "/sync/push", method="OPTIONS", headers={"Origin": GH})
    with urllib.request.urlopen(r, timeout=5) as resp:
        ah = resp.headers.get("Access-Control-Allow-Headers", "")
        check("preflight sin token permitido + expone X-Auth-Token", resp.status == 200 and "X-Auth-Token" in ah, f"{resp.status} {ah}")
finally:
    stop(p)

print()
print("RESULTADO:", "TODO OK" if not FAILS else f"{len(FAILS)} FALLOS: {FAILS}")
sys.exit(1 if FAILS else 0)
