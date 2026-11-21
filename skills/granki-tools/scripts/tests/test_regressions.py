"""Regression tests for problems found by independent reviews (2026-11-21)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_scripts import (SCRIPTS, SeriesCase, build_html, check, claims, impact, journal, canon,  # noqa: E402
                          run, status)
from granki_core import decimal_tokens, integer_tokens, prose, render, split_frontmatter  # noqa: E402

FINDING = {'target': '01-results.md', 'where': 'абз. 1', 'severity': 'обычно', 'kind': 'спорная',
           'before': '«Лучше всего вышло»', 'after': '[переставить]', 'rule': 'проход 2'}


class NumbersTests(unittest.TestCase):
    def test_tokens_and_rounding(self):
        self.assertEqual(decimal_tokens('_91,00_ и __92,00__ и x1,25'), ['91,00', '92,00', '1,25'])
        self.assertEqual(decimal_tokens('всего 12 500,75 рубля'), ['12500,75'])
        self.assertEqual(decimal_tokens('версия 2.6.1, оценка 3,5,7'), ['3,5'])
        self.assertIn('0,13', render('0.125', ['fixed:2']))
        self.assertIn('2,68', render('2.675', ['fixed:2']))
        self.assertIn('87,50', render('0.875', ['percent:2']))

    def test_prose_skips_tilde_fences_and_indented_tables(self):
        text = 'Текст 1,5.\n  | 2,5 |\n~~~\n3,5\n~~~\nЕщё 4,5.'
        self.assertEqual(decimal_tokens(prose(text)), ['1,5', '4,5'])

    def test_integer_tokens(self):
        self.assertEqual(integer_tokens('На 62 текстах Qwen3 и 27B, версия 2.6 и 3,5; 2026 год'), ['62', '2026'])


class ClaimsRegressionTests(SeriesCase):
    def plan_with_rules(self, extra=''):
        self.edit(self.green / 'plan.md', 'claims: [data/claims.csv]',
                  'claims: [data/claims.csv]\nclaims_build:\n  - {source: tasting.csv, key: cup, '
                  'id: "T-{cup}-{column}", columns: [share]' + extra + '}')

    def test_build_without_rules_is_refused_and_keeps_file(self):
        before = (self.green / 'data/claims.csv').read_text(encoding='utf-8')
        code, report = run(claims, 'build', '--plan', self.green / 'plan.md')
        self.assertEqual((code, report['status']), (2, 'error'))
        self.assertEqual((self.green / 'data/claims.csv').read_text(encoding='utf-8'), before)

    def test_build_keeps_manual_and_derived_rows(self):
        self.plan_with_rules()
        code, report = run(claims, 'build', '--plan', self.green / 'plan.md')
        self.assertEqual(code, 0, report)
        self.assertEqual(sorted(report['kept']), ['T-best-share', 'T-best-temp', 'T-derived'])
        text = (self.green / 'data/claims.csv').read_text(encoding='utf-8')
        for claim_id in ['T-a-share', 'T-b-share', 'T-best-temp', 'T-derived']:
            self.assertIn(claim_id, text)
        self.assertEqual(run(check, '--plan', self.green / 'plan.md')[0], 0)

    def test_where_goes_into_locator_and_key_must_be_unique(self):
        self.plan_with_rules(', where: {temperature: "80"}')
        run(claims, 'build', '--plan', self.green / 'plan.md')
        self.assertIn('tasting.csv: cup=b; temperature=80; column=share',
                      (self.green / 'data/claims.csv').read_text(encoding='utf-8'))
        self.edit(self.green / 'data/tasting.csv', 'b,2.5,80,0.875', 'a,2.5,80,0.875')
        self.assertEqual(run(claims, 'build', '--plan', self.green / 'plan.md')[0], 2)

    def test_broken_locator_fails_instead_of_unverifiable(self):
        self.edit(self.green / 'data/claims.csv', 'column=share', 'column=shre')
        code, report = run(check, '--plan', self.green / 'plan.md')
        failed = self.failed(report)['claims']
        self.assertEqual(failed['invalid'][0]['id'], 'T-best-share')
        self.assertEqual([u['id'] for u in failed['unverifiable']], ['T-derived'])

    def test_duplicate_ids_and_bom(self):
        path = self.green / 'data/claims.csv'
        path.write_text('﻿' + path.read_text(encoding='utf-8') +
                        'T-best-share,Дубль,0.875,tasting.csv: cup=b; column=share\n', encoding='utf-8')
        code, report = run(check, '--plan', self.green / 'plan.md')
        self.assertEqual(self.failed(report)['claims']['duplicates'], ['T-best-share'])

    def test_unknown_claims_and_caveats_in_plan_sections(self):
        self.edit(self.green / 'plan.md', 'claims: [T-best-share]', 'claims: [T-no-such]')
        report = run(check, '--plan', self.green / 'plan.md')[1]
        self.assertEqual(self.failed(report)['plan-sections']['unknown_claims'], ['T-no-such'])


class CheckRegressionTests(SeriesCase):
    def test_all_link_forms_follow_the_build_rule(self):
        results = self.green / 'sections/01-results.md'
        results.write_text(results.read_text(encoding='utf-8') +
                           '\n[пример][1]\n\n[1]: https://example.org\n\n<img src="//example.com/x.png">\n\n'
                           '[таблица](../data/tasting.csv)\n', encoding='utf-8')
        problems = self.failed(run(check, '--plan', self.green / 'plan.md')[1])['links']['problems']
        reasons = sorted({p['reason'].split(';')[0] for p in problems})
        self.assertEqual(reasons, ['external link', 'local link to a non-image'])
        self.assertEqual(len(problems), 3)

    def test_marker_needs_text_and_is_ignored_in_code(self):
        intro = self.green / 'sections/00-intro.md'
        self.edit(intro, '<!-- caveat:C1 --> Пробовал только один сорт, поэтому выводы скромные.',
                  '```\n<!-- caveat:C1 --> пример метки\n```\n\n<!-- caveat:C1 -->')
        report = run(check, '--plan', self.green / 'plan.md')[1]
        caveats = self.failed(report)['caveats']
        self.assertEqual(caveats['markers_without_text'], ['C1'])
        self.assertEqual(caveats['missing'], [{'caveat': 'C1', 'section': '00-intro.md'}])

    def test_frontmatter_only_file_without_newline(self):
        meta, body = split_frontmatter('---\ngranki: 1\n---')
        self.assertEqual((meta, body), ({'granki': 1}, ''))

    def test_bad_plan_fields_give_configuration_errors(self):
        self.edit(self.green / 'plan.md', "public: {forbidden: ['секретн'], assets_dir: assets}",
                  "public: {forbidden: ['('], assets_dir: assets}")
        self.assertEqual(run(check, '--plan', self.green / 'plan.md')[0], 2)

    def test_exit_codes_through_the_real_cli(self):
        script = str(SCRIPTS / 'check.py')
        ok = subprocess.run([sys.executable, script, '--plan', str(self.green / 'plan.md')], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.edit(self.green / 'sections/01-results.md', '87,50% гостей', '91,00% гостей')
        bad = subprocess.run([sys.executable, script, '--plan', str(self.green / 'plan.md')], capture_output=True, text=True)
        self.assertEqual((bad.returncode, json.loads(bad.stdout)['status']), (1, 'failed'))
        error = subprocess.run([sys.executable, script], capture_output=True, text=True)
        self.assertEqual(error.returncode, 2)


class DateNumbersTests(unittest.TestCase):
    def test_dates_are_not_traced_as_integers(self):
        # pilot: the agent made a claim for every day of month to pass integers: true
        from granki_core import without_dates
        text = 'С 6–31 октября было 145 сборок, кэш включили 3 ноября 2025 года, в ноябре 2025 — 12 промахов.'
        self.assertEqual(integer_tokens(without_dates(text)), ['145', '12'])
        self.assertIn('31', integer_tokens(text))


class AggregateClaimTests(unittest.TestCase):
    """Pilot: on a raw log 44 of 46 claims were 'derived:' and nobody checked them."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'log.csv').write_text('run,cache,secs\n1,off,800\n2,off,900\n3,off,1000\n4,hit,400\n5,miss,950\n6,hit,\n',
                                         encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def verify(self, table):
        rows = [dict(zip(['ID', 'formulation', 'value', 'source'], r)) for r in table]
        return claims.verify_rows(rows, [self.tmp])

    def test_aggregates_and_expressions_are_recomputed(self):
        report = self.verify([
            ('n-off', 'n', '3', 'log.csv: cache=off; agg=count'),
            ('med-off', 'm', '900', 'log.csv: cache=off; agg=median; column=secs'),
            ('med-cache', 'm', '675', 'log.csv: cache=hit|miss; agg=median; column=secs'),
            ('mean-all', 'm', '810', 'log.csv: agg=mean; column=secs'),
            ('effect', 'e', '-0.25', 'expr: med-cache / med-off - 1'),
            ('minutes', 'e', '15.0', 'expr: med-off / 60'),
        ])
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(report['unverifiable'], [])

    def test_drift_and_bad_aggregates_fail(self):
        report = self.verify([
            ('med-off', 'm', '850', 'log.csv: cache=off; agg=median; column=secs'),
            ('rounded', 'm', '0.3', 'expr: med-off / 3000'),
            ('typo', 'm', '1', 'log.csv: cache=off; agg=avg; column=secs'),
            ('nope', 'm', '1', 'expr: med-off / missing-id'),
            ('text', 'm', '1', 'log.csv: agg=sum; column=cache'),
        ])
        self.assertEqual([d['id'] for d in report['drift']], ['med-off'])
        self.assertEqual(sorted(i['id'] for i in report['invalid']), ['nope', 'text', 'typo'])


