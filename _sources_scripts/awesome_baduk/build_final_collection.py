#!/usr/bin/env python3
"""
Construye la coleccion DEFINITIVA de audios a partir del JSON original.

- Fuente de verdad: clips[].video-id  (UUID) -> vimeo-ids[UUID] -> ID de Vimeo.
  Los vimeo-ids que ningun clip referencia se consideran sobrantes y NO se copian.
- Copia (no mueve) desde out/cursos/<curso>/{ID}.m4a  a  out/cursos_final/<curso>/{ID}.m4a
- Genera:
    <dst>/cursos.csv     listado de cursos
    <dst>/report.json    faltantes, sobrantes y avisos
    <dst>/<curso>/course.json   metadatos + clips en orden (runtime, problemas, audio)

Uso (desde ...\\awesome_baduk):
    python build_final_collection.py cursos_originales.json
    python build_final_collection.py carpeta_con_jsons --check-duration
    python build_final_collection.py original.json --dry-run
"""
import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CSV_COLUMNS = ["ID", "Title", "runtime", "#Clips", "#Downloaded Clips", "#Problems",
               "target-group", "author", "contentTags", "description",
               "runtime_s", "Folder"]


# ------------------------------------------------------------------ helpers
def sanitize(name, maxlen=100):
    name = BAD_CHARS.sub("_", name or "").strip().rstrip(". ")
    name = re.sub(r"\s+", " ", name)
    return name[:maxlen].rstrip(". ") or "sin_titulo"


