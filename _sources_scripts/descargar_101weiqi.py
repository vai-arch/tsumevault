"""
descargar_101weiqi.py
Scraper para 101weiqi.com — descarga problemas como SGF + JSON.

Usa requests para book/chapter y Playwright para problemas
(necesario para obtener el estado completo del tablero renderizado).

Estructura de salida:
  output/{book_id}/book.json
  output/{book_id}/{chapter_id}/chapter.json
  output/{book_id}/{chapter_id}/{problem_id}.sgf
  output/{book_id}/{chapter_id}/{problem_id}.json

Uso:
  python descargar_101weiqi.py --books books.json [--config config.json] [--output output] [--delay-min 2.0] [--delay-max 5.0]
"""

import argparse
import json
import logging
import random
import re
import sys
import time
from pathlib import Path

import requests
from deep_translator import GoogleTranslator
from playwright.sync_api import Page, sync_playwright

# ── Constantes ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.101weiqi.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.101weiqi.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MAX_RETRIES = 5
BACKOFF_BASE = 2.0

GO_TERMS = {
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
    "死活": "Life and Death",
    "手筋": "Tesuji",
    "官子": "Endgame",
    "布局": "Fuseki",
    "定式": "Joseki",
    "中盘": "Middlegame",
    "吃子": "Capture",
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
    "落子题": "Stone placement",
    "死活题": "Life and Death",
    "手筋题": "Tesuji",
    "官子题": "Endgame",
    "定式题": "Joseki",
    "布局题": "Fuseki",
    "对杀题": "Capturing race",
    "黑先": "Black first",
    "白先": "White first",
    "白净死": "White dies cleanly",
    "白淨死": "White dies cleanly",
    "黑先活": "Black lives",
    "黑先死": "Black kills",
    "先手": "Sente",
    "后手": "Gote",
    "上册": "Volume 1",
    "下册": "Volume 2",
    "上": "Upper",
    "下": "Lower",
    "篇": "Chapter",
    "级": "Kyu",
    "段": "Dan",
}

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("descargar_101weiqi.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Traducción ────────────────────────────────────────────────────────────────

_translate_cache: dict[str, str] = {}
_translator = GoogleTranslator(source="zh-CN", target="en")


def translate(text: str) -> str:
    if not text or not text.strip():
        return text
    text = text.strip()
    if text in GO_TERMS:
        return GO_TERMS[text]
    if text in _translate_cache:
        return _translate_cache[text]
    working = text
    for zh, en in sorted(GO_TERMS.items(), key=lambda x: -len(x[0])):
        working = working.replace(zh, en)
    if not any("\u4e00" <= c <= "\u9fff" for c in working):
        _translate_cache[text] = working
        return working
    try:
        translated = _translator.translate(working)
        if translated:
            _translate_cache[text] = translated
            return translated
    except Exception as e:
        log.debug(f"Error traduciendo '{text[:50]}': {e}")
    _translate_cache[text] = text
    return text


# ── SGF desde andata ──────────────────────────────────────────────────────────


def andata_to_sgf(qqdata: dict, black_stones: list, white_stones: list) -> str:
    andata = qqdata.get("andata", {})
    if not andata:
        return None

    lu = qqdata.get("lu", 19)
    blackfirst = qqdata.get("blackfirst", True)
    title = qqdata.get("name") or qqdata.get("title") or ""
    levelname = qqdata.get("levelname", "")
    qtypename = qqdata.get("qtypename", "")
    vote = qqdata.get("vote", 0)
    yes_count = qqdata.get("yes_count", 0)
    no_count = qqdata.get("no_count", 0)
    desc = qqdata.get("desc") or ""

    def node_color(depth: int) -> str:
        if blackfirst:
            return "B" if depth % 2 == 1 else "W"
        else:
            return "W" if depth % 2 == 1 else "B"

    def build_node(node_id: int, depth: int) -> str:
        node = andata.get(str(node_id))
        if node is None:
            return ""
        pt = node.get("pt", "")
        subs = node.get("subs", [])
        o = node.get("o", 0)
        c = node.get("c", 0)
        f = node.get("f", 0)
        tip = node.get("tip", "")
        parts = []
        if depth > 0 and pt:
            color = node_color(depth)
            parts.append(f"{color}[{pt}]")
        if not subs:
            comments = []
            tip_en = translate(tip) if tip else ""
            if o == 1 or c == 1:
                if "RIGHT" not in tip_en.upper():
                    comments.append("RIGHT")
            elif f == 1:
                if "WRONG" not in tip_en.upper():
                    comments.append("WRONG")
            if tip_en:
                comments.append(tip_en)
            if comments:
                comment_str = " — ".join(comments)
                parts.append(f"C[{comment_str}]")
        node_str = ";" + "".join(parts)
        if not subs:
            return node_str
        if len(subs) == 1:
            return node_str + build_node(subs[0], depth + 1)
        branches = "".join(f"({build_node(s, depth + 1)})" for s in subs)
        return node_str + branches

    ab = "".join(f"AB[{s}]" for s in black_stones)
    aw = "".join(f"AW[{s}]" for s in white_stones)
    header = f";FF[4]CA[UTF-8]GM[1]SZ[{lu}]"
    if title:
        title_en = translate(title)
        safe_title = title_en.replace("]", "\\]")
        header += f"GN[{safe_title}]"
    gc_parts = []
    if qtypename:
        gc_parts.append(f"Type: {translate(qtypename)}")
    if levelname:
        gc_parts.append(f"Level: {levelname}")
    if vote:
        total = yes_count + no_count
        pct = round(yes_count / total * 100) if total > 0 else 0
        gc_parts.append(f"Rating: {vote}/5")
        gc_parts.append(f"Correct: {pct}% ({yes_count}/{total})")
    if desc:
        gc_parts.append(f"Desc: {translate(desc)}")
    first_move = "Black" if blackfirst else "White"
    gc_parts.append(f"First move: {first_move}")
    if gc_parts:
        gc_str = " | ".join(gc_parts).replace("]", "\\]")
        header += f"GC[{gc_str}]"
    if ab:
        header += ab
    if aw:
        header += aw
    tree = build_node(0, 0)
    return f"({header}{tree})"


# ── JSON de libro/capítulo/problema ──────────────────────────────────────────


def extract_book_json(bookdata: dict) -> dict:
    return {
        "id": bookdata.get("id"),
        "name": bookdata.get("name", ""),
        "name_en": translate(bookdata.get("name", "")),
        "desc": bookdata.get("desc", ""),
        "desc_en": translate(bookdata.get("desc", "")) if bookdata.get("desc") else "",
        "nodecount": bookdata.get("nodecount", 0),
        "chapters": [
            {
                "id": ch.get("id"),
                "name": ch.get("name", ""),
                "name_en": translate(ch.get("name", "")),
                "nodecount": ch.get("nodecount", 0),
                "isfree": ch.get("isfree", False),
            }
            for ch in bookdata.get("chapters", [])
        ],
    }


def extract_chapter_json(nodedata: dict) -> dict:
    pd = nodedata.get("pagedata", {})
    return {
        "id": pd.get("id"),
        "name": pd.get("name", ""),
        "name_en": translate(pd.get("name", "")),
        "desc": pd.get("desc", ""),
        "nodecount": pd.get("nodecount", 0),
        "problems": [
            {
                "qid": q.get("qid"),
                "qindex": q.get("qindex"),
                "levelname": q.get("levelname", ""),
                "blackfirst": q.get("blackfirst", True),
            }
            for q in pd.get("qs", [])
        ],
    }


def extract_problem_json(qqdata: dict, black_stones: list, white_stones: list) -> dict:
    title = qqdata.get("name") or qqdata.get("title") or ""
    desc = qqdata.get("desc") or ""
    qtypename = qqdata.get("qtypename", "")
    yes_count = qqdata.get("yes_count", 0)
    no_count = qqdata.get("no_count", 0)
    total = yes_count + no_count
    pct = round(yes_count / total * 100) if total > 0 else 0
    andata_clean = {}
    for node_id, node in (qqdata.get("andata") or {}).items():
        tip = node.get("tip", "")
        andata_clean[node_id] = {
            "id": node.get("id"),
            "p": node.get("p"),
            "subs": node.get("subs", []),
            "pt": node.get("pt", ""),
            "o": node.get("o", 0),
            "c": node.get("c", 0),
            "f": node.get("f", 0),
            "tip": tip,
            "tip_en": translate(tip) if tip else "",
        }
    return {
        "id": qqdata.get("id"),
        "qtype": qqdata.get("qtype"),
        "qtypename": qtypename,
        "qtypename_en": translate(qtypename) if qtypename else "",
        "levelname": qqdata.get("levelname", ""),
        "title": title,
        "title_en": translate(title) if title else "",
        "desc": desc,
        "desc_en": translate(desc) if desc else "",
        "lu": qqdata.get("lu", 19),
        "blackfirst": qqdata.get("blackfirst", True),
        "prepos": qqdata.get("prepos", [[], []]),
        "black_stones": black_stones,
        "white_stones": white_stones,
        "vote": qqdata.get("vote", 0),
        "yes_count": yes_count,
        "no_count": no_count,
        "correct_pct": pct,
        "sx": qqdata.get("sx"),
        "sy": qqdata.get("sy"),
        "pos_x1": qqdata.get("pos_x1"),
        "pos_x2": qqdata.get("pos_x2"),
        "pos_y1": qqdata.get("pos_y1"),
        "pos_y2": qqdata.get("pos_y2"),
        "andata": andata_clean,
    }


# ── HTTP con reintentos (para book/chapter) ───────────────────────────────────


def get_with_retry(
    session: requests.Session, url: str, delay_range: tuple
) -> requests.Response | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 503):
                wait = BACKOFF_BASE**attempt + random.uniform(0, 1)
                log.warning(
                    f"HTTP {resp.status_code} en {url} — espera {wait:.1f}s (intento {attempt}/{MAX_RETRIES})"
                )
                time.sleep(wait)
                continue
            if resp.status_code in (403, 404):
                log.warning(f"HTTP {resp.status_code} en {url} — sin acceso, skip")
                return None
            log.warning(
                f"HTTP {resp.status_code} inesperado en {url} — intento {attempt}/{MAX_RETRIES}"
            )
            time.sleep(BACKOFF_BASE * attempt)
        except requests.RequestException as e:
            wait = BACKOFF_BASE**attempt
            log.warning(
                f"Error de red en {url}: {e} — espera {wait:.1f}s (intento {attempt}/{MAX_RETRIES})"
            )
            time.sleep(wait)
    log.error(f"Fallaron {MAX_RETRIES} intentos para {url}")
    return None


