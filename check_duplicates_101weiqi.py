import json
import os
from collections import defaultdict

INPUT_DIR = r"D:\Go\tsumevault\_sources_scripts\output"

problem_to_books = defaultdict(list)

for book_id_str in os.listdir(INPUT_DIR):
    book_dir = os.path.join(INPUT_DIR, book_id_str)
    book_json = os.path.join(book_dir, "book.json")
    if not os.path.isfile(book_json):
        continue

    with open(book_json, "r", encoding="utf-8") as f:
        book = json.load(f)

    for chap_ref in book.get("chapters", []):
        chap_dir = os.path.join(book_dir, str(chap_ref["id"]))
        chap_json = os.path.join(chap_dir, "chapter.json")
        if not os.path.isfile(chap_json):
            continue
        with open(chap_json, "r", encoding="utf-8") as f:
            chap = json.load(f)
        for p in chap.get("problems", []):
            problem_to_books[p["qid"]].append(int(book_id_str))

duplicates = {qid: books for qid, books in problem_to_books.items() if len(books) > 1}
print(f"Total problemas unicos en JSONs: {len(problem_to_books)}")
print(f"Problemas en mas de un libro  : {len(duplicates)}")
if duplicates:
    print("\nPrimeros 20 duplicados:")
    for qid, books in list(duplicates.items())[:20]:
        print(f"  qid={qid} en libros: {sorted(set(books))}")
