import json, re, time, requests

API_KEY = "AIzaSyC-lnkKAtRoCd30xecSXWQ77xhla9S44I8"
RT_PATH = "awesomebaduk_rt"  # ajusta al nombre real de tu fichero del token
HEADERS = {"Referer": "https://awesomebaduk.com/"}
BASE = "https://firestore.googleapis.com/v1/projects/badol-online-academy/databases/(default)/documents"

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

schedule = json.load(open("challenge.json", encoding="utf-8"))["schedule"]
weeks = re.findall(r"\[([^\[\]]*)\]", schedule[1:-1])
days = []
for w, week in enumerate(weeks):
    for d, tok in enumerate(re.findall(r'"([^"]+)"|\bnil\b', week)):
        if tok:
            days.append({"week": w, "day": d, "id": tok})
print("días en schedule:", len(days))

for item in days:
    rr = requests.get(f"{BASE}/problem-collections/{item['id']}", headers=H)
    if rr.status_code != 200:
        print("error", item["week"], item["day"], rr.status_code)
        continue
    item["doc"] = {k: plain(v) for k, v in rr.json()["fields"].items()}
    time.sleep(0.3)

json.dump(days, open("days.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("descargados:", sum(1 for x in days if "doc" in x))
first = days[0].get("doc", {})
print("title:", first.get("title"))
print("tipo de problems:", type(first.get("problems")).__name__)
print(json.dumps(first.get("problems"), ensure_ascii=False)[:700])