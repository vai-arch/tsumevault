import json
import re

import requests

cookies = {
    "sessionid": "r7h03pga7jsblaugo1v98pgoq9os7zb3",
    "csrftoken": "3LCgrbJDglVy9MS4gx3oMEt9OIH69bbf",
}
headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.101weiqi.com/"}

r = requests.get(
    "https://www.101weiqi.com/book/30115/21813/11128/", cookies=cookies, headers=headers
)
for line in r.text.splitlines():
    if "var qqdata" in line:
        dd = json.loads(
            re.search(r"var qqdata = (.+);?\s*$", line).group(1).rstrip(";")
        )
        for k, v in dd.get("andata", {}).items():
            print(
                f"node {k}: pt={v.get('pt')} subs={v.get('subs')} o={v.get('o')} c={v.get('c')} f={v.get('f')} tip={v.get('tip')}"
            )
