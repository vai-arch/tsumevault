#!/usr/bin/env python3
"""
Extrae de lessons.json el enlace  clip -> problemas  (clips[].problems = [{"id": ...}]).
Genera un fichero pequeno (lesson_problems.json) para trabajar los problemas de las lecciones
sin cargar con el export completo.

Uso (PowerShell, desde ...\\awesome_baduk):
    python extract_lesson_problems.py lessons.json --ids player_test\\player\\lesson_ids.json --out lesson_problems.json

--ids es opcional: con el registro de IDs de la conversion (lesson_ids.json) cada entrada lleva el
lessonId (900000+) de la leccion correspondiente; sin el, queda a null.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import awesome_to_player as A  # noqa: E402  (reutiliza su lector del export)


def problem_ids(clip):
    out = []
    for p in clip.get('problems') or []:
        pid = p.get('id') if isinstance(p, dict) else p
        if isinstance(pid, str) and pid:
            out.append(pid)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('course_json')
    ap.add_argument('--ids', default=None, help='lesson_ids.json del conversor (para incluir el lessonId)')
    ap.add_argument('--out', default='lesson_problems.json')
    args = ap.parse_args()

    ids = {}
    if args.ids:
        ids = json.loads(Path(args.ids).read_text(encoding='utf-8'))

    entries, total_clips, courses_with = [], 0, set()
    refs = collections.Counter()
    for cid, course in A.load_course(args.course_json):
        title = (course.get('title') or cid).strip()
        vimeo = {}
        for u, p in (course.get('vimeo-ids') or {}).items():
            tail = str(p).rstrip('/').split('/')[-1]
            vimeo[u] = int(tail) if tail.isdigit() else None
        for ci, clip in enumerate(course.get('clips') or [], 1):
            total_clips += 1
            pids = problem_ids(clip)
            if not pids:
                continue
            courses_with.add(cid)
            refs.update(pids)
            vid_uuid = clip.get('video-id')
            entries.append({
                'lessonId': ids.get(f'{cid}/{vid_uuid}'),
                'courseId': cid,
                'course': title,
                'clip': ci,
                'vimeoId': vimeo.get(vid_uuid),
                'targetGroup': course.get('target-group') or '',
                'problems': pids,
            })

    Path(args.out).write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding='utf-8')
    dup = {k: v for k, v in refs.items() if v > 1}
    print(f'Clips totales: {total_clips} | clips con problemas: {len(entries)} | cursos con problemas: {len(courses_with)}')
    print(f'Referencias a problemas: {sum(refs.values())} | ids distintos: {len(refs)} | ids que salen en mas de un clip: {len(dup)}')
    if args.ids:
        print(f'Entradas sin lessonId (clip no convertido o sin audio): {sum(1 for e in entries if e["lessonId"] is None)}')
    print(f'Escrito {args.out}')


if __name__ == '__main__':
    main()
