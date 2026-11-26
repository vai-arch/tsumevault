#!/usr/bin/env python3
"""AR1 (WORKPLAN_ARCHIVO.md): descarga los datos PÚBLICOS de kifumaster.org a kifumaster/data/raw/,
tal cual, para que kifu_build.py construya el catálogo sin volver a pedir nada.

    python kifumaster/kifu_crawl.py                 continúa el ciclo en curso (o empieza el primero)
    python kifumaster/kifu_crawl.py --nuevo-ciclo   empieza un ciclo nuevo (uso mensual)
    python kifumaster/kifu_crawl.py --limite 5      solo 5 peticiones (pruebas)

Qué se baja (1028 ficheros): database/{aliases,aliasesevent,aliasesrank,event_families}.csv y
seo/{te,t,ts,g}/00.json … ff.json. Los SGF NO: están tras App Check; se bajan a mano.

Cortesía: una petición cada 6-8 s, de una en una, User-Agent identificable, petición condicional
(If-None-Match/If-Modified-Since: lo que no cambió responde 304 y no se descarga), respeta robots.txt
(nada de "?step="). Ante 429 o 5xx espera 1, 5 y 30 min; si sigue fallando, se para. Reanudable: el
estado se guarda tras cada petición en data/raw/_estado.json; Ctrl-C en cualquier momento.
"""
import argparse, datetime, gzip, json, os, random, sys, time, urllib.error, urllib.request

BASE = os.environ.get("KIFU_BASE", "https://kifumaster.org/")
UA = "TsumeVault-archive/0.2 (estudio personal; +https://github.com/vai-arch/tsumevault)"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("KIFU_DATA", os.path.join(HERE, "data"))
RAW = os.path.join(DATA, "raw")
STATE = os.path.join(RAW, "_estado.json")
LOGS = os.path.join(DATA, "logs")
_d = os.environ.get("KIFU_DELAY")            # solo los tests lo cambian
DELAY = (float(_d), float(_d)) if _d is not None else (6.0, 8.0)
BACKOFF = [float(x) for x in os.environ.get("KIFU_BACKOFF", "60,300,1800").split(",")]

CSVS = ["database/aliases.csv", "database/aliasesevent.csv", "database/aliasesrank.csv", "database/event_families.csv"]
SHARDS = [f"{i:02x}" for i in range(256)]
FAMILIES = ["te", "t", "ts", "g"]            # g (el índice, el más pesado) al final


def targets():
    out = list(CSVS)
    for fam in FAMILIES:
        out += [f"seo/{fam}/{s}.json" for s in SHARDS]
    return out


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


class Log:
    def __init__(self):
        os.makedirs(LOGS, exist_ok=True)
        self.f = open(os.path.join(LOGS, "crawl_" + datetime.date.today().strftime("%Y%m%d") + ".log"), "a", encoding="utf-8")

    def __call__(self, msg):
        line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        self.f.write(line + "\n"); self.f.flush()


