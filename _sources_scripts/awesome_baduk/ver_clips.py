import json, collections

ARCHIVO = "find_chapters_dump.json"

def forma(v):
    if isinstance(v, dict):
        return "dict{" + ", ".join(list(v)[:6]) + ("…" if len(v) > 6 else "") + "}"
    if isinstance(v, (list, tuple)):
        return f"list[{len(v)}]" + (f" de {forma(v[0])}" if v else "")
    if isinstance(v, str):
        return f"str({len(v)}): {v[:50]!r}"
    return type(v).__name__

def main():
    datos = json.load(open(ARCHIVO, encoding="utf-8"))
    cursos = {k: v for k, v in datos.items() if k.startswith("courses/")}
    con_problemas = []
    tipos = collections.Counter()
    for k, c in cursos.items():
        clips = c.get("clips") or []
        total = 0
        for cl in clips:
            p = cl.get("problems")
            tipos[type(p).__name__] += 1
            if p:
                total += len(p)
        if total:
            con_problemas.append((c.get("title") or "(sin título)", len(clips), total, k.split("/")[1][:8]))
    print(f"cursos: {len(cursos)} | con clips que traen problemas: {len(con_problemas)}")
    print("tipo del campo problems en los clips:", dict(tipos))
    print("\n--- Lecciones L-Shape ---")
    for k, c in cursos.items():
        if "l-shape" in (c.get("title") or "").lower():
            print(f"\n{c.get('title')} ({k.split('/')[1][:8]}) | target-group: {c.get('target-group')} | tags: {c.get('content-tags')}")
            for i, cl in enumerate(c.get("clips") or [], 1):
                print(f"  clip {i}: runtime {cl.get('runtime')} | video {str(cl.get('video-id'))[:8]} | problems: {forma(cl.get('problems'))}")
    print("\n--- Primeras 25 lecciones con problemas en clips (título | clips | problemas | id) ---")
    for t, nc, tot, i in sorted(con_problemas, key=lambda x: x[0].lower())[:25]:
        print(f"{t[:60]} | {nc} | {tot} | {i}")

if __name__ == "__main__":
    main()