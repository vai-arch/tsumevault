import json
import os
import re
import time

import requests

BASE = "https://www.101weiqi.com"

COOKIES = {
    "sessionid": "r7h03pga7jsblaugo1v98pgoq9os7zb3",
    "csrftoken": "3LCgrbJDglVy9MS4gx3oMEt9OIH69bbf",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.101weiqi.com/",
}


session = requests.Session()
session.headers.update(HEADERS)
session.cookies.update(COOKIES)


# ---------------------------
# utils
# ---------------------------


def get(url):
    r = session.get(url)
    r.raise_for_status()
    return r.text


def extract_js_object(html, varname):
    pattern = rf"var {varname} = (\{{.*?\}});"
    m = re.search(pattern, html, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def safe_mkdir(path):
    os.makedirs(path, exist_ok=True)


# ---------------------------
# step 1: book page
# ---------------------------


def parse_book(book_id):
    url = f"{BASE}/book/{book_id}/"
    html = get(url)

    data = extract_js_object(html, "nodedata")
    if not data:
        raise Exception("nodedata not found")

    chapters = []

    # chapters are implicit in subs or links
    for sub in data.get("pagedata", {}).get("subs", []):
        chapters.append(sub)

    return data, chapters


# ---------------------------
# step 2: chapter page
# ---------------------------


def parse_chapter(book_id, chapter_id):
    url = f"{BASE}/book/{book_id}/{chapter_id}/"
    html = get(url)

    data = extract_js_object(html, "nodedata")
    if not data:
        raise Exception("chapter nodedata missing")

    qs = data["pagedata"]["qs"]
    return data, qs


# ---------------------------
# step 3: problem page
# ---------------------------


def parse_problem(qid):
    url = f"{BASE}/problem/{qid}/"
    html = get(url)

    data = extract_js_object(html, "qqdata")
    if not data:
        raise Exception(f"qqdata missing for {qid}")

    return data


# ---------------------------
# SGF handling (raw export)
# ---------------------------


def save_sgf(book_id, chapter_id, problem_id, qqdata, outdir="data"):
    path = f"{outdir}/{book_id}/{chapter_id}"
    safe_mkdir(path)

    sgf_path = f"{path}/{problem_id}.sgf"
    json_path = f"{path}/{problem_id}.json"

    # ⚠️ we do NOT decode content — store raw
    sgf_raw = qqdata.get("content", "")

    with open(sgf_path, "w", encoding="utf-8") as f:
        f.write(sgf_raw)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(qqdata, f, ensure_ascii=False, indent=2)


# ---------------------------
# main pipeline
# ---------------------------


def run(books):
    for book in books:
        book_id = book["bookRef"]

        print("BOOK:", book_id)

        book_data, chapters = parse_book(book_id)

        # fallback if subs not reliable
        chapter_ids = book_data["pagedata"].get("subs", [])

        for chapter_id in chapter_ids:
            print("  CHAPTER:", chapter_id)

            try:
                chapter_data, qs = parse_chapter(book_id, chapter_id)
            except Exception as e:
                print("    chapter error:", e)
                continue

            for q in qs:
                qid = q["qid"]

                print("    PROBLEM:", qid)

                try:
                    qqdata = parse_problem(qid)
                    save_sgf(book_id, chapter_id, qid, qqdata)
                except Exception as e:
                    print("      problem error:", e)

                time.sleep(0.3)  # light throttle


# ---------------------------
# entry
# ---------------------------

if __name__ == "__main__":
    with open("books.json", "r", encoding="utf-8") as f:
        books = json.load(f)

    run(books)
