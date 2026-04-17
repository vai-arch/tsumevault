import json
import re
from collections import Counter
from pathlib import Path

root = Path("go_problems/problems")

problems = []
for f in root.rglob("*.json"):
    try:
        with open(f, encoding="utf-8") as fh:
            problems.append(json.load(fh))
    except Exception:
        pass

corpus = [p for p in problems if p.get("isCanon") or p.get("isStandard")]
total = len(corpus)
print(f"Canon+Standard: {total} problemas\n")

# ── 1. Dificultad (elo) ──
elos = [p["elo"] for p in corpus if p.get("elo") is not None]
elos_sorted = sorted(elos)
buckets = Counter()
for e in elos:
    if e < 800:
        buckets["< 800 (~20k+)"] += 1
    elif e < 1000:
        buckets["800–1000 (~15-20k)"] += 1
    elif e < 1200:
        buckets["1000–1200 (~10-15k)"] += 1
    elif e < 1400:
        buckets["1200–1400 (~5-10k)"] += 1
    elif e < 1600:
        buckets["1400–1600 (~1-5k)"] += 1
    elif e < 1800:
        buckets["1600–1800 (~1-3d)"] += 1
    elif e < 2000:
        buckets["1800–2000 (~3-5d)"] += 1
    else:
        buckets["2000+ (~5d+)"] += 1

print("── 1. Dificultad (elo) ──")
print(
    f"  Min: {min(elos):.0f}  Max: {max(elos):.0f}  Media: {sum(elos) / len(elos):.0f}"
)
for label in [
    "< 800 (~20k+)",
    "800–1000 (~15-20k)",
    "1000–1200 (~10-15k)",
    "1200–1400 (~5-10k)",
    "1400–1600 (~1-5k)",
    "1600–1800 (~1-3d)",
    "1800–2000 (~3-5d)",
    "2000+ (~5d+)",
]:
    n = buckets[label]
    print(f"  {label:25}  {n:5d} ({n / total * 100:4.1f}%)")

# ── 2. Cobertura de colecciones ──
print("\n── 2. Nº de colecciones por problema ──")
tag_counts = Counter(len(p.get("collections") or []) for p in corpus)
for k in sorted(tag_counts):
    n = tag_counts[k]
    print(f"  {k} tags:  {n:5d} ({n / total * 100:4.1f}%)")

# ── 3. Genre / specificGenre ──
print("\n── 3. Genre ──")
genres = Counter(p.get("genre") or "null" for p in corpus)
for g, n in genres.most_common():
    print(f"  {n:5d} ({n / total * 100:4.1f}%)  {g}")

print("\n── 3b. specificGenre ──")
sgenres = Counter(p.get("specificGenre") or "null" for p in corpus)
for g, n in sgenres.most_common():
    print(f"  {n:5d} ({n / total * 100:4.1f}%)  {g}")

# ── 4. Tamaño de tablero ──
print("\n── 4. Tamaño de tablero ──")
sz_re = re.compile(r"SZ\[(\d+)\]")
sizes = Counter()
for p in corpus:
    sgf = p.get("sgf") or ""
    m = sz_re.search(sgf)
    sizes[int(m.group(1)) if m else 19] += 1
for s, n in sizes.most_common():
    print(f"  {s:2d}x{s:<2d}  {n:5d} ({n / total * 100:4.1f}%)")

# ── 5. Rating ──
print("\n── 5. Rating (Canon+Standard) ──")
with_votes = [p for p in corpus if (p.get("rating") or {}).get("votes", 0) > 0]
no_votes = total - len(with_votes)
print(f"  Con votos:  {len(with_votes):5d} ({len(with_votes) / total * 100:.1f}%)")
print(f"  Sin votos:  {no_votes:5d} ({no_votes / total * 100:.1f}%)")
stars = Counter(round((p.get("rating") or {}).get("stars", 0)) for p in with_votes)
for s in sorted(stars):
    n = stars[s]
    print(f"  {s}★  {n:5d} ({n / len(with_votes) * 100:4.1f}%)")

corpus_elo0 = [p for p in corpus if p.get("elo") == 0]
print(f"elo=0: {len(corpus_elo0)}")

print("\n── 3. Genre como agrupación principal ──")
from collections import defaultdict

by_genre = defaultdict(list)
for p in corpus:
    by_genre[p.get("genre") or "null"].append(p)

