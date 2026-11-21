#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Keep an article's (or a series') journal: a findings register and a chronology.

journal.md has two parts. «## Находки» is the single register of findings,
with IDs unique within the journal (N001, N002, …) and a status:
open, deferred, applied or rejected. «## Хронология» is an append-only list
of actions: who did what, when, to which section. IDs start with S in the
series journal (next to series-plan.md) and with N in an article journal.

  log   --journal J --actor A --action TEXT [--target FILE]
  add   --journal J --source REVIEW --findings FILE.json [--actor A]
        FILE.json is a list of objects with keys: target, where, severity
        (критично|обычно), kind (бесспорная|спорная|вопрос), before, after, rule.
        In a series journal, target is ARTICLE/FILE.
  set   --journal J --id N001,N002 --status STATUS [--note TEXT] [--actor A]
  list  --journal J [--plan PLAN] [--all]   open and deferred findings
  list  --series SERIES_PLAN [--all]        the same across every article

`add` and `set` also write a chronology line; `add` appends the new IDs to
`findings:` of the review file named by --source (relative to the journal). `list` puts critical findings
first and reports whether every «quoted» fragment of «Было» is still in the
section. The journal is
created on first write. Prints JSON. Exit code 0, or 2 on errors.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml

from granki_core import (KINDS, SEVERITIES, GrankiError, atomic_write, dump_json, load_plan,  # noqa: E402
                         load_series, locked, split_frontmatter)

STATUSES = ('open', 'deferred', 'applied', 'rejected')
PENDING = ('open', 'deferred')
COLUMNS = ['ID', 'Дата', 'Источник', 'Раздел', 'Где', 'Важность', 'Вид', 'Было', 'Стало', 'Правило', 'Статус']
KEYS = {'Раздел': 'target', 'Где': 'where', 'Важность': 'severity', 'Вид': 'kind',
        'Было': 'before', 'Стало': 'after', 'Правило': 'rule'}
QUOTE = re.compile(r'«([^»]+)»')
SKELETON = """# Журнал

## Находки

| {header} |
| {rule} |

## Хронология
"""


def now() -> str:
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')


def cells(line: str) -> list[str]:
    parts = re.split(r'(?<!\\)\|', line.strip())
    return [p.strip() for p in parts[1:-1]]


def cell(value) -> str:
    return ' '.join(str(value or '').split()).replace('|', '\\|')


def unescape(value: str) -> str:
    return (value or '').replace('\\|', '|')


def state(row: dict) -> str:
    """Status word without the note: 'rejected (автор против)' -> 'rejected'."""
    return (row.get('Статус') or 'open').split(' ', 1)[0].strip().lower()


def read(path: Path) -> list[str]:
    if not path.exists():
        return SKELETON.format(header=' | '.join(COLUMNS), rule=' | '.join(['---'] * len(COLUMNS))).splitlines()
    return path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').splitlines()


def table(lines: list[str]) -> tuple[int, int, list[tuple[int, dict]]]:
    """Header line, last table line and rows of the «Находки» table.

    The table runs to the next «## » heading; blank lines inside it are skipped,
    so a hand edit that leaves an empty line does not hide the rows below it.
    """
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == '## Находки')
    except StopIteration:
        raise GrankiError('Journal has no «## Находки» section')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    header_at = next((i for i in range(start, end) if lines[i].startswith('|')), None)
    if header_at is None:
        raise GrankiError('Journal has no findings table')
    header = cells(lines[header_at])
    missing = [c for c in ('ID', 'Статус') if c not in header]
    if missing:
        raise GrankiError('Findings table lacks columns: ' + ', '.join(missing))
    rows, last = [], header_at + 1
    for i in range(header_at + 2, end):
        if not lines[i].startswith('|'):
            continue
        rows.append((i, dict(zip(header, cells(lines[i])))))
        last = i
    problems = []
    ids = [r.get('ID') for _, r in rows]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append('duplicate IDs ' + ', '.join(duplicates))
    unknown = sorted({f'{r.get("ID")}: {r.get("Статус")}' for _, r in rows if state(r) not in STATUSES})
    if unknown:
        problems.append('unknown statuses ' + '; '.join(unknown))
    if problems:
        raise GrankiError('Journal findings table needs fixing: ' + ' | '.join(problems))
    return header_at, last, rows


def write(path: Path, lines: list[str]) -> None:
    atomic_write(path, '\n'.join(lines).rstrip('\n') + '\n')


def append_log(lines: list[str], actor: str, action: str, target: str | None = None) -> list[str]:
    if not any(l.strip() == '## Хронология' for l in lines):
        lines += ['', '## Хронология', '']
    elif lines and lines[-1].strip() == '## Хронология':
        lines = lines + ['']
    entry = ' · '.join(x for x in [now(), actor, target, ' '.join(str(action).split())] if x)
    return lines + [f'- {entry}']


def log_event(path: Path, actor: str, action: str, target: str | None = None) -> None:
    """Append one chronology line under the journal lock."""
    with locked(path):
        write(path, append_log(read(path), actor, action, target))