class PlanStageCheckTests(SeriesCase):
    def test_plan_is_checked_before_any_section_is_written(self):
        # pilot: check.py --plan on a fresh plan failed with "Sections folder not found"
        shutil.rmtree(self.green / 'sections')
        plan = self.green / 'plan.md'
        text = plan.read_text(encoding='utf-8')
        text = re.sub(r'status: (accepted|drafted), (accepted_sha: \w+, )?', 'status: planned, ', text)
        plan.write_text(text, encoding='utf-8')
        code, report = run(check, '--plan', plan)
        sections = next(c for c in report['checks'] if c['name'] == 'plan-sections')
        self.assertEqual(sections['not_written'], ['00-intro.md', '01-results.md'])
        self.assertEqual(sections['missing_files'], [])
        self.assertEqual(sections['status'], 'passed')


class JournalRegressionTests(SeriesCase):
    def setUp(self):
        super().setUp()
        self.journal = self.green / 'journal.md'
        self.payload = self.tmp / 'f.json'

    def add(self, items):
        self.payload.write_text(json.dumps(items, ensure_ascii=False), encoding='utf-8')
        return run(journal, 'add', '--journal', self.journal, '--source', 'r.md', '--findings', self.payload)

    def test_blank_line_duplicates_and_unknown_status(self):
        self.add([FINDING, FINDING])
        lines = self.journal.read_text(encoding='utf-8').splitlines()
        row = next(i for i, l in enumerate(lines) if l.startswith('| N002'))
        self.journal.write_text('\n'.join(lines[:row] + [''] + lines[row:]) + '\n', encoding='utf-8')
        self.assertEqual(run(journal, 'list', '--journal', self.journal)[1]['pending'], 2)
        self.assertEqual(self.add([FINDING])[1]['added'], ['N003'])
        text = self.journal.read_text(encoding='utf-8')
        self.journal.write_text(text.replace('| N003 |', '| N001 |'), encoding='utf-8')
        self.assertEqual(run(journal, 'list', '--journal', self.journal)[0], 2)
        self.journal.write_text(text.replace('| open |', '| Opne |', 1), encoding='utf-8')
        self.assertEqual(run(journal, 'list', '--journal', self.journal)[0], 2)

    def test_values_are_validated(self):
        self.assertEqual(self.add([{**FINDING, 'severity': 'critical'}])[0], 2)
        self.assertEqual(self.add([{**FINDING, 'kind': 'странная'}])[0], 2)
        self.assertEqual(self.add([{**FINDING, 'severity': 'Критично'}])[0], 0)
        self.assertEqual(run(journal, 'list', '--journal', self.journal)[1]['critical_pending'], 1)

    def test_quotes_with_pipe_and_ellipsis(self):
        (self.green / 'sections/01-results.md').write_text('## Р\n\nдоля | время и всё.\n', encoding='utf-8')
        self.add([{**FINDING, 'before': '«доля | время»'}, {**FINDING, 'before': '«…»'}])
        present = [f['still_present'] for f in run(journal, 'list', '--journal', self.journal)[1]['findings']]
        self.assertEqual(present, [True, None])

    def test_series_journal_resolves_article_targets(self):
        series_journal = self.tmp / 'journal.md'
        self.payload.write_text(json.dumps([{**FINDING, 'target': '01-green/01-results.md'}], ensure_ascii=False),
                                encoding='utf-8')
        run(journal, 'add', '--journal', series_journal, '--source', 'reviews/series.md', '--findings', self.payload)
        report = run(journal, 'list', '--series', self.series)[1]
        self.assertEqual(report['journals'][0]['findings'][0]['still_present'], True)

    def test_applied_warns_when_the_quote_is_still_in_the_text(self):
        # pilot: an edit failed, the finding was marked applied anyway
        (self.green / 'sections/01-results.md').write_text('## Р\n\nстарая фраза тут.\n', encoding='utf-8')
        self.add([{**FINDING, 'before': '«старая фраза»'}, {**FINDING, 'before': '«старая фраза»'}])
        report = run(journal, 'set', '--journal', self.journal, '--id', 'N001', '--status', 'applied')[1]
        self.assertTrue(any(w.startswith('N001') for w in report['warnings']))
        (self.green / 'sections/01-results.md').write_text('## Р\n\nновая фраза тут.\n', encoding='utf-8')
        report = run(journal, 'set', '--journal', self.journal, '--id', 'N002', '--status', 'applied')[1]
        self.assertNotIn('warnings', report)

    def test_parallel_adds_lose_nothing(self):
        self.payload.write_text(json.dumps([FINDING] * 5, ensure_ascii=False), encoding='utf-8')
        cmd = [sys.executable, str(SCRIPTS / 'journal.py'), 'add', '--journal', str(self.journal),
               '--source', 'r.md', '--findings', str(self.payload)]
        procs = [subprocess.Popen(cmd, stdout=subprocess.DEVNULL) for _ in range(8)]
        self.assertEqual([p.wait() for p in procs], [0] * 8)
        report = run(journal, 'list', '--journal', self.journal)[1]
        ids = [f['id'] for f in report['findings']]
        self.assertEqual((len(ids), len(set(ids))), (40, 40))


