"""
organizar_videos.py - Mueve los MP4 grabados a su carpeta en videos/.

Uso:
    python organizar_videos.py <carpeta_mp4> [carpeta_raiz]

    carpeta_mp4  : carpeta donde están los MP4 descargados (ej: C:\\Users\\Victor\\Downloads)
    carpeta_raiz : raíz del proyecto donde está all_lessons.json y se creará videos/
                   (por defecto: directorio actual)

Ejemplo:
    python organizar_videos.py "C:\\Users\\Victor\\Downloads"
    python organizar_videos.py "C:\\Users\\Victor\\Downloads" "D:\\GoVideos\\Guo Juan"

El script:
  1. Lee all_lessons.json para construir el índice id→lección
  2. Recorre carpeta_mp4 buscando ficheros *.mp4
  3. Extrae el ID del nombre con regex [ID{n}]
  4. Construye la ruta destino en videos/ con la misma estructura que lessons/
  5. Mueve el fichero
"""

import os
import re
import sys
import json
import shutil

# =========================
# CONFIG
# =========================

LESSONS_FILE = "all_lessons.json"
VIDEOS_DIR   = "D:\\Go\\GoVideos\\Guo Juan"

# =========================
# HELPERS
# =========================

def sanitize(name):
    """Réplica exacta de descargar_lecciones.py."""
    forbidden = r'\/:*?"<>|'
    for ch in forbidden:
        name = name.replace(ch, "_")
    return name.strip().rstrip(".")


def video_dir(lesson, videos_root):
    type_name       = sanitize(lesson.get("typeName", "Unknown").strip())
    collection_name = sanitize(lesson.get("collectionName", "Unknown").strip())
    lesson_name     = sanitize(lesson.get("lessonName", "Unknown").strip())

    return os.path.join(videos_root, type_name, collection_name, lesson_name)


ID_RE = re.compile(r'\[ID(\d+)\]', re.IGNORECASE)

def extract_id(filename):
    """Extrae el lessonId del nombre del fichero. Devuelve int o None."""
    m = ID_RE.search(filename)
    return int(m.group(1)) if m else None

mp4_dir     = os.path.dirname(os.path.abspath(__file__))
root_dir    = mp4_dir
videos_root = os.path.join(root_dir, VIDEOS_DIR)
lessons_file = os.path.join(root_dir, LESSONS_FILE)

if not os.path.isdir(mp4_dir):
    print(f"Error: '{mp4_dir}' no es una carpeta válida.")
    sys.exit(1)

if not os.path.isfile(lessons_file):
    print(f"Error: no se encuentra '{lessons_file}'.")
    sys.exit(1)

# =========================
# CARGAR ÍNDICE
# =========================

with open(lessons_file, "r", encoding="utf-8") as f:
    data = json.load(f)

lessons_by_id = {r["lessonId"]: r for r in data["rows"] if r}
print(f"Lecciones en índice: {len(lessons_by_id)}")

# =========================
# BUSCAR MP4
# =========================

mp4_files = [
    f for f in os.listdir(mp4_dir)
    if f.lower().endswith(".mp4") and os.path.isfile(os.path.join(mp4_dir, f))
]

print(f"MP4 encontrados    : {len(mp4_files)}")
print("=" * 60)

# =========================
# MOVER
# =========================

ok_count  = 0
err_count = 0

for fname in sorted(mp4_files):
    lesson_id = extract_id(fname)

    if lesson_id is None:
        print(f"[SKIP] Sin ID en nombre: {fname}")
        err_count += 1
        continue

    lesson = lessons_by_id.get(lesson_id)
    if lesson is None:
        print(f"[SKIP] ID {lesson_id} no encontrado en all_lessons.json: {fname}")
        err_count += 1
        continue

    dest_dir = video_dir(lesson, videos_root)
    os.makedirs(dest_dir, exist_ok=True)

    src  = os.path.join(mp4_dir, fname)
    dest = os.path.join(dest_dir, fname)

    if os.path.exists(dest):
        print(f"[SKIP] Ya existe: {dest}")
        continue

    shutil.move(src, dest)
    print(f"[OK] {fname}")
    print(f"     → {os.path.relpath(dest, root_dir)}")
    ok_count += 1

# =========================
# RESUMEN
# =========================

print("=" * 60)
print(f"Movidos : {ok_count}")
print(f"Errores : {err_count}")
