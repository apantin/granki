"""Tests for the Granki scripts on a small fictional series.

Run: uv run --with pyyaml python -m unittest discover -s skills/granki-tools/scripts/tests
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_html  # noqa: E402
import check  # noqa: E402
import claims  # noqa: E402
import journal  # noqa: E402
import plan  # noqa: E402
import rooms  # noqa: E402
import impact  # noqa: E402
import canon  # noqa: E402
import status  # noqa: E402
import style  # noqa: E402
from fixture import make_series  # noqa: E402
from granki_core import GrankiError, decimal_tokens, prose, render, section_paths  # noqa: E402


def run(module, *args) -> tuple[int, dict | str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main([str(a) for a in args])
    text = out.getvalue()
    try:
        return code, json.loads(text)
    except json.JSONDecodeError:
        return code, text


class SeriesCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.series = make_series(self.tmp)
        self.green = self.tmp / '01-green'
        self.black = self.tmp / '02-black'

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, path: Path, old: str, new: str):
        text = path.read_text(encoding='utf-8')
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding='utf-8')

    def failed(self, report) -> dict:
        return {c['name']: c for c in report['checks'] if c['status'] == 'failed'}


class CoreTests(SeriesCase):
    def test_prose_excludes_tables_code_and_comments(self):
        text = 'Текст 1,5.\n| 2,5 |\n```\n3,5\n```\n<!-- 4,5 -->'
        self.assertEqual(decimal_tokens(prose(text)), ['1,5'])

    def test_render_forms(self):
        self.assertEqual(render(0.875, ['percent:2', 'fixed:1']), {'87,50', '0,9'})
        self.assertEqual(render('нет данных', ['fixed:2']), set())

    def test_duplicate_section_prefix_is_rejected(self):
        (self.green / 'sections/01-other.md').write_text('## Другой\n', encoding='utf-8')
        with self.assertRaises(GrankiError):
            section_paths(self.green / 'sections')


class CheckTests(SeriesCase):
    def test_article_passes(self):
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual(code, 0, report)
        names = {c['name']: c for c in report['checks']}
        self.assertEqual(names['numbers']['occurrences'], 3)
        self.assertEqual(names['caveats']['found'], {'C1': 'marker'})
        self.assertEqual([u['id'] for u in names['claims']['unverifiable']], ['T-derived'])

    def test_untraced_number_fails(self):
        self.edit(self.green / 'sections/01-results.md', '87,50% гостей', '91,00% гостей')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual(code, 1)
        self.assertEqual(self.failed(report)['numbers']['untraced'], [{'section': '01-results.md', 'number': '91,00'}])

    def test_hedged_rounded_number_passes(self):
        self.edit(self.green / 'plan.md', 'allow: ["2,5"]}', 'allow: ["2,5"], integers: true}')
        self.edit(self.green / 'sections/01-results.md', '87,50% гостей', 'почти 90% гостей')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual(code, 0, report)
        self.assertEqual({c['name']: c for c in report['checks']}['numbers']['approximate'], 1)

    def test_rounded_forms(self):
        # {form: not below the value}: «почти 90%» fits 87,5% but not 94,4%; 149 is not «около 100».
        self.assertEqual(check.rounded_forms(0.875), {'88': True, '90': True})
        self.assertEqual(check.rounded_forms(0.944), {'94': False, '90': False})
        self.assertEqual(check.rounded_forms(149), {'150': True})
        self.assertEqual(check.rounded_forms(897.76), {'900': True})

    def test_rounded_number_needs_its_own_hedge_word(self):
        # «около 90B» is a name, not a rounded 90; 70 is too far from 87,5.
        self.edit(self.green / 'plan.md', 'allow: ["2,5"]}', 'allow: ["2,5"], integers: true}')
        for text, number in [('90% гостей, а не почти 90%,', '90'), ('90% гостей ждали около 90B и', '90'),
                             ('почти 70% гостей', '70'), ('около 70% гостей', '70')]:
            with self.subTest(text=text):
                section = self.green / 'sections/01-results.md'
                original = section.read_text(encoding='utf-8')
                self.edit(section, '87,50% гостей', text)
                code, report = run(check, '--plan', self.green / 'plan.md')
                section.write_text(original, encoding='utf-8')
                self.assertEqual(code, 1)
                self.assertEqual(self.failed(report)['numbers']['untraced'], [{'section': '01-results.md', 'number': number}])

    def test_missing_caveat_fails(self):
        self.edit(self.green / 'sections/00-intro.md', '<!-- caveat:C1 -->', '')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual(code, 1)
        self.assertIn('caveats', self.failed(report))

    def test_claim_drift_fails(self):
        self.edit(self.green / 'data/tasting.csv', 'b,2.5,80,0.875', 'b,2.5,80,0.9')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual(self.failed(report)['claims']['drift'][0]['id'], 'T-best-share')

    def test_forbidden_and_missing_link_fail(self):
        self.edit(self.green / 'sections/01-results.md', 'Лучше всего', 'Секретный рецепт. Лучше всего')
        (self.green / 'assets/chart.png').unlink()
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual(set(self.failed(report)), {'public', 'links'})

    def test_length_bounds(self):
        self.edit(self.green / 'plan.md', 'max: 2000', 'max: 60')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual((code, report['warnings']), (0, ['length']))
        self.edit(self.green / 'plan.md', 'max: 60', 'max: 60, strict: true')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertIn('length', self.failed(report))

    def test_section_scope_checks_only_that_section(self):
        self.edit(self.green / 'sections/00-intro.md', 'три раза', 'три раза при 99,9 градусах')
        code, report = run(check, '--plan', self.green / 'plan.md', '--section', '01-results.md')
        self.assertEqual(code, 0, report)
        self.assertEqual(report['scope'], 'section')
        code, report = run(check, '--plan', self.green / 'plan.md', '--section', '00-intro.md')
        self.assertEqual(code, 1)

    def test_published_article_is_locked(self):
        self.assertEqual(run(check, '--plan', self.black / 'plan.md')[0], 0)
        self.edit(self.black / 'sections/00-intro.md', 'тоже', 'также')
        code, report = run(check, '--plan', self.black / 'plan.md')
        self.assertEqual(self.failed(report)['published-lock']['changed'], ['00-intro.md'])
        self.edit(self.black / 'plan.md', 'status: published', 'status: revising')
        self.assertEqual(run(check, '--plan', self.black / 'plan.md')[0], 0)

    def test_series_detects_conflicting_claims(self):
        self.assertEqual(run(check, '--series', self.series)[0], 0)
        self.edit(self.black / 'data/claims.csv', '0.875,tasting', '0.9,tasting')
        self.edit(self.black / 'data/tasting.csv', 'b,2.5,80,0.875', 'b,2.5,80,0.9')
        self.edit(self.black / 'sections/00-intro.md', '87,50%', '90,00%')
        self.edit(self.black / 'plan.md', 'status: published', 'status: revising')
        code, report = run(check, '--series', self.series)
        self.assertEqual(code, 1)
        self.assertEqual(report['checks'][0]['conflicts'][0]['id'], 'T-best-share')
        self.edit(self.series, 'known_divergences: []', 'known_divergences: [T-best-share]')
        self.assertEqual(run(check, '--series', self.series)[0], 0)

    def test_bad_plan_is_a_configuration_error(self):
        self.edit(self.green / 'plan.md', 'status: writing', 'status: done')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual((code, report['status']), (2, 'error'))


class ClaimsTests(SeriesCase):
    def test_build_from_rules(self):
        self.edit(self.green / 'plan.md', 'claims: [data/claims.csv]',
                  'claims: [data/claims.csv]\nclaims_build:\n  - {source: tasting.csv, key: cup, '
                  'id: "T-{cup}-{column}", columns: [share, minutes]}')
        out = self.tmp / 'built.csv'
        code, report = run(claims, 'build', '--plan', self.green / 'plan.md', '--output', out)
        self.assertEqual((code, report['claims']), (0, 4))
        rows = list(csv.DictReader(io.StringIO(out.read_text(encoding='utf-8'))))
        self.assertEqual(rows[2], {'ID': 'T-b-share', 'formulation': 'share', 'value': '0.875',
                                   'source': 'tasting.csv: cup=b; column=share'})
        code, report = run(claims, 'verify', '--plan', self.green / 'plan.md', '--claims', out)
        self.assertEqual((code, report['status']), (0, 'passed'))

    def test_missing_data_file_fails(self):
        (self.green / 'data/tasting.csv').unlink()
        code, report = run(claims, 'verify', '--plan', self.green / 'plan.md')
        self.assertEqual(code, 1)
        self.assertEqual(report['missing'], ['T-best-share', 'T-best-temp'])
        self.assertEqual([u['id'] for u in report['unverifiable']], ['T-derived'])

    def test_locator_forms(self):
        dirs = [self.green / 'data']
        from granki_core import resolve_locator
        self.assertEqual(resolve_locator('tasting.csv: row=2; column=cup', dirs), ['a'])
        self.assertEqual(resolve_locator('tasting.csv: cup=b,minutes=2.5; column=share', dirs), ['0.875'])
        (self.green / 'data/run.json').write_text('{"runs": [{"n": 3}]}', encoding='utf-8')
        self.assertEqual(resolve_locator('run.json#/runs/0/n', dirs), ['3'])


class StatusTests(SeriesCase):
    def test_modified_section_and_stale_review(self):
        code, state = run(status, '--series', self.series)
        self.assertEqual(code, 0)
        green = state['articles'][0]
        self.assertEqual((green['sections_accepted'], green['sections_total']), (1, 2))
        intro_sha = green['sections'][0]['sha256']
        (self.green / 'reviews').mkdir()
        (self.green / 'reviews/sec-00.md').write_text(
            f'---\nscope: section\ntarget: 00-intro.md\nreviewed_sha: {intro_sha}\n---\n', encoding='utf-8')
        self.assertFalse(run(status, '--series', self.series)[1]['articles'][0]['reviews'][0]['stale'])
        self.edit(self.green / 'sections/00-intro.md', 'три раза', 'четыре раза')
        state = run(status, '--series', self.series)[1]['articles'][0]
        self.assertTrue(state['sections'][0]['modified_since_accepted'])
        self.assertTrue(state['reviews'][0]['stale'])
        code, table = run(status, '--series', self.series, '--format', 'md')
        self.assertIn('| 01-green | writing v1 | принято 0/2; accepted после правки 1, drafted 1 | 00-intro.md |', table)


FINDINGS = [
    {'target': '01-results.md', 'where': 'абз. 1 «Лучше всего»', 'severity': 'критично', 'kind': 'спорная',
     'before': '«Лучше всего вышло за 2,5 минуты»', 'after': '«За 2,5 минуты вышло лучше всего»', 'rule': 'проход 4'},
    {'target': '01-results.md', 'where': 'абз. 1', 'severity': 'обычно', 'kind': 'бесспорная',
     'before': '«вода была 80,0 градусов»', 'after': '«при 80,0 градусах»', 'rule': 'проход 4 | залог'},
    {'target': '01-results.md', 'where': 'конец раздела', 'severity': 'обычно', 'kind': 'спорная',
     'before': 'раздел без мостика', 'after': 'добавить переход', 'rule': 'проход 2'},
    {'target': '01-results.md', 'where': 'абз. 1', 'severity': 'критично', 'kind': 'вопрос',
     'before': '«87,50% гостей» и «вода была»', 'after': '[нужно от автора: сколько было гостей]', 'rule': 'жанр'},
]


class JournalTests(SeriesCase):
    def setUp(self):
        super().setUp()
        self.journal = self.green / 'journal.md'
        self.payload = self.tmp / 'findings.json'
        self.payload.write_text(json.dumps(FINDINGS, ensure_ascii=False), encoding='utf-8')

    def add(self):
        return run(journal, 'add', '--journal', self.journal, '--source', 'reviews/sec-01-editorial.md',
                   '--findings', self.payload)

    def test_add_assigns_ids_and_logs(self):
        code, report = self.add()
        self.assertEqual((code, report['added']), (0, ['N001', 'N002', 'N003', 'N004']))
        self.assertEqual(self.add()[1]['added'], ['N005', 'N006', 'N007', 'N008'])
        text = self.journal.read_text(encoding='utf-8')
        self.assertIn('проход 4 \\| залог', text)
        self.assertIn('добавлено находок: 4 (N001–N004) из reviews/sec-01-editorial.md', text)
        self.assertIn('| --- | --- |', text)
        self.assertNotIn('||', text.replace('\\|', ''))
        listed = run(journal, 'list', '--journal', self.journal)[1]['findings']
        self.assertEqual([f['id'] for f in listed][:4], ['N001', 'N004', 'N005', 'N008'])

    def test_list_checks_quotes(self):
        self.add()
        present = {f['id']: f['still_present'] for f in run(journal, 'list', '--journal', self.journal)[1]['findings']}
        self.assertEqual(present, {'N001': True, 'N002': True, 'N003': None, 'N004': True})
        self.edit(self.green / 'sections/01-results.md', 'вода была', 'вода оказалась')
        present = {f['id']: f['still_present'] for f in run(journal, 'list', '--journal', self.journal)[1]['findings']}
        self.assertFalse(present['N002'])
        self.assertFalse(present['N004'])

    def test_defer_and_resume_in_another_session(self):
        self.add()
        run(journal, 'set', '--journal', self.journal, '--id', 'N001,N002,N003,N004', '--status', 'deferred')
        report = run(journal, 'list', '--series', self.series)[1]
        self.assertEqual(report['pending_total'], 4)
        green = run(status, '--series', self.series)[1]['articles'][0]
        self.assertEqual((green['pending_findings'], green['critical_pending']), (4, 2))
        run(journal, 'set', '--journal', self.journal, '--id', 'N004', '--status', 'applied', '--actor', 'автор')
        run(journal, 'set', '--journal', self.journal, '--id', 'N001,N002', '--status', 'applied', '--actor', 'агент')
        report = run(journal, 'set', '--journal', self.journal, '--id', 'N003', '--status', 'rejected',
                     '--note', 'автор против', '--actor', 'автор')[1]
        self.assertEqual(report['pending'], 0)
        text = self.journal.read_text(encoding='utf-8')
        self.assertIn('rejected (автор против)', text)
        self.assertIn('· автор · N003 → rejected: автор против', text)
        self.assertEqual(run(journal, 'list', '--series', self.series)[1]['pending_total'], 0)
        self.assertEqual(len(run(journal, 'list', '--journal', self.journal, '--all')[1]['findings']), 4)

    def test_log_and_errors(self):
        run(journal, 'log', '--journal', self.journal, '--actor', 'автор', '--action', 'принял раздел',
            '--target', '00-intro.md')
        self.assertIn('· автор · 00-intro.md · принял раздел', self.journal.read_text(encoding='utf-8'))
        self.add()
        self.assertEqual(run(journal, 'set', '--journal', self.journal, '--id', 'N009', '--status', 'applied')[0], 2)
        self.assertEqual(run(journal, 'set', '--journal', self.journal, '--id', 'N001', '--status', 'done')[0], 2)
        self.payload.write_text('[{"target": "x.md"}]', encoding='utf-8')
        self.assertEqual(self.add()[0], 2)


class ImpactTests(SeriesCase):
    def test_claim_change_matrix(self):
        code, report = run(impact, '--series', self.series, '--claim', 'T-best-share')
        self.assertEqual(code, 0)
        green, black = report['articles']
        self.assertEqual(green['affected_sections'][0]['reasons'], [{'claim': 'T-best-share', 'how': 'declared'}])
        self.assertEqual(green['options'], ['rework'])
        self.assertEqual(black['affected_sections'][0]['reasons'][0]['how'], 'value match')
        self.assertEqual(black['options'], ['new-version', 'record-divergence', 'no-change'])

    def test_term_and_empty_change(self):
        report = run(impact, '--series', self.series, '--term', 'сорт')[1]
        self.assertEqual([s['section'] for s in report['articles'][0]['affected_sections']], ['00-intro.md'])
        self.assertEqual(run(impact, '--series', self.series)[0], 2)


class PlanTests(SeriesCase):
    def test_lifecycle_to_publication_and_new_version(self):
        p = self.green / 'plan.md'
        body_before = (p.read_text(encoding='utf-8')).split('\n---\n', 1)[1]
        code, report = run(plan, 'status', '--plan', p, '--set', 'article-review')
        self.assertEqual(code, 2)
        self.assertIn('01-results.md', report['reason'])
        report = run(plan, 'section', '--plan', p, '--file', '01-results.md', '--set', 'accepted', '--actor', 'автор')[1]
        self.assertEqual(len(report['accepted_sha']), 64)
        for target in ['article-review', 'ready']:
            self.assertEqual(run(plan, 'status', '--plan', p, '--set', target)[0], 0)
        self.assertEqual(run(plan, 'status', '--plan', p, '--set', 'published')[0], 2)
        page = self.tmp / 'green.html'
        page.write_text('<html></html>', encoding='utf-8')
        report = run(plan, 'publish', '--plan', p, '--url', 'https://example.org/tea', '--date', '2026-02-01',
                     '--html', page)[1]
        self.assertEqual((report['version'], report['sections']), (1, 2))
        self.assertIn('html_sha256', p.read_text(encoding='utf-8'))
        self.assertEqual(run(check, '--plan', p)[0], 0)
        self.edit(self.green / 'sections/01-results.md', 'Лучше всего', 'Лучше всех')
        self.assertIn('published-lock', self.failed(run(check, '--plan', p)[1]))
        self.assertEqual(run(plan, 'revise', '--plan', p)[1]['version'], 2)
        self.assertEqual(run(check, '--plan', p)[0], 0)
        text = p.read_text(encoding='utf-8')
        self.assertTrue(text.endswith(body_before))
        log = (self.green / 'journal.md').read_text(encoding='utf-8')
        for line in ['· автор · 01-results.md · раздел: drafted → accepted', 'статус статьи: writing → article-review',
                     'опубликована версия 1: https://example.org/tea', 'начата версия 2']:
            self.assertIn(line, log)

    def test_refused_and_forced_transitions(self):
        p = self.green / 'plan.md'
        self.assertEqual(run(plan, 'status', '--plan', p, '--set', 'planned')[0], 2)
        self.assertEqual(run(plan, 'status', '--plan', p, '--set', 'planned', '--force')[0], 0)
        self.assertIn('(принудительно)', (self.green / 'journal.md').read_text(encoding='utf-8'))
        self.assertEqual(run(plan, 'revise', '--plan', p)[0], 2)
        self.assertEqual(run(plan, 'section', '--plan', p, '--file', '07-none.md', '--set', 'drafted')[0], 2)

    def test_sync_adds_unplanned_sections(self):
        (self.green / 'sections/02-extra.md').write_text('## Ещё\n\nТекст.\n', encoding='utf-8')
        self.assertIn('plan-sections', self.failed(run(check, '--plan', self.green / 'plan.md')[1]))
        self.assertEqual(run(plan, 'sync', '--plan', self.green / 'plan.md')[1]['added'], ['02-extra.md'])
        self.assertEqual(run(check, '--plan', self.green / 'plan.md')[0], 0)


STYLE_TEXT = """\
---
title: Пуэр
---

