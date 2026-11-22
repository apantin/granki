"""Shared helpers for Granki scripts: plans, sections, prose, numbers, claims.

The module is imported by the command-line scripts next to it. It has no
command-line interface of its own.
"""
from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import os
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import yaml

SCHEMA = 1
ARTICLE_STATUSES = ('planned', 'plan-draft', 'plan-approved', 'writing',
                    'article-review', 'ready', 'published', 'revising')
SECTION_STATUSES = ('planned', 'drafted', 'agent-reviewed', 'accepted', 'needs-rework')
SECTION_NAME = re.compile(r'(\d{2})-.+\.md')
FENCE = re.compile(r'(```|~~~).*?\1', re.S)
COMMENT = re.compile(r'<!--.*?-->', re.S)
MARKER = re.compile(r'<!--\s*caveat:([A-Za-z0-9_.-]+)\s*-->')
LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
REFERENCE_LINK = re.compile(r'^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?', re.M)
AUTOLINK = re.compile(r'<((?:https?|ftp|mailto):[^>\s]+)>')
RAW_LINK = re.compile(r'<(?:a|img|source|video|audio|iframe|object|embed)\b[^>]*?\b(?:href|src|data|poster)\s*=\s*["\']([^"\']+)', re.I)
SEVERITIES = ('критично', 'обычно')
KINDS = ('бесспорная', 'спорная', 'вопрос')

DEFAULTS = {
    'sections_dir': 'sections',
    'numbers': {'decimal': ',', 'renderers': ['percent:2', 'fixed:2'], 'allow': [], 'integers': False, 'dates': False},
    'claims': [],
    'data_dirs': ['data'],
    'caveats': {},
    'required_caveats': [],
    'public': {'forbidden': [], 'allow_external_links': False, 'assets_dir': 'assets'},
    'figures': {'manifest': 'assets/*manifest.json'},
    'published': [],
    'sections': [],
}


class GrankiError(Exception):
    """A configuration or input error that stops a script before checking."""


class DataNotFound(GrankiError):
    """A data file named by a locator does not exist in the data folders."""


class BadLocator(GrankiError):
    """A claim source that should be a locator cannot be parsed or resolved."""


