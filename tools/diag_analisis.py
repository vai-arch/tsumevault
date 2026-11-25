#!/usr/bin/env python3
"""diag_analisis.py — diagnóstico de solo lectura de la caché de análisis (AN4/AN5).
Uso en el VPS:  cd /opt/tsumevault && python3 diag_analisis.py [nº de partidas, por defecto 3]
Para cada partida reciente: cuántas posiciones de la gráfica hay en caché, cuántos errores
(>= 5 pts) salen y cuáles tienen ya su análisis 🔍 guardado (con la clave actual y con la
antigua, sin ordenar las piedras de handicap). No escribe nada."""
import inspect, json, hashlib, os, re, sqlite3, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRV = os.path.join(os.path.dirname(_HERE), "server")
SERVER_DIR = _SRV if os.path.isdir(_SRV) else _HERE   # en el VPS se copia junto al servidor
sys.path.insert(0, SERVER_DIR)
import ai_engines as ae

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
conf = "/etc/systemd/system/tsumevault.service.d/katago.conf"
model = os.path.basename(os.environ.get("KATAGO_MODEL") or re.search(r"KATAGO_MODEL=([^\s\"]+)", open(conf).read()).group(1))
print("modelo:", model, "· clave con handicap ordenado:", "sorted(" in inspect.getsource(ae.cache_key))

def key(kind, pos, moves, params, sort_hc):
    hc = sorted(pos["handicap_stones"]) if sort_hc else list(pos["handicap_stones"])
    blob = json.dumps({"v": ae.AN_CACHE_VERSION, "model": model, "kind": kind, "rules": pos["rules"],
                       "komi": pos["komi"], "hc": hc, "moves": moves, "params": params},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

con = sqlite3.connect("file:" + os.path.join(SERVER_DIR, "tsumeVault.db") + "?mode=ro", uri=True)
def get(k):
    r = con.execute("SELECT result, created_at FROM ai_analysis_cache WHERE key=?", (k,)).fetchone()
    return (json.loads(r[0]), r[1]) if r else (None, None)

tot = con.execute("SELECT kind, COUNT(*), MAX(created_at) FROM ai_analysis_cache GROUP BY kind").fetchall()
print("caché:", ", ".join(f"{k}={c} (último {m})" for k, c, m in tot))
for uuid, played, level, hc, sgf, mine in con.execute(
        "SELECT uuid, played_at, ai_level, handicap, sgf, my_color FROM ai_games WHERE deleted=0 ORDER BY played_at DESC LIMIT ?", (N,)).fetchall():
    print(f"\n== {played} {level} H{hc} ({uuid[:8]})")
    try:
        pos = ae.AiService._position(dict(ae.sgf_to_position(sgf)))
    except Exception as e:
        print("   no se puede leer el SGF:", e); continue
    n = len(pos["moves"])
    print(f"   {n} jugadas · handicap {pos['handicap_stones']} · komi {pos['komi']} · {pos['rules']}")
    for sort_hc in (True, False):
        leads = {}
        for i in range(n + 1):
            r, _ = get(key("pos_eval", pos, pos["moves"][:i], {"visits": ae.AN_GRAPH_VISITS}, sort_hc))
            if r is not None:
                leads[i] = r["white_lead"]
        label = "clave nueva" if sort_hc else "clave antigua"
        if not pos["handicap_stones"] and not sort_hc:
            continue
        print(f"   [{label}] gráfica: {len(leads)}/{n + 1} posiciones")
        if len(leads) < n + 1:
            continue
        errs = sorted([e for e in ae.graph_mistakes(pos, leads) if pos["moves"][e[0] - 1][0] == mine], key=lambda x: -x[1])
        have, missing = [], []
        for i, loss in errs:
            color, vertex = pos["moves"][i - 1]
            params = {"visits": ae.AN_VISITS_DEFAULT, "to_play": color, "played": vertex}
            r, when = get(key("analyze", pos, pos["moves"][:i - 1], params, sort_hc))
            (have if r is not None else missing).append((i, round(loss, 1), color, when))
        print(f"   [{label}] tus errores (≥ {ae.AN_PRE_MISTAKE + 0.05:g} pts, juegas con {mine}): {len(errs)} · con 🔍 guardado: {len(have)}")
        if have:
            print("      guardados (jugada, pérdida, color, cuándo):", have[:10], "…" if len(have) > 10 else "")
        if missing:
            print("      SIN guardar:", missing[:15], "…" if len(missing) > 15 else "")
