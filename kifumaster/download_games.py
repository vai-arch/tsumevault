import time
import random
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
LIST_DIR = ROOT_DIR / "data" / "lists"
USER_DATA_DIR = ROOT_DIR / "browser_profile"

BASE_DELAY = 6              # base entre partidas (se añade jitter)
INITIAL_ERROR_DELAY = 15
MAX_ERROR_DELAY = 900       # 15 min máximo
TIMEOUT = 60

# Pausa larga cada N descargas correctas
PAUSE_EVERY = 30
PAUSE_MIN = 45
PAUSE_MAX = 120


# --------------------------------------------------
# LOCALIZAR ARCHIVOS DE PARTIDAS
# --------------------------------------------------

def find_pending_files():
    pending_files = []

    if not LIST_DIR.exists():
        print(f"[ERROR] No existe la carpeta: {LIST_DIR}")
        return pending_files

    for competition_dir in sorted(LIST_DIR.iterdir()):
        if not competition_dir.is_dir():
            continue
        if competition_dir.name.lower().startswith("otros-"):
            continue

        root_list = competition_dir / "games_pendientes.txt"
        if root_list.exists():
            pending_files.append(root_list)
            continue

        for edition_dir in sorted(competition_dir.iterdir()):
            if not edition_dir.is_dir():
                continue
            edition_list = edition_dir / "games_pendientes.txt"
            if edition_list.exists():
                pending_files.append(edition_list)

    return pending_files


# --------------------------------------------------
# ESPERAS HUMANAS
# --------------------------------------------------

def human_delay(base=BASE_DELAY):
    return base + random.uniform(1.5, 4.0)


def calculate_error_delay(consecutive_errors):
    delay = INITIAL_ERROR_DELAY * (2 ** (consecutive_errors - 1))
    return min(delay, MAX_ERROR_DELAY) + random.uniform(0, 5)


# --------------------------------------------------
# DESCARGA DE UNA PARTIDA
# --------------------------------------------------

def download_game(page, game_id, output_dir):
    url = f"https://kifumaster.org/game/{game_id}"
    print(f"\n[DOWNLOAD] {game_id}")

    try:
        with page.expect_response(
            lambda r: (
                "firebasestorage.googleapis.com" in r.url
                and f"{game_id}.sgf" in r.url
            ),
            timeout=TIMEOUT * 1000,
        ) as response_info:
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)

        response = response_info.value

        if response.status != 200:
            try:
                body_preview = response.text()[:400]
            except Exception:
                body_preview = "(no se pudo leer el cuerpo)"
            print(f"[ERROR] Firebase HTTP {response.status}")
            print(f"        {body_preview}")
            return False

        content = response.body()

        if not content.lstrip().startswith(b"(;"):
            print("[ERROR] La respuesta no es un SGF válido")
            return False

        output_file = output_dir / f"{game_id}.sgf"
        output_file.write_bytes(content)
        print(f"[OK] Guardado: {output_file}")
        return True

    except PlaywrightTimeoutError:
        print("[ERROR] Timeout esperando la respuesta SGF de Firebase")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


# --------------------------------------------------
# PROCESAR UNA LISTA
# --------------------------------------------------

def process_pending_file(page, pending_file, global_stats):
    output_dir = pending_file.parent

    game_ids = [
        line.strip()
        for line in pending_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    print("\n" + "=" * 65)
    print(f"COMPETICIÓN / EDICIÓN: {pending_file.parent.relative_to(ROOT_DIR)}")
    print(f"Partidas en lista: {len(game_ids)}")
    print("=" * 65)

    consecutive_errors = 0
    attempted_games = 0

    for index, game_id in enumerate(game_ids, start=1):
        output_file = output_dir / f"{game_id}.sgf"

        # Saltar archivos ya descargados
        if output_file.exists() and output_file.stat().st_size > 0:
            global_stats["skipped"] += 1
            global_stats["processed"] += 1
            print(f"[SKIP] {game_id} ({index}/{len(game_ids)})")
            continue

        # Espera antes del siguiente intento
        if attempted_games > 0:
            if consecutive_errors == 0:
                delay = human_delay(BASE_DELAY)
                print(f"[WAIT] {delay:.1f} segundos")
            else:
                delay = calculate_error_delay(consecutive_errors)
                print(
                    f"[BACKOFF] {consecutive_errors} fallos consecutivos. "
                    f"Esperando {delay:.1f} segundos."
                )
            time.sleep(delay)

        attempted_games += 1
        success = download_game(page, game_id, output_dir)

        global_stats["processed"] += 1
        global_stats["download_attempts"] += 1

        if success:
            global_stats["downloaded"] += 1
            consecutive_errors = 0

            # Pausa larga periódica
            if global_stats["downloaded"] % PAUSE_EVERY == 0:
                pause = random.uniform(PAUSE_MIN, PAUSE_MAX)
                print(f"[PAUSA LARGA] {pause:.0f}s para no saturar...")
                time.sleep(pause)
        else:
            global_stats["errors"] += 1
            consecutive_errors += 1

        print(
            f"Progreso: {global_stats['processed']} "
            f"| OK: {global_stats['downloaded']} "
            f"| Error: {global_stats['errors']} "
            f"| Omitidas: {global_stats['skipped']}"
        )


# --------------------------------------------------
# PROGRAMA PRINCIPAL
# --------------------------------------------------

def main():
    pending_files = find_pending_files()

    if not pending_files:
        print("[INFO] No se han encontrado archivos games_pendientes.txt")
        return

    print(f"Archivos de listas encontrados: {len(pending_files)}")

    global_stats = {
        "processed": 0,
        "downloaded": 0,
        "errors": 0,
        "skipped": 0,
        "download_attempts": 0,
    }

    USER_DATA_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chrome",  # Chrome real (más estable)
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900},
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://kifumaster.org", wait_until="domcontentloaded")

        input(
            "\n>>> Si no estás logueado: General → Sign in (mejor Email/Password).\n"
            ">>> Cuando el error de Firebase haya desaparecido, pulsa Enter aquí..."
        )

        try:
            for pending_file in pending_files:
                process_pending_file(page, pending_file, global_stats)
        finally:
            context.close()

    print("\n" + "=" * 65)
    print("DESCARGA FINALIZADA")
    print("=" * 65)
    print(f"Partidas procesadas: {global_stats['processed']}")
    print(f"Descargadas:         {global_stats['downloaded']}")
    print(f"Errores:             {global_stats['errors']}")
    print(f"Omitidas:            {global_stats['skipped']}")
    print("=" * 65)


if __name__ == "__main__":
    main()