import json, collections
from list_inventory import login, listar

ARCHIVO = "find_chapters_dump.json"

def main():
    datos = json.load(open(ARCHIVO, encoding="utf-8"))
    uso = collections.defaultdict(list)   # problem_id -> [(lección, nº clip)]
    n_lecc = n_prob = 0
    for k, c in datos.items():
        if not k.startswith("courses/"):
            continue
        n_lecc += 1
        for i, cl in enumerate(c.get("clips") or [], 1):
            for p in cl.get("problems") or []:
                pid = p.get("id") if isinstance(p, dict) else p
                if pid:
                    uso[pid].append((c.get("title") or "(sin título)", i))
                    n_prob += 1
    print(f"lecciones: {n_lecc} | referencias a problemas en clips: {n_prob} | problemas distintos: {len(uso)}")

    H = login()
    cols, est = listar(H, "problem-collections", ["title", "problems"])
    caps = [(cid, f) for cid, f in cols if (f.get("title") or "").strip().lower().startswith("chapter")]
    print(f"colecciones 'Chapter': {len(caps)}\n")
    for cid, f in sorted(caps, key=lambda x: x[1].get("title", "")):
        probs = [p if isinstance(p, str) else p.get("id") for p in (f.get("problems") or [])]
        print(f"{f.get('title')} ({cid[:8]}) | {len(probs)} problemas")
        for pid in probs:
            donde = uso.get(pid)
            if donde:
                resumen = collections.Counter(t for t, _ in donde)
                print(f"    {pid[:8]} -> en lecciones: {dict(resumen)}")
            else:
                print(f"    {pid[:8]} -> no aparece en ninguna lección")

    print("\n--- Problemas por lección de L-Shape (distintos / ya presentes en alguna Chapter) ---")
    en_caps = {p if isinstance(p, str) else p.get("id") for _, f in caps for p in (f.get("problems") or [])}
    for k, c in datos.items():
        if k.startswith("courses/") and "l-shape" in (c.get("title") or "").lower():
            ids = [p.get("id") for cl in c.get("clips") or [] for p in (cl.get("problems") or []) if isinstance(p, dict)]
            print(f"{c.get('title')}: {len(ids)} problemas, {len(set(ids))} distintos, {len(set(ids) & en_caps)} también en colecciones Chapter")

if __name__ == "__main__":
    main()