for genre, probs in sorted(by_genre.items(), key=lambda x: -len(x[1])):
    canon = sum(1 for p in probs if p.get("isCanon"))
    standard = sum(1 for p in probs if not p.get("isCanon") and p.get("isStandard"))
    sz19 = sum(1 for p in probs if True)  # ya filtrado arriba
    print(f"\n  {genre} ({len(probs)} problemas)")
    print(f"    Canon: {canon}  Solo-Standard: {standard}")
    # sub-agrupación por specificGenre (por si difiere en el futuro)
    sg = Counter(p.get("specificGenre") or "null" for p in probs)
    for g, n in sg.most_common():
        print(f"    specificGenre '{g}': {n}")
    # tableros
    sizes = Counter()
    for p in probs:
        sgf = p.get("sgf") or ""
        m = sz_re.search(sgf)
        sizes[int(m.group(1)) if m else 19] += 1
    print(f"    Tableros: {dict(sizes.most_common())}")
print("── Colecciones más frecuentes en Canon+Standard ──")
tag_freq = Counter()
for p in corpus:
    for c in p.get("collections") or []:
        tag_freq[c["name"]] += 1

for name, n in tag_freq.most_common(30):
    print(f"  {n:5d}  {name}")

print("\n── Top colecciones por genre ──")
for genre in ["life and death", "tesuji"]:
    sub = [p for p in corpus if p.get("genre") == genre]
    freq = Counter()
    for p in sub:
        for c in p.get("collections") or []:
            freq[c["name"]] += 1
    print(f"\n  {genre}:")
    for name, n in freq.most_common(10):
        print(f"    {n:5d}  {name}")

print("── Distribución por rank en Canon+Standard ──")
ranks = Counter()
for p in corpus:
    r = p.get("rank") or {}
    val = r.get("value")
    unit = r.get("unit")
    if val is not None:
        ranks[f"{val} {unit}"] += 1
    else:
        ranks["null"] += 1

for label, n in sorted(
    ranks.items(),
    key=lambda x: (
        0 if "kyu" in x[0] else 1 if "dan" in x[0] else 2,
        -int(x[0].split()[0]) if x[0] != "null" else 0,
    ),
):
    print(f"  {label:8}  {n:5d}")
print("── elo=0 ──")
print(f"  {sum(1 for p in corpus if p.get('elo') == 0)}")

print("\n── Sin rating (null o sin votos) ──")
print(f"  {sum(1 for p in corpus if not (p.get('rating') or {}).get('votes', 0))}")

print("\n── Rating bajo (1-2★) con votos ──")
low = [
    p
    for p in corpus
    if (p.get("rating") or {}).get("votes", 0) >= 3
    and round((p.get("rating") or {}).get("stars", 5)) <= 2
]
print(f"  {len(low)}")

print("\n── hasNegativeFlags (ya sabemos: 29 canon, 0 standard) ──")
print(f"  {sum(1 for p in corpus if p.get('hasNegativeFlags'))}")

print("\n── SGF vacío o muy corto ──")
short = [p for p in corpus if len(p.get("sgf") or "") < 50]
print(f"  {len(short)}")

print("\n── Sin colecciones (ningún tag) ──")
print(f"  {sum(1 for p in corpus if not p.get('collections'))}")

no_votes = [p for p in corpus if not (p.get("rating") or {}).get("votes", 0)]
canon_nv = sum(1 for p in no_votes if p.get("isCanon"))
standard_nv = sum(1 for p in no_votes if not p.get("isCanon") and p.get("isStandard"))
print(f"Sin votos — Canon: {canon_nv}  Solo-Standard: {standard_nv}")

final = [
    p
    for p in corpus
    if p.get("isCanon")
    or (p.get("isStandard") and (p.get("rating") or {}).get("votes", 0) > 0)
]
print(f"Canon + Standard-con-votos: {len(final)}")
final_ids = {p["id"] for p in final}
lost = [p for p in corpus if p["id"] not in final_ids]
print(f"Excluidos: {len(lost)}")

print("\n── Excluidos por rank ──")
ranks_lost = Counter()
for p in lost:
    r = p.get("rank") or {}
    val = r.get("value")
    unit = r.get("unit")
    ranks_lost[f"{val} {unit}" if val else "null"] += 1

for label, n in sorted(
    ranks_lost.items(),
    key=lambda x: (
        0 if "kyu" in x[0] else 1 if "dan" in x[0] else 2,
        -int(x[0].split()[0]) if x[0] != "null" else 0,
    ),
):
    print(f"  {label:8}  {n:5d}")
