import json
from list_inventory import login, listar
from analyze_all import parse_edn

COLECCIONES = ["courses", "josekichallenge26", "auto-challenges"]

def buscar_ids(obj, ids):
    texto = json.dumps(obj, ensure_ascii=False)
    return [i for i in ids if i in texto]

def main():
    H = login()
    cols, est = listar(H, "problem-collections", ["title", "problems"])
    titulo = {cid: (f.get("title") or "(sin título)", len(f.get("problems") or [])) for cid, f in cols}
    caps = [cid for cid, (t, n) in titulo.items() if t.strip().lower().startswith("chapter")]
    print(f"problem-collections: {len(cols)} [{est}] | con título 'Chapter': {len(caps)}")
    for cid in caps:
        print(f"   {cid[:8]} | {titulo[cid][0]} | {titulo[cid][1]} problemas")

    volcado = {}
    for col in COLECCIONES:
        docs, est = listar(H, col, [])
        print(f"\n=== {col}: {len(docs)} documentos [{est}] ===")
        for did, f in docs:
            volcado[f"{col}/{did}"] = f
            tit = f.get("title") or f.get("name") or ""
            campos = {k: (type(v).__name__ + (f"[{len(v)}]" if hasattr(v, "__len__") and not isinstance(v, str) else "")) for k, v in f.items()}
            print(f"- {did[:8]} | {str(tit)[:60]} | campos: {campos}")
            refs = buscar_ids(f, caps)
            if refs:
                print(f"     REFERENCIA a capítulos: {[titulo[r][0] + ' (' + r[:8] + ')' for r in refs]}")
            # desafíos: resolver los días del schedule
            if col == "auto-challenges" and isinstance(f.get("schedule"), str):
                try:
                    sched = parse_edn(f["schedule"])
                    ids = [x for sem in sched for x in sem if x]
                    sin = [x for x in ids if x not in titulo]
                    print(f"     schedule: {len(ids)} días, {len(sin)} sin colección")
                    for x in ids[:30]:
                        print(f"        {x[:8]} -> {titulo.get(x, ('(no existe)', 0))[0]} ({titulo.get(x, ('', 0))[1]} problemas)")
                except Exception as e:
                    print("     schedule no interpretable:", e)

    json.dump(volcado, open("find_chapters_dump.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nVolcado completo en find_chapters_dump.json")

if __name__ == "__main__":
    main()