# Пуэр на даче

<!-- caveat:C1 --> Один чайник, одна кружка, одна неделя. Выводов я не делаю.

Заваривал утром: вода из колодца, шумовка вместо сита. Всего три заварки, время по памяти, около пяти минут.

```
выводов не делаю
```

| Чай | Минуты |
|---|---|
| пуэр | 5 |

## Вкус

Горечь записана в таблице, так она и стоит в таблице. Журнал не говорит, откуда она.

Итог: «волшебный» не напишу, хотя напрашивается.

- Было: горько
- Стало: мягче
"""


class StyleTests(SeriesCase):
    def test_counts_traces_in_prose_only(self):
        path = self.tmp / 'puer.md'
        path.write_text(STYLE_TEXT, encoding='utf-8')
        code, report = run(style, '--file', path)
        self.assertEqual(code, 0, report)
        cat = report['categories']
        where = lambda kind: [(m['heading'], m['paragraph'], m['quote']) for m in cat[kind]['matches']]  # noqa: E731
        # code, tables, comments and the frontmatter are not prose; a limit with a fact is not a refusal
        self.assertEqual(where('refusal'), [('Пуэр на даче', 1, 'Выводов я не делаю'), ('Вкус', 1, 'Журнал не говорит')])
        self.assertEqual(where('self_ref'), [('Вкус', 1, 'в таблице'), ('Вкус', 1, 'так она и стоит в таблице')])
        self.assertEqual(where('inoculation'), [('Вкус', 2, '«волшебный» не напишу, хотя напрашивается')])
        self.assertEqual(where('anaphora'), [('Пуэр на даче', 1, 'Один чайник, одна кружка, одна неделя.')])
        # a one-word label, a colon before a quotation and list items are not explanation colons
        self.assertEqual([m['quote'] for m in cat['colon']['matches']], ['Заваривал утром: вода из колодца, шумовка'])
        dist = report['distribution']
        self.assertEqual((dist['paragraphs'], dist['flagged_paragraphs']), (5, 2))
        self.assertEqual(cat['refusal']['matches'][0]['file'], 'puer.md')
        # the sentence opened by a caveat marker is the required caveat: marked, not hidden
        self.assertEqual(cat['anaphora']['matches'][0].get('caveat'), 'C1')
        self.assertNotIn('caveat', cat['refusal']['matches'][0])
        self.assertIn('фразы-отказы в 2 из 5 абзацев', report['signals'][0])
        self.assertTrue(any(s.startswith('«прививка»') for s in report['signals']))
        self.assertTrue(any(s.startswith('анафорическая тройка') for s in report['signals']))

    def test_dashes_between_words(self):
        path = self.tmp / 'dash.md'
        path.write_text('Мешок — около тысячи. Печь одна — у другого выйдет иначе.\n\n'
                        '— Скажу, — ответил я. Тропа — к реке.\n\n- Было — список, не проза\n', encoding='utf-8')
        code, report = run(style, '--file', path)
        quotes = [m['quote'] for m in report['categories']['dash']['matches']]
        # dialogue dashes and list items are not counted
        self.assertEqual(quotes, ['Мешок — около тысячи.', 'Печь одна — у другого выйдет иначе.', 'Тропа — к реке.'])
        self.assertTrue(any(s.startswith('тире между словами: 3') for s in report['signals']))

    def test_plan_scope_and_input_errors(self):
        p = self.green / 'plan.md'
        code, report = run(style, '--plan', p)
        self.assertEqual((code, report['scope'], report['sections']), (0, 'article', ['00-intro.md', '01-results.md']))
        self.assertEqual(report['categories']['refusal']['count'], 0)
        code, report = run(style, '--plan', p, '--section', 'sections/01-results.md')
        self.assertEqual((code, report['sections']), (0, ['01-results.md']))
        self.assertEqual(report['categories']['colon']['matches'][0]['heading'], 'Результаты')
        self.assertEqual(run(style, '--plan', p, '--section', '07-none.md')[0], 2)
        self.assertEqual(run(style, '--section', '01-results.md')[0], 2)
        self.assertEqual(run(style, '--file', self.tmp / 'none.md')[0], 2)


class RoomsTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project)

    def test_install_is_idempotent_and_keeps_team_overrides(self):
        self.assertEqual(run(rooms, 'install', '--project-root', self.project)[0], 2)
        custom = self.project / '_bmad/custom'
        custom.mkdir(parents=True)
        (custom / 'bmad-party-mode.toml').write_text(
            '[[workflow.party_members]]\ncode = "granki-zanuda"\nname = "Свой Зануда"\npersona = "командный"\n',
            encoding='utf-8')
        code, report = run(rooms, 'install', '--project-root', self.project)
        self.assertEqual(code, 0)
        self.assertNotIn('granki-zanuda', report['added'])
        self.assertIn('granki-reader-panel', report['added'])
        self.assertEqual(run(rooms, 'install', '--project-root', self.project)[1]['added'], [])
        self.assertTrue(run(rooms, 'status', '--project-root', self.project)[1]['installed'])
        import tomllib
        data = tomllib.loads((custom / 'bmad-party-mode.toml').read_text(encoding='utf-8'))['workflow']
        names = {m['code']: m['name'] for m in data['party_members']}
        self.assertEqual(names['granki-zanuda'], 'Свой Зануда')
        members = set(names)
        for group in data['party_groups']:
            self.assertTrue(set(group['members']) <= members, group['id'])


class PolicyTests(SeriesCase):
    def test_layers_replace_append_remove(self):
        code, merged = run(canon, '--series', self.series, '--article', '01-green', '--format', 'json')
        self.assertEqual(code, 0)
        self.assertEqual([l['layer'] for l in merged['layers']], ['project', 'series', 'article'])
        sections = {s['title']: s for s in merged['sections']}
        self.assertEqual(list(sections), ['Регистр', 'Как я говорю и не говорю', 'Читатель серии'])
        self.assertEqual(sections['Регистр']['sources'], ['article'])
        self.assertIn('Строгий', sections['Регистр']['body'])
        voice = sections['Как я говорю и не говорю']
        self.assertEqual(voice['sources'], ['project', 'series'])
        self.assertIn('интервал включает ноль', voice['body'])
        self.assertIn('брендами', voice['body'])

    def test_article_without_own_layer_and_markdown_output(self):
        code, text = run(canon, '--series', self.series, '--article', '02-black')
        self.assertEqual(code, 0)
        self.assertIn('Авторский, на «ты».', text)
        self.assertIn('<!-- источник: project, series -->', text)
        self.assertTrue(text.startswith('# Канон проекта'))

    def test_missing_project_canon_is_an_error(self):
        (self.tmp / 'project-canon.md').unlink()
        self.assertEqual(run(canon, '--series', self.series)[0], 2)


class TemplateTests(unittest.TestCase):
    """Templates must parse and work with the scripts once filled in minimally."""

    def test_templates_make_a_working_series(self):
        templates = SCRIPTS.parent / 'assets' / 'templates'
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        series = (templates / 'series-plan.md').read_text(encoding='utf-8')
        series = series.replace('articles: []', 'articles: [01-demo]').replace('canon: ""', 'canon: canon-project.md')
        (tmp / 'series-plan.md').write_text(series, encoding='utf-8')
        shutil.copy(templates / 'canon.md', tmp / 'canon-project.md')
        article = tmp / '01-demo'
        (article / 'sections').mkdir(parents=True)
        (article / 'data').mkdir()
        plan = (templates / 'plan.md').read_text(encoding='utf-8')
        plan = plan.replace('sections: []', 'sections: [{file: 00-intro.md, status: drafted}]')
        plan = plan.replace('length: {min: 12000, max: 21000}', 'length: {min: 1, max: 1000}')
        (article / 'plan.md').write_text(plan, encoding='utf-8')
        (article / 'data/claims.csv').write_text('ID,formulation,value,source\n', encoding='utf-8')
        (article / 'sections/00-intro.md').write_text('# Демо\n\nТекст без чисел.\n', encoding='utf-8')
        self.assertEqual(run(check, '--plan', article / 'plan.md')[0], 0)
        code, state = run(status, '--series', tmp / 'series-plan.md')
        self.assertEqual((code, state['articles'][0]['status']), (0, 'plan-draft'))
        code, merged = run(canon, '--series', tmp / 'series-plan.md', '--format', 'json')
        self.assertEqual(code, 0)
        self.assertIn('Как я говорю и не говорю', [s['title'] for s in merged['sections']])
        for name in ['author-notes.md']:
            self.assertTrue((templates / name).read_text(encoding='utf-8').strip())


@unittest.skipUnless(os.environ.get('GRANKI_PANDOC') or shutil.which('pandoc'), 'Pandoc is not available')
class BuildTests(SeriesCase):
    def test_series_builds_and_strips_markers(self):
        out = self.tmp / 'html'
        code, report = run(build_html, '--series', self.series, '--output', out)
        self.assertEqual(code, 0, report)
        self.assertEqual((report['articles'], report['images']), (2, 1))
        page = (out / '01-green.html').read_text(encoding='utf-8')
        self.assertNotIn('caveat:C1', page)
        self.assertIn('Опыты на кухне', page)
        self.assertIn('data:image/png;base64,', page)
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['articles'][0]['checks']['tables'], 1)

    def test_image_outside_assets_is_rejected(self):
        (self.green / 'sections/stray.png').write_bytes((self.green / 'assets/chart.png').read_bytes())
        self.edit(self.green / 'sections/01-results.md', '../assets/chart.png', 'stray.png')
        code, report = run(build_html, '--plan', self.green / 'plan.md', '--output', self.tmp / 'html')
        self.assertEqual((code, report['status']), (2, 'error'))


if __name__ == '__main__':
    unittest.main()
