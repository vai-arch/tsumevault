import json, os, time, requests

API_KEY = "AIzaSyC-lnkKAtRoCd30xecSXWQ77xhla9S44I8"
RT_PATH = "awesomebaduk_rt"  # ajusta al nombre real de tu fichero del token
HEADERS = {"Referer": "https://awesomebaduk.com/"}
BASE = "https://firestore.googleapis.com/v1/projects/badol-online-academy/databases/(default)/documents"
TIMEOUT = 30      # segundos por petición
REINTENTOS = 3
PAUSA = 0.3

def plain(v):
    k, x = next(iter(v.items()))
    if k == "mapValue":
        return {a: plain(b) for a, b in x.get("fields", {}).items()}
    if k == "arrayValue":
        return [plain(i) for i in x.get("values", [])]
    if k == "integerValue":
        return int(x)
    if k == "nullValue":
        return None
    return x

def ya_descargado(path):
    if not os.path.exists(path):
        return False
    try:
        d = json.load(open(path, encoding="utf-8"))
        return "variations" in d and "id" in d
    except Exception:
        return False   # fichero corrupto o a medias: se vuelve a bajar

S = requests.Session()
S.headers.update(HEADERS)

rt = open(RT_PATH, encoding="utf-8").read().strip()
r = S.post(f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
           data={"grant_type": "refresh_token", "refresh_token": rt}, timeout=TIMEOUT)
r.raise_for_status()
S.headers["Authorization"] = f"Bearer {r.json()['id_token']}"

def pedir(pid):
    ultimo = ""
    for intento in range(1, REINTENTOS + 1):
        try:
            rr = S.get(f"{BASE}/problems/{pid}", timeout=TIMEOUT)
            if rr.status_code == 200:
                return rr, ""
            if rr.status_code not in (429, 500, 502, 503, 504):
                return rr, f"HTTP {rr.status_code}"
            ultimo = f"HTTP {rr.status_code}"
        except requests.RequestException as e:
            ultimo = type(e).__name__
        print(f"   reintento {intento}/{REINTENTOS} ({ultimo})", flush=True)
        time.sleep(2 * intento)
    return None, ultimo

days = json.load(open("days.json", encoding="utf-8"))
os.makedirs("problems_raw", exist_ok=True)
todos = [(it, pid) for it in days for pid in it["doc"]["problems"]]
print(f"problemas a revisar: {len(todos)}", flush=True)

nuevos = errores = saltados = 0
for i, (item, pid) in enumerate(todos, 1):
    path = os.path.join("problems_raw", pid + ".json")
    if ya_descargado(path):
        saltados += 1
        continue
    rr, err = pedir(pid)
    if rr is None or rr.status_code != 200:
        print(f"error semana {item['week']} día {item['day']} {pid[:8]}: {err}", flush=True)
        errores += 1
        continue
    doc = {k: plain(v) for k, v in rr.json()["fields"].items()}
    tmp = path + ".tmp"
    json.dump(doc, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    nuevos += 1
    if nuevos % 10 == 0 or i == len(todos):
        print(f"  {i}/{len(todos)} revisados, {nuevos} descargados", flush=True)
    time.sleep(PAUSA)

print("descargados ahora:", nuevos, "| ya estaban:", saltados, "| errores:", errores)
print("ficheros en problems_raw:", len([f for f in os.listdir("problems_raw") if f.endswith(".json")]))
for w in range(4):
    sem = [x for x in days if x["week"] == w]
    titulos = sorted({x["doc"]["title"] for x in sem})
    n = sum(len(x["doc"]["problems"]) for x in sem)
    print(f"semana {w + 1}: {len(sem)} días, {n} problemas, títulos: {titulos}")