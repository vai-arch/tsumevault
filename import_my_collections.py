#!/usr/bin/env python3
"""
import_my_collection.py — Validate and load Victor's hand-curated Go problem
collections into TsumeVault via the running server's admin API. This script
never opens tsumeVault.db directly. The DB source name is set with --source
(default: my_collections) and must match the value used in tsumevault.html's
source dropdown.

Expected folder layout under the given root:

    <collection folder>/<chapter folder>/<file>.sgf
    <collection folder>/<chapter folder>/difficulty-<value>   (optional)

  - "difficulty-<value>" is a zero-byte marker file, e.g. "difficulty-20k"
    or "difficulty-3d". It applies to every problem in that chapter folder.
  - No renaming/moving of already-imported folders or files is assumed
    (problem identity is derived from its path).

Usage:
    python import_my_collection.py <path-to-my_collections-folder> [options]

Options:
    --server URL      Base URL of the running tsumevault_server.py
                       (default: http://localhost:3002)
    --token TOKEN      X-Auth-Token header value, if the server requires one.
                       Defaults to the TSUMEVAULT_TOKEN environment variable.
    --validate-only    Only run validation and print the report; never
                       contacts the server.
    --force            Load anyway even if BROKEN problems were found.
                       BROKEN problems themselves are still excluded from
                       the load either way -- this only lifts the "refuse
                       to continue at all" guard.

Exit codes:
    0 - loaded successfully (or --validate-only found nothing blocking)
    1 - validation found ERROR/BROKEN issues, or the server rejected the
        request; nothing was loaded
    2 - usage error (bad root path, etc.)
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

from sgf_lib import SGFParseError, parse_sgf, validate_problem

DIFF_RE = re.compile(r'^difficulty-(\d+)([kd])$', re.IGNORECASE)


def _is_junk_dir(name):
    """Tool/editor-generated folders that can end up inside my_collections
    (e.g. __pycache__ if the scripts are placed inside it, .git, .vscode)
    -- never treated as a collection or chapter."""
    return name.startswith('.') or name.startswith('__')


def kyu_dan_to_num(marker_filename):
    """'difficulty-20k' -> 100, 'difficulty-3d' -> 2300. Matches the exact
    inverse of tsumevault.html's diffLabel() (num<=2000: kyu; num>2000: dan)."""
    m = DIFF_RE.match(marker_filename)
    if not m:
        return None
    n, kind = int(m.group(1)), m.group(2).lower()
    return 2100 - 100 * n if kind == 'k' else 2000 + 100 * n


def find_difficulty_marker(chapter_dir, report, ctx):
    matches = [f for f in os.listdir(chapter_dir)
               if os.path.isfile(os.path.join(chapter_dir, f)) and DIFF_RE.match(f)]
    if len(matches) > 1:
        report['errors'].append(f'{ctx}: multiple difficulty markers found: {matches}')
        return None, None
    if not matches:
        report['warnings'].append(f'{ctx}: no difficulty-<value> marker file found')
        return None, None
    raw = matches[0].split('-', 1)[1]  # e.g. '20k'
    return raw, kyu_dan_to_num(matches[0])