def atomic_write(path: Path, text: str) -> None:
    """Write through a temporary file in the same folder, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(path: Path):
    """Exclusive lock for a read-modify-write of path (POSIX flock; no-op elsewhere)."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
    lock = Path(tempfile.gettempdir()) / f'granki-{key}.lock'  # outside the repository
    with open(lock, 'a') as handle:
        try:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - Windows
            pass
        yield


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return YAML frontmatter and body; a file without frontmatter yields {}."""
    text = text.lstrip('\ufeff').replace('\r\n', '\n')
    if not text.startswith('---\n'):
        return {}, text
    if text.endswith('\n---'):
        text += '\n'
    end = text.find('\n---\n', 3)
    if end < 0:
        raise GrankiError('Frontmatter is not closed with ---')
    meta = yaml.safe_load(text[4:end]) or {}
    if not isinstance(meta, dict):
        raise GrankiError('Frontmatter must be a mapping')
    return meta, text[end + 5:]


def merged(meta: dict) -> dict:
    """Fill defaults one level deep so scripts can rely on every key."""
    result = {}
    for key, default in DEFAULTS.items():
        value = meta.get(key, default)
        if isinstance(default, dict) and isinstance(value, dict):
            value = {**default, **value}
        result[key] = value
    for key, value in meta.items():
        result.setdefault(key, value)
    return result


def load_plan(path: Path) -> dict:
    """Read an article plan; validate the schema version and statuses."""
    if not path.is_file():
        raise GrankiError(f'Plan not found: {path}')
    meta, _ = split_frontmatter(path.read_text(encoding='utf-8'))
    if meta.get('granki') != SCHEMA:
        raise GrankiError(f'{path}: expected "granki: {SCHEMA}" in frontmatter')
    plan = merged(meta)
    status = plan.get('status', 'planned')
    if status not in ARTICLE_STATUSES:
        raise GrankiError(f'{path}: unknown article status {status!r}')
    plan['status'] = status
    # Article root: the plan's folder, or `root` relative to it.
    plan['_root'] = (path.parent / str(meta.get('root', '.'))).resolve()
    # Workspace: journal.md and reviews/ live next to plan.md, even when root points elsewhere.
    plan['_workspace'] = path.parent.resolve()
    validate(plan, path)
    for entry in plan['sections']:
        if entry.get('status', 'planned') not in SECTION_STATUSES:
            raise GrankiError(f'{path}: unknown section status {entry.get("status")!r} for {entry.get("file")}')
    return plan


def validate(plan: dict, path: Path) -> None:
    """Refuse plan fields of the wrong type instead of failing later with a traceback."""
    lists = {'claims': plan['claims'], 'data_dirs': plan['data_dirs'], 'required_caveats': plan['required_caveats'],
             'sections': plan['sections'], 'published': plan['published'],
             'public.forbidden': plan['public'].get('forbidden') or [],
             'numbers.renderers': plan['numbers'].get('renderers'), 'numbers.allow': plan['numbers'].get('allow') or []}
    for name, value in lists.items():
        if not isinstance(value, list):
            raise GrankiError(f'{path}: {name} must be a list')
    if not isinstance(plan['caveats'], dict):
        raise GrankiError(f'{path}: caveats must be a mapping of ID to description')
    if any(not isinstance(e, dict) or 'file' not in e for e in plan['sections']):
        raise GrankiError(f'{path}: every entry of sections needs a file')
    plan['public']['forbidden'] = plan['public'].get('forbidden') or []
    plan['numbers']['allow'] = plan['numbers'].get('allow') or []
    for pattern in plan['public']['forbidden']:
        try:
            re.compile(pattern)
        except (re.error, TypeError) as error:
            raise GrankiError(f'{path}: bad forbidden pattern {pattern!r}: {error}')


def load_series(path: Path) -> dict:
    if not path.is_file():
        raise GrankiError(f'Series plan not found: {path}')
    meta, _ = split_frontmatter(path.read_text(encoding='utf-8'))
    if meta.get('granki') != SCHEMA:
        raise GrankiError(f'{path}: expected "granki: {SCHEMA}" in frontmatter')
    if not isinstance(meta.get('articles'), list) or not meta['articles']:
        raise GrankiError(f'{path}: "articles" must list article folders')
    meta.setdefault('known_divergences', [])
    return meta


def has_sections(plan: dict) -> bool:
    """True when the article already has at least one NN-*.md section file."""
    folder = plan['_root'] / plan['sections_dir']
    return folder.is_dir() and any(SECTION_NAME.fullmatch(p.name) for p in folder.glob('*.md'))


def series_of(plan_path: Path) -> tuple[Path, dict] | None:
    """The series an article belongs to: series-plan.md one folder up that lists it."""
    candidate = plan_path.resolve().parent.parent / 'series-plan.md'
    if not candidate.is_file():
        return None
    try:
        series = load_series(candidate)
    except GrankiError:
        return None
    return (candidate, series) if plan_path.resolve().parent.name in series['articles'] else None


def section_paths(directory: Path) -> list[Path]:
    """Sections are NN-*.md files; the two-digit prefixes set the order and must be unique."""
    if not directory.is_dir():
        raise GrankiError(f'Sections folder not found: {directory}')
    paths = sorted(p for p in directory.glob('*.md') if SECTION_NAME.fullmatch(p.name))
    seen = {}
    for path in paths:
        prefix = path.name[:2]
        if prefix in seen:
            raise GrankiError(f'Duplicate section prefix {prefix}: {seen[prefix].name}, {path.name}')
        seen[prefix] = path
    if not paths:
        raise GrankiError(f'No NN-*.md sections in {directory}')
    return paths


def join_sections(texts: list[str]) -> str:
    return '\n\n'.join(t.rstrip('\n') for t in texts) + '\n'


def strip_code(text: str) -> str:
    """Text without fenced code blocks."""
    return FENCE.sub('', text)


def prose(text: str) -> str:
    """Text that counts for length and number tracing: no tables, fenced code or comments."""
    body = '\n'.join(line for line in strip_code(text).splitlines() if not line.lstrip().startswith('|'))
    return COMMENT.sub('', body)


def decimal_tokens(text: str, decimal: str = ',') -> list[str]:
    """Decimal numbers written in the text, without sign; thousands spaces are dropped."""
    sep = re.escape(decimal)
    pattern = r'(?<![\d.,])(\d{1,3}(?:[ \u00a0\u202f]\d{3})+' + sep + r'\d+|\d+' + sep + r'\d+)'
    return [re.sub(r'[ \u00a0\u202f]', '', t) for t in re.findall(pattern, text)]


MONTHS = (r'(?:январ[ьяе]|феврал[ьяе]|март[ае]?|апрел[ьяе]|ма[йяе]|июн[ьяе]|июл[ьяе]|август[ае]?|сентябр[ьяе]'
          r'|октябр[ьяе]|ноябр[ьяе]|декабр[ьяе])(?![а-яё])')
DATE = re.compile(
    r'(?<![\w.,])\d{1,2}(?:\s*[–—-]\s*\d{1,2})?\s+' + MONTHS + r'(?:\s+(?:19|20)\d{2}(?:\s*(?:г\.|год[а-я]*))?)?'
    r'|(?<![\w.,])' + MONTHS + r'\s+(?:19|20)\d{2}(?:\s*(?:г\.|год[а-я]*))?'
    r'|(?<![\w.,])(?:19|20)\d{2}(?:\s*[–—-]\s*(?:19|20)?\d{2})?\s*(?:гг?\.|год[а-я]*)(?![а-яё])', re.I)


def without_dates(text: str) -> str:
    """Dates like «3–14 ноября», «ноябрь 2025», «2025 года» are not traced as numbers."""
    return DATE.sub(' ', text)


def integer_tokens(text: str, decimal: str = ',') -> list[str]:
    """Whole numbers of two or more digits that stand alone (not part of 27B, Qwen3, 3,5 or 2.6)."""
    sep = re.escape(decimal)
    return re.findall(r'(?<![\w.,\-])(\d{2,})(?![\w.]|' + sep + r'\d)', text)


def render(value, renderers: list[str], decimal: str = ',') -> set[str]:
    """All literal forms a numeric value may take in the text."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return set()
    try:
        exact = Decimal(str(value).strip())
    except InvalidOperation:
        exact = Decimal(repr(number))
    forms = set()
    for spec in renderers:
        kind, _, digits = spec.partition(':')
        if kind not in ('percent', 'fixed'):
            raise GrankiError(f'Unknown number renderer {spec!r}')
        digits = int(digits or 0)
        scaled = number * 100 if kind == 'percent' else number
        forms.add(f'{scaled:.{digits}f}'.replace('.', decimal).lstrip('+-'))
        # Authors round half up; binary floats sometimes round the other way.
        base = exact * 100 if kind == 'percent' else exact
        half_up = base.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
        forms.add(f'{half_up:f}'.replace('.', decimal).lstrip('+-'))
    return forms