class StatusImpactPolicyTests(SeriesCase):
    def test_accepted_without_hash_and_review_without_hash(self):
        self.edit(self.green / 'plan.md', 'status: drafted, claims', 'status: accepted, claims')
        (self.green / 'reviews').mkdir()
        (self.green / 'reviews/a.md').write_text('---\nscope: Article\n---\n', encoding='utf-8')
        green = run(status, '--series', self.series)[1]['articles'][0]
        problems = {s['file']: s['problem'] for s in green['sections']}
        self.assertIn('accepted without accepted_sha', problems['01-results.md'])
        self.assertFalse(green['all_sections_accepted'])
        self.assertEqual((green['reviews'][0]['scope'], green['reviews'][0]['stale']), ('article', True))

    def test_impact_rejects_unknown_input_and_sees_tables(self):
        self.assertEqual(run(impact, '--series', self.series, '--claim', 'T-typo')[0], 2)
        self.assertEqual(run(impact, '--series', self.series, '--section', '01-green/09-none.md')[0], 2)
        self.edit(self.green / 'sections/01-results.md', ': 87,50% гостей выбрали эту чашку', '')
        report = run(impact, '--series', self.series, '--claim', 'T-best-temp')[1]
        self.assertTrue(report['articles'][0]['affected_sections'])

    def test_canon_warns_about_empty_replacements_and_code_headings(self):
        (self.green / 'canon.md').write_text('## Регистр\n\n```\n## Не заголовок\n```\n', encoding='utf-8')
        (self.tmp / 'canon.md').write_text('## Как я говорю и не говорю\n\n', encoding='utf-8')
        merged = run(canon, '--series', self.series, '--article', str(self.green), '--format', 'json')[1]
        self.assertTrue(any('empty section' in w for w in merged['warnings']))
        self.assertEqual([s['title'] for s in merged['sections']], ['Регистр', 'Как я говорю и не говорю', 'Площадки'])
        self.assertIn('## Не заголовок', merged['sections'][0]['body'])

    def test_canon_warns_when_append_or_remove_misses_the_upper_section(self):
        # a project file made by another tool may name the voice section differently
        (self.tmp / 'canon.md').write_text(
            '## Примеры голоса и уточнения (+)\n\n- пара\n\n## Площадка (-)\n', encoding='utf-8')
        merged = run(canon, '--series', self.series, '--article', str(self.green), '--format', 'json')[1]
        self.assertTrue(any('appends to «Примеры голоса и уточнения»' in w for w in merged['warnings']))
        self.assertTrue(any('removes «Площадка»' in w for w in merged['warnings']))
        self.assertIn('Площадки', [s['title'] for s in merged['sections']])


