"""
ai_engines.py — Motores de Go para jugar contra la IA en TsumeVault (IA1).

Tres piezas:
  - GtpEngine: proceso GTP genérico (lanzar, enviar comando, leer respuesta,
    cerrar). No sabe nada de ningún motor concreto.
  - Drivers: lo específico de cada motor. Hoy solo KataGoDriver; añadir otro
    motor (p. ej. GNU Go) es escribir su driver y registrarlo en AiService.
  - AiService: valida las peticiones de /ai/*, elige motor por el prefijo del
    nivel ("katago:rank_15k"), reconstruye la posición en cada petición y
    cierra los motores tras un rato sin uso.

El recuento lo hace SIEMPRE KataGo, sea cual sea el rival.

Configuración por variables de entorno (si falta algo, /ai/* responde 503 y el
resto del servidor funciona igual):
    KATAGO_BIN          ejecutable (un .py se lanza con el Python actual: tests)
    KATAGO_CFG          config GTP (en el VPS: /opt/katago-models/tv_human.cfg)
    KATAGO_MODEL        modelo principal (g170e-b15c192...)
    KATAGO_HUMAN_MODEL  modelo humano (b18c384nbt-humanv0...)
    KATAGO_IDLE_S       segundos sin uso antes de cerrar el proceso (900)
    KATAGO_LOG          fichero para el stderr del motor (opcional)
"""

import collections
import hashlib
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time

log = logging.getLogger("tsumevault.ai")

VERTEX_RE = re.compile(r"^[A-HJ-T](1[0-9]|[1-9])$")
MAX_MOVES = 1000

START_TIMEOUT_S = 90.0     # carga de modelos
CMD_TIMEOUT_S = 15.0       # comandos de preparación (play, komi...)
GENMOVE_TIMEOUT_S = 60.0
SCORE_TIMEOUT_S = 60.0
LOCK_WAIT_S = 120.0        # espera máxima si otra petición está usando el motor


class AiError(Exception):
    """Error con código HTTP (400 petición inválida, 502 motor caído,
    503 no disponible/ocupado, 504 timeout)."""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


# ── Proceso GTP genérico ─────────────────────────────────────────────────────