def caveat_markers(text: str) -> list[str]:
    """Caveat markers outside code that are followed by the caveat's own words."""
    code_free = strip_code(text)
    found = []
    for match in MARKER.finditer(code_free):
        paragraph = code_free[match.end():].split('\n\n', 1)[0]
        if len(re.findall(r'\w{2,}', COMMENT.sub('', paragraph))) >= 3:
            found.append(match.group(1))
    return found


def bare_markers(text: str) -> list[str]:
    """Caveat markers outside code with no caveat text after them."""
    with_text = set(caveat_markers(text))
    return [m.group(1) for m in MARKER.finditer(strip_code(text)) if m.group(1) not in with_text]


def link_targets(text: str) -> list[str]:
    """Targets of inline, reference, autolinks and raw HTML links outside code and comments."""
    clean = COMMENT.sub('', strip_code(text))
    return LINK.findall(clean) + REFERENCE_LINK.findall(clean) + AUTOLINK.findall(clean) + RAW_LINK.findall(clean)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def find_data(name: str, dirs: list[Path]) -> Path:
    for directory in dirs:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    raise DataNotFound(f'Data file {name} not found in: ' + ', '.join(str(d) for d in dirs))


AGGREGATES = ('count', 'sum', 'mean', 'median', 'min', 'max')


def parse_locator(locator: str) -> tuple[str, list[tuple[str, str]], str]:
    """'file.csv: key=value; key2=value2; column=col' -> (file, conditions, column).

    Conditions may also be joined by commas: 'file.csv: a=1,b=2; column=col'.
    An aggregate ('agg=median') is returned as the condition ('agg', 'median'); with it
    the row selector is optional and column= may be left out for agg=count.
    """
    name, sep, rest = locator.partition(':')
    if not sep:
        raise BadLocator(f'Locator without "file.csv:" prefix: {locator!r}')
    conditions, column = [], None
    for part in (p.strip() for p in rest.split(';')):
        if not part:
            continue
        pieces = [part]
        if ',' in part and all('=' in piece for piece in part.split(',')):
            pieces = part.split(',')
        for piece in pieces:
            key, eq, value = piece.partition('=')
            if not eq:
                raise BadLocator(f'Locator part without "=": {locator!r}')
            if key.strip() == 'column':
                column = value.strip()
            else:
                conditions.append((key.strip(), value.strip()))
    agg = [v for k, v in conditions if k == 'agg']
    if agg:
        if len(agg) > 1 or agg[0] not in AGGREGATES:
            raise BadLocator(f'agg= takes one of {", ".join(AGGREGATES)}: {locator!r}')
        if column is None and agg[0] != 'count':
            raise BadLocator(f'agg={agg[0]} needs column=: {locator!r}')
        return name.strip(), conditions, column
    if column is None or not conditions:
        raise BadLocator(f'Locator needs a row selector and column=: {locator!r}')
    return name.strip(), conditions, column


