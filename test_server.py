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
    shutil.copy(os.path.join(HERE, "ai_engines.py"), TESTDIR)  # IA1
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
    # T18: los attempts que colgaban de ese run (att-new-1, att-new-2) NO se
    # borran; se desvinculan (run_id=NULL) y pasan a contar como Free Practice.
    n_att = con.execute("SELECT COUNT(*) FROM attempts WHERE uuid IN ('att-new-1','att-new-2')").fetchone()[0]
    orphan_run_ids = {r[0] for r in con.execute(
        "SELECT run_id FROM attempts WHERE uuid IN ('att-new-1','att-new-2')")}
    check("T18: attempts de run borrado (ids) no se eliminan", n_att == 2, f"n={n_att}")
    check("T18: attempts de run borrado (ids) quedan con run_id=NULL", orphan_run_ids == {None}, f"{orphan_run_ids}")
    con.close()
    st, _, _ = req("/db/runs/delete", "POST", {"uuids": ["run-dup"]})
    con = sqlite3.connect(DB)
    gone = con.execute("SELECT COUNT(*) FROM runs WHERE uuid='run-dup'").fetchone()[0]
    check("delete por uuids funciona", st == 200 and gone == 0)
    # T18: mismo comportamiento por la rama de uuids (att-dup colgaba de run-dup).
    att_dup_row = con.execute("SELECT run_id FROM attempts WHERE uuid='att-dup'").fetchone()
    check("T18: attempt de run borrado (uuids) no se elimina", att_dup_row is not None)
    check("T18: attempt de run borrado (uuids) queda con run_id=NULL",
          att_dup_row is not None and att_dup_row[0] is None, f"{att_dup_row}")
    con.close()

    # ── T19: recalculo automatico de sm2_state al borrar un run ──
    # Caso A: el problema se queda con 1 attempt 'correct' tras borrar el run
    # 600 (mas antiguo); el run 601 (se conserva) aporta el attempt que debe
    # sobrevivir en el replay. sm2_state se siembra "adelantado" (como si
    # updateSm2() hubiera corrido sobre los 3 intentos), simulando el bug real.
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES (600,'tsumego_hero','chapter','closed',2,2,'2026-08-01T10:00:00Z','run-t19-a')")
    con.execute("INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES (601,'tsumego_hero','chapter','closed',1,1,'2026-08-05T10:00:00Z','run-t19-b')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (600,'tsumego_hero','t19p1',600,'correct',900,'2026-08-01T10:00:00Z','att-t19-a1')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (601,'tsumego_hero','t19p1',600,'wrong',900,'2026-08-01T10:01:00Z','att-t19-a2')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (602,'tsumego_hero','t19p1',601,'correct',900,'2026-08-05T10:00:00Z','att-t19-b1')")
    con.execute("INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at) VALUES ('tsumego_hero','t19p1','2026-09-01',6,2.3,1,'2026-08-05T10:00:01Z')")
    con.commit(); con.close()
    st, _, _ = req("/db/runs/delete", "POST", {"uuids": ["run-t19-a"]})
    check("T19: borrado del run con historial ok", st == 200, f"st={st}")
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM sm2_state WHERE source='tsumego_hero' AND problem_id='t19p1'").fetchone()
    check("T19: sm2_state recalculado (repetitions=1, solo queda el correct de run 601)",
          row is not None and row["repetitions"] == 1, f"row={dict(row) if row else None}")
    check("T19: sm2_state recalculado (interval=6.0, primera repeticion)",
          row is not None and abs(row["interval"] - 6.0) < 0.01, f"interval={row['interval'] if row else None}")
    check("T19: sm2_state recalculado (easiness=2.5, sin fallos en el historial restante)",
          row is not None and abs(row["easiness"] - 2.5) < 0.001, f"easiness={row['easiness'] if row else None}")
    # due_date: ancla = fecha del ULTIMO intento restante (2026-08-05, NO "hoy")
    # + jitter entero en [6,14] dias (next_base=6, next_next=js_round(6*2.5)=15, span=9)
    due_ok = row is not None and "2026-08-11" <= row["due_date"] <= "2026-08-19"
    check("T19: due_date anclado en el ultimo intento restante, no en 'hoy'",
          due_ok, f"due_date={row['due_date'] if row else None}")
    con.close()

    # Caso B: el problema se queda SIN ningun attempt run_id IS NOT NULL tras
    # el borrado (era su unico run) -> sm2_state NO se toca (mismo criterio
    # que recalc_sm2.py, que simplemente nunca visita ese par).
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES (610,'tsumego_hero','chapter','closed',1,1,'2026-08-02T10:00:00Z','run-t19-c')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (610,'tsumego_hero','t19p2',610,'correct',900,'2026-08-02T10:00:00Z','att-t19-c1')")
    con.execute("INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at) VALUES ('tsumego_hero','t19p2','2026-08-20',6,2.5,1,'2026-08-02T10:00:01Z')")
    con.commit(); con.close()
    st, _, _ = req("/db/runs/delete", "POST", {"uuids": ["run-t19-c"]})
    check("T19: borrado del run sin otros attempts restantes ok", st == 200, f"st={st}")
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM sm2_state WHERE source='tsumego_hero' AND problem_id='t19p2'").fetchone()
    check("T19: sin historial restante -> sm2_state NO se toca (misma fila que antes)",
          row is not None and row["due_date"] == "2026-08-20" and row["repetitions"] == 1
          and abs(row["interval"] - 6) < 0.01 and abs(row["easiness"] - 2.5) < 0.001,
          f"row={dict(row) if row else None}")
    con.close()

    # Caso C: filtro anti-churn -- repetitions/interval/easiness YA coinciden
    # tras el borrado -> due_date NO se re-sortea (se deja una fecha imposible
    # de producir por jitter real para detectar si se toco o no).
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES (620,'tsumego_hero','chapter','closed',1,1,'2026-08-03T10:00:00Z','run-t19-d1')")
    con.execute("INSERT INTO runs (id,source,type,status,total,done,started_at,uuid) VALUES (621,'tsumego_hero','chapter','closed',1,1,'2026-08-04T10:00:00Z','run-t19-d2')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (620,'tsumego_hero','t19p3',620,'correct',900,'2026-08-03T10:00:00Z','att-t19-d1')")
    con.execute("INSERT INTO attempts (id,source,problem_id,run_id,result,time_ms,created_at,uuid) VALUES (621,'tsumego_hero','t19p3',621,'wrong',900,'2026-08-04T10:00:00Z','att-t19-d2')")
    con.execute("INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at) VALUES ('tsumego_hero','t19p3','2099-01-01',6.0,2.5,1,'2026-08-04T10:00:01Z')")
    con.commit(); con.close()
    st, _, _ = req("/db/runs/delete", "POST", {"uuids": ["run-t19-d2"]})
    check("T19: borrado del run (filtro anti-churn) ok", st == 200, f"st={st}")
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM sm2_state WHERE source='tsumego_hero' AND problem_id='t19p3'").fetchone()
    check("T19: filtro anti-churn -> due_date NO se re-sortea si repetitions/interval/easiness no cambian",
          row is not None and row["due_date"] == "2099-01-01", f"row={dict(row) if row else None}")
    con.close()

    # T19: limpieza -- estas filas de sm2_state no deben contaminar tests
    # posteriores que cuentan filas por fecha (p.ej. "sm2 pull incluye
    # registro frontera").
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM sm2_state WHERE problem_id IN ('t19p1','t19p2','t19p3')")
    con.commit(); con.close()

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
    # ── T34: /sync/chapter_visibility (push de pendientes + tabla completa) ──
    # Endpoints antiguos retirados: un cliente viejo recibe 404 (no pisa nada).
    st, _, _ = req("/sync/chapters_mostrar", "PUT", {"chapters": [{"id": 1, "mostrar": 1}]})
    check("T34: PUT /sync/chapters_mostrar retirado → 404", st == 404, f"st={st}")
    st, _, _ = req("/db/chapter/mostrar", "PUT", {"chapter_id": 1, "mostrar": 1})
    check("T34: PUT /db/chapter/mostrar retirado → 404", st == 404, f"st={st}")
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar) VALUES (801,'t34',1,1,1)")
    con.execute("INSERT INTO chapters (id,source,set_id,chapter_num,mostrar) VALUES (802,'t34',1,2,0)")
    con.commit(); con.close()
    def _vis(b): return {r["id"]: r["mostrar"] for r in b.get("chapters", [])}
    st, body, _ = req("/sync/chapter_visibility", "PUT", {"chapters": []})
    check("T34: push vacío → 200 y tabla completa (801=1, 802=0)", st == 200 and body.get("updated") == 0
          and _vis(body).get(801) == 1 and _vis(body).get(802) == 0, f"st={st} body={body}")
    st, body, _ = req("/sync/chapter_visibility", "PUT", {"chapters": [{"id": 802, "mostrar": 1}]})
    con = sqlite3.connect(DB)
    v802 = con.execute("SELECT mostrar FROM chapters WHERE id=802").fetchone()[0]
    con.close()
    check("T34: push aplica el cambio y la respuesta lo refleja", st == 200 and body.get("updated") == 1
          and v802 == 1 and _vis(body).get(802) == 1, f"st={st} body={body} v802={v802}")
    st, body, _ = req("/sync/chapter_visibility", "PUT", {"chapters": [{"id": 801, "mostrar": True}]})
    check("T34: push sin cambio real → updated=0 (bool True aceptado como 1)", st == 200 and body.get("updated") == 0
          and _vis(body).get(801) == 1, f"st={st} body={body}")
    st, body, _ = req("/sync/chapter_visibility", "PUT", {"chapters": [{"id": 99999, "mostrar": 1}]})
    con = sqlite3.connect(DB)
    n_ghost = con.execute("SELECT COUNT(*) FROM chapters WHERE id=99999").fetchone()[0]
    con.close()
    check("T34: id inexistente se ignora (no crea filas)", st == 200 and body.get("updated") == 0
          and n_ghost == 0 and 99999 not in _vis(body), f"st={st} body={body} n={n_ghost}")
    for label, bad in (("sin mostrar", {"chapters": [{"id": 801}]}),
                       ("mostrar fuera de {0,1}", {"chapters": [{"id": 801, "mostrar": 5}]}),
                       ("mostrar como texto", {"chapters": [{"id": 801, "mostrar": "1"}]}),
                       ("id no numérico", {"chapters": [{"id": "abc", "mostrar": 1}]}),
                       ("chapters no-lista", {"chapters": "no-list"})):
        st, _, _ = req("/sync/chapter_visibility", "PUT", bad)
        check(f"T34: chapter_visibility {label} → 400", st == 400, f"st={st}")
    con = sqlite3.connect(DB)
    v801 = con.execute("SELECT mostrar FROM chapters WHERE id=801").fetchone()[0]
    check("T34: los push rechazados no tocan nada (801 sigue en 1)", v801 == 1, f"v801={v801}")
    con.execute("DELETE FROM chapters WHERE source='t34'")   # limpieza: no contaminar audit (Fase C)
    con.commit(); con.close()

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
    # ── T33: static_version refleja cambios de dificultad (no solo MAX(rowid)) ──
    st, b0, _ = req("/sync/static_version")
    v0 = b0.get("version")
    check("T33: static_version baseline es entero > 0", st == 200 and isinstance(v0, int) and v0 > 0, f"b0={b0}")
    st, b1, _ = req("/sync/static_version")
    check("T33: static_version estable si no cambia nada", b1.get("version") == v0, f"v0={v0} b1={b1}")
    con = sqlite3.connect(DB)
    con.execute("UPDATE chapters SET diff_avg=1500 WHERE id=901")
    con.commit(); con.close()
    st, b2, _ = req("/sync/static_version")
    v2 = b2.get("version")
    check("T33: static_version cambia al cambiar chapters.diff_avg", v2 != v0 and isinstance(v2, int), f"v0={v0} v2={v2}")
    con = sqlite3.connect(DB)
    con.execute("UPDATE problems SET difficulty_num=1200 WHERE source='th' AND problem_id='hx1'")
    con.commit(); con.close()
    st, b3, _ = req("/sync/static_version")
    v3 = b3.get("version")
    check("T33: static_version cambia al cambiar problems.difficulty_num", v3 != v2 and v3 != v0, f"v0={v0} v2={v2} v3={v3}")
    con = sqlite3.connect(DB)
    con.execute("UPDATE chapters SET diff_avg=NULL WHERE id=901")
    con.execute("UPDATE problems SET difficulty_num=NULL WHERE source='th' AND problem_id='hx1'")
    con.commit(); con.close()
    st, b4, _ = req("/sync/static_version")
    check("T33: static_version vuelve al valor original al revertir", b4.get("version") == v0, f"v0={v0} b4={b4}")
    # ── T23: etiquetas — dominio (union), asignaciones (LWW), borrado (409 si en uso) ──
    st, body, _ = req("/sync/tags", "PUT", {"tags": ["ko", "Seki"]})
    check("T23: PUT /sync/tags crea tags y responde lista", st == 200 and body.get("added") == 2
          and sorted(t.lower() for t in body.get("tags", [])) == ["ko", "seki"], f"st={st} body={body}")
    st, body, _ = req("/sync/tags", "PUT", {"tags": ["KO"]})
    check("T23: tag duplicado por mayusculas no se crea (case-insensitive, union)", st == 200
          and body.get("added") == 0 and len(body.get("tags", [])) == 2, f"body={body}")
    st, body, _ = req("/sync/tags", "PUT", {"tags": []})
    check("T23: push vacio NO borra el dominio (union)", st == 200 and len(body.get("tags", [])) == 2, f"body={body}")
    st, _, _ = req("/sync/tags", "PUT", {"tags": "no-list"})
    check("T23: tags no-lista -> 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/tags", "PUT", {"tags": ["   "]})
    check("T23: tag vacio -> 400", st == 400, f"st={st}")
    pt = {"source": "th", "problem_id": "hx1", "tag": "ko", "active": 1, "updated_at": "2026-09-01T10:00:00Z"}
    st, body, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": [pt]})
    check("T23: push asignacion aplicada", st == 200 and body.get("applied") == 1, f"st={st} body={body}")
    st, body, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": [dict(pt, active=0, updated_at="2026-08-31T10:00:00Z")]})
    con = sqlite3.connect(DB)
    act = con.execute("SELECT active FROM problem_tags WHERE source='th' AND problem_id='hx1' AND tag='ko'").fetchone()[0]
    con.close()
    check("T23: LWW — un updated_at mas antiguo NO pisa el estado", st == 200 and body.get("applied") == 0 and act == 1, f"body={body} active={act}")
    st, body, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": [dict(pt, active=0, updated_at="2026-09-02T10:00:00Z")]})
    con = sqlite3.connect(DB)
    act = con.execute("SELECT active FROM problem_tags WHERE source='th' AND problem_id='hx1' AND tag='ko'").fetchone()[0]
    con.close()
    check("T23: LWW — un updated_at mas reciente aplica el tombstone (active=0)", st == 200 and body.get("applied") == 1 and act == 0, f"body={body} active={act}")
    st, body, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": [dict(pt, problem_id="no-existe")]})
    con = sqlite3.connect(DB)
    n_ghost = con.execute("SELECT COUNT(*) FROM problem_tags WHERE problem_id='no-existe'").fetchone()[0]
    con.close()
    check("T23: asignacion a problem inexistente se ignora (sin filas fantasma)", st == 200 and body.get("applied") == 0 and n_ghost == 0, f"body={body} n={n_ghost}")
    st, body, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": [dict(pt, problem_id="hx2", tag="tesuji", updated_at="2026-09-03T10:00:00Z")]})
    con = sqlite3.connect(DB)
    n_tag = con.execute("SELECT COUNT(*) FROM tags WHERE tag='tesuji'").fetchone()[0]
    con.close()
    check("T23: push con tag desconocido lo crea en el dominio (sin huerfanos)", st == 200 and body.get("applied") == 1 and n_tag == 1, f"body={body} n_tag={n_tag}")
    st, body, _ = req("/sync/problem_tags/pull?since=2026-09-02T10:00:00Z")
    rows = body.get("problem_tags", [])
    check("T23: pull desde cursor incluye la frontera (>=) y el tombstone", st == 200
          and any(r["problem_id"] == "hx1" and r["tag"] == "ko" and r["active"] == 0 for r in rows)
          and any(r["tag"] == "tesuji" for r in rows) and len(rows) == 2, f"rows={rows}")
    st, _, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": [{"source": "th", "tag": "ko"}]})
    check("T23: push sin campos obligatorios -> 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": [dict(pt, active=5)]})
    check("T23: push con active fuera de {0,1} -> 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/problem_tags/push", "POST", {"problem_tags": "no-list"})
    check("T23: push no-lista -> 400", st == 400, f"st={st}")
    st, body, _ = req("/sync/tags/delete", "POST", {"tag": "tesuji"})
    check("T23: borrar tag EN USO -> 409 con in_use", st == 409 and body.get("in_use") == 1, f"st={st} body={body}")
    st, body, _ = req("/sync/tags/delete", "POST", {"tag": "ko"})
    con = sqlite3.connect(DB)
    n_tag = con.execute("SELECT COUNT(*) FROM tags WHERE tag='ko'").fetchone()[0]
    n_pt = con.execute("SELECT COUNT(*) FROM problem_tags WHERE tag='ko'").fetchone()[0]
    con.close()
    check("T23: borrar tag sin asignaciones activas -> 200 y limpia sus tombstones", st == 200 and body.get("ok") is True
          and n_tag == 0 and n_pt == 0 and "ko" not in [t.lower() for t in body.get("tags", [])], f"st={st} body={body} n_tag={n_tag} n_pt={n_pt}")
    st, _, _ = req("/sync/tags/delete", "POST", {})
    check("T23: delete sin tag -> 400", st == 400, f"st={st}")
    # limpieza: no contaminar audit (Fase C) ni otros tests
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM problem_tags"); con.execute("DELETE FROM tags")
    con.commit(); con.close()

    # ── J2: progreso de josekis — tablas v4, joseki_sm2 (LWW), joseki_attempts (dedupe) ──
    con = sqlite3.connect(DB)
    jt = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    check("J2: migración legacy crea joseki_sm2 y joseki_attempts", {"joseki_sm2", "joseki_attempts"} <= jt, f"{sorted(jt)}")
    js = {"card_id": "4-4 Joseki#pd.nc#B", "due_date": "2026-10-20", "interval": 6, "easiness": 2.5,
          "repetitions": 1, "updated_at": "2026-10-14T10:00:00Z"}
    js2 = dict(js, card_id="4-4 Joseki#pd.nc#W", updated_at="2026-10-15T10:00:00Z")
    st, body, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": [js, js2]})
    check("J2: joseki_sm2 push aplica 2 registros", st == 200 and body.get("applied") == 2, f"st={st} body={body}")
    st, body, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": [dict(js, repetitions=9, updated_at="2026-10-13T10:00:00Z")]})
    con = sqlite3.connect(DB)
    reps_ = con.execute("SELECT repetitions FROM joseki_sm2 WHERE card_id=?", (js["card_id"],)).fetchone()[0]
    con.close()
    check("J2: LWW — joseki_sm2 más antiguo NO pisa", st == 200 and body.get("applied") == 0 and reps_ == 1, f"body={body} reps={reps_}")
    st, body, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": [dict(js, repetitions=2, updated_at="2026-10-16T10:00:00Z")]})
    con = sqlite3.connect(DB)
    reps_ = con.execute("SELECT repetitions FROM joseki_sm2 WHERE card_id=?", (js["card_id"],)).fetchone()[0]
    con.close()
    check("J2: LWW — joseki_sm2 más reciente aplica", st == 200 and body.get("applied") == 1 and reps_ == 2, f"body={body} reps={reps_}")
    st, body, _ = req("/sync/joseki_sm2/pull?since=2026-10-15T10:00:00Z")
    rows = body.get("joseki_sm2", [])
    check("J2: joseki_sm2 pull incluye frontera (>=) y excluye lo anterior", st == 200 and len(rows) == 2
          and {r["card_id"] for r in rows} == {js["card_id"], js2["card_id"]}, f"rows={rows}")
    st, body, _ = req("/sync/joseki_sm2/pull?since=2026-10-16T10:00:01Z")
    check("J2: joseki_sm2 pull posterior a todo → vacío (anti-vacío del anterior)", st == 200 and body.get("joseki_sm2") == [], f"{body}")
    st, _, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": [{"card_id": "x"}]})
    check("J2: joseki_sm2 push sin campos → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": [dict(js, card_id="")]})
    check("J2: joseki_sm2 push con card_id vacío → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": "no-list"})
    check("J2: joseki_sm2 push no-lista → 400", st == 400, f"st={st}")

    ja = {"uuid": "ja-1", "card_id": js["card_id"], "result": "correct", "hint": 0, "time_ms": 4200,
          "created_at": "2026-10-14T10:00:00Z"}
    ja2 = dict(ja, uuid="ja-2", result="wrong", hint=1, time_ms=None, created_at="2026-10-14T10:05:00Z")
    st, body, _ = req("/sync/joseki_attempts/push", "POST", {"joseki_attempts": [ja, ja2]})
    check("J2: joseki_attempts push inserta 2", st == 200 and body.get("inserted") == 2 and body.get("skipped") == 0, f"st={st} body={body}")
    st, body, _ = req("/sync/joseki_attempts/push", "POST", {"joseki_attempts": [ja, ja2]})
    con = sqlite3.connect(DB)
    n_ja = con.execute("SELECT COUNT(*) FROM joseki_attempts").fetchone()[0]
    con.close()
    check("J2: joseki_attempts push repetido no duplica (dedupe por uuid)", st == 200 and body.get("inserted") == 0
          and body.get("skipped") == 2 and n_ja == 2, f"body={body} n={n_ja}")
    st, body, _ = req("/sync/joseki_attempts/pull?since_id=0")
    rows = body.get("joseki_attempts", [])
    check("J2: joseki_attempts pull desde 0 devuelve ambos con hint guardado", st == 200 and len(rows) == 2
          and [r["hint"] for r in rows] == [0, 1] and rows[0]["time_ms"] == 4200 and rows[1]["time_ms"] is None, f"rows={rows}")
    last_id = rows[-1]["id"] if rows else 0
    st, body, _ = req(f"/sync/joseki_attempts/pull?since_id={last_id}")
    check("J2: joseki_attempts pull desde el último id → vacío", st == 200 and body.get("joseki_attempts") == [], f"{body}")
    st, _, _ = req("/sync/joseki_attempts/pull?since_id=abc")
    check("J2: joseki_attempts pull since_id no numérico → 400", st == 400, f"st={st}")
    for label, bad in (("result fuera de dominio", dict(ja, uuid="ja-x", result="maybe")),
                       ("hint fuera de {0,1}", dict(ja, uuid="ja-x", hint=5)),
                       ("sin uuid", {k: v for k, v in ja.items() if k != "uuid"}),
                       ("time_ms no entero", dict(ja, uuid="ja-x", time_ms="lento"))):
        st, _, _ = req("/sync/joseki_attempts/push", "POST", {"joseki_attempts": [bad]})
        check(f"J2: joseki_attempts push con {label} → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/joseki_attempts/push", "POST", {"joseki_attempts": "no-list"})
    check("J2: joseki_attempts push no-lista → 400", st == 400, f"st={st}")
    con = sqlite3.connect(DB)
    n_ja = con.execute("SELECT COUNT(*) FROM joseki_attempts").fetchone()[0]
    con.close()
    check("J2: los push rechazados no insertan nada", n_ja == 2, f"n={n_ja}")
    st, _, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": []}, origin="https://evil.example")
    check("J2: escritura joseki con Origin ajeno → 403", st == 403, f"st={st}")
    # limpieza: no contaminar audit (Fase C)
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM joseki_attempts"); con.execute("DELETE FROM joseki_sm2")
    con.commit(); con.close()
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

    # ── FC1: Focus — tablas v5, attempts.session_uuid, /sync/focus (LWW) ──
    con = sqlite3.connect(DB)
    ft = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    acols = [r[1] for r in con.execute("PRAGMA table_info(attempts)")]
    n_old_su = con.execute("SELECT COUNT(*) FROM attempts WHERE session_uuid IS NOT NULL").fetchone()[0]
    con.close()
    check("FC1: migración legacy crea focus, focus_chapters y focus_sessions",
          {"focus", "focus_chapters", "focus_sessions"} <= ft, f"{sorted(ft)}")
    check("FC1: migración añade attempts.session_uuid y los intentos previos quedan sin sesión",
          "session_uuid" in acols and n_old_su == 0, f"cols={acols} n={n_old_su}")
    fo = {"uuid": "fc1-f1", "name": "  Corner   patterns ", "archived": 0, "deleted": 0,
          "created_at": "2026-11-03T10:00:00Z", "updated_at": "2026-11-03T10:00:00Z"}
    fch = {"focus_uuid": "fc1-f1", "chapter_id": 901, "promoted": 0, "active": 1, "updated_at": "2026-11-03T10:00:01Z"}
    fse = {"uuid": "fc1-s1", "focus_uuid": "fc1-f1", "started_at": "2026-11-03T10:05:00Z", "ended_at": None,
           "completed": 0, "updated_at": "2026-11-03T10:05:00Z"}
    st, body, _ = req("/sync/focus/push", "POST", {"focus": [fo], "focus_chapters": [fch], "focus_sessions": [fse]})
    check("FC1: focus push aplica las tres tablas", st == 200
          and body.get("applied") == {"focus": 1, "focus_chapters": 1, "focus_sessions": 1}, f"st={st} body={body}")
    st, body, _ = req("/sync/focus/push", "POST", {"focus": [fo], "focus_chapters": [fch], "focus_sessions": [fse]})
    check("FC1: push repetido (mismo updated_at) no aplica nada (LWW estricto)", st == 200
          and body.get("applied") == {"focus": 0, "focus_chapters": 0, "focus_sessions": 0}, f"body={body}")
    fse_done = dict(fse, ended_at="2026-11-03T10:20:00Z", completed=1, updated_at="2026-11-03T10:20:00Z")
    st, body, _ = req("/sync/focus/push", "POST", {"focus_sessions": [fse_done]})
    check("FC1: LWW — sesión completada (más reciente) aplica", st == 200
          and body.get("applied", {}).get("focus_sessions") == 1, f"body={body}")
    st, body, _ = req("/sync/focus/push", "POST", {"focus_sessions": [fse], "focus_chapters": [dict(fch, active=0, updated_at="2026-11-03T09:00:00Z")]})
    con = sqlite3.connect(DB)
    s_row = con.execute("SELECT completed, ended_at FROM focus_sessions WHERE uuid='fc1-s1'").fetchone()
    c_row = con.execute("SELECT active FROM focus_chapters WHERE focus_uuid='fc1-f1' AND chapter_id=901").fetchone()
    con.close()
    check("FC1: LWW — filas más antiguas NO pisan (sesión sigue completada, capítulo sigue activo)",
          st == 200 and body.get("applied") == {"focus": 0, "focus_chapters": 0, "focus_sessions": 0}
          and s_row == (1, "2026-11-03T10:20:00Z") and c_row == (1,), f"body={body} s={s_row} c={c_row}")
    st, body, _ = req("/sync/focus/pull?since=1970-01-01T00:00:00Z")
    check("FC1: pull completo devuelve las tres tablas con el nombre normalizado", st == 200
          and [f["name"] for f in body.get("focus", [])] == ["Corner patterns"]
          and [c["chapter_id"] for c in body.get("focus_chapters", [])] == [901]
          and [s["completed"] for s in body.get("focus_sessions", [])] == [1], f"body={body}")
    st, body, _ = req("/sync/focus/pull?since=2026-11-03T10:20:00Z")
    check("FC1: pull desde cursor incluye la frontera (>=) y excluye lo anterior", st == 200
          and body.get("focus") == [] and body.get("focus_chapters") == []
          and [s["uuid"] for s in body.get("focus_sessions", [])] == ["fc1-s1"], f"body={body}")
    for label, bad in (("tabla no-lista", {"focus": "x"}),
                       ("flag fuera de {0,1}", {"focus": [dict(fo, archived=2)]}),
                       ("flag booleano", {"focus_chapters": [dict(fch, active=True)]}),
                       ("chapter_id no entero", {"focus_chapters": [dict(fch, chapter_id="901")]}),
                       ("nombre vacío", {"focus": [dict(fo, name="   ")]}),
                       ("nombre de más de 60", {"focus": [dict(fo, name="x" * 61)]}),
                       ("sin updated_at", {"focus_sessions": [{k: v for k, v in fse.items() if k != "updated_at"}]}),
                       ("ended_at no texto", {"focus_sessions": [dict(fse, ended_at=5)]})):
        st, _, _ = req("/sync/focus/push", "POST", bad)
        check(f"FC1: focus push con {label} → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/focus/push", "POST", {"focus": [dict(fo, uuid="fc1-f2")], "focus_chapters": [dict(fch, promoted=7)]})
    con = sqlite3.connect(DB)
    n_f2 = con.execute("SELECT COUNT(*) FROM focus WHERE uuid='fc1-f2'").fetchone()[0]
    con.close()
    check("FC1: un push con una sola fila inválida no escribe nada (validación previa)", st == 400 and n_f2 == 0, f"st={st} n={n_f2}")
    st, _, _ = req("/sync/focus/push", "POST", {"focus": []}, origin="https://evil.example")
    check("FC1: escritura focus con Origin ajeno → 403", st == 403, f"st={st}")
    att_s = {"uuid": "fc1-a1", "source": "tsumego_hero", "problem_id": 31, "result": "correct",
             "created_at": "2026-11-03T10:06:00Z", "session_uuid": "fc1-s1", "client_id": 1}
    st, body, _ = req("/sync/push", "POST", {"attempts": [att_s], "runs": []})
    check("FC1: push de attempt con session_uuid ok", st == 200 and body.get("ok"), f"st={st} body={body}")
    st, body, _ = req("/sync/pull?since_attempt_id=0&since_run_id=0")
    got = [a for a in body.get("attempts", []) if a.get("uuid") == "fc1-a1"]
    check("FC1: pull devuelve el session_uuid del attempt", got and got[0].get("session_uuid") == "fc1-s1", f"{got}")
    st, _, _ = req("/sync/push", "POST", {"attempts": [dict(att_s, uuid="fc1-a2", session_uuid=7)], "runs": []})
    check("FC1: attempt con session_uuid no texto → 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/push", "POST", {"attempts": [{k: v for k, v in att_s.items() if k != "session_uuid"} | {"uuid": "fc1-a3"}], "runs": []})
    con = sqlite3.connect(DB)
    su3 = con.execute("SELECT session_uuid FROM attempts WHERE uuid='fc1-a3'").fetchone()
    con.close()
    check("FC1: attempt sin session_uuid (cliente antiguo) se guarda con sesión NULL", st == 200 and su3 == (None,), f"st={st} row={su3}")
    # limpieza: no contaminar audit (Fase C) ni otros tests
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM focus"); con.execute("DELETE FROM focus_chapters"); con.execute("DELETE FROM focus_sessions")
    con.execute("DELETE FROM attempts WHERE uuid IN ('fc1-a1','fc1-a3')")
    con.commit(); con.close()

    # ── IA2: ai_games — tabla v6, push LWW, pull por cursor server_at, borrado lógico ──
    con = sqlite3.connect(DB)
    gcols = [r[1] for r in con.execute("PRAGMA table_info(ai_games)")]
    con.close()
    check("IA2: migración legacy crea ai_games con server_at", "uuid" in gcols and "server_at" in gcols, f"{gcols}")
    g1 = {"uuid": "ia2-g1", "played_at": "2026-11-13T18:00:00Z", "my_color": "B", "ai_level": "katago:rank_15k",
          "model": "humanv0", "handicap": 2, "rules": "japanese", "komi": 0.5, "end_type": "passes",
          "score": 12.5, "sgf": "(;GM[1]SZ[19];B[pd])", "deleted": 0, "updated_at": "2026-11-13T18:00:00Z"}
    g2 = dict(g1, uuid="ia2-g2", my_color="W", handicap=-3, end_type="resign_me", score=-0.5,
              played_at="2026-11-12T10:00:00Z", updated_at="2026-11-12T10:00:00Z")   # partida "offline" más antigua
    st, body, _ = req("/sync/ai_games/push", "POST", {"ai_games": [g1]})
    check("IA2: push aplica una partida", st == 200 and body.get("applied") == 1, f"st={st} body={body}")
    st, body, _ = req("/sync/ai_games/pull")
    rows = body.get("ai_games", [])
    cur = rows[0]["server_at"] if rows else None
    check("IA2: pull completo devuelve la partida con server_at y todos sus campos", st == 200 and len(rows) == 1
          and all(rows[0][k] == g1[k] for k in g1) and cur, f"rows={rows}")
    st, body, _ = req("/sync/ai_games/push", "POST", {"ai_games": [g1]})
    check("IA2: push repetido (mismo updated_at) no aplica (LWW estricto)", st == 200 and body.get("applied") == 0, f"{body}")
    time.sleep(1.1)
    st, body, _ = req("/sync/ai_games/push", "POST", {"ai_games": [g2]})
    st, body, _ = req(f"/sync/ai_games/pull?since={cur}")
    got = [r["uuid"] for r in body.get("ai_games", [])]
    check("IA2: una partida antigua subida tarde (offline) SÍ llega a quien ya tenía cursor (server_at)",
          "ia2-g2" in got, f"got={got}")
    check("IA2 anti-vacío: con cursor por updated_at esa partida se habría perdido", g2["updated_at"] < cur, f"{g2['updated_at']} vs {cur}")
    st, body, _ = req("/sync/ai_games/push", "POST", {"ai_games": [dict(g1, deleted=1, updated_at="2026-11-13T19:00:00Z")]})
    con = sqlite3.connect(DB)
    d1 = con.execute("SELECT deleted, sgf FROM ai_games WHERE uuid='ia2-g1'").fetchone()
    con.close()
    check("IA2: borrado lógico por LWW (deleted=1, la fila y su SGF se conservan)", st == 200
          and body.get("applied") == 1 and d1 == (1, g1["sgf"]), f"body={body} row={d1}")
    st, body, _ = req("/sync/ai_games/push", "POST", {"ai_games": [dict(g1, deleted=0, updated_at="2026-11-13T18:30:00Z")]})
    con = sqlite3.connect(DB)
    d1 = con.execute("SELECT deleted FROM ai_games WHERE uuid='ia2-g1'").fetchone()[0]
    con.close()
    check("IA2: LWW — un cambio más antiguo no resucita la partida borrada", body.get("applied") == 0 and d1 == 1, f"{body} {d1}")
    for label, bad in (("color", dict(g1, uuid="x", my_color="X")),
                       ("nivel sin motor", dict(g1, uuid="x", ai_level="rank_15k")),
                       ("handicap fuera", dict(g1, uuid="x", handicap=10)),
                       ("handicap booleano", dict(g1, uuid="x", handicap=True)),
                       ("reglas", dict(g1, uuid="x", rules="aga")),
                       ("end_type", dict(g1, uuid="x", end_type="timeout")),
                       ("score no numérico", dict(g1, uuid="x", score="12")),
                       ("sgf vacío", dict(g1, uuid="x", sgf="")),
                       ("sgf enorme", dict(g1, uuid="x", sgf="(" + "x" * 200_001)),
                       ("deleted fuera", dict(g1, uuid="x", deleted=2)),
                       ("sin updated_at", {k: v for k, v in g1.items() if k != "updated_at"} | {"uuid": "x"})):
        st, _, _ = req("/sync/ai_games/push", "POST", {"ai_games": [dict(g2, uuid="y"), bad]})
        check(f"IA2: push con {label} -> 400", st == 400, f"st={st}")
    con = sqlite3.connect(DB)
    n_xy = con.execute("SELECT COUNT(*) FROM ai_games WHERE uuid IN ('x','y')").fetchone()[0]
    con.close()
    check("IA2: un push con una fila inválida no escribe ninguna (validación previa)", n_xy == 0, f"n={n_xy}")
    st, _, _ = req("/sync/ai_games/push", "POST", {"ai_games": "no-list"})
    check("IA2: push no-lista -> 400", st == 400, f"st={st}")
    st, _, _ = req("/sync/ai_games/push", "POST", {"ai_games": []}, origin="https://evil.example")
    check("IA2: push con Origin ajeno -> 403", st == 403, f"st={st}")
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM ai_games")   # limpieza: no contaminar audit (Fase C)
    con.commit(); con.close()

    # T11-A: schema_version formal sellado tras las migraciones
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    con.close()
    # T13: la migracion v2 (problems.hidden) sellaba schema_version=2.
    # T23: la migracion v3 (tags/problem_tags) sellaba schema_version=3.
    # J2: la migracion v4 (josekis) sellaba schema_version=4.
    # FC1: la migracion v5 (Focus) sellaba schema_version=5.
    # IA2: la migracion v6 (ai_games) sella ahora schema_version=6.
    check("user_version sellado a 7 tras migrar DB legacy (AN3)", uv == 7, f"uv={uv}")

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

    # ── IA1: sin motor configurado, /ai/* responde 503 y no afecta al resto ──
    st, body, _ = req("/ai/status")
    check("IA1: /ai/status sin motor -> available=false", st == 200 and body.get("available") is False
          and body.get("levels") == [], f"st={st} body={body}")
    st, body, _ = req("/ai/move", "POST", {"level": "katago:rank_15k", "rules": "japanese", "komi": 6.5,
                                           "handicap_stones": [], "moves": [], "to_play": "B"})
    check("IA1: /ai/move sin motor -> 503", st == 503, f"st={st} body={body}")
    # ── PA6: /ai/analysis_status (validación; sin motor, todo "none") ──
    st, body, _ = req("/ai/analysis_status", "POST", {"uuids": ["no-existe", "no-existe"]})
    check("PA6: sin motor -> 200 y 'none' (uuids repetidos una vez)", st == 200 and body.get("status") == {"no-existe": {"state": "none"}}, f"st={st} {body}")
    st, body, _ = req("/ai/analysis_status", "POST", {"uuids": []})
    check("PA6: lista vacía -> status vacío", st == 200 and body.get("status") == {}, f"st={st} {body}")
    for label, bad in (("sin uuids", {}), ("uuids no-lista", {"uuids": "x"}), ("más de 200", {"uuids": [f"u{i}" for i in range(201)]}),
                       ("uuid no texto", {"uuids": [5]}), ("uuid vacío", {"uuids": [""]}), ("uuid de más de 64", {"uuids": ["x" * 65]})):
        st, _, _ = req("/ai/analysis_status", "POST", bad)
        check(f"PA6: analysis_status con {label} -> 400", st == 400, f"st={st}")
    st, _, _ = req("/ai/analysis_status", "POST", {"uuids": []}, origin="https://evil.example")
    check("PA6: analysis_status con Origin ajeno -> 403", st == 403, f"st={st}")

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

