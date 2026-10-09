import json, requests

API_KEY = "AIzaSyC-lnkKAtRoCd30xecSXWQ77xhla9S44I8"
RT_PATH = "awesomebaduk_rt"  # ajusta al nombre real de tu fichero del token
HEADERS = {"Referer": "https://awesomebaduk.com/"}
BASE = "https://firestore.googleapis.com/v1/projects/badol-online-academy/databases/(default)/documents"
CHALLENGE = "bc55b5f0-db45-47ab-a1be-700e18e90301"

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

rt = open(RT_PATH, encoding="utf-8").read().strip()
r = requests.post(f"https://securetoken.googleapis.com/v1/token?key={API_KEY}",
                  data={"grant_type": "refresh_token", "refresh_token": rt}, headers=HEADERS)
r.raise_for_status()
H = {"Authorization": f"Bearer {r.json()['id_token']}", **HEADERS}

r = requests.get(f"{BASE}/auto-challenges/{CHALLENGE}", headers=H)
r.raise_for_status()
doc = {k: plain(v) for k, v in r.json()["fields"].items()}
json.dump(doc, open("challenge.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

print("title:", doc.get("title"))
print("start-date:", doc.get("start-date"))
print("tipo de schedule:", type(doc["schedule"]).__name__)
print(json.dumps(doc["schedule"], ensure_ascii=False, indent=1)[:1500])