def aggregate(kind: str, rows: list[dict], column: str | None, locator: str) -> float:
    if kind == 'count':  # with column=, rows whose cell is blank do not count
        return float(len([r for r in rows if column is None or (r.get(column) or '').strip()]))
    numbers = []
    for row in rows:
        cell = (row.get(column) or '').strip().replace(',', '.')
        if not cell:
            continue  # blank cells do not count
        try:
            numbers.append(float(cell))
        except ValueError:
            raise BadLocator(f'agg={kind}: {cell!r} in {column!r} is not a number: {locator!r}') from None
    if not numbers:
        raise BadLocator(f'agg={kind}: no numbers selected: {locator!r}')
    if kind == 'sum':
        return sum(numbers)
    if kind == 'mean':
        return sum(numbers) / len(numbers)
    if kind == 'min':
        return min(numbers)
    if kind == 'max':
        return max(numbers)
    numbers.sort()
    middle = len(numbers) // 2
    return numbers[middle] if len(numbers) % 2 else (numbers[middle - 1] + numbers[middle]) / 2


def json_pointer(data, pointer: str):
    """Resolve an RFC 6901 pointer such as /a/0/b; negative indices are not allowed."""
    for token in pointer.lstrip('/').split('/') if pointer.strip('/') else []:
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(data, list):
            if not token.isdigit():
                raise KeyError(token)
            data = data[int(token)]
        elif isinstance(data, dict):
            data = data[token]
        else:
            raise KeyError(token)
    return data


def resolve_locator(locator: str, dirs: list[Path], cache: dict | None = None) -> list[str]:
    """Values of the located cell.

    CSV: 'file.csv: key=value; column=col' or 'file.csv: row=N; column=col'
    (N counts data records from 2, the header being 1; blank lines are not records).
    CSV aggregate: 'file.csv: key=a|b; agg=median; column=col' -> [the number] over the selected rows.
    JSON: 'file.json#/pointer' -> the value at that pointer, as text.
    Raises BadLocator for a source that is not a valid locator, DataNotFound
    for a missing file; returns [] when the row or pointer does not exist.
    """
    cache = {} if cache is None else cache
    if '#/' in locator and ':' not in locator.split('#/', 1)[0]:
        name, pointer = locator.split('#', 1)
        path = find_data(name.strip(), dirs)
        if path not in cache:
            cache[path] = json.loads(path.read_text(encoding='utf-8-sig'))
        try:
            value = json_pointer(cache[path], pointer)
        except (KeyError, IndexError, ValueError):
            return []
        return [value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)]
    name, conditions, column = parse_locator(locator)
    path = find_data(name, dirs)
    if path not in cache:
        cache[path] = read_csv(path)
    rows = cache[path]
    agg = next((v for k, v in conditions if k == 'agg'), None)
    if agg:
        conditions = [(k, v) for k, v in conditions if k != 'agg']
        unknown = [k for k in [c for c, _ in conditions] + ([column] if column else []) if rows and k not in rows[0]]
        if unknown:
            raise BadLocator(f'Column {unknown[0]!r} not in {name}')
        # in an aggregate a condition may list alternatives: cache=hit|miss
        selected = [r for r in rows if all(r.get(k) in [x.strip() for x in v.split('|')] for k, v in conditions)]
        return [aggregate(agg, selected, column, locator)]
    if rows and column not in rows[0]:
        raise BadLocator(f'Column {column!r} not in {name}')
    if conditions[0][0] == 'row' and len(conditions) == 1:
        if not conditions[0][1].isdigit():
            raise BadLocator(f'row= needs a number: {locator!r}')
        index = int(conditions[0][1]) - 2
        selected = [rows[index]] if 0 <= index < len(rows) else []
    else:
        unknown = [k for k, _ in conditions if rows and k not in rows[0]]
        if unknown:
            raise BadLocator(f'Column {unknown[0]!r} not in {name}')
        selected = [r for r in rows if all(r.get(k) == v for k, v in conditions)]
    return [r[column] for r in selected]


def dump_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'