# ══ FASE C: T20 — auditoría de integridad (GET /db/audit) ══
# Se inyectan inconsistencias sintéticas DETERMINISTAS (ids 9xxx, source
# propio 'aud_src') directamente en la DB y se verifica que el endpoint las
# detecta con la severidad correcta, que es de solo lectura y que respeta auth.
con = sqlite3.connect(DB)
con.executescript("""
    -- cadena COHERENTE propia para el escenario del check 13
    INSERT INTO collections (source,set_id,name,folder) VALUES ('aud_src',9001,'AudCol','f');
    INSERT INTO chapters (id,source,set_id,chapter_num,problem_count,mostrar)
        VALUES (9001,'aud_src',9001,1,2,1);
    INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path,hidden) VALUES
        ('aud_src',9101,9001,9001,1,'p',0),
        ('aud_src',9102,9001,9001,2,'p',0);
    INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,closed_at,uuid)
        VALUES (9001,'aud_src',9001,9001,'chapter','closed',1,1,
                '2026-01-02T10:00:00Z','2026-01-02T11:00:00Z','aud-run-9001');
    INSERT INTO run_items (run_id,source,problem_id,order_in_run,result)
        VALUES (9001,'aud_src',9101,1,'correct');
    INSERT INTO attempts (source,problem_id,run_id,result,created_at,uuid) VALUES
        ('aud_src',9101,9001,'correct','2026-01-02T10:01:00Z','aud-a1'),
        ('aud_src',9101,9001,'wrong',  '2026-01-02T10:02:00Z','aud-a2'),
        ('aud_src',9101,9001,'correct','2026-01-02T10:03:00Z','aud-a3');
    -- check 13: historial correct,wrong,correct -> racha real 1; guardado 6 (mal)
    INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at)
        VALUES ('aud_src','9101','2026-06-01',595,2.5,6,'2026-01-02T10:03:00Z');
    -- check 12: easiness/repetitions imposibles (y check 11: problem inexistente)
    INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at)
        VALUES ('aud_src','9999','2026-06-01',6,0.9,-1,'2026-01-02T10:03:00Z');
    -- check 2: run_item huérfano
    INSERT INTO run_items (run_id,source,problem_id,order_in_run,result)
        VALUES (999999,'aud_src',9101,1,'correct');
    -- check 1: attempt (Free) de un problem inexistente
    INSERT INTO attempts (source,problem_id,run_id,result,created_at,uuid)
        VALUES ('aud_src',424242,NULL,'correct','2026-01-03T10:00:00Z','aud-a4');
    -- check 9c: run closed sin closed_at (total=0 para no disparar el 7 de rebote)
    INSERT INTO runs (id,source,type,status,total,done,started_at,uuid)
        VALUES (9002,'aud_src','chapter','closed',0,0,'2026-01-03T10:00:00Z','aud-run-9002');
    -- check A3: hidden=2 no debe existir nunca en servidor
    UPDATE problems SET hidden=2 WHERE source='aud_src' AND problem_id=9102;
    -- T20.1: problema con id de TEXTO (estilo many_faces) con cadena coherente:
    -- NO debe disparar el check 11 y debe salir en A10 como INFO
    INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path,hidden)
        VALUES ('aud_src','txt_p_01',9001,9001,3,'p',0);
    INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,closed_at,uuid)
        VALUES (9003,'aud_src',9001,9001,'chapter','closed',1,1,
                '2026-01-04T10:00:00Z','2026-01-04T11:00:00Z','aud-run-9003');
    INSERT INTO run_items (run_id,source,problem_id,order_in_run,result)
        VALUES (9003,'aud_src','txt_p_01',1,'correct');
    INSERT INTO attempts (source,problem_id,run_id,result,created_at,uuid)
        VALUES ('aud_src','txt_p_01',9003,'correct','2026-01-04T10:01:00Z','aud-a5');
    INSERT INTO sm2_state (source,problem_id,due_date,interval,easiness,repetitions,updated_at)
        VALUES ('aud_src','txt_p_01','2026-01-10',6,2.5,1,'2026-01-04T10:01:00Z');
    -- T20.1: item contestado SIN attempt en NINGUNA parte (check 6 = ERROR);
    -- el item huérfano de arriba (run 999999, problem 9101 con attempts) debe ir a 6c
    INSERT INTO problems (source,problem_id,set_id,chapter_id,order_in_chapter,sgf_path,hidden)
        VALUES ('aud_src',9104,9001,9001,4,'p',0);
    INSERT INTO runs (id,source,set_id,chapter_id,type,status,total,done,started_at,closed_at,uuid)
        VALUES (9004,'aud_src',9001,9001,'chapter','closed',1,1,
                '2026-01-05T10:00:00Z','2026-01-05T11:00:00Z','aud-run-9004');
    INSERT INTO run_items (run_id,source,problem_id,order_in_run,result)
        VALUES (9004,'aud_src',9104,1,'correct');
    -- T23: etiquetas — una cadena coherente (NO debe aparecer) + 3 anomalias
    INSERT INTO tags (tag, created_at) VALUES ('aud_tag','2026-01-02T10:00:00Z');
    INSERT INTO problem_tags (source,problem_id,tag,active,updated_at) VALUES ('aud_src','9101','aud_tag',1,'2026-01-02T10:00:00Z');
    INSERT INTO problem_tags (source,problem_id,tag,active,updated_at) VALUES ('aud_src','9101','tag_huerfano',1,'2026-01-02T10:00:00Z');
    INSERT INTO problem_tags (source,problem_id,tag,active,updated_at) VALUES ('aud_src','424242','aud_tag',1,'2026-01-02T10:00:00Z');
    INSERT INTO problem_tags (source,problem_id,tag,active,updated_at) VALUES ('aud_src','9102','aud_tag',5,'2026-01-02T10:00:00Z');
    -- IA2: ai_games — una coherente (NO debe aparecer) + una fuera de dominio + un abandono con signo contrario
    INSERT INTO ai_games (uuid,played_at,my_color,ai_level,model,handicap,rules,komi,end_type,score,sgf,deleted,updated_at,server_at)
        VALUES ('aud-g-ok','2026-01-02T10:00:00Z','B','katago:rank_15k','humanv0',0,'japanese',6.5,'resign_me',-0.5,'(;)',0,'2026-01-02T10:00:00Z','2026-01-02T10:00:00Z');
    INSERT INTO ai_games (uuid,played_at,my_color,ai_level,model,handicap,rules,komi,end_type,score,sgf,deleted,updated_at,server_at)
        VALUES ('aud-g-mal','2026-01-02T10:00:00Z','X','katago:rank_15k','humanv0',12,'japanese',6.5,'passes',3,'(;)',0,'2026-01-02T10:00:00Z','2026-01-02T10:00:00Z');
    INSERT INTO ai_games (uuid,played_at,my_color,ai_level,model,handicap,rules,komi,end_type,score,sgf,deleted,updated_at,server_at)
        VALUES ('aud-g-signo','2026-01-02T10:00:00Z','W','katago:max','b15c192',0,'chinese',7.5,'resign_me',4.5,'(;)',0,'2026-01-02T10:00:00Z','2026-01-02T10:00:00Z');
    -- J2: josekis — una cadena coherente (NO debe aparecer) + 3 anomalias
    INSERT INTO joseki_sm2 (card_id,due_date,interval,easiness,repetitions,updated_at)
        VALUES ('aud#ok#B','2026-01-10',6,2.5,1,'2026-01-04T10:00:00Z');
    INSERT INTO joseki_sm2 (card_id,due_date,interval,easiness,repetitions,updated_at)
        VALUES ('aud#mal#B','2026-01-10',6,0.9,1,'2026-01-04T10:00:00Z');
    INSERT INTO joseki_attempts (uuid,card_id,result,hint,created_at)
        VALUES ('aud-j1','aud#ok#B','correct',0,'2026-01-04T10:00:00Z');
    INSERT INTO joseki_attempts (uuid,card_id,result,hint,created_at)
        VALUES ('aud-j2','aud#ok#B','maybe',0,'2026-01-04T10:01:00Z');
    INSERT INTO joseki_attempts (uuid,card_id,result,hint,created_at)
        VALUES ('aud-j3','aud#huerfana#W','wrong',1,'2026-01-04T10:02:00Z');
""")
con.commit(); con.close()

