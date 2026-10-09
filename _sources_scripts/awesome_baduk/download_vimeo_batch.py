#!/usr/bin/env python3
"""
Descarga en batch el audio (y opcionalmente el video) de las lecciones de
awesomebaduk, organizado por curso.

Flujo (lo hace yt-dlp internamente):
    ID -> player.vimeo.com/video/{ID}/config -> master.m3u8 -> pista audio -> .m4a

Estructura de salida:
    <out>/cursos/<Titulo del curso>/
        511881670.m4a
        511881669.m4a
        video/511881670.mp4        (solo con --video)
        course.json                (metadatos del curso, orden y runtimes)
    <out>/manifest.json
    <out>/download.log

Uso (PowerShell):
    python download_vimeo_batch.py lesson.json -o out --ytdlp "C:\\ruta\\yt-dlp.exe"
    python download_vimeo_batch.py carpeta_jsons -o out --video
"""
import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

PAIR_RE = re.compile(r'"([0-9a-fA-F-]{36})"\s*:\s*"/videos/(\d+)"')
COURSE_RE = re.compile(r'"courses/([A-Za-z0-9_-]+)"')
TITLE_RE = re.compile(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"')
BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

log = logging.getLogger("vimeo")


# ----------------------------------------------------------------- parsing
def collect_inputs(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(p.rglob("*.json"))
        elif p.is_file():
            files.append(p)
        else:
            log.warning("No existe: %s", p)
    return files


def _course_from_node(course_id, node):
    uuid_to_vid = {}
    for uuid, path in (node.get("vimeo-ids") or {}).items():
        m = re.search(r"/videos/(\d+)", str(path))
        if m:
            uuid_to_vid[uuid] = m.group(1)

    order, runtimes = [], {}
    for clip in node.get("clips") or []:
        vid = uuid_to_vid.get(clip.get("video-id"))
        if vid and vid not in order:
            order.append(vid)
            runtimes[vid] = clip.get("runtime")
    # videos de vimeo-ids que ningun clip usa (pruebas subidas): por defecto NO se bajan
    extra = [v for v in dict.fromkeys(uuid_to_vid.values()) if v not in order]

    return {
        "id": course_id,
        "title": node.get("title") or course_id,
        "description": node.get("description"),
        "tags": node.get("content-tags"),
        "updated": node.get("updated"),
        "uuid_to_vid": uuid_to_vid,
        "videos": order,
        "extra": extra,
        "runtime_ms": runtimes,
    }


def _walk(node, key, out):
    if isinstance(node, dict):
        if "vimeo-ids" in node:
            out.append(_course_from_node(str(key).split("/")[-1], node))
        else:
            for k, v in node.items():
                _walk(v, k, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, key, out)


def load_courses(f):
    text = f.read_text(encoding="utf-8-sig", errors="replace").strip()
    data = None
    for cand in (text, "{" + text.rstrip(",").strip() + "}"):
        try:
            data = json.loads(cand)
            break
        except json.JSONDecodeError:
            continue

    courses = []
    if data is not None:
        _walk(data, f.stem, courses)
    if courses:
        return courses

    # Fallback: regex (fichero no parseable)
    pairs = PAIR_RE.findall(text)
    if not pairs:
        return []
    cm = COURSE_RE.search(text)
    tm = TITLE_RE.search(text)
    cid = cm.group(1) if cm else f.stem
    title = json.loads('"' + tm.group(1) + '"') if tm else cid
    uuid_to_vid = {u: v for u, v in pairs}
    return [{
        "id": cid, "title": title, "description": None, "tags": None,
        "updated": None, "uuid_to_vid": uuid_to_vid,
        "videos": list(dict.fromkeys(uuid_to_vid.values())), "extra": [],
        "no_clip_info": True, "runtime_ms": {},
    }]


# ------------------------------------------------------------- course dirs
def sanitize(name, maxlen=100):
    name = BAD_CHARS.sub("_", name).strip().rstrip(". ")
    name = re.sub(r"\s+", " ", name)
    return name[:maxlen].rstrip(". ") or "sin_titulo"


def course_dir(root, course, taken):
    """Carpeta cursos/<titulo>. Si el titulo ya lo usa OTRO curso, añade [id]."""
    base = sanitize(course["title"])
    cid = course["id"]

    def owner_of(d):
        meta = d / "course.json"
        if meta.exists():
            try:
                return json.loads(meta.read_text(encoding="utf-8")).get("id")
            except Exception:
                return None
        return None

    cand = root / base
    owner = taken.get(cand.name) or owner_of(cand)
    if owner and owner != cid:
        cand = root / f"{base} [{cid}]"
    taken[cand.name] = cid
    return cand


# ---------------------------------------------------------------- download
def build_cmd(args, vid, mode, outdir):
    url = f"https://player.vimeo.com/video/{vid}"
    cmd = [
        args.ytdlp, "--no-update", "--no-warnings", "--no-playlist",
        "--referer", args.referer,
        "--retries", "5", "--fragment-retries", "5", "--newline",
    ]
    if args.ffmpeg:
        cmd += ["--ffmpeg-location", args.ffmpeg]
    if mode == "audio":
        cmd += ["-f", "ba", "-x", "--audio-format", "m4a",
                "-o", str(outdir / f"{vid}.%(ext)s"), url]
    else:
        cmd += ["-f", "bv*+ba/b", "--merge-output-format", "mp4",
                "-o", str(outdir / f"{vid}.%(ext)s"), url]
    return cmd


_SKIP_IDS = None


def skip_ids(args):
    """Ids de Vimeo ya publicados segun --skip-catalog (se carga una sola vez)."""
    global _SKIP_IDS
    if _SKIP_IDS is None:
        _SKIP_IDS = set()
        ruta_cat = getattr(args, "skip_catalog", None)
        if ruta_cat:
            rows = json.loads(Path(ruta_cat).read_text(encoding="utf-8-sig"))["rows"]
            _SKIP_IDS = {str(r["sourceVimeoId"]) for r in rows if r.get("sourceVimeoId")}
            log.info("Catalogo %s: %d audios ya publicados se saltan", ruta_cat, len(_SKIP_IDS))
    return _SKIP_IDS


def run_one(args, vid, mode, outdir):
    ext = "m4a" if mode == "audio" else "mp4"
    target = outdir / f"{vid}.{ext}"
    if mode == "audio" and not args.force and str(vid) in skip_ids(args):
        return True, "skipped (ya en catalogo)"
    if target.exists() and target.stat().st_size > 0 and not args.force:
        return True, "skipped (ya existe)"

    last_err = ""
    for attempt in range(1, args.attempts + 1):
        proc = subprocess.run(
            build_cmd(args, vid, mode, outdir),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
            return True, "ok"
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        last_err = " | ".join(tail)
        log.warning("%s [%s] intento %d/%d fallo: %s",
                    vid, mode, attempt, args.attempts, last_err)
        time.sleep(2 * attempt)
    return False, last_err or "error desconocido"


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="JSON(s) o carpeta(s)")
    ap.add_argument("-o", "--out", default="out", help="carpeta base (se crea cursos/ dentro)")
    ap.add_argument("--ytdlp", default="yt-dlp", help="ruta a yt-dlp(.exe)")
    ap.add_argument("--ffmpeg", default=None, help="ruta a ffmpeg si no esta en PATH")
    ap.add_argument("--referer", default="https://awesomebaduk.com/")
    ap.add_argument("--video", action="store_true", help="descargar tambien el video")
    ap.add_argument("--video-only", action="store_true", help="solo video")
    ap.add_argument("--all-videos", action="store_true",
                    help="bajar tambien los vimeo-ids que ningun clip usa (por defecto NO)")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--pause", type=float, default=1.0)
    ap.add_argument("--skip-catalog", default=None,
                    help="catalogo de lecciones (awesome_baduk_lessons.json): se saltan los audios "
                         "cuyo id de Vimeo ya figura como sourceVimeoId")
    args = ap.parse_args()

    base = Path(args.out)
    cursos = base / "cursos"
    cursos.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(base / "download.log", encoding="utf-8")],
    )

    courses = []
    for f in collect_inputs(args.inputs):
        found = load_courses(f)
        log.info("%s: %d curso(s)", f.name, len(found))
        courses += found
    if not courses:
        log.error("No se encontro ningun curso con vimeo-ids.")
        return 1

    modes = []
    if not args.video_only:
        modes.append("audio")
    if args.video or args.video_only:
        modes.append("video")

    manifest_path = base / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}

    taken, failures = {}, 0
    for c in courses:
        cdir = course_dir(cursos, c, taken)
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "course.json").write_text(
            json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
        vids = c["videos"] + (c["extra"] if args.all_videos else [])
        skipped = 0 if args.all_videos else len(c["extra"])
        log.info("== Curso: %s  -> %s  (%d videos de clips%s)", c["title"], cdir.name,
                 len(vids), f", {skipped} sobrantes omitidos" if skipped else "")
        if c.get("no_clip_info"):
            log.warning("   (sin informacion de clips: se bajan todos los vimeo-ids)")
        elif not c["videos"]:
            log.warning("   (el curso no tiene clips con video: nada que bajar)")

        vid2uuid = {v: u for u, v in c["uuid_to_vid"].items()}
        for i, vid in enumerate(vids, 1):
            entry = {"course_id": c["id"], "course_title": c["title"],
                     "folder": cdir.name, "uuid": vid2uuid.get(vid),
                     "order": i, "runtime_ms": c["runtime_ms"].get(vid)}
            did_download = False
            for mode in modes:
                outdir = cdir if mode == "audio" else cdir / "video"
                outdir.mkdir(exist_ok=True)
                log.info("[%d/%d] %s (%s)", i, len(vids), vid, mode)
                ok, msg = run_one(args, vid, mode, outdir)
                if not msg.startswith("skipped"):
                    did_download = True
                rel = outdir.relative_to(base) / f"{vid}.{'m4a' if mode == 'audio' else 'mp4'}"
                entry[mode] = {"ok": ok, "msg": msg, "file": rel.as_posix()}
                if not ok:
                    failures += 1
                    log.error("%s [%s] FALLO: %s", vid, mode, msg)
            manifest[f"{c['id']}/{vid}"] = entry
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
            if did_download:
                time.sleep(args.pause)

    log.info("Terminado. Fallos: %d. Manifest: %s", failures, manifest_path)
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