def scan(root_dir):
    """Walks root_dir and returns (collections_payload, report). report has
    'errors' / 'broken' / 'warnings' / 'cosmetic' lists of human-readable
    strings. collections_payload is None if the root itself is unusable."""
    report = {'errors': [], 'broken': [], 'warnings': [], 'cosmetic': []}

    if not os.path.isdir(root_dir):
        report['errors'].append(f'root folder not found: {root_dir}')
        return None, report

    collections = []
    all_top = sorted(d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d)))
    collection_names = []
    for d in all_top:
        if _is_junk_dir(d):
            report['warnings'].append(f'skipped junk directory {os.path.join(root_dir, d)}')
        else:
            collection_names.append(d)
    stray = [f for f in os.listdir(root_dir)
             if not os.path.isdir(os.path.join(root_dir, f))]
    if stray:
        report['warnings'].append(f'unexpected file(s) directly under {root_dir}: {stray}')

    for col_name in collection_names:
        col_dir = os.path.join(root_dir, col_name)
        all_sub = sorted(d for d in os.listdir(col_dir) if os.path.isdir(os.path.join(col_dir, d)))
        chapter_names = []
        for d in all_sub:
            if _is_junk_dir(d):
                report['warnings'].append(f'skipped junk directory {os.path.join(col_dir, d)}')
            else:
                chapter_names.append(d)
        stray = [f for f in os.listdir(col_dir)
                 if not os.path.isdir(os.path.join(col_dir, f))]
        if stray:
            report['warnings'].append(f'unexpected file(s) directly under {col_dir}: {stray}')

        if not chapter_names:
            report['warnings'].append(
                f'{col_dir}: no chapter subfolders found -- skipped entirely, '
                f'nothing sent to the server for it')
            continue

        chapters_payload = []
        for chap_name in chapter_names:
            chap_dir = os.path.join(col_dir, chap_name)
            ctx = chap_dir

            subdirs = [d for d in os.listdir(chap_dir)
                       if os.path.isdir(os.path.join(chap_dir, d))]
            if subdirs:
                report['errors'].append(
                    f'{ctx}: unexpected subfolder(s) {subdirs} -- expected exactly '
                    f'<collection>/<chapter>/<files>, no deeper nesting')

            diff_raw, diff_num = find_difficulty_marker(chap_dir, report, ctx)

            sgf_files = sorted(f for f in os.listdir(chap_dir) if f.lower().endswith('.sgf'))
            other_files = sorted(
                f for f in os.listdir(chap_dir)
                if os.path.isfile(os.path.join(chap_dir, f))
                and not f.lower().endswith('.sgf')
                and not DIFF_RE.match(f)
            )
            if other_files:
                report['warnings'].append(f'{ctx}: unrecognized file(s) ignored: {other_files}')

            problems_payload = []
            for order, fname in enumerate(sgf_files, start=1):
                fpath = os.path.join(chap_dir, fname)
                rel = os.path.relpath(fpath, root_dir).replace('\\', '/')
                problem_id = os.path.splitext(rel)[0]
                sgf_path = 'my_collections/' + rel

                try:
                    with open(fpath, 'rb') as fh:
                        text = fh.read().decode('utf-8', errors='replace')
                    root_node = parse_sgf(text)
                except (SGFParseError, Exception) as e:
                    report['errors'].append(f'{fpath}: failed to parse -- {e}')
                    continue

                result = validate_problem(root_node)
                for sev, msg in result['issues']:
                    line = f'{fpath}: {msg}'
                    bucket = {'ERROR': 'errors', 'BROKEN': 'broken',
                              'WARNING': 'warnings', 'COSMETIC': 'cosmetic'}[sev]
                    report[bucket].append(line)

                if result['has_error'] or result['has_broken']:
                    continue  # excluded from payload -- fix and re-run

                problems_payload.append({
                    'problem_id': problem_id,
                    'sgf_path': sgf_path,
                    'order_in_chapter': order,
                    'color_to_play': result['color_to_play'],
                })

            chapters_payload.append({
                'folder': chap_name,
                'difficulty_raw': diff_raw,
                'difficulty_num': diff_num,
                'problems': problems_payload,
            })

        collections.append({
            'folder': col_name,
            'chapters': chapters_payload,
        })

    return collections, report


def print_report(report):
    sections = [
        ('ERRORS -- excluded, must fix', 'errors'),
        ('BROKEN -- excluded (app would mis-score these), needs a fix', 'broken'),
        ('WARNINGS -- informational, nothing excluded', 'warnings'),
        ('COSMETIC -- harmless typos the app already treats as correct', 'cosmetic'),
    ]
    for label, key in sections:
        items = report[key]
        print(f'\n=== {label}: {len(items)} ===')
        for line in items:
            print(f'  - {line}')


def post_import(server, source, collections, token):
    url = server.rstrip('/') + '/admin/import_my_collection'
    payload = json.dumps({'source': source, 'collections': collections}).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Auth-Token'] = token
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {'error': 'non-JSON error response'}
    except urllib.error.URLError as e:
        return None, {'error': str(e)}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root', help='Path to the my_collections folder')
    ap.add_argument('--server', default='http://localhost:3002')
    ap.add_argument('--token', default=os.environ.get('TSUMEVAULT_TOKEN', ''))
    ap.add_argument('--source', default='my_collections',
                     help="Value stored in the DB's source column for every "
                          "row this script writes (default: my_collections). "
                          "Must exactly match the value used in tsumevault.html's "
                          "source dropdown <option value=\"...\">.")
    ap.add_argument('--validate-only', action='store_true')
    ap.add_argument('--force', action='store_true',
                     help='Load anyway even if BROKEN problems were found '
                          '(those specific problems are still excluded)')
    args = ap.parse_args()

    print(f"Using source='{args.source}' (change with --source if this is wrong)\n")

    collections, report = scan(args.root)
    print_report(report)

    if collections is None:
        sys.exit(2)

    total = sum(len(ch['problems']) for col in collections for ch in col['chapters'])
    print(f'\n{total} problem(s) ready to load across {len(collections)} collection(s).')

    if report['errors']:
        print('\nRefusing to continue: fix the ERRORS above first.')
        sys.exit(1)

    if report['broken'] and not args.force:
        print('\nRefusing to continue: BROKEN problems found (see above).')
        print('Fix them, or re-run with --force to load everything else and '
              'skip only the broken ones.')
        sys.exit(1)

    if args.validate_only:
        sys.exit(0)

    status, body = post_import(args.server, args.source, collections, args.token)
    print(f'\nServer responded {status}:')
    print(json.dumps(body, indent=2, ensure_ascii=False))
    sys.exit(0 if status == 200 else 1)


if __name__ == '__main__':
    main()