p = start_server({})
try:
    st, body, _ = req("/db/audit")
    check("T20 audit → 200 con estructura completa",
          st == 200 and all(k in body for k in ("checks", "summary", "ok", "generated_at", "elapsed_ms", "db_path")),
          f"st={st} keys={sorted(body.keys())}")
    found = {str(c["id"]): c for c in body.get("checks", [])}
    def _sev(cid): return found.get(cid, {}).get("severity")
    def _cnt(cid): return found.get(cid, {}).get("count", -1)
    check("T20 detecta run_item huérfano (2=ERROR)", _sev("2") == "ERROR" and _cnt("2") >= 1, f"{found.get('2')}")
    check("T20 detecta attempt sin problem (1=WARNING)", _sev("1") == "WARNING" and _cnt("1") >= 1, f"{found.get('1')}")
    check("T20 detecta run closed sin closed_at (9c=ERROR)", _sev("9c") == "ERROR" and _cnt("9c") >= 1, f"{found.get('9c')}")
    check("T20 detecta hidden=2 en servidor (A3=ERROR)", _sev("A3") == "ERROR" and _cnt("A3") >= 1, f"{found.get('A3')}")
    check("T20 detecta repetitions desajustado (13=ERROR)", _sev("13") == "ERROR" and _cnt("13") >= 1, f"{found.get('13')}")
    ex13 = [e for e in found.get("13", {}).get("examples", []) if e.get("source") == "aud_src"]
    check("T20 ejemplo 13 autosuficiente (stored+reconstructed+historial completo)",
          bool(ex13) and "stored" in ex13[0] and "reconstructed" in ex13[0]
          and len(ex13[0].get("attempt_history", [])) == 3
          and ex13[0]["reconstructed"]["repetitions"] == 1
          and ex13[0]["stored"]["repetitions"] == 6,
          f"{ex13[:1]}")
    check("T20 detecta sm2 con valores imposibles (12=ERROR)", _sev("12") == "ERROR" and _cnt("12") >= 1, f"{found.get('12')}")
    check("T20 detecta sm2 sin problem (11=WARNING)", _sev("11") == "WARNING" and _cnt("11") >= 1, f"{found.get('11')}")
    check("T20 interval>=90 listado como investigación (15=INFO)", _sev("15") == "INFO" and _cnt("15") >= 1, f"{found.get('15')}")
    check("T20 ok=false y summary cuenta errores", body.get("ok") is False and body["summary"]["errors"] >= 5, f"{body.get('summary')}")
    # Anti-vacuo: checks sanos deben seguir en PASS pese a las inyecciones
    check("T20 anti-vacuo: uuids de attempts sin duplicar (17a=PASS)", _sev("17a") == "PASS", f"{found.get('17a')}")
    check("T20 anti-vacuo: run_items.result válidos (A9=PASS)", _sev("A9") == "PASS", f"{found.get('A9')}")
    check("T20 anti-vacuo: attempts de run con run existente (4=PASS)", _sev("4") == "PASS", f"{found.get('4')}")
    # T20.1: división del check 6 según exista el attempt en otro sitio
    check("T20.1 item con attempt en OTRO run → 6c WARNING", _sev("6c") == "WARNING" and _cnt("6c") >= 1, f"{found.get('6c')}")
    check("T20.1 item sin attempt en NINGUNA parte → 6 ERROR", _sev("6") == "ERROR" and _cnt("6") >= 1, f"{found.get('6')}")
    ex6 = found.get("6", {}).get("examples", [])
    check("T20.1 el huérfano real del 6 es el inyectado (9104)",
          any(str(e.get("problem_id")) == "9104" for e in ex6)
          and not any(str(e.get("problem_id")) == "9101" for e in ex6), f"{ex6[:3]}")
    # T20.1: ids de texto (estilo many_faces) no son huérfanos de sm2
    ex11 = found.get("11", {}).get("examples", [])
    check("T20.1 id de texto NO es huérfano sm2 (11 sin txt_p_01)",
          _cnt("11") >= 1 and not any(str(e.get("problem_id")) == "txt_p_01" for e in ex11), f"{ex11[:3]}")
    # T23: checks de etiquetas
    ex23a = found.get("T23a", {}).get("examples", [])
    check("T23 audit detecta tag huerfano (T23a=ERROR) y no marca la cadena coherente",
          _sev("T23a") == "ERROR" and any(e.get("tag") == "tag_huerfano" for e in ex23a)
          and not any(e.get("tag") == "aud_tag" for e in ex23a), f"{found.get('T23a')}")
    ex23b = found.get("T23b", {}).get("examples", [])
    check("T23 audit detecta asignacion a problem inexistente (T23b=WARNING)",
          _sev("T23b") == "WARNING" and any(str(e.get("problem_id")) == "424242" for e in ex23b)
          and not any(str(e.get("problem_id")) == "9101" for e in ex23b), f"{found.get('T23b')}")
    check("T23 audit detecta active fuera de {0,1} (T23c=ERROR)", _sev("T23c") == "ERROR" and _cnt("T23c") == 1, f"{found.get('T23c')}")
    # J2: checks de josekis
    exj2a = found.get("J2a", {}).get("examples", [])
    check("J2 audit detecta joseki_sm2 imposible (J2a=ERROR) y no marca la fila coherente",
          _sev("J2a") == "ERROR" and _cnt("J2a") == 1 and exj2a and exj2a[0].get("card_id") == "aud#mal#B", f"{found.get('J2a')}")
    exj2b = found.get("J2b", {}).get("examples", [])
    check("J2 audit detecta joseki_attempts.result fuera de dominio (J2b=ERROR)",
          _sev("J2b") == "ERROR" and _cnt("J2b") == 1 and exj2b and exj2b[0].get("uuid") == "aud-j2", f"{found.get('J2b')}")
    exj2c = found.get("J2c", {}).get("examples", [])
    check("J2 audit detecta intentos sin joseki_sm2 (J2c=WARNING) y no la tarjeta con estado",
          _sev("J2c") == "WARNING" and _cnt("J2c") == 1 and exj2c and exj2c[0].get("card_id") == "aud#huerfana#W", f"{found.get('J2c')}")
    # IA2: checks de partidas contra la IA
    exia = found.get("IA2a", {}).get("examples", [])
    check("IA2 audit detecta ai_games fuera de dominio (IA2a=ERROR) y no marca la coherente",
          _sev("IA2a") == "ERROR" and _cnt("IA2a") == 1 and exia and exia[0].get("uuid") == "aud-g-mal", f"{found.get('IA2a')}")
    exib = found.get("IA2b", {}).get("examples", [])
    check("IA2 audit detecta abandono con score de signo contrario (IA2b=WARNING)",
          _sev("IA2b") == "WARNING" and _cnt("IA2b") == 1 and exib and exib[0].get("uuid") == "aud-g-signo", f"{found.get('IA2b')}")
    # T20.3: A10 eliminado (inventario permanente sin valor; el check 11 cubre
    # cualquier huérfano real con id de texto)
    check("T20.3 el check A10 ya no existe", "A10" not in found, f"{found.get('A10')}")
    # T20.1: parámetros summary y check
    st, sm, _ = req("/db/audit?summary=1")
    check("T20.1 summary=1 → panorama sin ejemplos",
          st == 200 and sm.get("summary_only") is True and len(sm.get("checks", [])) >= 40
          and all(c["examples"] == [] for c in sm["checks"])
          and all(c["count"] >= 0 for c in sm["checks"]), f"st={st} n={len(sm.get('checks', []))}")
    st, fl, _ = req("/db/audit?check=13,6c")
    ids = sorted(str(c["id"]) for c in fl.get("checks", []))
    check("T20.1 check=13,6c filtra la lista de checks", st == 200 and ids == ["13", "6c"], f"{ids}")
    check("T20.1 el filtro no altera el summary global",
          fl.get("summary", {}).get("checks_total", 0) >= 40, f"{fl.get('summary')}")
    # Parámetros verbose / skip_integrity
    st, vb, _ = req("/db/audit?verbose=1&skip_integrity=1")
    fv = {str(c["id"]): c for c in vb.get("checks", [])}
    check("T20 skip_integrity=1 → A1 en SKIP", st == 200 and fv.get("A1", {}).get("severity") == "SKIP", f"{fv.get('A1')}")
    check("T20 verbose=1 → sin límite de ejemplos", vb.get("limit_per_check") is None and vb.get("verbose") is True, f"{vb.get('limit_per_check')}")
    # Solo lectura: el volcado lógico completo debe ser idéntico tras auditar
    def _dump():
        c = sqlite3.connect(DB); d = "\n".join(c.iterdump()); c.close(); return d
    d1 = _dump()
    req("/db/audit?verbose=1")
    d2 = _dump()
    check("T20 auditoría es de SOLO lectura (dump lógico idéntico)", d1 == d2, f"len {len(d1)} vs {len(d2)}")
