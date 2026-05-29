import re
import json
import base64
import requests

URL = "https://www.101weiqi.com/qday/2026/5/27/1/"

html = requests.get(URL).text

# extraer qqdata
m = re.search(r'var\s+qqdata\s*=\s*(\{.*?\});', html, re.S)

if not m:
    raise Exception("No encontré qqdata")

qqdata = json.loads(m.group(1))

content = qqdata["content"]
ru = qqdata["ru"]

# clave XOR usada por la web
i = ru + 1
key = f"101{i}{i}{i}"

# decode base64
raw = base64.b64decode(content)

# XOR
decoded = bytearray()

for n, b in enumerate(raw):
    decoded.append(b ^ ord(key[n % len(key)]))

stones = json.loads(decoded.decode("utf-8"))

black = stones[0]
white = stones[1]

AB = "".join(f"[{s}]" for s in black)
AW = "".join(f"[{s}]" for s in white)

sgf = f"(;GM[1]FF[4]CA[UTF-8]SZ[19]AB{AB}AW{AW})"

print(sgf)

with open("problem.sgf", "w", encoding="utf-8") as f:
    f.write(sgf)

print("Guardado en problem.sgf")