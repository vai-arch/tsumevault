import json, time, collections, requests
from list_inventory import login, listar, BASE, PAUSA

ARCHIVO = "find_chapters_dump.json"

def listar_problemas(H):
    """Devuelve [(id, createTime)] de toda la colección problems."""
    out, tok, pag = [], "", 0
    while pag < 400:
        params = [("pageSize", 300), ("mask.fieldPaths", "id")]
        if tok:
            params.append(("pageToken", tok))
        r = requests.get(f"{BASE}/problems", headers=H, params=params)
        if r.status_code != 200:
            print("error listando problems:", r.status_code)
            break
        j = r.json()
        for d in j.get("documents", []):
            out.append((d["name"].split("/")[-1], d.get("createTime", "")))
        pag += 1
        tok = j.get("nextPageToken", "")
        if not tok:
            break
        time.sleep(PAUSA)
    return out

def main():
    datos = json.load(open(ARCHIVO, encoding="utf-8"))
    ref = set()
    for k, c in datos.items():
        if k.startswith("courses/"):
            for cl in c.get("clips") or []:
                for p in cl.get("problems") or []:
                    pid = p.get("id") if isinstance(p, dict) else p
                    if pid:
                        ref.add(pid)
    H = login()
    cols, _ = listar(H, "problem-collections", ["title", "problems"])
    caps = set()
    for cid, f in cols:
        for p in f.get("problems") or []:
            pid = p if isinstance(p, str) else p.get("id")
            if pid:
                ref.add(pid)
                if (f.get("title") or "").strip().lower().startswith("chapter"):
                    caps.add(pid)
    todos = listar_problemas(H)
    print(f"problemas en total: {len(todos)} | referenciados (colecciones + lecciones): {len(ref)}")
    huerfanos = [(i, t) for i, t in todos if i not in ref]
    print(f"huérfanos (sin referencia): {len(huerfanos)}")
    crea = {i: t for i, t in todos}
    print("\nFecha de creación de los 12 problemas de las colecciones 'Chapter':")
    for i in sorted(caps, key=lambda x: crea.get(x, "")):
        print("  ", i[:8], crea.get(i, "?")[:19])
    json.dump(huerfanos, open("huerfanos.json", "w", encoding="utf-8"))
    dias = collections.Counter(t[:10] for _, t in huerfanos)
    print("\nHuérfanos por día de creación (los 15 días con más):")
    for d, n in dias.most_common(15):
        print(f"   {d}: {n}")
    if caps:
        dias_cap = {crea[i][:10] for i in caps if i in crea}
        print("\nHuérfanos creados el mismo día que algún 'Chapter':", {d: dias.get(d, 0) for d in sorted(dias_cap)})
    print("\nGuardado en huerfanos.json")

if __name__ == "__main__":
    main()