@unittest.skipUnless(os.environ.get('GRANKI_PANDOC') or shutil.which('pandoc'), 'Pandoc is not available')
class BuildRegressionTests(SeriesCase):
    def test_external_resources_comments_in_code_and_stale_pages(self):
        out = self.tmp / 'html'
        self.assertEqual(run(build_html, '--series', self.series, '--output', out)[0], 0)
        self.assertTrue((out / '02-black.html').is_file())
        self.edit(self.series, 'articles: [01-green, 02-black]', 'articles: [01-green]')
        report = run(build_html, '--series', self.series, '--output', out)[1]
        self.assertEqual(report['removed_pages'], ['02-black.html'])
        self.assertFalse((out / '02-black.html').exists())
        results = self.green / 'sections/01-results.md'
        results.write_text(results.read_text(encoding='utf-8') + '\n```\n<!-- в коде -->\n```\n', encoding='utf-8')
        self.assertEqual(run(build_html, '--series', self.series, '--output', out)[0], 0)
        self.assertIn('&lt;!-- в коде --&gt;', (out / '01-green.html').read_text(encoding='utf-8'))
        results.write_text(results.read_text(encoding='utf-8') + '\n<video src="//example.com/v.mp4"></video>\n',
                           encoding='utf-8')
        self.assertEqual(run(build_html, '--series', self.series, '--output', out)[0], 1)