finally:
    stop(p)

# Auth: /db/audit protegido por token como cualquier ruta GET
p = start_server({"TSUMEVAULT_TOKEN": "tok-test"})
try:
    st, _, _ = req("/db/audit")
    check("T20 audit sin token → 401", st == 401, f"st={st}")
    st, body, _ = req("/db/audit", token="tok-test")
    check("T20 audit con token → 200", st == 200 and "summary" in body, f"st={st}")
finally:
    stop(p)

# ══ FASE D: J2 — migración v3 -> v4 sobre una BD ya en v3, e idempotencia ══
con = sqlite3.connect(DB)
con.execute("DROP TABLE joseki_attempts"); con.execute("DROP TABLE joseki_sm2")
con.execute("PRAGMA user_version = 3")
con.commit()
jt = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
con.close()
check("J2 anti-vacío: BD simulada en v3 sin tablas de josekis", not ({"joseki_sm2", "joseki_attempts"} & jt), f"{sorted(jt)}")
p = start_server({})
try:
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    jt = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    n_tags = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    con.close()
    check("J2: v3 -> v4 crea las tablas y sella 7 (FC1 v5, IA2 v6 y AN3 v7 encadenadas)", uv == 7 and {"joseki_sm2", "joseki_attempts"} <= jt, f"uv={uv} {sorted(jt)}")
    check("J2: la migración v4 no toca datos de v3 (tags intactos)", n_tags == 1, f"n_tags={n_tags}")
    st, body, _ = req("/sync/joseki_sm2/push", "POST", {"joseki_sm2": [{"card_id": "persist#B", "due_date": "2026-11-01",
                      "interval": 6, "easiness": 2.5, "repetitions": 1, "updated_at": "2026-10-16T10:00:00Z"}]})
    check("J2: push tras migrar v3 -> v4 ok", st == 200 and body.get("applied") == 1, f"st={st} body={body}")