def polite_sleep(delay_range: tuple):
    time.sleep(random.uniform(*delay_range))


# ── Extracción de variables JS ────────────────────────────────────────────────


def extract_js_var(html: str, varname: str) -> dict | None:
    pattern = rf"var\s+{varname}\s*=\s*(\{{.*?\}});?\s*\n"
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        pattern2 = rf"var\s+{varname}\s*=\s*(\{{.+?\}})(?:\s*;|\s*\n)"
        match = re.search(pattern2, html, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        log.debug(f"JSON inválido en var {varname}: {e}")
        return None


# ── Playwright: extraer estado del tablero ────────────────────────────────────

EXTRACT_BOARD_JS = """() => {
    try {
        const elements = document.querySelectorAll('[x-data]');
        for (const el of elements) {
            const data = el._x_dataStack;
            if (!data) continue;
            for (const d of data) {
                if (d && d.game && d.game.wqp) {
                    const wqp = d.game.wqp;
                    const size = wqp.qipan.state.config.size;
                    const vertices = wqp.qipan.state.curr.vertices;
                    const letters = 'abcdefghijklmnopqrstuvwxyz';
                    const black = [], white = [];
                    for (let x = 0; x < size; x++) {
                        for (let y = 0; y < size; y++) {
                            const v = vertices[x * size + y];
                            const coord = letters[y] + letters[x];
                            if (v === 1) black.push(coord);
                            else if (v === 2) white.push(coord);
                        }
                    }
                    return {black, white, size, ok: true};
                }
            }
        }
        return {ok: false, error: 'game.wqp not found'};
    } catch(e) {
        return {ok: false, error: e.toString()};
    }
}"""


def playwright_get_problem(
    page: Page, url: str, delay_range: tuple
) -> tuple[dict | None, list, list]:
    """
    Navega a la URL del problema con Playwright.
    Devuelve (qqdata, black_stones, white_stones).
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            polite_sleep(delay_range)

            # Extraer qqdata del HTML
            html = page.content()

            # Detectar throttling
            if "qqdata" not in html:
                log.warning("  Posible throttling — pausa 60-120s")
                time.sleep(random.uniform(60, 120))
                continue

            qqdata = extract_js_var(html, "qqdata")
            if not qqdata:
                log.warning(f"  qqdata no encontrado en {url}")
                return None, [], []

            # Extraer piedras del DOM renderizado
            board = page.evaluate(EXTRACT_BOARD_JS)
            if board.get("ok"):
                return qqdata, board["black"], board["white"]
            else:
                log.warning(
                    f"  Board extract falló: {board.get('error')} — usando prepos"
                )
                prepos = qqdata.get("prepos", [[], []])
                return (
                    qqdata,
                    prepos[0] if prepos else [],
                    prepos[1] if len(prepos) > 1 else [],
                )

        except Exception as e:
            wait = BACKOFF_BASE**attempt
            log.warning(
                f"  Error Playwright en {url}: {e} — espera {wait:.1f}s (intento {attempt}/{MAX_RETRIES})"
            )
            time.sleep(wait)

    log.error(f"  Fallaron {MAX_RETRIES} intentos Playwright para {url}")
    return None, [], []


# ── Pipeline principal ────────────────────────────────────────────────────────


def scrape_problem(
    page: Page,
    qid: int,
    book_id: int,
    chapter_id: int,
    out_dir: Path,
    delay_range: tuple,
) -> bool:
    sgf_path = out_dir / str(book_id) / str(chapter_id) / f"{qid}.sgf"
    json_path = out_dir / str(book_id) / str(chapter_id) / f"{qid}.json"

    if sgf_path.exists() and json_path.exists():
        log.debug(f"  Skip qid={qid} (ya existe)")
        return True

    url = f"{BASE_URL}/book/{book_id}/{chapter_id}/{qid}/"
    qqdata, black_stones, white_stones = playwright_get_problem(page, url, delay_range)

    if not qqdata:
        log.warning(f"  No se pudo obtener qid={qid}")
        return False

    andata = qqdata.get("andata")
    if not andata:
        log.warning(f"  Sin andata en qid={qid} (qtype={qqdata.get('qtype')}) — skip")
        return False

    try:
        sgf = andata_to_sgf(qqdata, black_stones, white_stones)
        problem_json = extract_problem_json(qqdata, black_stones, white_stones)
    except Exception as e:
        log.error(f"  Error procesando qid={qid}: {e}")
        return False

    if not sgf:
        log.warning(f"  SGF vacío para qid={qid} — skip")
        return False

    sgf_path.parent.mkdir(parents=True, exist_ok=True)
    sgf_path.write_text(sgf, encoding="utf-8")
    json_path.write_text(
        json.dumps(problem_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"  ✓ qid={qid} → {sgf_path}")
    return True


def scrape_chapter(
    session: requests.Session,
    page: Page,
    book_id: int,
    chapter: dict,
    out_dir: Path,
    delay_range: tuple,
) -> tuple[int, int]:
    chapter_id = chapter["id"]
    chapter_name = chapter.get("name", "?")
    url = f"{BASE_URL}/book/{book_id}/{chapter_id}/"

    log.info(f"  Capítulo {chapter_id} '{chapter_name}'")

    resp = get_with_retry(session, url, delay_range)
    polite_sleep(delay_range)

    if resp is None:
        log.warning(f"  No se pudo obtener capítulo {chapter_id} — skip")
        return 0, 0

    nodedata = extract_js_var(resp.text, "nodedata")
    if not nodedata:
        log.warning(
            f"  nodedata no encontrado en capítulo {chapter_id} — posible acceso denegado"
        )
        return 0, 0

    chapter_json_path = out_dir / str(book_id) / str(chapter_id) / "chapter.json"
    if not chapter_json_path.exists():
        try:
            chapter_data = extract_chapter_json(nodedata)
            chapter_json_path.parent.mkdir(parents=True, exist_ok=True)
            chapter_json_path.write_text(
                json.dumps(chapter_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            log.warning(f"  Error guardando chapter.json: {e}")

    qs = nodedata.get("pagedata", {}).get("qs", [])
    if not qs:
        log.warning(f"  Sin problemas en capítulo {chapter_id}")
        return 0, 0

    ok = 0
    failed = 0
    for q in qs:
        qid = q.get("qid")
        if qid is None:
            continue
        if scrape_problem(page, qid, book_id, chapter_id, out_dir, delay_range):
            ok += 1
        else:
            failed += 1

    return ok, failed


def scrape_book(
    session: requests.Session,
    page: Page,
    book_id: int,
    out_dir: Path,
    delay_range: tuple,
) -> bool:
    url = f"{BASE_URL}/book/{book_id}/"
    log.info(f"Libro {book_id} — {url}")

    resp = get_with_retry(session, url, delay_range)
    polite_sleep(delay_range)

    if resp is None:
        log.warning(f"Libro {book_id} inaccesible — skip")
        return False

    bookdata = extract_js_var(resp.text, "bookdata")
    if not bookdata:
        log.warning(
            f"Libro {book_id}: bookdata no encontrado — posible acceso denegado, skip"
        )
        return False

    book_name = bookdata.get("name", "?")
    chapters = bookdata.get("chapters", [])
    log.info(f"  '{book_name}' — {len(chapters)} capítulos")

    book_json_path = out_dir / str(book_id) / "book.json"
    if not book_json_path.exists():
        try:
            book_data = extract_book_json(bookdata)
            book_json_path.parent.mkdir(parents=True, exist_ok=True)
            book_json_path.write_text(
                json.dumps(book_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            log.warning(f"  Error guardando book.json: {e}")

    total_ok = 0
    total_failed = 0
    for chapter in chapters:
        ok, failed = scrape_chapter(
            session, page, book_id, chapter, out_dir, delay_range
        )
        total_ok += ok
        total_failed += failed

    log.info(f"  Libro {book_id} completado: {total_ok} OK, {total_failed} fallidos")
    return True


def main():
    parser = argparse.ArgumentParser(description="Scraper de 101weiqi.com")
    parser.add_argument(
        "--books", default="books.json", help="JSON con lista de book_ids"
    )
    parser.add_argument(
        "--config", default="config.json", help="JSON con cookies de sesión"
    )
    parser.add_argument("--output", default="output", help="Directorio de salida")
    parser.add_argument(
        "--delay-min", type=float, default=2.0, help="Delay mínimo entre requests (seg)"
    )
    parser.add_argument(
        "--delay-max", type=float, default=5.0, help="Delay máximo entre requests (seg)"
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        log.error(f"No se encontró {config_path}")
        sys.exit(1)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    cookies = config.get("cookies", {})

    books_path = Path(args.books)
    if not books_path.exists():
        log.error(f"No se encontró {books_path}")
        sys.exit(1)
    books_data = json.loads(books_path.read_text(encoding="utf-8"))

    book_ids = []
    for entry in books_data:
        if isinstance(entry, int):
            book_ids.append(entry)
        elif isinstance(entry, dict):
            bid = entry.get("id") or entry.get("book_id") or entry.get("bookRef")
            if bid:
                book_ids.append(int(bid))

    if not book_ids:
        log.error("books.json no contiene IDs válidos")
        sys.exit(1)

    log.info(f"Total libros en books.json: {len(book_ids)}")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    delay_range = (args.delay_min, args.delay_max)

    # Sesión requests para book/chapter
    session = requests.Session()
    session.cookies.update(cookies)

    # Playwright para problemas
    pw_cookies = [
        {"name": k, "value": v, "domain": ".101weiqi.com", "path": "/"}
        for k, v in cookies.items()
    ]

    accessible = 0
    skipped = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )
        ctx.add_cookies(pw_cookies)
        page = ctx.new_page()

        for book_id in book_ids:
            ok = scrape_book(session, page, book_id, out_dir, delay_range)
            if ok:
                accessible += 1
            else:
                skipped += 1

        browser.close()

    log.info(
        f"Finalizado. Libros accesibles: {accessible}, sin acceso/error: {skipped}"
    )


if __name__ == "__main__":
    main()
