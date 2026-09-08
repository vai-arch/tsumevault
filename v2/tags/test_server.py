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
    # T13: la migracion v2 (problems.hidden) sellaba schema_version=2.
    # T23: la migracion v3 (tags/problem_tags) sella ahora schema_version=3.
    check("user_version sellado a 3 tras migrar DB legacy", uv == 3, f"uv={uv}")

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

print()
print("RESULTADO:", "TODO OK" if not FAILS else f"{len(FAILS)} FALLOS: {FAILS}")
sys.exit(1 if FAILS else 0)