def prefix_for(path: Path) -> str:
    """S for the series journal (next to series-plan.md), N for an article journal."""
    return 'S' if (path.parent / 'series-plan.md').is_file() else 'N'


def next_ids(rows: list[tuple[int, dict]], count: int, prefix: str = 'N') -> list[str]:
    used = [int(r['ID'][1:]) for _, r in rows if re.fullmatch(r'[NS]\d+', r.get('ID', ''))]
    start = max(used, default=0) + 1
    return [f'{prefix}{n:03d}' for n in range(start, start + count)]


def id_range(ids: list[str]) -> str:
    return ids[0] if len(ids) == 1 else f'{ids[0]}–{ids[-1]}'


def link_review(journal: Path, source: str, ids: list[str]) -> str | None:
    """Add the new IDs to `findings:` of the review file, when the source is one."""
    review = (journal.parent / source)
    if not ids or not review.is_file() or review.suffix != '.md':
        return None
    text = review.read_text(encoding='utf-8')
    meta, body = split_frontmatter(text)
    if not meta.get('scope'):
        return None
    known = [str(i) for i in (meta.get('findings') or [])]
    meta['findings'] = known + [i for i in ids if i not in known]
    atomic_write(review, '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000) + '---\n' + body)
    return str(review)


def normalize(item: dict) -> dict:
    missing = [k for k in ('target', 'severity', 'kind', 'before', 'after') if not item.get(k)]
    if missing:
        raise GrankiError(f'Finding without {", ".join(missing)}: {item}')
    severity, kind = str(item['severity']).strip().lower(), str(item['kind']).strip().lower()
    if severity not in SEVERITIES:
        raise GrankiError(f'severity must be one of {", ".join(SEVERITIES)}, got {item["severity"]!r}')
    if kind not in KINDS:
        raise GrankiError(f'kind must be one of {", ".join(KINDS)}, got {item["kind"]!r}')
    return {**item, 'severity': severity, 'kind': kind}


def add(path: Path, source: str, findings: list[dict], actor: str) -> dict:
    findings = [normalize(f) for f in findings]
    with locked(path):
        lines = read(path)
        _, last, rows = table(lines)
        ids = next_ids(rows, len(findings), prefix_for(path))
        date = datetime.date.today().isoformat()
        new = []
        for fid, item in zip(ids, findings):
            values = {'ID': fid, 'Дата': date, 'Источник': source, 'Статус': 'open',
                      **{col: item.get(key, '') for col, key in KEYS.items()}}
            new.append('| ' + ' | '.join(cell(values[c]) for c in COLUMNS) + ' |')
        lines = lines[:last + 1] + new + lines[last + 1:]
        if not ids:
            lines = append_log(lines, actor, f'ревью без находок: {source}')
        if ids:
            targets = sorted({f['target'] for f in findings})
            lines = append_log(lines, actor, f'добавлено находок: {len(ids)} ({id_range(ids)}) из {source}',
                               ', '.join(targets))
        write(path, lines)
    linked = link_review(path, source, ids)
    return {'status': 'passed', 'journal': str(path), 'added': ids, 'review_updated': linked}


def set_status(path: Path, ids: list[str], status: str, note: str | None, actor: str) -> dict:
    if status not in STATUSES:
        raise GrankiError(f'Unknown status {status!r}; use one of {", ".join(STATUSES)}')
    if not path.exists():
        raise GrankiError(f'Journal not found: {path}')
    with locked(path):
        lines = read(path)
        header_at, _, rows = table(lines)
        column = cells(lines[header_at]).index('Статус')
        found, applied = [], []
        for number, row in rows:
            if row.get('ID') in ids:
                applied.append(row)
                values = cells(lines[number])
                values[column] = status + (f' ({cell(note)})' if note else '')
                lines[number] = '| ' + ' | '.join(values) + ' |'
                found.append(row['ID'])
        missing = sorted(set(ids) - set(found))
        if missing:
            raise GrankiError(f'No findings with ID {", ".join(missing)} in {path.name}')
        lines = append_log(lines, actor, f'{", ".join(found)} → {status}' + (f': {note}' if note else ''))
        write(path, lines)
    pending = sum(1 for _, r in table(lines)[2] if state(r) in PENDING)
    report = {'status': 'passed', 'journal': str(path), 'updated': found, 'pending': pending}
    if status == 'applied':  # an edit that silently failed leaves the quoted text in place
        series = path.parent / 'series-plan.md'
        text = series_reader(series) if series.is_file() else section_reader(path.parent / 'plan.md')
        stale = [f'{row["ID"]}: the quote from «Было» is still in {row.get("Раздел")}; check that the edit was made'
                 for row in applied if still_present(row.get('Было', ''), text(row.get('Раздел'))) is True]
        if stale:
            report['warnings'] = stale
    return report


def still_present(before: str, text: str | None):
    """True when every «quote» in Было is still in the text, False when any is gone,
    None when Было describes rather than quotes or the text is unknown."""
    quotes = [' '.join(q.strip(' …. ').split()) for q in QUOTE.findall(unescape(before))]
    quotes = [q for q in quotes if re.search(r'\w', q)]
    if not quotes or text is None:
        return None
    flat = ' '.join(text.split())
    return all(q in flat for q in quotes)


def section_reader(plan_path: Path | None):
    """Function from a finding's target to the section text, for an article journal."""
    plan = load_plan(plan_path) if plan_path and plan_path.is_file() else None
    cache = {}

    def text(target: str | None):
        if not plan or not target:
            return None
        if target == 'plan.md':  # findings about the article plan
            return plan_path.read_text(encoding='utf-8')
        if target not in cache:
            section = plan['_root'] / plan['sections_dir'] / target
            cache[target] = section.read_text(encoding='utf-8') if section.is_file() else None
        return cache[target]
    return text


def series_reader(series_path: Path):
    """Targets in a series journal are ARTICLE/FILE."""
    root = series_path.parent.resolve()
    readers = {}

    def text(target: str | None):
        if not target:
            return None
        if '/' not in target:  # findings about the series plan itself
            path = root / target
            return path.read_text(encoding='utf-8') if path.is_file() else None
        folder, name = target.split('/', 1)
        if folder not in readers:
            readers[folder] = section_reader(root / folder / 'plan.md')
        return readers[folder](name)
    return text


def describe(path: Path, plan_path: Path | None, everything: bool, reader=None) -> dict:
    if not path.exists():
        return {'journal': str(path), 'pending': 0, 'critical_pending': 0, 'findings': []}
    _, _, rows = table(read(path))
    text = reader or section_reader(plan_path)
    findings = []
    for _, row in rows:
        status = state(row)
        if not everything and status not in PENDING:
            continue
        target = row.get('Раздел')
        findings.append({'id': row.get('ID'), 'status': status, 'severity': row.get('Важность'),
                         'kind': row.get('Вид'), 'target': target, 'where': unescape(row.get('Где')),
                         'source': row.get('Источник'), 'date': row.get('Дата'),
                         'still_present': still_present(row.get('Было', ''), text(target))})
    order = {'критично': 0}
    findings.sort(key=lambda f: (order.get((f['severity'] or '').lower(), 1), f['id'] or ''))
    pending = [r for _, r in rows if state(r) in PENDING]
    return {'journal': str(path), 'pending': len(pending),
            'critical_pending': sum(1 for r in pending if (r.get('Важность') or '').lower() == 'критично'),
            'findings': findings}


def series_list(series_path: Path, everything: bool) -> dict:
    series = load_series(series_path)
    root = series_path.parent.resolve()
    journals = [{'scope': 'series', **describe(root / 'journal.md', None, everything, series_reader(series_path))}]
    for folder in series['articles']:
        journals.append({'scope': 'article', 'article': folder,
                         **describe(root / folder / 'journal.md', root / folder / 'plan.md', everything)})
    return {'status': 'passed', 'series': root.name, 'journals': journals,
            'pending_total': sum(j['pending'] for j in journals)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['log', 'add', 'set', 'list'])
    parser.add_argument('--journal', type=Path, help='journal.md of an article or series')
    parser.add_argument('--series', type=Path, help='series-plan.md (list)')
    parser.add_argument('--plan', type=Path, help='article plan.md, to check quotes (list); default: next to the journal')
    parser.add_argument('--actor', default='агент', help='who acts: агент, автор, or a role name')
    parser.add_argument('--action', help='what happened (log)')
    parser.add_argument('--target', help='section file the action concerns (log)')
    parser.add_argument('--source', help='review file the findings come from (add)')
    parser.add_argument('--findings', type=Path, help='JSON list of findings (add)')
    parser.add_argument('--id', help='comma-separated finding IDs (set)')
    parser.add_argument('--status', help='open, deferred, applied or rejected (set)')
    parser.add_argument('--note', help='short reason stored with the status (set)')
    parser.add_argument('--all', action='store_true', help='list also applied and rejected findings')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            if args.series:
                report = series_list(args.series, args.all)
            elif args.journal:
                plan = args.plan or args.journal.parent / 'plan.md'
                report = {'status': 'passed', **describe(args.journal, plan, args.all)}
            else:
                raise GrankiError('list needs --journal or --series')
        elif not args.journal:
            raise GrankiError(f'{args.command} needs --journal')
        elif args.command == 'log':
            if not args.action:
                raise GrankiError('log needs --action')
            log_event(args.journal, args.actor, args.action, args.target)
            report = {'status': 'passed', 'journal': str(args.journal)}
        elif args.command == 'add':
            if not (args.source and args.findings):
                raise GrankiError('add needs --source and --findings')
            items = json.loads(args.findings.read_text(encoding='utf-8'))
            if not isinstance(items, list):
                raise GrankiError('--findings must hold a JSON list')
            report = add(args.journal, args.source, items, args.actor)
        else:
            if not (args.id and args.status):
                raise GrankiError('set needs --id and --status')
            report = set_status(args.journal, [i.strip() for i in args.id.split(',') if i.strip()],
                                args.status, args.note, args.actor)
    except (GrankiError, OSError, json.JSONDecodeError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:  # unexpected input must not look like success or a failed check
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2
    sys.stdout.write(dump_json(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