class PolicyTemplateTests(unittest.TestCase):
    """Layers merge by exact section titles, so every place that names them must agree."""

    STANDARD = ['Проект и читатель', 'Площадки и форматы', 'Регистр и тональность', 'Словарь: запрещено/принято',
                'Фактура: на что опираемся', 'Примеры голоса', 'Как я говорю и не говорю', 'Открытые вопросы']
    REPO = Path(__file__).resolve().parents[4]

    def titles(self, path: Path) -> list[str]:
        return re.findall(r'^## (.+?)(?: \([+-]\))?$', path.read_text(encoding='utf-8'), re.M)

    def test_template_documents_and_skills_name_the_same_sections(self):
        template = self.titles(self.REPO / 'skills/granki-tools/assets/templates/canon.md')
        self.assertEqual(template, self.STANDARD, 'a renamed section breaks existing layers; update docs and examples')
        documented = (self.REPO / 'skills/granki-tools/references/formats.md').read_text(encoding='utf-8')
        voice = (self.REPO / 'skills/granki-editorial/references/voice.md').read_text(encoding='utf-8')
        for title in template:
            self.assertIn(f'«{title}»', documented, 'formats.md lists the standard sections')
            self.assertIn(f'«{title}»', voice, 'voice.md lists the standard sections')

    def test_example_project_layer_uses_template_titles_in_order(self):
        template = self.titles(self.REPO / 'skills/granki-tools/assets/templates/canon.md')
        example = self.titles(self.REPO / 'examples/bread/.agents/canon.md')
        self.assertEqual(example, [t for t in template if t in example])