def fmt_hms(ms):
    s = int(round((ms or 0) / 1000))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def flat(text):
    """Una sola linea: \\n, \\r y espacios repetidos pasan a un espacio."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def collect_inputs(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(p.rglob("*.json"))
        elif p.is_file():
            files.append(p)
        else:
            print(f"[aviso] no existe: {p}")
    return files


def load_json_fragment(path):
    """Acepta JSON valido o un fragmento tipo  "courses/xxx": {...},  ..."""
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    err = None
    for cand in (text, "{" + text.rstrip(",").strip() + "}"):
        try:
            return json.loads(cand, strict=False)
        except json.JSONDecodeError as e:
            err = e
    raise SystemExit(f"No pude parsear {path}: {err}")


def find_courses(node, key, out):
    if isinstance(node, dict):
        if "clips" in node or "vimeo-ids" in node:
            out.append((str(key).split("/")[-1], node))
        else:
            for k, v in node.items():
                find_courses(v, k, out)
    elif isinstance(node, list):
        for v in node:
            find_courses(v, key, out)


def build_course(cid, node):
    uuid2vid = {}
    for u, p in (node.get("vimeo-ids") or {}).items():
        m = re.search(r"/videos/(\d+)", str(p))
        if m:
            uuid2vid[u] = m.group(1)

    clips = []
    for i, c in enumerate(node.get("clips") or [], 1):
        u = c.get("video-id")
        probs = [p["id"] for p in (c.get("problems") or [])
                 if isinstance(p, dict) and p.get("id")]
        clips.append({"order": i, "clip_video_uuid": u,
                      "vimeo_id": uuid2vid.get(u),
                      "runtime_ms": c.get("runtime"),
                      "problems": probs})

    tags = node.get("content-tags") or []
    return {
        "id": cid,
        "title": (node.get("title") or cid).strip(),
        "description": node.get("description") or "",
        "tags": tags,
        "target_group": node.get("target-group") or "",
        "author": node.get("author") or "",
        "updated": node.get("updated"),
        "published": node.get("published"),
        "uuid_to_vid": uuid2vid,
        "clips": clips,
    }


def index_source(src):
    """{course_id: carpeta} leyendo los course.json que escribio el downloader."""
    idx = {}
    if src.is_dir():
        for d in src.iterdir():
            meta = d / "course.json"
            if d.is_dir() and meta.exists():
                try:
                    idx[json.loads(meta.read_text(encoding="utf-8")).get("id")] = d
                except Exception:
                    pass
    return idx


def final_dir(dst, course, taken):
    base = sanitize(course["title"])
    cand = dst / base
    owner = taken.get(cand.name)
    if owner is None and (cand / "course.json").exists():
        try:
            owner = json.loads((cand / "course.json").read_text(encoding="utf-8")).get("id")
        except Exception:
            owner = None
    if owner and owner != course["id"]:
        cand = dst / f"{base} [{course['id']}]"
    taken[cand.name] = course["id"]
    return cand


def probe_duration(ffprobe, path):
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
        return float(out.stdout.strip())
    except Exception:
        return None


def copy_if_needed(src, dst, force, dry):
    if dst.exists() and dst.stat().st_size == src.stat().st_size and not force:
        return "ya existia"
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return "copiado"


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="JSON(s) originales o carpeta")
    ap.add_argument("--src", default="out/cursos", help="carpeta con lo descargado")
    ap.add_argument("--dst", default="out/cursos_final", help="carpeta definitiva")
    ap.add_argument("--include-video", action="store_true",
                    help="copiar tambien video/{ID}.mp4 si existe")
    ap.add_argument("--check-duration", action="store_true",
                    help="comparar duracion del audio con runtime del clip (ffprobe)")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--tolerance", type=float, default=2.0, help="segundos")
    ap.add_argument("--delimiter", default=",",
                    help='separador del CSV; usa ";" para abrirlo con doble clic '
                         'en Excel con configuracion regional espanola')
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    if not src.is_dir():
        raise SystemExit(f"No existe la carpeta origen: {src}")

    courses = []
    for f in collect_inputs(args.inputs):
        found = []
        find_courses(load_json_fragment(f), f.stem, found)
        print(f"{f.name}: {len(found)} curso(s)")
        courses += [build_course(cid, node) for cid, node in found]
    if not courses:
        raise SystemExit("No se encontro ningun curso.")

    src_index = index_source(src)
    taken, rows, report = {}, [], {"courses": {}, "totals": {}}
    tot = {"clips": 0, "present": 0, "missing": 0, "orphans": 0, "copied": 0}

    for c in courses:
        cid = c["id"]
        sdir = src_index.get(cid)
        if sdir is None and (src / sanitize(c["title"])).is_dir():
            sdir = src / sanitize(c["title"])
        ddir = final_dir(dst, c, taken)

        rep = {"title": c["title"], "source_folder": sdir.name if sdir else None,
               "missing": [], "orphans": [], "warnings": []}
        if sdir is None:
            rep["warnings"].append("carpeta origen no encontrada")

        expected = []
        for clip in c["clips"]:
            vid = clip["vimeo_id"]
            if vid is None:
                rep["warnings"].append(
                    f"clip {clip['order']}: video-id {clip['clip_video_uuid']} "
                    f"no esta en vimeo-ids")
            elif vid not in expected:
                expected.append(vid)

        # copiar audios esperados
        present = set()
        for vid in expected:
            s = sdir / f"{vid}.m4a" if sdir else None
            if s and s.exists() and s.stat().st_size > 0:
                status = copy_if_needed(s, ddir / f"{vid}.m4a", args.force, args.dry_run)
                present.add(vid)
                if status == "copiado":
                    tot["copied"] += 1
                if args.include_video:
                    v = sdir / "video" / f"{vid}.mp4"
                    if v.exists():
                        copy_if_needed(v, ddir / "video" / f"{vid}.mp4",
                                       args.force, args.dry_run)
            else:
                rep["missing"].append(vid)

        # sobrantes: .m4a en origen que ningun clip usa (no se borra nada)
        if sdir:
            for f in sorted(sdir.glob("*.m4a")):
                if f.stem not in expected:
                    rep["orphans"].append(f.stem)

        # clips en orden + comprobacion de duracion opcional
        clip_out = []
        for clip in c["clips"]:
            vid = clip["vimeo_id"]
            ok = vid in present
            entry = dict(clip)
            entry["audio"] = f"{vid}.m4a" if ok else None
            if ok and args.check_duration and clip["runtime_ms"]:
                dur = probe_duration(args.ffprobe, sdir / f"{vid}.m4a")
                if dur is None:
                    rep["warnings"].append(f"{vid}: ffprobe no pudo leer la duracion")
                else:
                    diff = dur - clip["runtime_ms"] / 1000
                    entry["audio_seconds"] = round(dur, 1)
                    if abs(diff) > args.tolerance:
                        rep["warnings"].append(
                            f"{vid}: audio {dur:.1f}s vs runtime "
                            f"{clip['runtime_ms'] / 1000:.1f}s (dif {diff:+.1f}s)")
            clip_out.append(entry)

        n_clips = len(c["clips"])
        n_down = sum(1 for e in clip_out if e["audio"])
        n_probs = len({p for e in clip_out for p in e["problems"]})
        total_ms = sum((e["runtime_ms"] or 0) for e in clip_out)

        rows.append({
            "ID": cid, "Title": flat(c["title"]), "runtime": fmt_hms(total_ms),
            "#Clips": n_clips, "#Downloaded Clips": n_down, "#Problems": n_probs,
            "target-group": c["target_group"], "author": c["author"],
            "contentTags": ";".join(c["tags"]), "description": flat(c["description"]),
            "runtime_s": round(total_ms / 1000), "Folder": ddir.name,
        })

        if not args.dry_run:
            ddir.mkdir(parents=True, exist_ok=True)
            meta = {k: c[k] for k in ("id", "title", "description", "tags",
                                      "target_group", "author", "updated", "published")}
            meta["runtime_ms_total"] = total_ms
            meta["clips"] = clip_out
            (ddir / "course.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        report["courses"][cid] = rep
        tot["clips"] += n_clips
        tot["present"] += n_down
        tot["missing"] += len(rep["missing"])
        tot["orphans"] += len(rep["orphans"])
        flag = "OK " if not rep["missing"] and not rep["warnings"] else "!! "
        print(f"{flag}{c['title'][:60]:60} clips {n_down}/{n_clips}"
              f"  faltan {len(rep['missing'])}  sobrantes {len(rep['orphans'])}"
              f"  avisos {len(rep['warnings'])}")

    report["totals"] = tot
    if not args.dry_run:
        dst.mkdir(parents=True, exist_ok=True)
        with open(dst / "cursos.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=args.delimiter)
            w.writeheader()
            w.writerows(rows)
        (dst / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nCSV:     {dst / 'cursos.csv'}\nInforme: {dst / 'report.json'}")
    print(f"\nTotales: {tot}")
    return 0 if tot["missing"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
