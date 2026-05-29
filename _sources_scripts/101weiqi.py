import csv
import json
import re

from bs4 import BeautifulSoup

# -----------------------------
# GO TERMINOLOGY DICTIONARY
# -----------------------------

GO_TERMS = {
    # General
    "围棋": "Go",
    "棋": "Go",
    "基础": "Fundamentals",
    "入门": "Beginner",
    "初级": "Elementary",
    "中级": "Intermediate",
    "高级": "Advanced",
    "训练": "Training",
    "习题": "Problems",
    "题集": "Problem Collection",
    "实战": "Practical Play",
    # Life & death / tesuji
    "死活": "Life and Death",
    "手筋": "Tesuji",
    "官子": "Endgame",
    "布局": "Fuseki",
    "定式": "Joseki",
    "中盘": "Middlegame",
    # Your glossary
    "吃子": "Baochi",
    "吃子方向": "Capture direction",
    "逃子": "Escape",
    "逃子方向": "Escape direction",
    "抱吃和包吃": "Atari and capture",
    "门吃": "Capture by atari (menchi)",
    "双打": "Double atari",
    "接不归": "Connect and die",
    "扑吃": "Snapback",
    "枷吃和夹吃": "Net",
    "征子": "Ladder",
    "挖吃": "Wedge",
    "对杀": "Capturing race",
    "紧气": "Liberty-filling tesuji",
    "延气": "Liberty-extending tesuji",
    "有眼杀无眼": "One eye vs no eye",
    "大眼杀小眼": "Big eye vs small eye",
    "连接": "Connection",
    "切断": "Cutting",
    "双活": "Seki",
    "联络": "Connection tesuji",
    "滚打包收": "Squeeze",
    "龟不出头": "Crane's nest",
    "倒扑": "Snapback",
    "两扳长一气": "Extending liberties by two hane",
    "双": "Bamboo joint",
    "打二还一": "Sending two, returning one",
    "三目死活": "Three point life & death",
    "四目死活": "Four point life & death",
    "五目死活": "Five point life & death",
    "六目死活": "Six point life & death",
    "打劫": "Ko",
    "连环劫": "Double ko",
    "基础死活": "Basic life & death",
    "做眼": "Making eyes",
    "聚杀": "Nakade",
    "破眼": "Destroying eyes",
    "布局基础": "Opening basics",
    "棋形": "Shape",
    "简单官子": "Simple endgame",
    "胀牯牛": "Squash / crush",
    "七死八活": "Seven die but eight live",
    "大猪嘴": "Large pig's snout",
    "小猪嘴": "Small pig's snout",
    "盘角曲四": "Bent four in the corner",
    "金柜角": "Carpenter's square",
    "金鸡独立": "Golden chicken standing on one leg",
    "左右同型": "Symmetrical positions",
    "一一妙手": "1-1 point",
    "一二妙手": "1-2 point",
    "立": "Descent",
    "挤": "Squeeze",
    "断": "Cut",
    "扳": "Hane",
    "点": "Nakade",
    "尖": "Kosumi",
    "飞": "Keima",
    "虎": "Tiger's mouth",
    "跳": "One point jump",
    "夹": "Clamp",
    "顶": "Attaching",
    "挖": "Wedge",
    "长": "Extend",
    "扑": "Throw in",
    "跨": "Strike at the waist of the keima",
    "渡": "Connecting underneath",
    "托": "Underneath attachment",
    "枷": "Net",
    "碰": "Press",
    "弃子": "Sacrifice",
    "相思断": "Crosscut",
    "倒脱靴": "Under the stones",
    "大头鬼": "Tombstone squeeze",
    "黄莺扑蝶": "Patting the raccoon's belly",
    "老鼠偷油": "Mouse stealing oil",
    "盘龙眼": "Two headed dragon",
    "整形": "Correct shape",
    "攻击": "Attacking",
    "腾挪": "Sabaki",
    "涛哥十佳": "Yu Qingquan Top 10",
    "盲点": "Blind spot",
}

# -----------------------------
# OPTIONAL MACHINE TRANSLATION
# -----------------------------

USE_GOOGLE_TRANSLATE = False

if USE_GOOGLE_TRANSLATE:
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source="auto", target="en")

# -----------------------------
# TITLE TRANSLATION
# -----------------------------


def translate_go_title(title):

    # glossary replacements (longest first)
    for zh in sorted(GO_TERMS.keys(), key=len, reverse=True):
        en = GO_TERMS[zh]
        title = title.replace(zh, en)

    # optional machine translation for leftovers
    if USE_GOOGLE_TRANSLATE:
        remaining = re.findall(r"[\u4e00-\u9fff]+", title)

        for fragment in set(remaining):
            try:
                translated = translator.translate(fragment)
                title = title.replace(fragment, translated)

            except Exception:
                pass

    # REMOVE leftover chinese characters
    title = re.sub(r"[\u4e00-\u9fff]+", "", title)

    # cleanup formatting
    title = title.replace("（", "(").replace("）", ")").replace("，", ", ")

    # collapse spaces
    title = re.sub(r"\s+", " ", title)

    # cleanup weird empty parentheses
    title = re.sub(r"\(\s*\)", "", title)

    return title.strip()


# -----------------------------
# PARSE HTML
# -----------------------------

with open("101weiqi\getting_started.htm", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

results = []

for row in soup.find_all("tr"):
    a = row.find("a", href=re.compile(r"https://www\.101weiqi\.com/book/\d+/"))

    if not a:
        continue

    href = a["href"]

    # extract book reference
    m = re.search(r"/book/(\d+)/", href)

    if not m:
        continue

    book_ref = m.group(1)

    # original title
    original_title = a.get_text(" ", strip=True)

    # translated title
    translated_title = translate_go_title(original_title)

    # parse metadata
    num_problems = None
    difficulty = None

    for td in row.find_all("td"):
        text = td.get_text(" ", strip=True)

        m2 = re.search(r"(\d+)\s*problem\(s\)\s*[，,]\s*([^\s]+)", text)

        if m2:
            num_problems = int(m2.group(1))
            difficulty = m2.group(2)
            break

    results.append(
        {
            "bookRef": book_ref,
            "bookTitle": original_title,
            "translatedTitle": translated_title,
            "numProblems": num_problems,
            "difficulty": difficulty,
        }
    )

# -----------------------------
# REMOVE DUPLICATES
# -----------------------------

unique = []
seen = set()

for item in results:
    key = item["bookRef"]

    if key not in seen:
        seen.add(key)
        unique.append(item)

# -----------------------------
# OUTPUT JSON
# -----------------------------

with open("books.json", "w", encoding="utf-8") as f:
    json.dump(unique, f, ensure_ascii=False, indent=2)

# -----------------------------
# OUTPUT CSV
# -----------------------------

with open("books.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "bookRef",
            "bookTitle",
            "translatedTitle",
            "numProblems",
            "difficulty",
        ],
    )

    writer.writeheader()
    writer.writerows(unique)

print(f"Parsed {len(unique)} books")