if __name__ == '__main__':
    unittest.main()


class PlanRegressionTests(SeriesCase):
    def test_acceptance_is_blocked_by_author_gaps_and_pending_findings(self):
        plan_path = self.green / 'plan.md'
        results = self.green / 'sections/01-results.md'
        results.write_text(results.read_text(encoding='utf-8') + '\n[нужно от автора: сколько было гостей]\n', encoding='utf-8')
        from test_scripts import plan as plan_cli
        code, report = run(plan_cli, 'section', '--plan', plan_path, '--file', '01-results.md', '--set', 'accepted')
        self.assertEqual(code, 2)
        self.assertIn('нужно от автора', report['reason'])
        self.edit(results, '[нужно от автора: сколько было гостей]', '')
        payload = self.tmp / 'f.json'
        payload.write_text(json.dumps([FINDING], ensure_ascii=False), encoding='utf-8')
        run(journal, 'add', '--journal', self.green / 'journal.md', '--source', 'r.md', '--findings', payload)
        code, report = run(plan_cli, 'section', '--plan', plan_path, '--file', '01-results.md', '--set', 'accepted')
        self.assertIn('N001', report['reason'])
        run(journal, 'set', '--journal', self.green / 'journal.md', '--id', 'N001', '--status', 'deferred')
        code, report = run(plan_cli, 'section', '--plan', plan_path, '--file', '01-results.md', '--set', 'accepted')
        self.assertEqual(code, 0, report)
        self.assertIn('(отложены: N001)', (self.green / 'journal.md').read_text(encoding='utf-8'))
        payload.write_text(json.dumps([{**FINDING, 'severity': 'критично'}], ensure_ascii=False), encoding='utf-8')
        run(journal, 'add', '--journal', self.green / 'journal.md', '--source', 'r.md', '--findings', payload)
        run(journal, 'set', '--journal', self.green / 'journal.md', '--id', 'N002', '--status', 'deferred')
        self.assertEqual(run(plan_cli, 'section', '--plan', plan_path, '--file', '01-results.md', '--set', 'accepted')[0], 2)
        code, report = run(plan_cli, 'section', '--plan', plan_path, '--file', '01-results.md', '--set', 'accepted',
                           '--force', '--actor', 'автор')
        self.assertEqual(code, 0)
        self.assertIn('принят при: undecided or critical findings N002', (self.green / 'journal.md').read_text(encoding='utf-8'))

    def test_entry_and_series_status(self):
        from test_scripts import plan as plan_cli
        plan_path = self.green / 'plan.md'
        code, report = run(plan_cli, 'entry', '--plan', plan_path, '--file', '02-brewing.md', '--caveats', 'C1',
                           '--claims', 'T-best-temp', '--after', '01-results.md')
        self.assertEqual((code, report['created']), (0, True))
        self.assertEqual(run(plan_cli, 'entry', '--plan', plan_path, '--file', '02-brewing.md', '--caveats', 'C9')[0], 2)
        self.assertIn('02-brewing.md', plan_path.read_text(encoding='utf-8'))
        self.assertEqual(run(plan_cli, 'series', '--series', self.series, '--set', 'approved')[0], 2)
        self.assertEqual(run(plan_cli, 'series', '--series', self.series, '--set', 'draft')[0], 0)
        code, report = run(plan_cli, 'series', '--series', self.series, '--set', 'approved', '--actor', 'автор')
        self.assertEqual((code, report['to']), (0, 'approved'))
        self.assertEqual(run(plan_cli, 'series', '--series', self.series, '--set', 'whatever')[0], 2)
        state = run(status, '--series', self.series, '--format', 'md')[1]
        self.assertIn('План серии: approved.', state)

    def test_series_with_unplanned_article_and_series_ids(self):
        self.edit(self.series, 'articles: [01-green, 02-black]', 'articles: [01-green, 02-black, 03-oolong]')
        self.assertEqual(run(status, '--series', self.series)[0], 0)
        self.assertIn('| 03-oolong | planned, плана нет |', run(status, '--series', self.series, '--format', 'md')[1])
        code, report = run(check, '--series', self.series)
        self.assertEqual((code, report['not_planned']), (0, ['03-oolong']))
        self.assertEqual(run(impact, '--series', self.series, '--term', 'чай')[0], 0)
        payload = self.tmp / 'f.json'
        payload.write_text(json.dumps([{**FINDING, 'target': '01-green/01-results.md'}], ensure_ascii=False), encoding='utf-8')
        (self.tmp / 'reviews').mkdir()
        review = self.tmp / 'reviews/series-structure.md'
        review.write_text('---\nscope: series\nreviewed_sha: x\nfindings: []\n---\n\nОтчёт.\n', encoding='utf-8')
        report = run(journal, 'add', '--journal', self.tmp / 'journal.md', '--source', 'reviews/series-structure.md',
                     '--findings', payload)[1]
        self.assertEqual(report['added'], ['S001'])
        self.assertIn('findings:\n- S001', review.read_text(encoding='utf-8'))
        self.assertIn('(S001) из', (self.tmp / 'journal.md').read_text(encoding='utf-8'))

    def test_review_processed_after_its_findings_are_decided(self):
        section = self.green / 'sections/01-results.md'
        from granki_core import sha256_text
        (self.green / 'reviews').mkdir()
        review = self.green / 'reviews/sec-01-editorial.md'
        review.write_text(f'---\nscope: section\ntarget: 01-results.md\nreviewed_sha: '
                          f'{sha256_text(section.read_text(encoding="utf-8"))}\nfindings: []\n---\n', encoding='utf-8')
        payload = self.tmp / 'f.json'
        payload.write_text(json.dumps([FINDING], ensure_ascii=False), encoding='utf-8')
        run(journal, 'add', '--journal', self.green / 'journal.md', '--source', 'reviews/sec-01-editorial.md',
            '--findings', payload)
        states = lambda: [r['state'] for r in run(status, '--series', self.series)[1]['articles'][0]['reviews']]  # noqa: E731
        self.assertEqual(states(), ['current'])
        self.edit(section, 'Лучше всего вышло', 'Лучше всего получилось')
        self.assertEqual(states(), ['stale'])
        run(journal, 'set', '--journal', self.green / 'journal.md', '--id', 'N001', '--status', 'applied')
        self.assertEqual(states(), ['processed'])