finally:
    stop(p)
p = start_server({})
try:
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    n = con.execute("SELECT COUNT(*) FROM joseki_sm2 WHERE card_id='persist#B'").fetchone()[0]
    con.close()
    check("J2: rearranque sobre v4 es idempotente (sella 7, conserva filas)", uv == 7 and n == 1, f"uv={uv} n={n}")
finally:
    stop(p)

# ══ FASE E: FC1 — migración v4 -> v5 sobre una BD ya en v4, e idempotencia ══
con = sqlite3.connect(DB)
con.execute("DROP TABLE focus"); con.execute("DROP TABLE focus_chapters"); con.execute("DROP TABLE focus_sessions")
con.execute("DROP INDEX IF EXISTS idx_attempts_session")
con.execute("ALTER TABLE attempts DROP COLUMN session_uuid")
con.execute("PRAGMA user_version = 4")
con.commit()
ft = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
acols = [r[1] for r in con.execute("PRAGMA table_info(attempts)")]
n_att_before = con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
con.close()
check("FC1 anti-vacío: BD simulada en v4 sin tablas de Focus ni session_uuid",
      not ({"focus", "focus_chapters", "focus_sessions"} & ft) and "session_uuid" not in acols and n_att_before > 0,
      f"{sorted(ft)} cols={acols} n={n_att_before}")
p = start_server({})
try:
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    ft = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    acols = [r[1] for r in con.execute("PRAGMA table_info(attempts)")]
    n_att = con.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    n_js = con.execute("SELECT COUNT(*) FROM joseki_sm2").fetchone()[0]
    con.close()
    check("FC1: v4 -> v5 crea las tablas de Focus y la columna, y sella 7 (IA2 y AN3 encadenadas)",
          uv == 7 and {"focus", "focus_chapters", "focus_sessions"} <= ft and "session_uuid" in acols,
          f"uv={uv} {sorted(ft)} cols={acols}")
    check("FC1: la migración v5 no toca datos previos (attempts y josekis intactos)",
          n_att == n_att_before and n_js == 1, f"att={n_att}/{n_att_before} js={n_js}")
    st, body, _ = req("/sync/focus/push", "POST", {"focus": [{"uuid": "persist-f", "name": "Persist", "archived": 0,
                      "deleted": 0, "created_at": "2026-11-03T11:00:00Z", "updated_at": "2026-11-03T11:00:00Z"}]})
    check("FC1: push tras migrar v4 -> v5 ok", st == 200 and body.get("applied", {}).get("focus") == 1, f"st={st} body={body}")
finally:
    stop(p)
p = start_server({})
try:
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    n = con.execute("SELECT COUNT(*) FROM focus WHERE uuid='persist-f'").fetchone()[0]
    con.close()
    check("FC1: rearranque sobre v5 es idempotente (sella 7, conserva filas)", uv == 7 and n == 1, f"uv={uv} n={n}")
finally:
    stop(p)

# ══ FASE H: IA2 — migración v5 -> v6 sobre una BD ya en v5, e idempotencia ══
con = sqlite3.connect(DB)
con.execute("DROP TABLE ai_games")
con.execute("PRAGMA user_version = 5")
con.commit()
gt = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
n_focus_before = con.execute("SELECT COUNT(*) FROM focus").fetchone()[0]
con.close()
check("IA2 anti-vacío: BD simulada en v5 sin ai_games", "ai_games" not in gt and n_focus_before == 1, f"{sorted(gt)} focus={n_focus_before}")
p = start_server({})
try:
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    gt = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    n_focus = con.execute("SELECT COUNT(*) FROM focus").fetchone()[0]
    con.close()
    check("IA2: v5 -> v6 crea ai_games y sella 7 (AN3 encadenada) sin tocar datos previos", uv == 7 and "ai_games" in gt and n_focus == 1,
          f"uv={uv} {sorted(gt)} focus={n_focus}")
    st, body, _ = req("/sync/ai_games/push", "POST", {"ai_games": [{"uuid": "persist-g", "played_at": "2026-11-13T18:00:00Z",
        "my_color": "B", "ai_level": "katago:max", "model": "b15c192", "handicap": 0, "rules": "chinese", "komi": 7.5,
        "end_type": "passes", "score": -3.5, "sgf": "(;)", "deleted": 0, "updated_at": "2026-11-13T18:00:00Z"}]})
    check("IA2: push tras migrar v5 -> v6 ok", st == 200 and body.get("applied") == 1, f"st={st} body={body}")
finally:
    stop(p)
p = start_server({})
try:
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    n = con.execute("SELECT COUNT(*) FROM ai_games WHERE uuid='persist-g'").fetchone()[0]
    con.close()
    check("IA2: rearranque sobre v6 es idempotente (sella 7, conserva filas)", uv == 7 and n == 1, f"uv={uv} n={n}")
finally:
    stop(p)

# ══ FASE H2: AN3 — migración v6 -> v7 (caché de análisis) ══
con = sqlite3.connect(DB)
con.execute("DROP TABLE IF EXISTS ai_analysis_cache")
con.execute("PRAGMA user_version = 6")
con.commit()
n_games = con.execute("SELECT COUNT(*) FROM ai_games").fetchone()[0]
con.close()
p = start_server({})
try:
    con = sqlite3.connect(DB)
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    tt = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    n_games2 = con.execute("SELECT COUNT(*) FROM ai_games").fetchone()[0]
    con.close()
    check("AN3: v6 -> v7 crea ai_analysis_cache y sella 7 sin tocar las partidas", uv == 7 and "ai_analysis_cache" in tt and n_games2 == n_games == 1,
          f"uv={uv} {sorted(tt)} {n_games} {n_games2}")
finally:
    stop(p)

# ══ FASE F: IA1 — /ai/* con el motor GTP falso (fake_gtp.py) ══
FAKE = os.path.join(HERE, "fake_gtp.py")
GTP_LOG = os.path.join(TESTDIR, "gtp_cmds.log")
DIE = os.path.join(TESTDIR, "gtp_die")
AI_ENV = {"KATAGO_BIN": FAKE, "KATAGO_CFG": FAKE, "KATAGO_MODEL": FAKE, "KATAGO_HUMAN_MODEL": FAKE,
          "KATAGO_LOG": os.path.join(TESTDIR, "katago_stderr.log"), "FAKE_GTP_LOG": GTP_LOG,
          "FAKE_GTP_DIE_FILE": DIE,
          "KATAGO_BACKGROUND": "0"}   # AN4: sin análisis automático en las fases F/G (se prueba en la fase I)
for f_ in (GTP_LOG, DIE):
    if os.path.exists(f_): os.remove(f_)
def gtp_cmds():
    try:
        with open(GTP_LOG, encoding="utf-8") as f: return [l.rstrip("\n") for l in f]
    except FileNotFoundError:
        return []