def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"cycle": 0, "cycle_started": None, "cycle_finished": None, "files": {}}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def write_raw(path, body):
    dst = os.path.join(RAW, *path.split("/"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, dst)


def fetch(path, prev):
    """Devuelve (status, headers_lower, body). Petición condicional si hay ETag/Last-Modified previos."""
    h = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    if prev and os.path.exists(os.path.join(RAW, *path.split("/"))):
        if prev.get("etag"): h["If-None-Match"] = prev["etag"]
        if prev.get("last_modified"): h["If-Modified-Since"] = prev["last_modified"]
    req = urllib.request.Request(BASE + path, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, headers, body = r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        status, headers, body = e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, (e.read() or b"")
    if body and headers.get("content-encoding") == "gzip":
        body = gzip.decompress(body)
    return status, headers, body


def validate(path, body):
    """Que lo que guardamos sea lo esperado: JSON-objeto en seo/, CSV con cabecera en database/."""
    if path.endswith(".json"):
        j = json.loads(body.decode("utf-8"))
        if not isinstance(j, dict):
            raise ValueError("no es un objeto JSON")
        return f"{len(j)} claves"
    text = body.decode("utf-8-sig")
    if "," not in text.split("\n", 1)[0]:
        raise ValueError("CSV sin cabecera")
    return f"{text.count(chr(10))} líneas"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nuevo-ciclo", action="store_true", help="empieza un ciclo nuevo aunque el anterior esté completo")
    ap.add_argument("--limite", type=int, default=0, help="máximo de peticiones en esta ejecución (0 = sin límite)")
    a = ap.parse_args(argv)
    os.makedirs(RAW, exist_ok=True)
    log = Log()
    st = load_state()
    if st["cycle"] == 0 or a.nuevo_ciclo:
        if st["cycle"] and not st.get("cycle_finished") and a.nuevo_ciclo:
            log(f"Aviso: el ciclo {st['cycle']} no había terminado; se empieza otro igualmente.")
        st["cycle"] += 1; st["cycle_started"] = now_iso(); st["cycle_finished"] = None
        save_state(st)
        log(f"Ciclo {st['cycle']} empezado.")
    elif st.get("cycle_finished"):
        log(f"El ciclo {st['cycle']} ya está completo ({st['cycle_finished']}). Para buscar novedades: --nuevo-ciclo")
        return 0
    cyc = st["cycle"]
    all_t = targets()
    pending = [p for p in all_t if st["files"].get(p, {}).get("cycle") != cyc]
    log(f"Ciclo {cyc}: {len(all_t) - len(pending)} hechos, {len(pending)} pendientes. "
        f"Pausa {DELAY[0]:g}-{DELAY[1]:g} s ({len(pending) * sum(DELAY) / 2 / 60:.0f} min aprox.).")
    counts = {"nuevo": 0, "cambiado": 0, "igual": 0, "no existe": 0}
    done = 0
    for i, path in enumerate(pending):
        if a.limite and done >= a.limite:
            log(f"Límite de {a.limite} peticiones alcanzado; se sigue en la próxima ejecución.")
            break
        if done and DELAY[1]:
            time.sleep(random.uniform(*DELAY))
        prev = st["files"].get(path)
        attempt = 0
        while True:
            try:
                status, headers, body = fetch(path, prev)
            except Exception as e:                       # red caída, timeout…: se trata como un 5xx
                status, headers, body = 599, {}, str(e).encode()
            if status == 429 or status >= 500:
                if attempt >= len(BACKOFF):
                    log(f"PARADO: {path} sigue respondiendo {status} tras {attempt} esperas. Estado guardado; vuelve a lanzarlo más tarde.")
                    save_state(st)
                    return 2
                wait = BACKOFF[attempt]
                ra = headers.get("retry-after", "")
                if ra.isdigit():
                    wait = max(wait, float(ra))
                log(f"{status} en {path}: espero {wait:g} s antes de reintentar ({attempt + 1}/{len(BACKOFF)}).")
                time.sleep(wait); attempt += 1
                continue
            break
        done += 1
        rec = {"cycle": cyc, "checked_at": now_iso(), "status": status}
        if status == 200:
            try:
                info = validate(path, body)
            except Exception as e:
                log(f"PARADO: {path} respondió 200 pero el contenido no es válido ({e}). No se guarda.")
                save_state(st)
                return 3
            kind = "nuevo" if not prev or prev.get("status") != 200 else ("igual" if prev.get("sha") == _sha(body) else "cambiado")
            write_raw(path, body)
            rec.update(etag=headers.get("etag"), last_modified=headers.get("last-modified"), bytes=len(body), sha=_sha(body),
                       changed_at=now_iso() if kind != "igual" else prev.get("changed_at"))
            counts[kind] += 1
            log(f"[{len(all_t) - len(pending) + i + 1}/{len(all_t)}] 200 {path} {len(body)} B, {info} ({kind})")
        elif status == 304:
            rec.update({k: prev.get(k) for k in ("etag", "last_modified", "bytes", "sha", "changed_at")})
            rec["status"] = 200
            counts["igual"] += 1
            log(f"[{len(all_t) - len(pending) + i + 1}/{len(all_t)}] 304 {path} (sin cambios)")
        elif status == 404:
            counts["no existe"] += 1
            log(f"[{len(all_t) - len(pending) + i + 1}/{len(all_t)}] 404 {path} (no existe; se apunta)")
        else:
            log(f"PARADO: {path} respondió {status}, que no sé tratar. Estado guardado.")
            save_state(st)
            return 4
        st["files"][path] = rec
        save_state(st)
    if all(st["files"].get(p, {}).get("cycle") == cyc for p in all_t):
        st["cycle_finished"] = now_iso(); save_state(st)
        log(f"Ciclo {cyc} completo.")
    log("Resumen de esta ejecución: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


def _sha(b):
    import hashlib
    return hashlib.sha256(b).hexdigest()[:16]


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrumpido. El estado está guardado: al relanzarlo sigue donde lo dejó.")
        sys.exit(130)