class SecondRunRegressionTests(SeriesCase):
    def test_composite_key_and_plan_targets(self):
        from test_scripts import claims as claims_cli
        self.edit(self.green / 'plan.md', 'claims: [data/claims.csv]',
                  'claims: [data/claims.csv]\nclaims_build:\n  - {source: tasting.csv, key: [cup, minutes], '
                  'id: "T-{cup}-{minutes}-{column}", columns: [share]}')
        code, report = run(claims_cli, 'build', '--plan', self.green / 'plan.md')
        self.assertEqual(code, 0, report)
        self.assertIn('tasting.csv: cup=b; minutes=2.5; column=share',
                      (self.green / 'data/claims.csv').read_text(encoding='utf-8'))
        payload = self.tmp / 'f.json'
        payload.write_text(json.dumps([{**FINDING, 'target': 'plan.md', 'before': '«Раздел 00 — вступление»'}],
                                      ensure_ascii=False), encoding='utf-8')
        run(journal, 'add', '--journal', self.green / 'journal.md', '--source', 'r.md', '--findings', payload)
        found = run(journal, 'list', '--journal', self.green / 'journal.md')[1]['findings'][0]
        self.assertTrue(found['still_present'])
        payload.write_text(json.dumps([{**FINDING, 'target': 'series-plan.md', 'before': '«План серии для тестов»'}],
                                      ensure_ascii=False), encoding='utf-8')
        run(journal, 'add', '--journal', self.tmp / 'journal.md', '--source', 'r.md', '--findings', payload)
        series = run(journal, 'list', '--series', self.series)[1]['journals'][0]['findings'][0]
        self.assertTrue(series['still_present'])


