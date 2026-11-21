#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Build or verify an article's claims table.

A claims table is a CSV with columns ID, formulation, value, source. Each
source is a locator of one CSV cell: "file.csv: key=value; column=name" or
"file.csv: row=N; column=name" (N is the CSV line number, the header is 1),
or "file.json#/pointer". A value computed from many rows is an aggregate:
"file.csv: key=a|b; agg=median; column=name" (count, sum, mean, median, min,
max). A value computed from other claims is an expression: "expr: R-a / R-b - 1".
Both are recomputed and match when equal to the stated value rounded to its
decimals. Anything else starts with "derived:" and a description; it is
reported as unverifiable and needs a reader.

  build   write the claims table from the plan's `claims_build` rules; rows the
          rules do not produce (manual, derived) are kept
  verify  check that every claim still equals the cell its locator points to

Prints JSON. Exit code 0 when passed, 1 when claims drifted or are ambiguous,
2 on configuration errors.
"""
from __future__ import annotations

import argparse
import ast
import operator
import re
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import (BadLocator, DataNotFound, GrankiError, atomic_write, dump_json, find_data,  # noqa: E402
                         load_plan, locked, read_csv, resolve_locator)

FIELDS = ['ID', 'formulation', 'value', 'source']


def data_dirs(plan: dict, article: Path) -> list[Path]:
    return [(article / d).resolve() for d in plan['data_dirs']]


def build_rows(plan: dict, article: Path) -> list[dict]:
    """Expand `claims_build` rules: one claim per selected row and column."""
    rules = plan.get('claims_build') or []
    if not rules:
        raise GrankiError('The plan has no claims_build rules; nothing to build')
    dirs = data_dirs(plan, article)
    out, seen = [], set()
    for rule in rules:
        name = rule['source']
        rows = read_csv(find_data(name, dirs))
        where = {k: str(v) for k, v in (rule.get('where') or {}).items()}
        key = rule.get('key')
        keys = [key] if isinstance(key, str) else list(key or [])
        selected = [(line, row) for line, row in enumerate(rows, start=2)
                    if all(row.get(k) == v for k, v in where.items())]
        if keys:
            missing = [k for k in keys if selected and k not in selected[0][1]]
            if missing:
                raise GrankiError(f'{name}: key column {missing[0]!r} not found')
            values = [tuple(row.get(k) for k in keys) for _, row in selected]
            if len(set(values)) != len(values):
                raise GrankiError(f'{name}: key {keys} is not unique among the selected rows; add `where` or another key column')
        for line, row in selected:
            conditions = ([f'{k}={row[k]}' for k in keys] + [f'{k}={v}' for k, v in where.items() if k not in keys]) if keys else [f'row={line}']
            for column in rule['columns']:
                if column not in row:
                    raise GrankiError(f'{name}: column {column!r} not found')
                fields = {**row, 'column': column, 'row': line}
                claim_id = rule['id'].format(**fields)
                if claim_id in seen:
                    raise GrankiError(f'Duplicate claim ID {claim_id!r}; make the id pattern more specific')
                seen.add(claim_id)
                out.append({'ID': claim_id,
                            'formulation': rule.get('formulation', '{column}').format(**fields),
                            'value': row[column],
                            'source': f'{name}: {"; ".join(conditions)}; column={column}'})
    return out


def merge_rows(built: list[dict], existing: list[dict]) -> tuple[list[dict], list[str]]:
    """Rules replace the claims they produce; every other existing row (manual, derived) is kept."""
    produced = {r['ID'] for r in built}
    kept = [r for r in existing if r.get('ID') not in produced]
    return built + [{k: r.get(k, '') for k in FIELDS} for r in kept], [r['ID'] for r in kept]


def short(value: float) -> str:
    return f'{value:.6g}'


def close(stated: str, computed: float) -> bool:
    """A computed value matches the stated one rounded to the stated number of decimals."""
    text = (stated or '').strip().replace(',', '.')
    try:
        number = float(text)
    except ValueError:
        return False
    decimals = len(text.split('.', 1)[1]) if '.' in text else 0
    return abs(number - computed) <= 0.5 * 10 ** -decimals + 1e-9


OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def evaluate(expression: str, values: dict, own_id: str) -> float:
    """'expr: R-a / R-b - 1': arithmetic over the stated values of other claims."""
    ids = sorted((i for i in values if i and i != own_id), key=len, reverse=True)
    names = {}
    def name(match):
        names.setdefault(match.group(0), f'_v{len(names)}')
        return names[match.group(0)]
    pattern = '|'.join(re.escape(i) for i in ids) or r'(?!)'
    code = re.sub(rf'(?<![\w-])(?:{pattern})(?![\w-])', name, expression.strip())
    stray = re.findall(r'(?<![\w-])[A-Za-zА-Яа-я][\w]*-[\w-]+', code)
    if stray:
        raise BadLocator(f'expr: unknown claim ID {stray[0]}: {expression.strip()!r}')
    numbers = {}
    for claim_id, var in names.items():
        try:
            numbers[var] = float(str(values[claim_id]).replace(',', '.'))
        except ValueError:
            raise BadLocator(f'expr: {claim_id} is not a number') from None

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in numbers:
            return numbers[node.id]
        raise BadLocator(f'expr: only claim IDs, numbers and + - * / ( ) are allowed: {expression!r}')
    try:
        return walk(ast.parse(code.replace('−', '-'), mode='eval'))
    except (SyntaxError, ZeroDivisionError) as error:
        raise BadLocator(f'expr: {error}: {expression!r}') from None


def verify_rows(claims: list[dict], dirs: list[Path]) -> dict:
    """Compare claims with their cells.

    `derived:` sources describe computed values and are listed as unverifiable.
    A source that should be a locator but cannot be parsed, or names an unknown
    column, is invalid and fails the check, as do drift, ambiguity, missing
    cells and duplicate IDs.
    """
    cache, drift, ambiguous, missing, unverifiable, invalid = {}, [], [], [], [], []
    counts = {}
    for claim in claims:
        counts[claim.get('ID')] = counts.get(claim.get('ID'), 0) + 1
    duplicates = sorted(i for i, n in counts.items() if n > 1)
    values_by_id = {c.get('ID'): c.get('value') for c in claims}
    for claim in claims:
        source = claim.get('source') or ''
        if source.startswith('derived:'):
            unverifiable.append({'id': claim['ID'], 'source': source})
            continue
        try:
            if source.startswith('expr:'):
                values = [evaluate(source[5:], values_by_id, claim['ID'])]
            else:
                values = resolve_locator(source, dirs, cache)
        except DataNotFound:
            missing.append(claim['ID'])
            continue
        except BadLocator as error:
            invalid.append({'id': claim['ID'], 'source': source, 'reason': str(error)})
            continue
        if not values:
            missing.append(claim['ID'])
        elif len(set(values)) > 1:
            ambiguous.append(claim['ID'])
        elif isinstance(values[0], float):
            if not close(claim['value'], values[0]):
                drift.append({'id': claim['ID'], 'claim': claim['value'], 'source': short(values[0])})
        elif values[0] != claim['value']:
            drift.append({'id': claim['ID'], 'claim': claim['value'], 'source': values[0]})
    status = 'passed' if not (drift or ambiguous or missing or invalid or duplicates) else 'failed'
    return {'status': status, 'claims': len(claims), 'drift': drift, 'ambiguous': ambiguous,
            'missing': missing, 'invalid': invalid, 'duplicates': duplicates, 'unverifiable': unverifiable}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=['build', 'verify'])
    parser.add_argument('--plan', required=True, type=Path, help='article plan.md')
    parser.add_argument('--article-dir', type=Path, help='article folder (default: folder of the plan)')
    parser.add_argument('--claims', type=Path, help='claims CSV (default: first entry of the plan "claims")')
    parser.add_argument('--output', type=Path, help='build: where to write the CSV (default: --claims path)')
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.plan)
        article = (args.article_dir or plan['_root']).resolve()
        claims_path = args.claims or (article / plan['claims'][0] if plan['claims'] else None)
        if args.command == 'build':
            built = build_rows(plan, article)
            target = args.output or claims_path
            if target is None:
                raise GrankiError('No output path: pass --output or list a claims file in the plan')
            existing = read_csv(target) if target.is_file() else []
            rows, kept = merge_rows(built, existing)
            check = verify_rows(rows, data_dirs(plan, article))
            if check['ambiguous'] or check['invalid'] or check['duplicates']:
                raise GrankiError('Built claims would not verify: ' + json.dumps(
                    {k: check[k] for k in ('ambiguous', 'invalid', 'duplicates')}, ensure_ascii=False))
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
            with locked(target):
                atomic_write(target, buffer.getvalue())
            sys.stdout.write(dump_json({'status': 'passed', 'claims': len(rows), 'built': len(built),
                                        'kept': kept, 'output': str(target)}))
            return 0
        if claims_path is None:
            raise GrankiError('No claims table: pass --claims or list one in the plan')
        result = verify_rows(read_csv(claims_path), data_dirs(plan, article))
        result['claims_file'] = str(claims_path)
        sys.stdout.write(dump_json(result))
        return 0 if result['status'] == 'passed' else 1
    except (GrankiError, KeyError, OSError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:  # unexpected input must not look like a failed check
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
