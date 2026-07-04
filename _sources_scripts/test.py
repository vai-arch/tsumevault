import os
from collections import defaultdict

problems_dir = r"C:\Users\victor.diaz\Documents\All\Go\tsumevault\101_weiqi\problems_std"

qid_locations = defaultdict(list)  # qid -> [(book_id, chapter_id)]

for book in os.scandir(problems_dir):
    if not book.is_dir():
        continue
    for chap in os.scandir(book.path):
        if not chap.is_dir():
            continue
        for f in os.listdir(chap.path):
            if f.lower().endswith(".sgf"):
                try:
                    qid = int(os.path.splitext(f)[0])
                    qid_locations[qid].append((int(book.name), chap.name))
                except ValueError:
                    pass

duplicates = {qid: locs for qid, locs in qid_locations.items() if len(locs) > 1}
print(f"QIDs únicos: {len(qid_locations)}")
print(f"QIDs duplicados: {len(duplicates)}")
print(f"SGFs duplicados (copias extra): {sum(len(v)-1 for v in duplicates.values())}")

# Mostrar algunos ejemplos
for qid, locs in list(duplicates.items())[:5]:
    print(f"  qid {qid}: {locs}")