class ConsistencyRegressionTests(SeriesCase):
    def test_series_skips_planned_articles_without_sections(self):
        self.edit(self.series, 'articles: [01-green, 02-black]', 'articles: [01-green, 02-black, 03-oolong]')
        (self.tmp / '03-oolong').mkdir()
        (self.tmp / '03-oolong/plan.md').write_text((SCRIPTS.parent / 'assets/templates/plan.md').read_text(encoding='utf-8'),
                                                    encoding='utf-8')
        code, report = run(check, '--series', self.series)
        self.assertEqual((code, report['not_planned']), (0, ['03-oolong']))
        self.assertEqual(run(impact, '--series', self.series, '--claim', 'T-best-share')[0], 0)

    def test_known_divergence_in_published_article_is_reported_not_failed(self):
        self.edit(self.black / 'data/tasting.csv', 'b,2.5,80,0.875', 'b,2.5,80,0.9')
        self.assertEqual(run(check, '--series', self.series)[0], 1)
        self.edit(self.series, 'known_divergences: []', 'known_divergences: [T-best-share]')
        code, report = run(check, '--plan', self.black / 'plan.md')
        claims_check = next(c for c in report['checks'] if c['name'] == 'claims')
        self.assertEqual((code, [d['id'] for d in claims_check['accepted_divergences']]), (0, ['T-best-share']))

    def test_article_review_needs_unchanged_accepted_sections(self):
        from test_scripts import plan as plan_cli
        p = self.green / 'plan.md'
        run(plan_cli, 'section', '--plan', p, '--file', '01-results.md', '--set', 'accepted')
        self.edit(self.green / 'sections/01-results.md', 'Лучше всего', 'Лучше всех')
        code, report = run(plan_cli, 'status', '--plan', p, '--set', 'article-review')
        self.assertEqual(code, 2)
        self.assertIn('01-results.md', report['reason'])

    def test_empty_review_is_logged_and_rooms_without_bmad(self):
        payload = self.tmp / 'f.json'
        payload.write_text('[]', encoding='utf-8')
        run(journal, 'add', '--journal', self.green / 'journal.md', '--source', 'reviews/x.md', '--findings', payload)
        self.assertIn('ревью без находок: reviews/x.md', (self.green / 'journal.md').read_text(encoding='utf-8'))
        from test_scripts import rooms
        code, report = run(rooms, 'status', '--project-root', self.tmp)
        self.assertEqual((code, report['installed'], report['bmad_core']), (0, False, False))


@unittest.skipUnless(os.environ.get('GRANKI_PANDOC') or shutil.which('pandoc'), 'Pandoc is not available')
class SingleArticleBuildTests(SeriesCase):
    def test_single_article_build_matches_series_build(self):
        series_out, single_out = self.tmp / 'series', self.tmp / 'single'
        run(build_html, '--series', self.series, '--output', series_out)
        code, report = run(build_html, '--plan', self.black / 'plan.md', '--output', single_out)
        self.assertEqual(code, 0, report)
        self.assertEqual((single_out / '02-black.html').read_bytes(), (series_out / '02-black.html').read_bytes())


class WorkspaceTests(unittest.TestCase):
    def test_journal_and_reviews_live_next_to_the_plan_when_root_points_elsewhere(self):
        from fixture import make_series
        from test_scripts import plan as plan_cli
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        make_series(tmp / 'src')
        work = tmp / 'pilot/01-green'
        work.mkdir(parents=True)
        text = (tmp / 'src/01-green/plan.md').read_text(encoding='utf-8')
        (work / 'plan.md').write_text(text.replace('granki: 1\n', 'granki: 1\nroot: ../../src/01-green\n', 1), encoding='utf-8')
        (tmp / 'pilot/series-plan.md').write_text('---\ngranki: 1\narticles: [01-green]\n---\n', encoding='utf-8')
        code, report = run(plan_cli, 'entry', '--plan', work / 'plan.md', '--file', '02-more.md', '--set', 'drafted')
        self.assertEqual(code, 0, report)
        self.assertTrue((work / 'journal.md').is_file())
        self.assertFalse((tmp / 'src/01-green/journal.md').exists())
        state = run(status, '--series', tmp / 'pilot/series-plan.md')[1]['articles'][0]
        self.assertIn('02-more.md', [s['file'] for s in state['sections'] if s['status'] == 'drafted'])