POS = {"rules": "japanese", "komi": 0.5, "handicap_stones": ["D4", "Q16"], "moves": [["W", "Q4"]]}
p = start_server(AI_ENV)
try:
    st, body, _ = req("/ai/status")
    lv = body.get("levels", [])
    check("IA1: status con motor -> available, niveles 20k..9d + max, aún parado",
          st == 200 and body.get("available") is True and len(lv) == 30 and lv[0] == "katago:rank_20k"
          and "katago:rank_9d" in lv and lv[-1] == "katago:max"
          and body["engines"]["katago"]["running"] is False, f"st={st} body={body}")
    check("IA1 anti-vacío: el motor no arranca hasta la primera jugada", gtp_cmds() == [], f"{gtp_cmds()}")
    for label, bad in (("nivel sin motor", dict(POS, level="rank_15k", to_play="B")),
                       ("nivel desconocido", dict(POS, level="katago:rank_25k", to_play="B")),
                       ("motor desconocido", dict(POS, level="gnugo:10", to_play="B")),
                       ("reglas", dict(POS, rules="aga", level="katago:rank_15k", to_play="B")),
                       ("komi no múltiplo de 0,5", dict(POS, komi=6.3, level="katago:rank_15k", to_play="B")),
                       ("komi booleano", dict(POS, komi=True, level="katago:rank_15k", to_play="B")),
                       ("una sola piedra de handicap", dict(POS, handicap_stones=["D4"], level="katago:rank_15k", to_play="B")),
                       ("vértice con I", dict(POS, moves=[["W", "I5"]], level="katago:rank_15k", to_play="B")),
                       ("vértice fuera (T20)", dict(POS, moves=[["W", "T20"]], level="katago:rank_15k", to_play="B")),
                       ("inyección de comando", dict(POS, moves=[["W", "D5\nquit"]], level="katago:rank_15k", to_play="B")),
                       ("color inválido", dict(POS, moves=[["X", "D5"]], level="katago:rank_15k", to_play="B")),
                       ("to_play inválido", dict(POS, level="katago:rank_15k", to_play="black")),
                       ("moves no-lista", dict(POS, moves="D5", level="katago:rank_15k", to_play="B"))):
        st, _, _ = req("/ai/move", "POST", bad)
        check(f"IA1: /ai/move con {label} -> 400", st == 400, f"st={st}")
    st, _, _ = req("/ai/score", "POST", dict(POS, mode="exact"))
    check("IA1: /ai/score con mode inválido -> 400", st == 400, f"st={st}")
    check("IA1: las peticiones inválidas no llegan al motor", gtp_cmds() == [], f"{gtp_cmds()}")

    st, body, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"))
    check("IA1: /ai/move nivel humano -> jugada legal y modelo humano", st == 200
          and body.get("move") == "D16" and body.get("model") == "humanv0" and isinstance(body.get("ms"), int),
          f"st={st} body={body}")
    c = gtp_cmds()
    seq = ["boardsize 19", "clear_board", "kata-set-rules japanese", "komi 0.5", "set_free_handicap D4 Q16",
           "play W Q4", "kata-set-param humanSLProfile rank_15k", "kata-set-param humanSLChosenMoveProp 1",
           "kata-set-param maxVisits 2", "genmove B"]
    idx = [c.index(x) if x in c else -1 for x in seq]
    check("IA1: posición reconstruida en orden (reglas antes que komi, nivel antes de genmove)",
          -1 not in idx and idx == sorted(idx) and c[0] == "protocol_version", f"idx={idx} cmds={c}")
    st, body, _ = req("/ai/status")
    check("IA1: tras jugar, el motor queda arrancado", body.get("engines", {}).get("katago", {}).get("running") is True, f"{body}")

    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/move", "POST", dict(POS, level="katago:max", to_play="B"))
    c = gtp_cmds()[n0:]
    check("IA1: /ai/move Máximo -> modelo principal, búsqueda sin humano, sin reiniciar el motor", st == 200
          and body.get("model") == "b15c192" and "kata-set-param humanSLChosenMoveProp 0" in c
          and "kata-set-param maxVisits 50" in c and not any("humanSLProfile" in x for x in c)
          and "protocol_version" not in c, f"st={st} body={body} cmds={c}")

    # ── AN1: gráfica y análisis ──
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/graph", "POST", dict(POS, moves=[["W", "Q4"], ["B", "C3"], ["W", "pass"]]))
    wl = body.get("white_leads", [])
    check("AN1: /ai/graph -> una ventaja por posición (jugadas + 1), en orden", st == 200 and wl == [-2.9, -2.4, -1.9, -1.9], f"st={st} {body}")
    c = gtp_cmds()[n0:]
    check("AN1: la gráfica evalúa antes de cada jugada y tras la última", c.count("kata-raw-nn 0") == 4 and c.index("play W Q4") > c.index("kata-raw-nn 0"), f"{c}")
    st, body, _ = req("/ai/graph", "POST", dict(POS, moves=[["W", "Q4"], ["B", "Q4"]]))
    check("AN1: /ai/graph con jugada ilegal -> 400", st == 400 and "illegal move 1" in body.get("error", ""), f"{st} {body}")
    st, body, _ = req("/ai/graph", "POST", dict(POS, moves=[["B", "pass"]] * 601))
    check("AN1: /ai/graph con más de 600 jugadas -> 400", st == 400, f"{st}")
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/analyze", "POST", dict(POS, to_play="B"))
    cands = body.get("candidates", [])
    check("AN1: /ai/analyze -> candidatas ordenadas, de la última línea info, con secuencia", st == 200 and len(cands) == 3
          and cands[0]["scoreLead"] == 3.5 and cands[0]["order"] == 0 and len(cands[0]["pv"]) == 2
          and body.get("root", {}).get("scoreLead") == 3.4 and body.get("played") is None, f"st={st} {body}")
    c = gtp_cmds()[n0:]
    check("AN1: el análisis usa la búsqueda del modelo principal con 100 visitas por defecto",
          "kata-set-param humanSLChosenMoveProp 0" in c and "kata-set-param maxVisits 100" in c
          and any(x.startswith("kata-search_analyze B") for x in c), f"{c}")
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/analyze", "POST", dict(POS, to_play="B", visits=50, played="C3"))
    pl = body.get("played") or {}
    c = gtp_cmds()[n0:]
    check("AN1: coste de la jugada hecha fuera de las candidatas (búsqueda corta tras jugarla)",
          st == 200 and pl.get("move") == "C3" and pl.get("scoreLead") == -3.4 and pl.get("loss") == 6.9
          and "play B C3" in c and "kata-set-param maxVisits 30" in c and any(x.startswith("kata-search_analyze W") for x in c), f"st={st} {body} {c}")
    st, body, _ = req("/ai/analyze", "POST", dict(POS, to_play="B", played="K10"))
    pl = body.get("played") or {}
    check("AN1: jugada hecha entre las candidatas con visitas suficientes -> usa su valor (1.2, coste 2.3)",
          st == 200 and pl.get("scoreLead") == 1.2 and pl.get("loss") == 2.3, f"{body}")
    best = (body.get("candidates") or [{}])[0].get("move")
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/analyze", "POST", dict(POS, to_play="B", played=best))
    pl = body.get("played") or {}
    check("AN1: si la jugada hecha es la mejor candidata, coste 0 sin segunda búsqueda",
          st == 200 and pl.get("loss") == 0 and sum(x.startswith("kata-search_analyze") for x in gtp_cmds()[n0:]) == 1, f"{body}")
    for label, bad in (("to_play inválido", dict(POS, to_play="X")), ("visits fuera", dict(POS, to_play="B", visits=5)),
                       ("visits booleano", dict(POS, to_play="B", visits=True)), ("played inválido", dict(POS, to_play="B", played="I5")),
                       ("played con inyección", dict(POS, to_play="B", played="D4\nquit"))):
        st, _, _ = req("/ai/analyze", "POST", bad)
        check(f"AN1: /ai/analyze con {label} -> 400", st == 400, f"st={st}")

    # ── AN3: gráfica precisa por tramos y caché en el servidor ──
    G3 = dict(POS, moves=[["W", "Q4"], ["B", "C3"], ["W", "pass"]])
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/graph", "POST", dict(G3, **{"from": 0, "to": 3}))
    c = gtp_cmds()[n0:]
    check("AN3: tramo de gráfica con búsqueda corta: ventaja de blancas según a quién le toca",
          st == 200 and body.get("white_leads") == [3.4, -3.4, 3.4, -3.4] and body.get("cached") == 0, f"st={st} {body}")
    check("AN3: una búsqueda de 16 visitas por posición, no la evaluación instantánea",
          sum(x.startswith("kata-search_analyze") for x in c) == 4 and "kata-set-param maxVisits 16" in c and "kata-raw-nn 0" not in c, f"{c}")
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/graph", "POST", dict(G3, **{"from": 1, "to": 3}))
    check("AN3: posiciones ya calculadas salen de la caché sin tocar el motor",
          st == 200 and body.get("white_leads") == [-3.4, 3.4, -3.4] and body.get("cached") == 3 and gtp_cmds()[n0:] == [], f"{body} {gtp_cmds()[n0:]}")
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/graph", "POST", dict(G3, moves=G3["moves"] + [["B", "K10"]], **{"from": 2, "to": 4}))
    check("AN3: partida que comparte el principio: solo se calcula lo nuevo",
          st == 200 and body.get("cached") == 2 and sum(x.startswith("kata-search_analyze") for x in gtp_cmds()[n0:]) == 1, f"{body}")
    st, body, _ = req("/ai/graph", "POST", dict(G3, komi=7.5, **{"from": 0, "to": 0}))
    check("AN3: otro komi es otra posición (no reutiliza la caché)", st == 200 and body.get("cached") == 0, f"{body}")
    for label, rng in (("to > jugadas", {"from": 0, "to": 4}), ("from > to", {"from": 2, "to": 1}), ("negativo", {"from": -1, "to": 1}),
                       ("más de 40 posiciones", {"from": 0, "to": 3}), ("booleano", {"from": True, "to": 2}), ("solo from", {"from": 0})):
        b = dict(G3, **rng)
        if label == "más de 40 posiciones":
            b = dict(G3, moves=[["B", "pass"], ["W", "pass"]] * 30, **{"from": 0, "to": 40})
        st, _, _ = req("/ai/graph", "POST", b)
        check(f"AN3: tramo inválido ({label}) -> 400", st == 400, f"st={st}")
    n0 = len(gtp_cmds())
    st, b1, _ = req("/ai/analyze", "POST", dict(POS, to_play="B", played="C3"))
    st2, b2, _ = req("/ai/analyze", "POST", dict(POS, to_play="B", played="C3"))
    check("AN3: el mismo análisis la segunda vez sale de la caché, idéntico y sin tocar el motor",
          st == 200 and st2 == 200 and b1.get("cached") is False and b2.get("cached") is True
          and b2.get("candidates") == b1.get("candidates") and b2.get("played") == b1.get("played")
          and sum(x.startswith("kata-search_analyze") for x in gtp_cmds()[n0:]) == 2, f"{b1} {b2}")
    st, b3, _ = req("/ai/analyze", "POST", dict(POS, to_play="B", played="R3"))
    check("AN3: otra jugada hecha es otro análisis (no reutiliza el anterior)", st == 200 and b3.get("cached") is False, f"{b3}")

    for hc, lvl, prof, label in ((-9, "rank_20k", "rank_20k_11k", "doy 9 a un 20k"),
                                (3, "rank_12k", "rank_15k_12k", "recibo 3 de un 12k"),
                                (3, "rank_18k", "rank_18k", "fuera de escala (21k) -> normal"),
                                (-4, "rank_7d", "rank_7d", "fuera de escala (11d) -> normal"),
                                (0, "rank_12k", "rank_12k", "igualada -> normal")):
        n0 = len(gtp_cmds())
        st, body, _ = req("/ai/move", "POST", dict(POS, level=f"katago:{lvl}", to_play="B", handicap=hc))
        c = gtp_cmds()[n0:]
        check(f"IA handicap: {label} -> {prof}", st == 200 and f"kata-set-param humanSLProfile {prof}" in c, f"st={st} {c}")
    for bad in (10, -10, True, "3", 1.5):
        st, _, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B", handicap=bad))
        check(f"IA handicap: valor inválido {bad!r} -> 400", st == 400, f"st={st}")

    st, body, _ = req("/ai/move", "POST", dict(POS, moves=[["W", "Q4"], ["B", "Q4"]], level="katago:rank_15k", to_play="W"))
    check("IA1: jugada ilegal en el historial -> 400 con su índice", st == 400 and "illegal move 1" in body.get("error", ""), f"st={st} body={body}")

    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/score", "POST", dict(POS, mode="final"))
    c = gtp_cmds()[n0:]
    check("IA1: /ai/score final -> resultado, score con signo y muertas", st == 200
          and body.get("result") == "W+3.5" and body.get("score_white") == 3.5
          and body.get("dead") == ["D4", "E5", "Q16"] and body.get("mode") == "final", f"st={st} body={body}")
    check("IA1: el recuento final usa la búsqueda del modelo principal",
          "kata-set-param humanSLChosenMoveProp 0" in c and c.index("kata-set-param humanSLChosenMoveProp 0") < c.index("final_score"), f"{c}")
    st, body, _ = req("/ai/score", "POST", dict(POS, mode="estimate"))
    check("IA1: /ai/score estimate -> whiteLead redondeado (B+2.4)", st == 200
          and body.get("score_white") == -2.4 and body.get("result") == "B+2.4" and body.get("dead") == [],
          f"st={st} body={body}")
    own = body.get("ownership") or []
    check("IA1: estimate devuelve el mapa de propiedad (361 valores, fila a fila desde arriba)",
          len(own) == 361 and own[0] == -0.8 and own[9] == 0.0 and own[18] == 0.9 and own[19 * 18] == -0.8,
          f"len={len(own)} {own[:20]}")

    open(DIE, "w").close()
    st, body, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"))
    check("IA1: el motor muere a mitad de jugada -> 502", st == 502, f"st={st} body={body}")
    st, body, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"))
    check("IA1: la petición siguiente relanza el motor -> 200", st == 200 and body.get("move")
          and gtp_cmds().count("protocol_version") == 2, f"st={st} body={body}")
    st, _, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"), origin="https://evil.example")
    check("IA1: /ai/move con Origin ajeno -> 403", st == 403, f"st={st}")
finally:
    stop(p)
time.sleep(0.5)
check("IA1: al parar el servidor se cierra el motor (quit)", gtp_cmds()[-1:] == ["quit"], f"{gtp_cmds()[-3:]}")

