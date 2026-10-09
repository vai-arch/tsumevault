import json, time, requests
from analyze_all import parse_edn

API_KEY = "AIzaSyC-lnkKAtRoCd30xecSXWQ77xhla9S44I8"
RT_PATH = "awesomebaduk_rt"  # el mismo fichero de siempre
HEADERS = {"Referer": "https://awesomebaduk.com/"}
BASE = "https://firestore.googleapis.com/v1/projects/badol-online-academy/databases/(default)/documents"
PAUSA = 0.3
CANDIDATAS = ["courses", "playlists", "lessons", "videos", "clips", "challenges",
              "problem-sets", "josekichallenge26"]

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

def login():
    rt = open(RT_PATH, encoding="utf-8").read().strip()
    r = requests.post(f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
                      data={"grant_type": "refresh_token", "refresh_token": rt}, headers=HEADERS)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['id_token']}", **HEADERS}

def listar(H, col, campos, max_paginas=100):
    docs, tok, paginas = [], "", 0
    while paginas < max_paginas:
        params = [("pageSize", 300)] + [("mask.fieldPaths", c) for c in campos]
        if tok:
            params.append(("pageToken", tok))
        r = requests.get(f"{BASE}/{col}", headers=H, params=params)
        if r.status_code != 200:
            return docs, f"error {r.status_code}"
        j = r.json()
        for d in j.get("documents", []):
            docs.append((d["name"].split("/")[-1], {k: plain(v) for k, v in d.get("fields", {}).items()}))
        paginas += 1
        tok = j.get("nextPageToken", "")
        if not tok:
            return docs, "ok"
        time.sleep(PAUSA)
    return docs, f"cortado a {max_paginas} páginas"

def main():
    H = login()
    out = []
    P = out.append

    desafios, est = listar(H, "auto-challenges", ["title", "start-date", "published", "schedule"])
    P(f"=== DESAFÍOS (auto-challenges): {len(desafios)} [{est}] ===")
    en_desafio = {}
    for cid, f in desafios:
        try:
            sched = parse_edn(f.get("schedule", "[]"))
        except Exception:
            sched = ()
        ids = [x for sem in sched for x in sem if x]
        for i, x in enumerate(ids):
            en_desafio[x] = (cid, i + 1)
        P(f"- {cid[:8]} | {f.get('title')} | inicio {f.get('start-date')} | publicado {f.get('published')} | {len(ids)} días")

    cols, est = listar(H, "problem-collections", ["title", "problems"])
    P(f"\n=== COLECCIONES DE PROBLEMAS (problem-collections): {len(cols)} [{est}] ===")
    sueltas = []
    for cid, f in cols:
        n = len(f.get("problems") or [])
        if cid in en_desafio:
            continue
        sueltas.append((f.get("title") or "(sin título)", n, cid))
    en_total = len(cols) - len(sueltas)
    total_problemas = sum(len(f.get("problems") or []) for _, f in cols)
    P(f"Dentro de desafíos (días): {en_total} | Sueltas: {len(sueltas)} | Referencias a problemas en total: {total_problemas}")
    P("\n--- Colecciones sueltas (título | nº problemas | id) ---")
    for t, n, cid in sorted(sueltas, key=lambda x: x[0].lower()):
        P(f"{t} | {n} | {cid[:8]}")

    P("\n=== OTRAS COLECCIONES CANDIDATAS (nº de documentos en la primera página) ===")
    for c in CANDIDATAS:
        r = requests.get(f"{BASE}/{c}", headers=H, params={"pageSize": 5, "mask.fieldPaths": "__name__"})
        if r.status_code == 200:
            n = len(r.json().get("documents", []))
            P(f"{c}: accesible, {'sin documentos o no existe' if n == 0 else str(n) + '+ documentos'}")
        else:
            P(f"{c}: {r.status_code}")
        time.sleep(PAUSA)

    texto = "\n".join(out)
    open("inventario.txt", "w", encoding="utf-8").write(texto)
    print(texto if len(out) < 120 else "\n".join(out[:120]) + f"\n... ({len(out) - 120} líneas más en inventario.txt)")
    print("\nGuardado en inventario.txt")

if __name__ == "__main__":
    main()