class GtpEngine:
    def __init__(self, name, argv, log_path=None):
        self.name = name
        self.argv = argv
        self.log_path = log_path
        self.proc = None
        self.lines = None
        self.lock = threading.Lock()   # una conversación GTP a la vez
        self.last_used = 0.0
        self._log_fh = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def _start(self):
        if self.log_path:
            try:
                if os.path.getsize(self.log_path) > 5 * 1024 * 1024:
                    os.remove(self.log_path)   # rotación mínima
            except OSError:
                pass
            self._log_fh = open(self.log_path, "ab")
        # stderr NUNCA a un pipe sin leer: si se llena, el motor se bloquea
        err = self._log_fh if self._log_fh else subprocess.DEVNULL
        log.info("[ai] arrancando motor %s", self.name)
        self.proc = subprocess.Popen(
            self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        self.lines = queue.Queue()
        threading.Thread(target=self._reader, args=(self.proc, self.lines), daemon=True).start()
        # Primer comando: espera a que el motor termine de cargar los modelos
        self._send("protocol_version", START_TIMEOUT_S)

    @staticmethod
    def _reader(proc, q):
        try:
            for line in proc.stdout:
                q.put(line.rstrip("\r\n"))
        finally:
            q.put(None)   # EOF: el proceso ha muerto

    def _send(self, cmd, timeout):
        if "\n" in cmd or "\r" in cmd:
            raise AiError(400, "invalid command")   # nunca debería pasar: se valida antes
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            self.close()
            raise AiError(502, "engine not running")
        deadline = time.monotonic() + timeout
        out = []
        while True:
            left = deadline - time.monotonic()
            try:
                if left <= 0:
                    raise queue.Empty
                line = self.lines.get(timeout=left)
            except queue.Empty:
                log.warning("[ai] timeout en %r: se mata el motor", cmd.split(" ")[0])
                self.close()
                raise AiError(504, "engine timeout")
            if line is None:
                log.warning("[ai] el motor %s se cerró durante %r", self.name, cmd.split(" ")[0])
                self.close()
                raise AiError(502, "engine died")
            if not out and line == "":
                continue           # líneas en blanco sueltas antes de la respuesta
            if line == "":
                break              # fin de la respuesta GTP
            out.append(line)
        head = out[0]
        ok = head.startswith("=")
        if not ok and not head.startswith("?"):
            self.close()
            raise AiError(502, "bad gtp response")
        text = "\n".join([head[1:].strip()] + out[1:]).strip()
        return ok, text

    def command(self, cmd, timeout=CMD_TIMEOUT_S):
        """Envía un comando; arranca el motor si hace falta. Devuelve (ok, texto).
        Debe llamarse con self.lock tomado."""
        if not self.running():
            self.close()
            self._start()
        self.last_used = time.monotonic()
        try:
            return self._send(cmd, timeout)
        finally:
            self.last_used = time.monotonic()

    def must(self, cmd, timeout=CMD_TIMEOUT_S):
        ok, text = self.command(cmd, timeout)
        if not ok:
            raise AiError(502, f"engine rejected {cmd.split(' ')[0]}: {text}")
        return text

    def close(self):
        p, self.proc = self.proc, None
        if p is not None:
            try:
                if p.poll() is None:
                    try:
                        p.stdin.write("quit\n")
                        p.stdin.flush()
                    except (OSError, ValueError):
                        pass
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait(timeout=3)
            except Exception:
                log.exception("[ai] error cerrando %s", self.name)
            log.info("[ai] motor %s cerrado", self.name)
        if self._log_fh:
            try:
                self._log_fh.close()
            except OSError:
                pass
            self._log_fh = None


# ── Drivers ──────────────────────────────────────────────────────────────────


def _rank_idx(level):
    """'rank_20k' -> 0 … 'rank_1k' -> 19, 'rank_1d' -> 20 … 'rank_9d' -> 28; None si no es un rango."""
    m = re.match(r"^rank_(\d+)([kd])$", level or "")
    if not m:
        return None
    n = int(m.group(1))
    if m.group(2) == "k":
        return 20 - n if 1 <= n <= 20 else None
    return 19 + n if 1 <= n <= 9 else None


def _rank_txt(i):
    return f"{20 - i}k" if i < 20 else f"{i - 19}d"


def handicap_profile(level, handicap):
    """Perfil del modelo humano para una partida con handicap (WORKPLAN_IA, 14-nov).

    handicap con signo desde el jugador: +N recibe (el jugador, negras, es N rangos más
    débil que la IA), -N da (la IA, negras, es N rangos más débil que el jugador).
    Devuelve 'rank_{negras}_{blancas}': imita a esos dos rangos jugando entre sí y
    sabiéndolo (entrenado con partidas reales con handicap). En igualadas, o si el
    rango implícito se sale de la escala 20k..9d, devuelve el perfil normal.
    """
    i = _rank_idx(level)
    if i is None or not handicap:
        return level
    b, w = (i - handicap, i) if handicap > 0 else (i, i - handicap)
    if b < 0 or w > 28:
        return level
    return f"rank_{_rank_txt(b)}_{_rank_txt(w)}"


def _rank_levels():
    return [f"rank_{k}k" for k in range(20, 0, -1)] + [f"rank_{d}d" for d in range(1, 10)]


class KataGoDriver:
    name = "katago"
    model_human = "humanv0"
    model_max = "b15c192"

    # Valores de gtp_human5k_example.cfg (niveles humanos) y gtp_example.cfg ("Máximo").
    # Se fijan TODOS antes de cada genmove: nunca se hereda lo de la petición anterior.
    HUMAN_PARAMS = (("humanSLChosenMoveProp", "1"), ("maxVisits", "2"),
                    ("chosenMoveTemperatureEarly", "0.85"), ("chosenMoveTemperature", "0.70"))
    MAX_PARAMS = (("humanSLChosenMoveProp", "0"), ("maxVisits", "50"),
                  ("chosenMoveTemperatureEarly", "0.5"), ("chosenMoveTemperature", "0.10"))

    def __init__(self, env):
        self.bin = env.get("KATAGO_BIN", "").strip()
        self.cfg = env.get("KATAGO_CFG", "").strip()
        self.model = env.get("KATAGO_MODEL", "").strip()
        self.human = env.get("KATAGO_HUMAN_MODEL", "").strip()

    def unavailable_reason(self):
        for var, path in (("KATAGO_BIN", self.bin), ("KATAGO_CFG", self.cfg),
                          ("KATAGO_MODEL", self.model), ("KATAGO_HUMAN_MODEL", self.human)):
            if not path:
                return f"{var} not set"
            if not os.path.isfile(path):
                return f"{var} not found"
        return None

    def argv(self):
        base = [sys.executable, self.bin] if self.bin.endswith(".py") else [self.bin]
        return base + ["gtp", "-config", self.cfg, "-model", self.model, "-human-model", self.human]

    def levels(self):
        return _rank_levels() + ["max"]

    def model_for(self, level):
        return self.model_max if level == "max" else self.model_human

    def set_position(self, eng, pos):
        eng.must("boardsize 19")
        eng.must("clear_board")
        eng.must(f"kata-set-rules {pos['rules']}")
        eng.must(f"komi {pos['komi']}")   # después de las reglas: cambiarlas toca el komi (IA0)
        if pos["handicap_stones"]:
            eng.must("set_free_handicap " + " ".join(pos["handicap_stones"]))
        for i, (color, vertex) in enumerate(pos["moves"]):
            ok, text = eng.command(f"play {color} {vertex}")
            if not ok:
                raise AiError(400, f"illegal move {i}: {color} {vertex}")

    def set_level(self, eng, level, handicap=0):
        if level == "max":
            params = self.MAX_PARAMS
        else:
            params = (("humanSLProfile", handicap_profile(level, handicap)),) + self.HUMAN_PARAMS
        for k, v in params:
            eng.must(f"kata-set-param {k} {v}")

    def genmove(self, eng, color):
        mv = eng.must(f"genmove {color}", GENMOVE_TIMEOUT_S).strip()
        low = mv.lower()
        if low in ("pass", "resign"):
            return low
        mv = mv.upper()
        if not VERTEX_RE.match(mv):
            raise AiError(502, "bad move from engine")
        return mv

    def score_final(self, eng):
        # Recuento preciso (decide piedras muertas) con la búsqueda del modelo principal
        self.set_level(eng, "max")
        res = eng.must("final_score", SCORE_TIMEOUT_S).strip()
        dead = eng.must("final_status_list dead", SCORE_TIMEOUT_S).split()
        dead = [v.upper() for v in dead if VERTEX_RE.match(v.upper())]
        return {"result": res, "score_white": _parse_result(res), "dead": dead}

    def score_estimate(self, eng):
        # Una sola evaluación de la red: instantánea (para abandonos)
        text = eng.must("kata-raw-nn 0", SCORE_TIMEOUT_S)
        m = re.search(r"whiteLead\s+(-?\d+(?:\.\d+)?)", text)
        if not m:
            raise AiError(502, "no whiteLead in raw-nn")
        lead = round(float(m.group(1)), 1)
        return {"result": _format_result(lead), "score_white": lead, "dead": [],
                "ownership": _parse_ownership(text)}


# ── AN1: análisis de partidas (gráfica de ventaja y mejores jugadas) ────────────

AN_GRAPH_MAX_MOVES = 600
AN_VISITS_DEFAULT = 100        # ~6 s en el VPS con el modelo principal
AN_PLAYED_VISITS = 30          # evaluación de la jugada realmente hecha (~2 s)
AN_MAX_CANDIDATES = 5
AN_PV_MAX = 12
_AN_KEYS_NUM = ("visits", "winrate", "scoreLead", "prior", "order")


def _parse_search_analyze(text):
    """Salida de kata-search_analyze: varias líneas 'info move …' (una por intervalo)
    y una final 'play X'. Se usa la ÚLTIMA línea 'info' (la de más visitas).
    Devuelve (candidatas, root): candidatas ordenadas por 'order', con scoreLead y
    winrate desde el punto de vista del jugador al que le toca; root igual o None."""
    lines = [ln.lstrip("= ").strip() for ln in text.splitlines()]
    info = [ln for ln in lines if ln.startswith("info ")]
    if not info:
        raise AiError(502, "no analysis from engine")
    line = info[-1]
    root = None
    if "rootInfo" in line:
        line, root_txt = line.split("rootInfo", 1)
        toks = root_txt.split()
        root = {}
        for k, v in zip(toks[0::2], toks[1::2]):
            if k in ("visits", "winrate", "scoreLead"):
                try:
                    root[k] = float(v)
                except ValueError:
                    pass
    cands = []
    for seg in line.split("info ")[1:]:
        toks = seg.split()
        c, i = {}, 0
        while i < len(toks):
            k = toks[i]
            if k == "pv":
                j = i + 1
                pv = []
                while j < len(toks) and (toks[j] == "pass" or VERTEX_RE.match(toks[j])):
                    pv.append(toks[j]); j += 1
                c["pv"] = pv[:AN_PV_MAX]
                i = j
                continue
            if i + 1 < len(toks):
                v = toks[i + 1]
                if k == "move":
                    c["move"] = v
                elif k in _AN_KEYS_NUM:
                    try:
                        c[k] = float(v)
                    except ValueError:
                        pass
            i += 2
        if c.get("move") and (c["move"] == "pass" or VERTEX_RE.match(c["move"])) and "scoreLead" in c:
            cands.append({"move": c["move"], "visits": int(c.get("visits", 0)),
                          "winrate": round(c.get("winrate", 0.0), 3),
                          "scoreLead": round(c["scoreLead"], 1), "prior": round(c.get("prior", 0.0), 3),
                          "order": int(c.get("order", len(cands))), "pv": c.get("pv", [])})
    if not cands:
        raise AiError(502, "no analysis from engine")
    cands.sort(key=lambda x: x["order"])
    if root:
        root = {"visits": int(root.get("visits", 0)), "winrate": round(root.get("winrate", 0.0), 3),
                "scoreLead": round(root.get("scoreLead", cands[0]["scoreLead"]), 1)}
    return cands[:AN_MAX_CANDIDATES], root


def _parse_ownership(text):
    """Bloque 'whiteOwnership' de kata-raw-nn: 361 valores en -1..1 (+1 = de blancas),
    fila a fila desde arriba (fila 19) y de A a T, el mismo orden que x + 19*y en WGo.
    Devuelve None si no viene completo (el recuento sigue valiendo sin mapa)."""
    toks = text.split()
    try:
        i = toks.index("whiteOwnership")
    except ValueError:
        return None
    vals = []
    for t in toks[i + 1:i + 1 + 361]:
        try:
            v = float(t)
        except ValueError:
            return None
        vals.append(round(max(-1.0, min(1.0, v)), 2) if v == v else 0.0)
    return vals if len(vals) == 361 else None


def _parse_result(res):
    r = res.strip().upper()
    if r in ("0", "JIGO", "DRAW"):
        return 0.0
    m = re.match(r"^([BW])\+(\d+(?:\.\d+)?)$", r)
    if not m:
        raise AiError(502, "bad final_score")
    v = float(m.group(2))
    return v if m.group(1) == "W" else -v


def _format_result(score_white):
    if score_white == 0:
        return "0"
    return ("W+" if score_white > 0 else "B+") + f"{abs(score_white):g}"


def _raw_lead(eng):
    text = eng.must("kata-raw-nn 0", SCORE_TIMEOUT_S)
    m = re.search(r"whiteLead\s+(-?\d+(?:\.\d+)?)", text)
    if not m:
        raise AiError(502, "no whiteLead in raw-nn")
    return round(float(m.group(1)), 1)


def katago_graph(driver, eng, pos):
    """AN1: ventaja de blancas (evaluación instantánea) en cada posición de la partida:
    antes de la primera jugada y tras cada una (len = jugadas + 1)."""
    base = dict(pos, moves=[])
    driver.set_position(eng, base)
    leads = [_raw_lead(eng)]
    for i, (color, vertex) in enumerate(pos["moves"]):
        ok, _ = eng.command(f"play {color} {vertex}")
        if not ok:
            raise AiError(400, f"illegal move {i}: {color} {vertex}")
        leads.append(_raw_lead(eng))
    return leads


def katago_analyze(driver, eng, pos, to_play, visits, played):
    """AN1: mejores jugadas para quien juega (búsqueda con el modelo principal) y,
    si se indica, cuánto vale la jugada realmente hecha (búsqueda corta tras jugarla).
    Puntuaciones desde el punto de vista de to_play."""
    driver.set_position(eng, pos)
    for k, v in (("humanSLChosenMoveProp", "0"), ("maxVisits", str(visits))):
        eng.must(f"kata-set-param {k} {v}")
    text = eng.must(f"kata-search_analyze {to_play} 20 rootInfo true maxmoves {AN_MAX_CANDIDATES}", GENMOVE_TIMEOUT_S)
    cands, root = _parse_search_analyze(text)
    out = {"to_play": to_play, "candidates": cands, "root": root, "played": None}
    if played:
        known = next((c for c in cands if c["move"] == played and c["visits"] >= AN_PLAYED_VISITS), None)
        if known:
            lead = known["scoreLead"]
        else:
            ok, _ = eng.command(f"play {to_play} {played}")
            if not ok:
                raise AiError(400, f"illegal played move: {played}")
            eng.must(f"kata-set-param maxVisits {AN_PLAYED_VISITS}")
            opp = "W" if to_play == "B" else "B"
            _, r2 = _parse_search_analyze(eng.must(f"kata-search_analyze {opp} 20 rootInfo true maxmoves 1", GENMOVE_TIMEOUT_S))
            if not r2:
                raise AiError(502, "no rootInfo from engine")
            lead = round(-r2["scoreLead"], 1)
        out["played"] = {"move": played, "scoreLead": lead, "loss": round(cands[0]["scoreLead"] - lead, 1)}
    return out


# ── AN3: caché de análisis y gráfica precisa por tramos ──────────────────────────

AN_CACHE_VERSION = 1           # súbelo si cambia cómo se calcula algo: invalida la caché
AN_GRAPH_VISITS = 16           # búsqueda corta por posición de la gráfica (~1 s en el VPS)
AN_GRAPH_CHUNK_MAX = 40        # posiciones por petición: el motor no queda bloqueado minutos


def cache_key(model, kind, pos, moves, params):
    """Clave genérica de la caché: versión, modelo, tipo de resultado, posición y parámetros.
    'kind' + 'params' son lo que permitirá añadir análisis nuevos (p. ej. por nivel del
    modelo humano: kind='human_move', params={'profile': 'rank_15k'}) sin tocar la tabla.
    Las piedras de handicap van ordenadas: el SGF las trae en su orden (D4, Q16…) y la app
    las recorre por columnas; la posición es la misma y la clave también debe serlo."""
    blob = json.dumps({"v": AN_CACHE_VERSION, "model": model, "kind": kind, "rules": pos["rules"],
                       "komi": pos["komi"], "hc": sorted(pos["handicap_stones"]), "moves": moves, "params": params},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _to_play_at(pos, i):
    """Quién juega en la posición i (antes de la jugada i): el color de esa jugada si existe;
    si no, el contrario de la última; al inicio, blancas con piedras de handicap."""
    mv = pos["moves"]
    if i < len(mv):
        return mv[i][0]
    if mv:
        return "W" if mv[-1][0] == "B" else "B"
    return "W" if pos["handicap_stones"] else "B"


def katago_graph_search(driver, eng, pos, frm, to, cached, store):
    """AN3: ventaja de blancas en las posiciones frm..to con una búsqueda corta en cada una
    (estable en posiciones tácticas, a diferencia de la evaluación instantánea). Las que ya
    están en 'cached' (índice -> valor) no se recalculan; 'store(i, valor)' guarda las nuevas."""
    driver.set_position(eng, dict(pos, moves=pos["moves"][:frm]))
    for k, v in (("humanSLChosenMoveProp", "0"), ("maxVisits", str(AN_GRAPH_VISITS))):
        eng.must(f"kata-set-param {k} {v}")
    out = []
    for i in range(frm, to + 1):
        if i in cached:
            val = cached[i]
        else:
            tp = _to_play_at(pos, i)
            _, root = _parse_search_analyze(eng.must(f"kata-search_analyze {tp} 50 rootInfo true maxmoves 1", GENMOVE_TIMEOUT_S))
            if not root:
                raise AiError(502, "no rootInfo from engine")
            val = round(root["scoreLead"] if tp == "W" else -root["scoreLead"], 1)
            store(i, val)
        out.append(val)
        if i < to:
            color, vertex = pos["moves"][i]
            ok, _ = eng.command(f"play {color} {vertex}")
            if not ok:
                raise AiError(400, f"illegal move {i}: {color} {vertex}")
    return out


# ── AN4: lectura de SGF (partidas de la app: 19×19, sin variantes) ─────────────

_SGF_COLS = "ABCDEFGHJKLMNOPQRST"


def _sgf_nodes(sgf):
    """Nodos de la línea principal: [{PROP: [valores]}]. Respeta los corchetes escapados dentro de valores
    y se detiene en la primera variante o en el final del árbol."""
    nodes, i, n = [], sgf.find(";"), len(sgf)
    if i < 0:
        raise ValueError("SGF sin nodos")
    cur, key = None, ""
    while i < n:
        ch = sgf[i]
        if ch == ";":
            cur, key = {}, ""
            nodes.append(cur)
        elif ch in "()":
            if nodes:
                break
        elif ch == "[":
            j, val = i + 1, []
            while j < n and sgf[j] != "]":
                if sgf[j] == "\\" and j + 1 < n:
                    j += 1
                val.append(sgf[j]); j += 1
            k = "".join(c for c in key if c.isupper())
            if cur is not None and k:
                cur.setdefault(k, []).append("".join(val).strip())
            i = j
            if not (i + 1 < n and sgf[i + 1] == "["):
                key = ""
        elif ch.isalpha():
            key += ch
        i += 1
    return nodes


def _sgf_vertex(v):
    if not v or v == "tt":
        return "pass"
    x, y = ord(v[0]) - 97, ord(v[1]) - 97
    if not (0 <= x < 19 and 0 <= y < 19):
        raise ValueError(f"coordenada fuera del tablero: {v}")
    return f"{_SGF_COLS[x]}{19 - y}"


def sgf_to_position(sgf):
    """Posición en el formato de /ai/* a partir de un SGF de 19×19 con, como mucho,
    piedras iniciales negras (handicap). ValueError si no se puede analizar."""
    nodes = _sgf_nodes(sgf or "")
    if not nodes:
        raise ValueError("SGF vacío")
    root = nodes[0]
    if root.get("SZ", ["19"])[0] not in ("19", "19:19"):
        raise ValueError("solo 19×19")
    if root.get("AW"):
        raise ValueError("piedras blancas iniciales")
    hc = [_sgf_vertex(v) for v in root.get("AB", [])]
    if len(hc) == 1 or len(hc) > 9:
        raise ValueError("posición inicial no soportada")
    try:
        komi = float(root.get("KM", [""])[0])
    except ValueError:
        komi = 0.5 if hc else 6.5
    komi = max(-50.0, min(50.0, round(komi * 2) / 2))
    ru = root.get("RU", [""])[0].lower()
    rules = "chinese" if any(w in ru for w in ("chin", "aga", "nz", "tromp")) else "japanese"
    moves = []
    for nd in nodes[1:]:
        for c in ("B", "W"):
            if c in nd:
                moves.append([c, _sgf_vertex(nd[c][0])])
    return {"rules": rules, "komi": komi, "handicap_stones": hc, "moves": moves}


# ── AN4: análisis automático en segundo plano ─────────────────────────────────

AN_BG_STEP = 2      # posiciones por turno de motor: lo interactivo espera como mucho ~2 s
AN_PRE_MISTAKE = 5.95   # AN5: tras la gráfica, se analizan las jugadas que pierden >= 6 puntos (umbral de KaTrain, como la app)
AN_PRE_MAX = 200        # AN5: tope de seguridad; en la práctica se preparan todos los errores del jugador


def graph_mistakes(pos, leads):
    """AN5: jugadas que pierden puntos según la gráfica (ventaja de blancas por posición),
    igual que anMistakes en la app. Devuelve [(i, pérdida)] con i = nº de jugada (1..n)."""
    out = []
    for i in range(1, len(pos["moves"]) + 1):
        a, b = leads.get(i - 1), leads.get(i)
        if a is None or b is None:
            continue
        s = -1 if pos["moves"][i - 1][0] == "B" else 1
        loss = s * a - s * b
        if loss >= AN_PRE_MISTAKE:
            out.append((i, loss))
    return out


class GraphWorker:
    """Cola de partidas cuya gráfica precisa se calcula en segundo plano, guardando cada
    posición en la caché (la misma que usa /ai/graph). Cede el motor a las peticiones
    interactivas (jugadas, 🔍, tramos pedidos por la app). Un fallo solo descarta la partida."""

    def __init__(self, service, enabled):
        self.svc = service
        self.enabled = enabled
        self.q = collections.deque()
        self.ids = set()
        self.cv = threading.Condition()
        self.cur = None
        self._cur_job = None
        self.thread = None
        self.stopped = False
        self.done_day = (time.strftime("%Y-%m-%d"), 0)
        self.last_error = None

    def enqueue(self, pos, label, front=False, mine=None):
        """mine = color del jugador ('B'/'W'): tras la gráfica solo se preparan sus errores.
        None (partidas de colecciones) = los de los dos colores."""
        if not self.enabled:
            return False
        mine = mine if mine in ("B", "W") else None
        jid = cache_key(self.svc._model_id(), "graph_job", pos, pos["moves"], {"visits": AN_GRAPH_VISITS})
        with self.cv:
            if jid in self.ids or (self.cur and self.cur["id"] == jid):
                for job in list(self.q) + ([self._cur_job] if self.cur and self._cur_job else []):
                    if job["id"] == jid and mine and not job.get("mine"):
                        job["mine"] = mine
                if front and jid in self.ids:   # pedida por el usuario: pasa delante
                    for job in list(self.q):
                        if job["id"] == jid:
                            self.q.remove(job); self.q.appendleft(job)
                return True
            job = {"id": jid, "pos": pos, "label": str(label or "")[:80], "mine": mine}
            (self.q.appendleft if front else self.q.append)(job)
            self.ids.add(jid)
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._loop, name="graph-worker", daemon=True)
                self.thread.start()
            self.cv.notify()
        return True

    def stop(self):
        with self.cv:
            self.stopped = True
            self.cv.notify()

    def status(self):
        with self.cv:
            cur = dict(self.cur, pos=None) if self.cur else None
            day, cnt = self.done_day
            return {"enabled": self.enabled, "queue": len(self.q),
                    "current": {"label": cur["label"], "done": cur["done"], "total": cur["total"]} if cur else None,
                    "done_today": cnt if day == time.strftime("%Y-%m-%d") else 0,
                    "last_error": self.last_error}

    def _loop(self):
        while True:
            with self.cv:
                while not self.q and not self.stopped:
                    self.cv.wait()
                if self.stopped:
                    return
                job = self.q.popleft()
                self.ids.discard(job["id"])
                self.cur = dict(job, done=0, total=len(job["pos"]["moves"]) + 1)
                self._cur_job = job   # la partida en curso (para fijar "mine" si se vuelve a pedir)
            try:
                self._process(job)
                with self.cv:
                    day, cnt = self.done_day
                    today = time.strftime("%Y-%m-%d")
                    self.done_day = (today, (cnt if day == today else 0) + 1)
            except Exception as e:  # noqa: BLE001 — el trabajador nunca debe morir
                log.warning("[ai] análisis automático de %r falló: %s", job["label"], e)
                with self.cv:
                    self.last_error = {"msg": f"{job['label']}: {e}"[:200], "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            finally:
                with self.cv:
                    self.cur = None

    def _process(self, job):
        svc, pos = self.svc, job["pos"]
        n = len(pos["moves"])
        params = {"visits": AN_GRAPH_VISITS}
        model = svc._model_id()
        keys = [cache_key(model, "pos_eval", pos, pos["moves"][:i], params) for i in range(n + 1)]
        hit = svc.cache.get_many(keys) if svc.cache else {}
        have = {i: hit[k]["white_lead"] for i, k in enumerate(keys) if k in hit}
        with self.cv:
            self.cur["done"] = len(have)
        d = svc.drivers["katago"]
        while len(have) < n + 1:
            if self.stopped:
                return
            svc._check_available("katago")
            frm = next(i for i in range(n + 1) if i not in have)
            to = min(n, frm + AN_BG_STEP - 1)

            def store(i, val):
                have[i] = val
                if svc.cache:
                    svc.cache.put(keys[i], "pos_eval", params, {"white_lead": val})

            svc._yield_to_interactive()
            svc._run("katago", lambda eng: katago_graph_search(d, eng, pos, frm, to, dict(have), store), interactive=False)
            with self.cv:
                self.cur["done"] = len(have)
        self._precompute_mistakes(job, have)

    def _precompute_mistakes(self, job, leads):
        """AN5: deja en la caché el análisis de cada error (los mismos parámetros que usa 🔍
        en la app: posición anterior, quien jugó, la jugada hecha, visitas por defecto), para
        que al pulsar 🔍 sobre un error la respuesta sea instantánea."""
        svc, pos = self.svc, job["pos"]
        if not svc.cache:
            return
        mine = job.get("mine")
        errs = [e for e in graph_mistakes(pos, leads) if not mine or pos["moves"][e[0] - 1][0] == mine]
        errs = sorted(errs, key=lambda x: -x[1])[:AN_PRE_MAX]   # los mayores primero
        if not errs:
            return
        d, model = svc.drivers["katago"], svc._model_id()
        with self.cv:
            self.cur.update(label=job["label"] + " · errores", done=0, total=len(errs))
        for k, (i, _loss) in enumerate(errs):
            if self.stopped:
                return
            color, vertex = pos["moves"][i - 1]
            before = dict(pos, moves=pos["moves"][:i - 1])
            params = {"visits": AN_VISITS_DEFAULT, "to_play": color, "played": vertex}
            key = cache_key(model, "analyze", before, before["moves"], params)
            if not svc.cache.get(key):
                svc._check_available("katago")
                svc._yield_to_interactive()
                res = svc._run("katago", lambda eng: katago_analyze(d, eng, before, color, AN_VISITS_DEFAULT, vertex), interactive=False)
                svc.cache.put(key, "analyze", params, res)
            with self.cv:
                self.cur["done"] = k + 1


# ── Servicio ─────────────────────────────────────────────────────────────────


class AiService:
    def __init__(self, env=None, cache=None):
        self.cache = cache   # AN3: objeto con get/get_many/put (lo da el servidor); None = sin caché
        self._waiting = 0                     # AN4: peticiones interactivas esperando al motor
        self._waiting_lock = threading.Lock()
        self._move_ms = collections.deque(maxlen=20)   # ST1: tiempos de las últimas jugadas
        env = os.environ if env is None else env
        try:
            self.idle_s = max(1.0, float(env.get("KATAGO_IDLE_S", "900")))
        except ValueError:
            self.idle_s = 900.0
        self.log_path = env.get("KATAGO_LOG", "").strip() or None
        self.drivers = {"katago": KataGoDriver(env)}   # futuro: "gnugo": GnuGoDriver(env)
        self.engines = {}
        self._engines_lock = threading.Lock()
        self._watcher = None
        self._stop = threading.Event()
        env_bg = (env.get("KATAGO_BACKGROUND", "1") or "1").strip()
        self.worker = GraphWorker(self, enabled=env_bg != "0")   # AN4: KATAGO_BACKGROUND=0 lo apaga

    # ── estado ──
    def _available(self, name):
        d = self.drivers.get(name)
        return d is not None and d.unavailable_reason() is None

    def status(self, _qs=None):
        out = {"available": False, "engines": {}, "levels": []}
        for name, d in self.drivers.items():
            reason = d.unavailable_reason()
            eng = self.engines.get(name)
            out["engines"][name] = {"available": reason is None, "reason": reason,
                                    "running": bool(eng and eng.running())}
            if reason is None:
                out["available"] = True
                out["levels"] += [f"{name}:{lv}" for lv in d.levels()]
        return out

    # ── motores ──
    def _engine(self, name):
        with self._engines_lock:
            eng = self.engines.get(name)
            if eng is None:
                d = self.drivers[name]
                eng = GtpEngine(name, d.argv(), self.log_path)
                self.engines[name] = eng
            if self._watcher is None:
                self._watcher = threading.Thread(target=self._watch, daemon=True)
                self._watcher.start()
            return eng

    def _watch(self):
        interval = min(30.0, max(0.5, self.idle_s / 4))
        while not self._stop.wait(interval):
            now = time.monotonic()
            for eng in list(self.engines.values()):
                if eng.running() and now - eng.last_used > self.idle_s and eng.lock.acquire(blocking=False):
                    try:
                        if eng.running() and time.monotonic() - eng.last_used > self.idle_s:
                            log.info("[ai] %s sin uso %.0f s: se cierra", eng.name, self.idle_s)
                            eng.close()
                    finally:
                        eng.lock.release()

    def _run(self, name, fn, interactive=True):
        eng = self._engine(name)
        if interactive:
            with self._waiting_lock:
                self._waiting += 1
        try:
            got = eng.lock.acquire(timeout=LOCK_WAIT_S)
        finally:
            if interactive:
                with self._waiting_lock:
                    self._waiting -= 1
        if not got:
            raise AiError(503, "engine busy")
        try:
            return fn(eng)
        finally:
            eng.lock.release()

    def _yield_to_interactive(self):
        """AN4: el trabajador espera mientras haya peticiones interactivas en cola."""
        while True:
            with self._waiting_lock:
                if self._waiting == 0:
                    return
            time.sleep(0.05)

    def shutdown(self):
        self._stop.set()
        self.worker.stop()
        for eng in list(self.engines.values()):
            if eng.lock.acquire(timeout=5):
                try:
                    eng.close()
                finally:
                    eng.lock.release()

    # ── validación ──
    @staticmethod
    def _position(body):
        if not isinstance(body, dict):
            raise AiError(400, "invalid body")
        rules = body.get("rules")
        if rules not in ("japanese", "chinese"):
            raise AiError(400, "rules must be japanese|chinese")
        komi = body.get("komi")
        if isinstance(komi, bool) or not isinstance(komi, (int, float)) or not -50 <= komi <= 50 or (komi * 2) % 1:
            raise AiError(400, "invalid komi")
        hs = body.get("handicap_stones", [])
        if not isinstance(hs, list) or len(hs) == 1 or len(hs) > 9:
            raise AiError(400, "handicap_stones must have 0 or 2..9 vertices")
        if any(not isinstance(v, str) or not VERTEX_RE.match(v) for v in hs) or len(set(hs)) != len(hs):
            raise AiError(400, "invalid handicap vertex")
        moves = body.get("moves", [])
        if not isinstance(moves, list) or len(moves) > MAX_MOVES:
            raise AiError(400, "invalid moves")
        norm = []
        for m in moves:
            if (not isinstance(m, list) or len(m) != 2 or m[0] not in ("B", "W")
                    or not isinstance(m[1], str) or not (m[1] == "pass" or VERTEX_RE.match(m[1]))):
                raise AiError(400, "invalid move")
            norm.append((m[0], m[1]))
        k = float(komi)
        return {"rules": rules, "komi": f"{k:g}", "handicap_stones": list(hs), "moves": norm}

    def _check_available(self, name):
        if not self._available(name):
            raise AiError(503, "ai engine not available")

    # ── endpoints ──
    def move(self, body):
        pos = self._position(body)
        level = body.get("level")
        if not isinstance(level, str) or ":" not in level:
            raise AiError(400, "invalid level")
        name, lv = level.split(":", 1)
        d = self.drivers.get(name)
        if d is None or lv not in d.levels():
            raise AiError(400, "invalid level")
        hc = body.get("handicap", 0)   # opcional: clientes antiguos no lo mandan -> perfil normal
        if isinstance(hc, bool) or not isinstance(hc, int) or not -9 <= hc <= 9:
            raise AiError(400, "handicap must be an integer in -9..9")
        to_play = body.get("to_play")
        if to_play not in ("B", "W"):
            raise AiError(400, "to_play must be B|W")
        self._check_available(name)

        def go(eng):
            t0 = time.monotonic()
            d.set_position(eng, pos)
            d.set_level(eng, lv, hc)
            mv = d.genmove(eng, to_play)
            ms = int((time.monotonic() - t0) * 1000)
            self._move_ms.append(ms)
            return {"move": mv, "level": level, "model": d.model_for(lv), "ms": ms}
        return self._run(name, go)

    def _model_id(self):
        d = self.drivers["katago"]
        return os.path.basename(d.model)

    def graph(self, body):
        pos = self._position(body)
        if len(pos["moves"]) > AN_GRAPH_MAX_MOVES:
            raise AiError(400, "too many moves for a graph")
        if "from" in body or "to" in body:
            return self._graph_chunk(body, pos)
        self._check_available("katago")
        d = self.drivers["katago"]

        def go(eng):
            t0 = time.monotonic()
            leads = katago_graph(d, eng, pos)
            return {"white_leads": leads, "ms": int((time.monotonic() - t0) * 1000)}
        return self._run("katago", go)

    def _graph_chunk(self, body, pos):
        """AN3: tramo frm..to de la gráfica precisa, con caché por posición.
        AN4: con cached_only=true no calcula nada: devuelve lo guardado (null donde falte)."""
        n = len(pos["moves"])
        frm, to = body.get("from"), body.get("to")
        for v in (frm, to):
            if isinstance(v, bool) or not isinstance(v, int):
                raise AiError(400, "from/to must be integers")
        cached_only = body.get("cached_only") is True
        span_max = n + 1 if cached_only else AN_GRAPH_CHUNK_MAX
        if not (0 <= frm <= to <= n) or to - frm + 1 > span_max:
            raise AiError(400, f"invalid range (0 <= from <= to <= {n}, at most {AN_GRAPH_CHUNK_MAX} positions)")
        model = self._model_id() if "katago" in self.drivers else ""
        params = {"visits": AN_GRAPH_VISITS}
        keys = {i: cache_key(model, "pos_eval", pos, pos["moves"][:i], params) for i in range(frm, to + 1)}
        hit = self.cache.get_many(list(keys.values())) if self.cache else {}
        cached = {i: hit[k]["white_lead"] for i, k in keys.items() if k in hit}
        if cached_only:
            return {"from": frm, "to": to, "white_leads": [cached.get(i) for i in range(frm, to + 1)],
                    "cached": len(cached), "complete": len(cached) == len(keys), "ms": 0}
        if len(cached) == len(keys):
            return {"from": frm, "to": to, "white_leads": [cached[i] for i in range(frm, to + 1)], "cached": len(cached), "ms": 0}
        self._check_available("katago")
        d = self.drivers["katago"]

        def store(i, val):
            if self.cache:
                self.cache.put(keys[i], "pos_eval", params, {"white_lead": val})

        def go(eng):
            t0 = time.monotonic()
            leads = katago_graph_search(d, eng, pos, frm, to, cached, store)
            return {"from": frm, "to": to, "white_leads": leads, "cached": len(cached), "ms": int((time.monotonic() - t0) * 1000)}
        return self._run("katago", go)

    def graph_job(self, body):
        """AN4: encola el cálculo de la gráfica de una partida en el servidor (sigue aunque la
        app se cierre). Con el trabajador apagado devuelve enabled=false y la app calcula por tramos."""
        pos = self._position(body)
        if len(pos["moves"]) > AN_GRAPH_MAX_MOVES:
            raise AiError(400, "too many moves for a graph")
        if not self.worker.enabled:
            return {"enabled": False}
        self._check_available("katago")
        label = body.get("label") if isinstance(body.get("label"), str) else ""
        mine = body.get("mine") if body.get("mine") in ("B", "W") else None
        self.worker.enqueue(pos, label, front=True, mine=mine)
        return {"enabled": True, "queued": True}

    def enqueue_sgf(self, sgf, label, mine=None):
        """AN4: encola una partida guardada (ai_games). Nunca lanza: devuelve True/False."""
        try:
            if not self.worker.enabled or self._available("katago") is False:
                return False
            pos = self._position(dict(sgf_to_position(sgf)))
            if len(pos["moves"]) > AN_GRAPH_MAX_MOVES:
                return False
            return self.worker.enqueue(pos, label, mine=mine)
        except Exception as e:  # noqa: BLE001
            log.warning("[ai] no se pudo encolar %r: %s", label, e)
            return False

    def server_status(self):
        """ST1: resumen para la sección 'Estado del servidor' de ⚙."""
        st = self.status()
        eng = st["engines"].get("katago", {})
        ms = list(self._move_ms)
        return {"available": st["available"], "engine_running": bool(eng.get("running")),
                "engine_reason": eng.get("reason"),
                "move_ms_avg": int(sum(ms) / len(ms)) if ms else None, "move_samples": len(ms),
                "worker": self.worker.status()}

    def analyze(self, body):
        pos = self._position(body)
        to_play = body.get("to_play")
        if to_play not in ("B", "W"):
            raise AiError(400, "to_play must be B|W")
        visits = body.get("visits", AN_VISITS_DEFAULT)
        if isinstance(visits, bool) or not isinstance(visits, int) or not 10 <= visits <= 400:
            raise AiError(400, "visits must be an integer in 10..400")
        played = body.get("played")
        if played is not None and (not isinstance(played, str) or not (played == "pass" or VERTEX_RE.match(played))):
            raise AiError(400, "invalid played move")
        params = {"visits": visits, "to_play": to_play, "played": played}
        key = cache_key(self._model_id(), "analyze", pos, pos["moves"], params) if "katago" in self.drivers else None
        if self.cache and key:
            hit = self.cache.get(key)
            if hit:
                return dict(hit, cached=True, ms=0)
        self._check_available("katago")
        d = self.drivers["katago"]

        def go(eng):
            t0 = time.monotonic()
            res = katago_analyze(d, eng, pos, to_play, visits, played)
            if self.cache and key:
                self.cache.put(key, "analyze", params, res)
            res = dict(res, cached=False, ms=int((time.monotonic() - t0) * 1000))
            return res
        return self._run("katago", go)

    def score(self, body):
        pos = self._position(body)
        mode = body.get("mode")
        if mode not in ("final", "estimate"):
            raise AiError(400, "mode must be final|estimate")
        self._check_available("katago")
        d = self.drivers["katago"]

        def go(eng):
            t0 = time.monotonic()
            d.set_position(eng, pos)
            res = d.score_final(eng) if mode == "final" else d.score_estimate(eng)
            res["mode"] = mode
            res["ms"] = int((time.monotonic() - t0) * 1000)
            return res
        return self._run("katago", go)