# ══ FASE G: IA1 — el motor no bloquea el sync, cierre por inactividad, token ══
if os.path.exists(GTP_LOG): os.remove(GTP_LOG)
import threading as _th
p = start_server(dict(AI_ENV, FAKE_GTP_DELAY="2.5", KATAGO_IDLE_S="2", TSUMEVAULT_TOKEN="tok-test"))
try:
    st, _, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"))
    check("IA1: /ai/move sin token -> 401", st == 401, f"st={st}")
    st, _, _ = req("/ai/analysis_status", "POST", {"uuids": []})
    check("PA6: analysis_status sin token -> 401", st == 401, f"st={st}")
    st, body, _ = req("/ai/graph", "POST", dict(POS, moves=[["W", "Q4"], ["B", "C3"], ["W", "pass"]], **{"from": 0, "to": 3}), token="tok-test")
    check("AN3: la caché sobrevive al reinicio del servidor (está en la BD)",
          st == 200 and body.get("cached") == 4 and gtp_cmds() == [], f"{body} {gtp_cmds()}")
    res = {}
    def _slow():
        res["r"] = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"), token="tok-test")
    th = _th.Thread(target=_slow); th.start()
    time.sleep(1.0)
    t0 = time.monotonic()
    st, _, _ = req("/sync/pull?since_attempt_id=0&since_run_id=0", token="tok-test")
    dt = time.monotonic() - t0
    alive = th.is_alive()
    th.join(timeout=15)
    check("IA1: un sync durante una jugada lenta no espera a la IA", st == 200 and dt < 1.0 and alive, f"st={st} dt={dt:.2f} alive={alive}")
    check("IA1 anti-vacío: la jugada lenta terminó bien", res.get("r", (0,))[0] == 200, f"{res}")
    time.sleep(4.0)
    st, body, _ = req("/ai/status", token="tok-test")
    check("IA1: el motor se cierra solo tras KATAGO_IDLE_S sin uso", body.get("engines", {}).get("katago", {}).get("running") is False
          and gtp_cmds()[-1:] == ["quit"], f"{body} {gtp_cmds()[-2:]}")
finally:
    stop(p)

# Sin ai_engines.py junto al servidor: el sync sigue funcionando y /ai/* da 503
os.remove(os.path.join(TESTDIR, "ai_engines.py"))
import shutil as _sh; _sh.rmtree(os.path.join(TESTDIR, "__pycache__"), ignore_errors=True)
p = start_server(AI_ENV)
try:
    st1, b1, _ = req("/ai/status")
    st2, _, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"))
    st3, _, _ = req("/sync/static_version")
    check("IA1: sin ai_engines.py -> /ai/status available=false, /ai/move 503 y el sync intacto",
          st1 == 200 and b1.get("available") is False and st2 == 503 and st3 == 200, f"{st1} {b1} {st2} {st3}")
    st4, _, _ = req("/ai/analysis_status", "POST", {"uuids": ["x"]})
    check("PA6: sin ai_engines.py -> analysis_status 503", st4 == 503, f"st={st4}")
finally:
    stop(p)

# ══ FASE I: AN4 — análisis automático en segundo plano y estado del servidor (ST1) ══
import json as _json
BG_ENV = dict(AI_ENV, KATAGO_BACKGROUND="1", FAKE_GTP_SEARCH_DELAY="0.25")
_sh.copy(os.path.join(HERE, "ai_engines.py"), TESTDIR)   # la fase anterior lo quitó a propósito
for f_ in (GTP_LOG, DIE):
    if os.path.exists(f_): os.remove(f_)

def poll_graph(body, timeout=20):
    t_end = time.time() + timeout
    last = None
    while time.time() < t_end:
        n = len(body["moves"])
        st, last, _ = req("/ai/graph", "POST", dict(body, **{"from": 0, "to": n, "cached_only": True}))
        if st == 200 and last.get("complete"):
            return last
        time.sleep(0.3)
    return last

p = start_server(BG_ENV)
try:
    time.sleep(1.5)   # revisión al arrancar (partidas guardadas por fases anteriores)
    st, body, _ = req("/server/status")
    ai = body.get("ai", {})
    check("ST1: /server/status responde con versión de BD, disco, memoria, caché y motor",
          st == 200 and body.get("ok") is True and body.get("schema_version") == 7 and body.get("uptime_s", -1) >= 0
          and body.get("disk", {}).get("free", 0) > 0 and "rows" in body.get("cache", {}) and ai.get("available") is True
          and ai.get("worker", {}).get("enabled") is True, f"st={st} {body}")
    GJ = {"rules": "japanese", "komi": 5.5, "handicap_stones": [], "moves": [["B", "R16"], ["W", "C4"], ["B", "pass"]]}
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/graph", "POST", dict(GJ, **{"from": 0, "to": 3, "cached_only": True}))
    check("AN4: cached_only no calcula: devuelve null donde falta y complete=false, sin tocar el motor",
          st == 200 and body.get("white_leads") == [None, None, None, None] and body.get("complete") is False
          and gtp_cmds()[n0:] == [], f"{body} {gtp_cmds()[n0:]}")
    st, body, _ = req("/ai/graph_job", "POST", dict(GJ, label="prueba"))
    check("AN4: /ai/graph_job encola la gráfica", st == 200 and body.get("enabled") is True and body.get("queued") is True, f"st={st} {body}")
    g = poll_graph(GJ)
    check("AN4: el trabajador calcula toda la gráfica en segundo plano (misma caché que los tramos)",
          g and g.get("complete") is True and g.get("white_leads") == [-3.4, 3.4, -3.4, 3.4], f"{g}")
    # AN5: tras la gráfica, el trabajador deja hechos los análisis de los errores
    t_end = time.time() + 20
    while time.time() < t_end:
        st, sb, _ = req("/server/status")
        w = sb.get("ai", {}).get("worker", {})
        if not w.get("current") and w.get("queue") == 0:
            break
        time.sleep(0.3)
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/analyze", "POST", dict(GJ, moves=[], to_play="B", played="R16"))
    check("AN5: el análisis de un error de la gráfica ya está hecho (🔍 sale de la caché, sin motor)",
          st == 200 and body.get("cached") is True and body.get("played", {}).get("move") == "R16"
          and gtp_cmds()[n0:] == [], f"st={st} {body} {gtp_cmds()[n0:]}")
    st, body, _ = req("/ai/analyze", "POST", dict(GJ, moves=GJ["moves"][:1], to_play="W", played="C4"))
    check("AN5: también el error del otro color", st == 200 and body.get("cached") is True, f"{body}")
    # solo mis errores: con mine=B, tras la gráfica se preparan los de negras y no los de blancas
    GM = {"rules": "japanese", "komi": 4.5, "handicap_stones": [], "moves": [["B", "R16"], ["W", "C4"], ["B", "R4"], ["W", "C16"]]}
    st, body, _ = req("/ai/graph_job", "POST", dict(GM, label="mías", mine="B"))
    g = poll_graph(GM)
    t_end = time.time() + 20
    while time.time() < t_end:
        st, sb, _ = req("/server/status")
        w = sb.get("ai", {}).get("worker", {})
        if not w.get("current") and w.get("queue") == 0:
            break
        time.sleep(0.3)
    n0 = len(gtp_cmds())
    st1, b1, _ = req("/ai/analyze", "POST", dict(GM, moves=GM["moves"][:2], to_play="B", played="R4"))
    n1 = len(gtp_cmds())
    st2, b2, _ = req("/ai/analyze", "POST", dict(GM, moves=GM["moves"][:1], to_play="W", played="C4"))
    check("AN5c: con mine=B se preparan los errores de negras (≥6 pts) y no los de blancas",
          g and g.get("complete") and st1 == 200 and b1.get("cached") is True and n1 == n0
          and st2 == 200 and b2.get("cached") is False, f"g={g} b1={b1.get('cached')} b2={b2.get('cached')} {gtp_cmds()[n0:]}")
    st, _, _ = req("/ai/graph_job", "POST", dict(GJ, moves=[["B", "I5"]]))
    check("AN4: /ai/graph_job con posición inválida -> 400", st == 400, f"st={st}")
    # una partida guardada por sync entra sola en la cola
    sg = {"uuid": "an4-g1", "played_at": "2026-11-15T10:00:00Z", "my_color": "B", "ai_level": "katago:rank_15k",
          "model": "humanv0", "handicap": 0, "rules": "japanese", "komi": 6.5, "end_type": "passes", "score": 3.5,
          "sgf": "(;GM[1]SZ[19]KM[6.5]RU[Japanese];B[pd];W[dp];B[pp];W[dd];B[])", "deleted": 0, "updated_at": "2026-11-15T10:00:00Z"}
    st, body, _ = req("/sync/ai_games/push", "POST", {"ai_games": [sg]})
    check("AN4: el push de la partida responde igual que siempre", st == 200 and body.get("applied") == 1, f"{st} {body}")
    GP = {"rules": "japanese", "komi": 6.5, "handicap_stones": [], "moves": [["B", "Q16"], ["W", "D4"], ["B", "Q4"], ["W", "D16"], ["B", "pass"]]}
    g = poll_graph(GP)
    check("AN4: una partida recibida por sync se analiza sola (posiciones en la caché)", g and g.get("complete") is True, f"{g}")
    # PA6: al terminar (gráfica y errores) queda la marca y el indicador dice "done"
    t_end, sa = time.time() + 20, {}
    while time.time() < t_end:
        st, body, _ = req("/ai/analysis_status", "POST", {"uuids": ["an4-g1", "no-existe"]})
        sa = body.get("status", {})
        if sa.get("an4-g1", {}).get("state") == "done":
            break
        time.sleep(0.3)
    check("PA6: partida analizada por el trabajador -> done; uuid desconocido -> none",
          st == 200 and sa.get("an4-g1") == {"state": "done"} and sa.get("no-existe") == {"state": "none"}, f"st={st} {sa}")
    # prioridad: con un análisis largo en marcha, una jugada no espera a que termine
    GL = {"rules": "japanese", "komi": 6.5, "handicap_stones": [], "moves": [["B", "pass"], ["W", "pass"]] * 20}
    req("/ai/graph_job", "POST", dict(GL, label="larga"))
    t_end, cur = time.time() + 20, None
    while time.time() < t_end:   # espera a que termine lo anterior (gráfica + errores) y empiece la larga
        st, body, _ = req("/server/status")
        cur = body.get("ai", {}).get("worker", {}).get("current")
        if cur and cur.get("label") == "larga" and cur.get("done", 0) > 0:
            break
        time.sleep(0.2)
    check("ST1: el estado muestra la partida que se está analizando y su progreso",
          cur and cur.get("label") == "larga" and 0 < cur.get("done", 0) < cur.get("total", 0) == 41, f"{body.get('ai')}")
    # PA6: una partida guardada con la misma posición que la que se está calculando -> running con progreso;
    # otra distinta, recibida mientras tanto -> queued
    long_sgf = "(;GM[1]SZ[19]KM[6.5]RU[Japanese]" + ";B[];W[]" * 20 + ")"
    gl1 = dict(sg, uuid="pa6-long", sgf=long_sgf, updated_at="2026-11-22T10:00:00Z")
    gl2 = dict(sg, uuid="pa6-next", sgf="(;GM[1]SZ[19]KM[3.5]RU[Japanese];B[pd];W[dp])", updated_at="2026-11-22T10:00:00Z")
    req("/sync/ai_games/push", "POST", {"ai_games": [gl1, gl2]})
    st, body, _ = req("/ai/analysis_status", "POST", {"uuids": ["pa6-long", "pa6-next"]})
    sl, sn = body.get("status", {}).get("pa6-long", {}), body.get("status", {}).get("pa6-next", {})
    check("PA6: la partida que se está calculando -> running, fase gráfica y progreso",
          st == 200 and sl.get("state") == "running" and sl.get("phase") == "grafica" and sl.get("total") == 41 and 0 < sl.get("done", 0) < 41, f"st={st} {sl}")
    check("PA6: una partida en espera -> queued", sn == {"state": "queued"}, f"{sn}")
    t0 = time.monotonic()
    st, body, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"))
    dt = time.monotonic() - t0
    check("AN4: una jugada con el análisis en marcha espera como mucho un turno del trabajador (< 1.5 s)",
          st == 200 and dt < 1.5, f"st={st} dt={dt:.2f}")
    st, body, _ = req("/server/status")
    check("ST1: el estado incluye el tiempo medio de las jugadas", (body.get("ai", {}).get("move_ms_avg") or -1) >= 0, f"{body.get('ai')}")
finally:
    stop(p)

# mecanismo de prioridad, en el propio proceso: el trabajador no toma el motor mientras haya
# una petición interactiva esperando (protección extra además del reparto del candado)
sys.path.insert(0, HERE)
import importlib, threading as _th2
_ae = importlib.import_module("ai_engines")
_svc = _ae.AiService(env={})
_svc._waiting = 1
_done = []
_t = _th2.Thread(target=lambda: (_svc._yield_to_interactive(), _done.append(time.monotonic())))
_t0 = time.monotonic(); _t.start(); time.sleep(0.4)
_blocked = not _done
_svc._waiting = 0; _t.join(2)
check("AN4: el trabajador espera mientras hay una petición interactiva y sigue al quedar libre",
      _blocked and _done and _done[0] - _t0 >= 0.35, f"blocked={_blocked} done={_done}")

# la clave de la caché no depende del orden de las piedras de handicap: el trabajador las lee
# del SGF (D4, Q16, Q4) y la app las manda recorriendo el tablero por columnas (D4, Q4, Q16)
_sgf_hc = "(;GM[1]FF[4]SZ[19]KM[0.5]RU[Japanese]HA[3]AB[dp][pd][pp];W[cc];B[dd])"
_pos_srv = _svc._position(dict(_ae.sgf_to_position(_sgf_hc)))
_pos_app = _svc._position({"rules": "japanese", "komi": 0.5, "handicap_stones": ["D4", "Q4", "Q16"], "moves": [["W", "C17"], ["B", "D16"]]})
_k = lambda pos: _ae.cache_key("m", "graph", pos, pos["moves"], {"visits": 16})
check("AN5b: misma posición con handicap en otro orden -> misma clave de caché (gráfica y errores del trabajador sirven a la app)",
      _pos_srv["handicap_stones"] != _pos_app["handicap_stones"] and _k(_pos_srv) == _k(_pos_app),
      f"{_pos_srv['handicap_stones']} {_pos_app['handicap_stones']}")
