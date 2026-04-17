import json
import os
import random
import time

import requests

ROOT = "./go_problems"
PROBLEMS_ROOT = os.path.join(ROOT, "problems")

COLLECTIONS_FILE = os.path.join(ROOT, "collections.json")

COLLECTIONS_URL = "https://goproblems.com/api/collections"
COLLECTION_PROBLEMS_URL = "https://goproblems.com/api/collections/{}/problems"
PROBLEM_URL = "https://goproblems.com/api/v2/problems/{}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# ---------------- utils ----------------


def sleep():
    time.sleep(random.uniform(0.4, 1.2))


def slow_sleep(a=0.8, b=1.5):
    time.sleep(random.uniform(a, b))


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)


def save_json(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=(5, 15))
    r.raise_for_status()
    return r.json()


# ---------------- stage 1: collections ----------------s


def get_all_collections():
    offset = 0
    limit = 10
    all_items = []

    while True:
        url = f"{COLLECTIONS_URL}?text=&offset={offset}&limit={limit}&order=Size&sortDirection=desc"
        data = fetch(url)

        items = data.get("entries", [])
        if not items:
            break

        all_items.extend(items)

        if len(items) < limit:
            break

        offset += limit
        sleep()

    return all_items


# ---------------- stage 2: collection problems ----------------


def get_collection_problems(cid):
    offset = 0
    limit = 100
    all_items = []

    while True:
        url = COLLECTION_PROBLEMS_URL.format(cid)
        url += (
            f"?criteria%5Bcollection%5D={cid}"
            f"&criteria%5Blimit%5D={limit}"
            f"&criteria%5Boffset%5D={offset}"
            f"&criteria%5BsortDirection%5D=asc"
            f"&criteria%5BsortBy%5D=elo"
        )

        data = fetch(url)
        items = data.get("entries", [])

        if not items:
            break

        all_items.extend(items)

        if len(items) < limit:
            break

        offset += limit
        sleep()

    return all_items


# ---------------- stage 3: problem detail ----------------


def get_problem(pid):
    url = PROBLEM_URL.format(pid)
    return fetch(url)


# ---------------- pipeline ----------------


def run():
    ensure_dir(ROOT)
    ensure_dir(PROBLEMS_ROOT)

    # 1. collections
    print("Fetching collections...", flush=True)
    collections = get_all_collections()

    save_json(COLLECTIONS_FILE, collections)

    print(f"Saved {len(collections)} collections")

    # 2. per collection → problems list file
    for col in collections:
        cid = col["id"]

        print(f"\nCollection {cid}")

        col_file = os.path.join(ROOT, f"collection_{cid}_problems.json")

        try:
            problems = get_collection_problems(cid)
            save_json(col_file, problems)
        except Exception as e:
            print(f"Failed collection {cid}: {e}")
            continue

        slow_sleep()

        # 3. per problem → full details
        col_folder = os.path.join(PROBLEMS_ROOT, str(cid))
        ensure_dir(col_folder)

        for p in problems:
            pid = p["id"]
            out_file = os.path.join(col_folder, f"{pid}.json")

            if os.path.exists(out_file):
                continue

            try:
                detail = get_problem(pid)
                save_json(out_file, detail)
            except Exception as e:
                print(f"Problem {pid} failed: {e}")

            sleep()

    print("\nDone.")


if __name__ == "__main__":
    run()