check("AN5b: posiciones distintas siguen dando claves distintas",
      _k(_pos_srv) != _k(dict(_pos_app, handicap_stones=["D4", "Q4", "D16"])))

# PA6: estado sin servidor (caché en memoria): marca de los dos colores sirve para mine; SGF ilegible -> none
class _MemCache:
    def __init__(self): self.d = {}
    def get(self, k): return self.d.get(k)
    def get_many(self, ks): return {k: self.d[k] for k in ks if k in self.d}
    def put(self, k, kind, params, res): self.d[k] = res
_svc3 = _ae.AiService(env={"KATAGO_BACKGROUND": "0"}, cache=_MemCache())
_sgf3 = "(;GM[1]SZ[19]KM[6.5]RU[Japanese];B[pd];W[dp];B[pp])"
_pos3 = _svc3._position(dict(_ae.sgf_to_position(_sgf3)))
check("PA6 anti-vacío: sin marca -> none", _svc3.analysis_status([("u1", _sgf3, "B")]) == {"u1": {"state": "none"}})
_svc3.cache.put(_svc3.worker.done_key(_pos3, None), "graph_done", {}, {"at": "x"})
check("PA6: la marca de una partida analizada para los dos colores vale para mine=B",
      _svc3.analysis_status([("u1", _sgf3, "B"), ("u2", "(;GM[1]SZ[13];B[aa])", "B"), ("u3", "no es sgf", "W")])
      == {"u1": {"state": "done"}, "u2": {"state": "none"}, "u3": {"state": "none"}})
_svc4 = _ae.AiService(env={"KATAGO_BACKGROUND": "0"}, cache=_MemCache())
_svc4.cache.put(_svc4.worker.done_key(_pos3, "W"), "graph_done", {}, {"at": "x"})
check("PA6: la marca de 'solo blancas' no vale para negras", _svc4.analysis_status([("u1", _sgf3, "B")]) == {"u1": {"state": "none"}}
      and _svc4.analysis_status([("u1", _sgf3, "W")]) == {"u1": {"state": "done"}})
_jid = _ae.cache_key(_svc4._model_id(), "graph_job", _pos3, _pos3["moves"], {"visits": _ae.AN_GRAPH_VISITS})
_svc4.worker.ids.add(_jid)
check("PA6: en la cola del trabajador -> queued (antes que la marca)", _svc4.analysis_status([("u1", _sgf3, "W")]) == {"u1": {"state": "queued"}})

# reinicio: la revisión al arrancar encola las partidas guardadas y las ya analizadas salen de la caché
p = start_server(BG_ENV)
try:
    t_end, ok = time.time() + 10, False
    while time.time() < t_end and not ok:
        st, body, _ = req("/server/status")
        w = body.get("ai", {}).get("worker", {})
        ok = w.get("done_today", 0) >= 1
        time.sleep(0.3)
    check("AN4: al arrancar, el servidor revisa las partidas guardadas (done_today >= 1)", ok, f"{body.get('ai')}")
finally:
    stop(p)

# interruptor: KATAGO_BACKGROUND=0 apaga el análisis automático
p = start_server(dict(BG_ENV, KATAGO_BACKGROUND="0"))
try:
    st, body, _ = req("/ai/graph_job", "POST", dict(GJ, label="x"))
    st2, b2, _ = req("/sync/ai_games/push", "POST", {"ai_games": [dict(sg, uuid="an4-g2", updated_at="2026-11-15T11:00:00Z")]})
    st3, b3, _ = req("/server/status")
    w = b3.get("ai", {}).get("worker", {})
    check("AN4: con KATAGO_BACKGROUND=0 no se encola nada y la app sabe que debe calcular por tramos",
          st == 200 and body.get("enabled") is False and st2 == 200 and w.get("enabled") is False and w.get("queue") == 0 and not w.get("current"),
          f"{body} {b3.get('ai')}")
finally:
    stop(p)

# ══ FASE M: motores rivales extra por configuración (ai_engines.json, GtpDriver) ══
import logging as _logging
_logging.disable(_logging.WARNING)   # los avisos de entradas no válidas son lo esperado aquí
_cfg_dir = os.path.join(TESTDIR, "cfg_unit")
os.makedirs(_cfg_dir, exist_ok=True)
def _load(obj, raw=None):
    path = os.path.join(_cfg_dir, "ai_engines.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw if raw is not None else json.dumps(obj))
    return _ae.load_gtp_drivers(path)
_ok = {"name": "gnugo", "level": "10", "label": "GNU Go 10", "argv": ["/usr/games/gnugo", "--mode", "gtp"]}
check("M: sin fichero -> ningún motor extra", _ae.load_gtp_drivers(os.path.join(_cfg_dir, "no_existe.json")) == [])
check("M: JSON roto -> ningún motor extra", _load(None, raw="{engines: [") == [])
check("M: sin lista 'engines' -> ningún motor extra", _load({"motores": [_ok]}) == [] and _load([_ok]) == [])
_ds = _load({"_comment": "x", "engines": [
    dict(_ok, _nota="comentario"),
    dict(_ok, name="Bad Name"), dict(_ok, name="katago"), dict(_ok),                  # nombre: formato, reservado, repetido
    dict(_ok, name="a1", level="10:x"), dict(_ok, name="a2", label=""), dict(_ok, name="a3", label="x" * 41),
    dict(_ok, name="a4", argv=[]), dict(_ok, name="a5", argv="gnugo"), dict(_ok, name="a6", argv=["gnugo", ""]),
    dict(_ok, name="a7", rules_cmd="go_rules japanese"), dict(_ok, name="a8", extra=1), "no es objeto",
    dict(_ok, name="fuego", level="sims_3000", label=" Fuego ", rules_cmd="go_rules {rules}")]})
check("M: solo las entradas válidas, en orden; '_' ignoradas, etiqueta recortada",
      [(d.name, d.level, d.label) for d in _ds] == [("gnugo", "10", "GNU Go 10"), ("fuego", "sims_3000", "Fuego")],
      f"{[(d.name, d.level, d.label) for d in _ds]}")
check("M anti-vacío: cada entrada inválida falla sola (con su nombre válido sí carga)",
      [d.name for d in _load({"engines": [dict(_ok, name="a7", rules_cmd="go_rules {rules}"), dict(_ok, name="a2")]})] == ["a7", "a2"])
_g = _ds[0]
check("M: GtpDriver -> un nivel, etiqueta, modelo = nombre del motor, argv tal cual",
      _g.levels() == ["10"] and _g.labels() == {"gnugo:10": "GNU Go 10"} and _g.model_for("10") == "gnugo"
      and _g.argv() == ["/usr/games/gnugo", "--mode", "gtp"])
check("M: ejecutable inexistente -> no disponible", _ae.GtpDriver("x", "1", "X", ["/no/existe/x"]).unavailable_reason() == "executable not found")
check("M: ejecutable en el PATH o relativo al json -> disponible; .py con el Python actual",
      _ae.GtpDriver("x", "1", "X", ["python3"]).unavailable_reason() is None
      and _ae.GtpDriver("x", "1", "X", ["fake_gtp.py"], base_dir=HERE).unavailable_reason() is None
      and _ae.GtpDriver("x", "1", "X", ["fake_gtp.py", "-q"], base_dir=HERE).argv() == [sys.executable, FAKE, "-q"])

# servidor con dos motores extra (falsos) y uno sin ejecutable
EXTRA_JSON = os.path.join(TESTDIR, "extra_engines.json")
import shutil as _sh; _sh.copy(FAKE, os.path.join(TESTDIR, "fake_gtp.py"))
with open(EXTRA_JSON, "w", encoding="utf-8") as f:
    json.dump({"engines": [
        {"name": "gnugo", "level": "10", "label": "GNU Go 10", "argv": [FAKE, "--mode", "gtp", "--level", "10"]},
        {"name": "fuego", "level": "x", "label": "Fuego", "argv": ["fake_gtp.py"], "rules_cmd": "go_rules {rules}"},
        {"name": "pachi", "level": "x", "label": "Pachi", "argv": ["/no/existe/pachi"]},
        {"name": "Roto", "level": "x", "label": "Roto", "argv": [FAKE]}]}, f)
M_ENV = dict(AI_ENV, AI_ENGINES_JSON=EXTRA_JSON)
if os.path.exists(GTP_LOG): os.remove(GTP_LOG)
p = start_server(M_ENV)
try:
    st, body, _ = req("/ai/status")
    lv, en = body.get("levels", []), body.get("engines", {})
    check("M: status -> 30 niveles de KataGo y detrás los extra disponibles, con sus etiquetas",
          st == 200 and body.get("available") is True and len(lv) == 32 and lv[29] == "katago:max"
          and lv[30:] == ["gnugo:10", "fuego:x"] and body.get("labels") == {"gnugo:10": "GNU Go 10", "fuego:x": "Fuego"},
          f"st={st} {body}")
    check("M: motor sin ejecutable -> no disponible y fuera de la lista; la entrada inválida ni aparece",
          en.get("pachi", {}).get("available") is False and en["pachi"].get("reason") == "executable not found"
          and "pachi:x" not in lv and "Roto" not in en and set(en) == {"katago", "gnugo", "fuego", "pachi"}, f"{en}")
    st, body, _ = req("/ai/move", "POST", dict(POS, level="gnugo:10", to_play="B", handicap=5))
    c = gtp_cmds()
    seq = ["protocol_version", "boardsize 19", "clear_board", "komi 0.5", "set_free_handicap D4 Q16", "play W Q4", "genmove B"]
    check("M: /ai/move gnugo:10 -> jugada del motor extra, modelo 'gnugo'", st == 200 and body.get("move") == "D16"
          and body.get("model") == "gnugo" and body.get("level") == "gnugo:10", f"st={st} {body}")
    check("M: GNU Go recibe solo GTP estándar, en orden, sin kata-* (el handicap con signo no le llega)",
          c == seq, f"{c}")
    st, body, _ = req("/ai/status")
    en = body.get("engines", {})
    check("M: arranca solo el motor extra; KataGo sigue parado", en["gnugo"]["running"] is True and en["katago"]["running"] is False, f"{en}")
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/move", "POST", dict(POS, rules="chinese", level="fuego:x", to_play="B"))
    c = gtp_cmds()[n0:]
    check("M: rules_cmd -> reglas antes que el komi; ejecutable relativo al json",
          st == 200 and body.get("model") == "fuego" and "go_rules chinese" in c and c.index("go_rules chinese") < c.index("komi 0.5")
          and not any(x.startswith("kata-") for x in c), f"st={st} {body} {c}")
    st, _, _ = req("/ai/move", "POST", dict(POS, level="pachi:x", to_play="B"))
    check("M: motor extra no disponible -> 503", st == 503, f"st={st}")
    st, _, _ = req("/ai/move", "POST", dict(POS, level="gnugo:11", to_play="B"))
    check("M: nivel que el motor extra no tiene -> 400", st == 400, f"st={st}")
    n0 = len(gtp_cmds())
    st, body, _ = req("/ai/score", "POST", dict(POS, mode="final"))
    c = gtp_cmds()[n0:]
    check("M: el recuento lo hace KataGo", st == 200 and body.get("result") == "W+3.5" and "kata-set-rules japanese" in c
          and "final_score" in c, f"st={st} {body} {c}")
    st, body, _ = req("/ai/status")
    check("M: cada motor en su proceso (KataGo y GNU Go arrancados a la vez)",
          body["engines"]["katago"]["running"] is True and body["engines"]["gnugo"]["running"] is True, f"{body['engines']}")
finally:
    stop(p)

# json roto: el servidor arranca y KataGo sigue igual
with open(EXTRA_JSON, "w", encoding="utf-8") as f: f.write("{roto")
p = start_server(M_ENV)
try:
    st, body, _ = req("/ai/status")
    st2, b2, _ = req("/ai/move", "POST", dict(POS, level="katago:rank_15k", to_play="B"))
    check("M: ai_engines.json roto -> solo KataGo, que juega igual", st == 200 and len(body.get("levels", [])) == 30
          and body.get("labels") == {} and set(body.get("engines", {})) == {"katago"} and st2 == 200, f"{body} {st2}")
finally:
    stop(p)

# sin KataGo no se ofrece ningún rival (no habría recuento)
with open(EXTRA_JSON, "w", encoding="utf-8") as f:
    json.dump({"engines": [{"name": "gnugo", "level": "10", "label": "GNU Go 10", "argv": [FAKE]}]}, f)
p = start_server({"AI_ENGINES_JSON": EXTRA_JSON, "KATAGO_BACKGROUND": "0"})
try:
    st, body, _ = req("/ai/status")
    st2, _, _ = req("/ai/move", "POST", dict(POS, level="gnugo:10", to_play="B"))
    check("M: sin KataGo -> no disponible, sin niveles, y GNU Go responde 503",
          st == 200 and body.get("available") is False and body.get("levels") == [] and body["engines"]["gnugo"]["available"] is True
          and st2 == 503, f"{body} {st2}")
finally:
    stop(p)
_logging.disable(_logging.NOTSET)

print()
print("RESULTADO:", "TODO OK" if not FAILS else f"{len(FAILS)} FALLOS: {FAILS}")
sys.exit(1 if FAILS else 0)
