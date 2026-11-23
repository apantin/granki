#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Count structural traces of model prose in a section, an article or a file.

Scope:
  --plan PLAN                    every section of the article, in plan order
  --plan PLAN --section FILE     one section
  --file FILE                    any Markdown file

Only prose counts: frontmatter, HTML comments, code, tables, headings and
images are skipped. Paragraphs are numbered from the nearest heading, as
«абз. N» in editorial findings; tables, code and images are not paragraphs.

Categories:
  refusal      the text says what it will not do or cannot tell:
               «выводов не делаю», «сравнивать не буду», «не назову»,
               «дневник не говорит», «по дневнику не понять», «это опыт
               одной кухни». A limit stated with a fact («всего три
               поездки», «по памяти», «около») is not a refusal.
  self_ref     the text talks about its data or its own layout: «в таблице»,
               «так она и стоит в таблице», «эта цифра слабее», «дальше это
               видно», «в этом разделе».
  inoculation  a cliché named in order to disown it: «„в разы“ не напишу»,
               «хотя напрашивается».
  colon        a colon that explains inside a prose sentence; not before a
               list or table, not after a one-word label («Было: …»), not
               before a quotation.
  anaphora     three short parallel phrases that open with the same word:
               «одна печь, одна мука, одно лето».
  dash         a dash between words inside a prose sentence: «мешок — около
               тысячи», «— у другого пекаря может выйти иначе».

A match in a sentence that a caveat marker opens carries `caveat: <ID>`:
it is the required caveat, its content stays.

Distribution: paragraphs with a refusal or self_ref, the coefficient of
variation of sentence and paragraph length (in words), one-sentence
paragraphs. Lists count as one paragraph and are left out of the lengths.

Signals are landmarks, not norms. They were picked by hand on the texts of
the November 2026 pilot (docs/dev/style.md), 370–1500 words each: eight
Granki versions of the studs article written by Opus, which readers
recognised as model prose, against the bare model and the `statya` skill
on three topics (seven texts). Ranges below are «Granki studs» against
«bare model and statya»:
  refusal ≥ 5 per 1000 words or in ≥ 25% of paragraphs: 8–15 per 1000 and
               38–50% of paragraphs against 0–3 and at most 11%. The one
               Sonnet version had 3.6 and 14% and does not fire.
  self_ref ≥ 10 per 1000 words: 6–14 against 0–9. The bare model also says
               «в таблице», so self_ref alone is a weak sign.
  refusal or self_ref in ≥ 45% of paragraphs: 60–75% against 0–28%.
  inoculation, anaphora: any case. Inoculation in four Granki versions and
               in no other text; anaphora in two Granki versions and one
               bare-model text.
  colon ≥ 15 per 1000 words: 12–22 against 6–15.
  dash ≥ 14 per 1000 words (the limit of the blog-eval kit): the authors'
               old posts 5–9, Granki full runs 15–24, the bare model 0–23.
  sentence length CV < 0.45: 0.33–0.50 against 0.45–0.59.
  paragraph length CV < 0.40 (from 5 prose paragraphs): 0.35–0.63 against
               0.40–0.57.
  one-sentence paragraphs ≥ 25% (from 8 prose paragraphs): a sign of chopped
               prose from outside reviews; no pilot text reached it (at most
               23%, and the Granki versions had 0–3).
Densities need at least two cases (three colons, two paragraphs), so one
phrase in a short section does not fire.
Other Granki texts of the pilot (the first bike article, CI, solar) fall in
between: many colons and self_ref, few refusals. Recalibrate on new texts before
treating any limit as firm.

The script finds candidates; the agent decides. A limit on a conclusion and
a required caveat (`caveat` marker) are not defects.

Prints a JSON report. Exit code 0 whatever the counts, 2 on input errors.
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from granki_core import (COMMENT, MARKER, GrankiError, dump_json, load_plan, section_paths,  # noqa: E402
                         split_frontmatter, strip_code)

# Words that name the author's own records.
DATA = (r'(?:(?:дневник|таблиц|выгрузк|запис[ьяиейя])\w*|журнал(?:е|а|у|ом|ы|ах|ов)?|лог(?:и|ах|ам|ов|а|у)?'
        r'|данн(?:ые|ых|ым|ыми))')
# Verbs of reasoning that a refusal declines: «сравнивать не буду», «не берусь судить».
REASON = (r'(?:сравнивать|считать|подсчитывать|гадать|выдумывать|придумывать|судить|утверждать|обобщать|называть|'
          r'делать|говорить|писать|оценивать|приписывать|экстраполировать|переносить|объяснять|угадывать|домысливать|'
          r'спекулировать|раскладывать|повторять|сравню|посчитаю)')

REFUSAL = [
    r'выводо?в?а? (?:[\w-]+ ){0,4}не (?:делаю|делаем|сделаю|будет|буду|стану)',
    r'(?:не )?делать выводы? (?:[\w-]+ ){0,2}не (?:буду|стану|берусь)',
    REASON + r' (?:[\w-]+ ){0,1}не (?:буду|будем|стану|станем|берусь|возьмусь)',
    r'не (?:буду|будем|стану|берусь|возьмусь) (?:[\w-]+ ){0,1}' + REASON,
    r'не берусь',
    r'не (?:сравниваю|списываю)',
    r'вывод\w* (?:[\w-]+ ){0,3}нет',
    r'(?:сравнивать|разделить|сказать|судить|утверждать|понять) (?:[\w-]+ ){0,3}нельзя',
    r'не (?:скажу|назову|напишу|утверждаю|обещаю|претендую)',
    r'(?:нельзя|не могу|не возьмусь|трудно|сложно) (?:сказать|судить|утверждать)',
    r'(?:сказать|судить|утверждать) (?:нельзя|не могу|не берусь|трудно|сложно)',
    DATA + r' (?:[\w-]+ ){0,2}не (?:говор|показ|скаж|отвеча|позволя|да[её]т|дают)\w*',
    r'(?:по|из) (?:мо\w+ |эт\w+ |сво\w+ |одн\w+ )?' + DATA + r' (?:[\w-]+ ){0,2}не (?:понять|сказать|скажешь|видно|ясно|разобрать|определить|узнать)',
    r'не (?:понять|сказать|скажешь|видно|разобрать) по (?:мо\w+ |эт\w+ |сво\w+ )?' + DATA,
    r'по [\w-]+(?: [\w-]+)? не (?:понять|скажешь|сказать)',
    r'(?:поэтому|так что) (?:[\w-]+ ){0,2}не (?:считаю|сравниваю|оцениваю|делаю|пишу)',
    r'опыт одн(?:ого|ой|ого моего|ой моей)\b(?: [\w-]+)?',
    r'(?:выводы?|это|всё это|все это) только (?:про|обо?|для) (?:меня|себя|мо\w+|наш\w+)',
    r'за всех (?:я )?не (?:отвечаю|скажу|ручаюсь)',
    r'решать (?:каждому|вам|тебе|самому|самим|читателю)',
]
SELF_REF = [
    r'так (?:она|он|оно|они) и (?:стои\w+|записан\w*|остал\w+)(?: в ' + DATA + r')?',
    r'(?:в|из|по) (?:эт\w+ |мо\w+ |сво\w+ |наш\w+ )?' + DATA,
    DATA + r' (?:говор|показ|стоит|стоят|записан)\w*',
    r'(?:эта|эти|это|та|такая|самая) (?:цифр|числ|граф)\w*(?: [\w-]+)? (?:слабее|сильнее|точнее|надёжнее|грубее|мягче|приблизительн\w*|слаб\w+|мягк\w+)',
    r'(?:дальше|ниже|выше) (?:это )?(?:будет )?видно',
    r'как (?:видно|показано|сказано|говорилось)(?: (?:выше|ниже|в таблице))?',
    r'(?:выше|ниже) в (?:таблице|тексте|разделе)',
    r'(?:в )?(?:этом|этого|этот|следующем|прошлом|предыдущем) (?:разделе|раздел|тексте|текст)',
    r'(?:в )?(?:этой|эта|этой же|следующей|прошлой|первой) (?:статье|статья|статьи)(?: серии)?',
]
QUOTE = r'[«"„][^»"“\n]{1,40}[»"“]'
INOCULATION = [
    r'(?:так |это |этого )?не (?:на)?(?:пишу|пишем|скажу|назову),? хотя (?:и |так и )?напрашива\w+',
    QUOTE + r' (?:[\w-]+ ){0,2}не (?:на)?(?:пишу|пишем|скажу|назову|буду писать)(?:,? хотя (?:и |так и )?напрашива\w+)?',
    r'не (?:на)?(?:пишу|пишем|скажу|назову) ' + QUOTE + r'(?:,? хотя (?:и |так и )?напрашива\w+)?',
    r'хотя (?:и |так и )?напрашива\w+',
    r'язык не повернётся',
    r'громко сказано',
    r'(?:модн|красив|громк)\w+ слов\w*',
]


def compile_any(patterns: list[str]) -> re.Pattern:
    return re.compile(r'(?<![\w-])(?:' + '|'.join(patterns) + r')(?![\w-])', re.I)


RX = {'refusal': compile_any(REFUSAL), 'self_ref': compile_any(SELF_REF), 'inoculation': compile_any(INOCULATION)}
WORD = re.compile(r'\d+(?:[.,]\d+)*|[^\W\d_]+(?:-[^\W\d_]+)*')
SENTENCE_END = re.compile(r'(?<=[.!?…])["»)]?\s+(?=[^a-zа-яё,;:])|\n')
HEADING = re.compile(r'^ {0,3}#{1,6}(?:[ \t]+(.*?))?[ \t#]*$')
LIST_ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+')
# A caveat marker kept in the prose while comments are removed: it tells which sentence is a required caveat.
KEPT_MARKER = re.compile('\ue000([A-Za-z0-9_.-]+)\ue001')
DASH = re.compile(r'(?<=\w)[*_»")]*\s+[—–]\s+(?=[\w«"„])')
COLON = re.compile(r'(?<=[^\s:])[*_]*:\s+(?=[^\s«"„])')
# Words that start each of three parallel phrases; forms of one word count as one.
FAMILIES = {f: base for base, forms in {
    'один': 'один одна одно одни одного одной одному одним одну',
    'каждый': 'каждый каждая каждое каждые каждого каждой каждому каждую',
    'мой': 'мой моя моё мое мои моего моей',
    'свой': 'свой своя своё свое свои своего своей',
    'этот': 'этот эта это эти этого этой',
    'тот': 'тот та то те того той',
    'весь': 'весь вся всё все всего всей',
    'никакой': 'никакой никакая никакое никакие никаких',
}.items() for f in forms.split()}

# Landmarks from the pilot texts, see the module docstring.
SIGNAL_LIMITS = {'refusal_per_1000': 5, 'refusal_share': 0.25, 'self_ref_per_1000': 10, 'flagged_share': 0.45,
                 'colon_per_1000': 15, 'sentence_cv': 0.45, 'paragraph_cv': 0.40, 'one_sentence_share': 0.25,
                 'dash_per_1000': 14, 'min_cases': 2, 'min_colons': 3}


def words(text: str) -> list[str]:
    return WORD.findall(text)


def paragraphs(name: str, text: str) -> list[dict]:
    """Prose paragraphs of one file with the heading they follow and their number under it."""
    _, body = split_frontmatter(text)
    body = COMMENT.sub('', MARKER.sub(lambda m: f' \ue000{m.group(1)}\ue001 ', strip_code(body)))
    out, current, heading, number = [], None, None, 0

    def close():
        nonlocal current, number
        if current and re.search(r'\w', clean(' '.join(current['lines']))):
            number += 1
            raw = ('\n' if current['list'] else ' ').join(current['lines'])
            out.append({'file': name, 'heading': heading, 'paragraph': number, 'list': current['list'],
                        'text': clean(raw), 'sentences': sentences(raw)})
        current = None

    for line in body.splitlines():
        stripped = line.strip()
        match = HEADING.match(line)
        if match:
            close()
            heading, number = (match.group(1) or '').strip(), 0
            continue
        if not stripped or stripped.startswith(('|', '![', '<')):
            close()
            continue
        stripped = re.sub(r'^(?:>\s*)+', '', stripped)
        item = LIST_ITEM.match(stripped)
        if item:
            if current and not current['list']:
                close()
            current = current or {'lines': [], 'list': True}
            current['lines'].append(stripped[item.end():])
            continue
        if current and current['list'] and not line.startswith((' ', '\t')):
            close()
        current = current or {'lines': [], 'list': False}
        current['lines'].append(stripped)
    close()
    return out


def clean(text: str) -> str:
    return re.sub(r'[^\S\n]+', ' ', KEPT_MARKER.sub('', text)).strip()


def sentences(text: str) -> list[tuple[str | None, str]]:
    """(caveat ID or None, sentence); the ID is set when a caveat marker opens the sentence."""
    out = []
    for piece in SENTENCE_END.split(text):
        if not re.search(r'\w', clean(piece)):
            continue
        opening = KEPT_MARKER.match(piece.strip())
        out.append((opening.group(1) if opening else None, clean(piece)))
    return out


def anaphora(sentence: str) -> list[str]:
    """Runs of three or more short phrases, split by commas or «и», that open with the same word."""
    found = []
    segments = [s.strip(' —-«»"()') for s in re.split(r',|;|\s—\s|\s(?:и|или|а)\s', sentence)]
    run = []
    for seg in segments + ['']:
        toks = words(seg)
        lead = toks[0].lower() if toks and len(toks) <= 4 else None
        key = FAMILIES.get(lead, lead if lead and len(lead) >= 3 and not lead.isdigit() else None)
        if key and run and run[-1][0] == key:
            run.append((key, seg))
            continue
        if len(run) >= 3:
            first, last = run[0][1], run[-1][1]
            start = sentence.find(first)
            end = sentence.find(last, start) + len(last)
            found.append(sentence[start:end] if start >= 0 and end > start else ', '.join(s for _, s in run))
        run = [(key, seg)] if key else []
    return found


def colons(sentence: str) -> list[str]:
    hits = []
    for match in COLON.finditer(sentence):
        before, after = sentence[:match.start()], sentence[match.end():]
        if len(words(before)) < 2 or not words(after) or before.count('[') > before.count(']'):
            continue  # a label such as «Было: …», a colon that ends the sentence, «[нужно от автора: …]»
        hits.append(' '.join(before.split()[-3:]) + ': ' + ' '.join(after.split()[:4]))
    return hits


def dashes(sentence: str) -> list[str]:
    return [' '.join(sentence[:m.start()].split()[-3:]) + ' — ' + ' '.join(sentence[m.end():].split()[:4])
            for m in DASH.finditer(sentence)]


def cv(values: list[int]) -> float | None:
    if len(values) < 2 or not statistics.mean(values):
        return None
    return round(statistics.pstdev(values) / statistics.mean(values), 2)


def per_1000(count: int, total: int) -> float:
    return round(count * 1000 / total, 1) if total else 0.0


def measure(texts: list[tuple[str, str]]) -> dict:
    pars = [p for name, text in texts for p in paragraphs(name, text)]
    for index, par in enumerate(pars):
        par['index'] = index
    total = sum(len(words(p['text'])) for p in pars)
    found = {k: [] for k in ('refusal', 'self_ref', 'inoculation', 'colon', 'anaphora', 'dash')}
    for par, caveat, sent in [(p, c, s) for p in pars for c, s in p['sentences']]:
        spans = {}
        for kind in ('inoculation', 'refusal', 'self_ref'):
            spans[kind] = [m for m in RX[kind].finditer(sent)]
        taken = [(m.start(), m.end()) for m in spans['inoculation']]
        # a disowned cliché is counted once, as inoculation
        spans['refusal'] = [m for m in spans['refusal'] if not any(a < m.end() and m.start() < b for a, b in taken)]
        taken += [(m.start(), m.end()) for m in spans['refusal']]
        # «дневник не говорит» is a refusal; its «дневник» is not counted again as self_ref
        spans['self_ref'] = [m for m in spans['self_ref'] if not any(a < m.end() and m.start() < b for a, b in taken)]
        hits = {k: [m.group(0) for m in v] for k, v in spans.items()}
        if not par['list']:
            hits['colon'] = colons(sent)
            hits['dash'] = dashes(sent)
        hits['anaphora'] = anaphora(sent)
        for kind, quotes in hits.items():
            for quote in quotes:
                hit = {'file': par['file'], 'heading': par['heading'], 'paragraph': par['paragraph'],
                       'quote': quote, 'sentence': sent}
                if caveat:
                    hit['caveat'] = caveat
                found[kind].append((par['index'], hit))
    categories = {}
    for kind, hits in found.items():
        categories[kind] = {'count': len(hits), 'per_1000': per_1000(len(hits), total),
                            'paragraphs': len({i for i, _ in hits}), 'matches': [h for _, h in hits]}
    flagged = {i for kind in ('refusal', 'self_ref') for i, _ in found[kind]}
    prose_pars = [p for p in pars if not p['list']]
    sent_len = [len(words(s)) for p in prose_pars for _, s in p['sentences']]
    par_len = [len(words(p['text'])) for p in prose_pars]
    one_sentence = [p for p in prose_pars if len(p['sentences']) == 1]
    distribution = {
        'paragraphs': len(pars),
        'flagged_paragraphs': len(flagged),
        'flagged_share': round(len(flagged) / len(pars), 2) if pars else 0.0,
        'refusal_share': round(categories['refusal']['paragraphs'] / len(pars), 2) if pars else 0.0,
        'sentences': len(sent_len),
        'sentence_mean': round(statistics.mean(sent_len), 1) if sent_len else 0.0,
        'sentence_cv': cv(sent_len),
        'paragraph_cv': cv(par_len),
        'one_sentence_paragraphs': len(one_sentence),
    }
    return {'words': total, 'categories': categories, 'distribution': distribution,
            'signals': signals(categories, distribution, len(pars), len(prose_pars), total)}


def number(value: float) -> str:
    return f'{value:g}'.replace('.', ',')


def quoted(text: str) -> str:
    """«…» around a quote; quotation marks inside become „…“."""
    return '«' + text.replace('«', '„').replace('»', '“') + '»'


def of_paragraphs(part: int, whole: int) -> str:
    """«в 6 из 11 абзацев», «в 2 из 21 абзаца»."""
    noun = 'абзаца' if whole % 10 == 1 and whole % 100 != 11 else 'абзацев'
    return f'в {part} из {whole} {noun}'


def signals(cat: dict, dist: dict, n_pars: int, n_prose: int, total: int) -> list[str]:
    """Landmarks that fired, in words; thresholds and their origin are in the module docstring."""
    out, lim = [], SIGNAL_LIMITS
    if not total:
        return out
    ref, own, colon = cat['refusal'], cat['self_ref'], cat['colon']
    if ref['count'] >= lim['min_cases'] and (ref['per_1000'] >= lim['refusal_per_1000'] or dist['refusal_share'] >= lim['refusal_share']):
        out.append(f'фразы-отказы {of_paragraphs(ref["paragraphs"], n_pars)}: {ref["count"]}, '
                   f'{number(ref["per_1000"])} на 1000 слов')
    if own['count'] >= lim['min_cases'] and own['per_1000'] >= lim['self_ref_per_1000']:
        out.append(f'текст о своих данных и устройстве {of_paragraphs(own["paragraphs"], n_pars)}: {own["count"]}, '
                   f'{number(own["per_1000"])} на 1000 слов')
    if dist['flagged_paragraphs'] >= lim['min_cases'] and dist['flagged_share'] >= lim['flagged_share']:
        out.append(f'отказ или текст о своих данных {of_paragraphs(dist["flagged_paragraphs"], n_pars)}')
    for kind, label in (('inoculation', '«прививка», штамп назван ради отказа от него'),
                        ('anaphora', 'анафорическая тройка')):
        if cat[kind]['count']:
            out.append(label + ': ' + '; '.join(quoted(h['quote']) for h in cat[kind]['matches'][:3]))
    if colon['count'] >= lim['min_colons'] and colon['per_1000'] >= lim['colon_per_1000']:
        out.append(f'двоеточия-пояснения: {colon["count"]}, {number(colon["per_1000"])} на 1000 слов')
    dash = cat['dash']
    if dash['count'] >= lim['min_colons'] and dash['per_1000'] >= lim['dash_per_1000']:
        out.append(f'тире между словами: {dash["count"]}, {number(dash["per_1000"])} на 1000 слов')
    if dist['sentence_cv'] is not None and dist['sentences'] >= 10 and dist['sentence_cv'] < lim['sentence_cv']:
        out.append(f'предложения ровной длины: коэффициент вариации {number(dist["sentence_cv"])}, '
                   f'ориентир — от {number(lim["sentence_cv"])}')
    if dist['paragraph_cv'] is not None and n_prose >= 5 and dist['paragraph_cv'] < lim['paragraph_cv']:
        out.append(f'абзацы ровной длины: коэффициент вариации {number(dist["paragraph_cv"])}, '
                   f'ориентир — от {number(lim["paragraph_cv"])}')
    if n_prose >= 8 and dist['one_sentence_paragraphs'] / n_prose >= lim['one_sentence_share']:
        out.append(f'абзацы из одного предложения: {dist["one_sentence_paragraphs"]} из {n_prose}')
    return out


NOTE = ('Скрипт находит кандидатов, решает агент. Ограничение вывода и обязательная оговорка (caveat) — не дефект; '
        'ориентиры signals взяты по текстам пилота, это не нормы.')


def style_plan(plan_path: Path, section: str | None = None) -> dict:
    plan = load_plan(plan_path)
    sections_dir = (plan['_root'] / plan['sections_dir']).resolve()
    paths = section_paths(sections_dir)
    if section is not None:
        paths = [p for p in paths if p.name == section]
        if not paths:
            raise GrankiError(f'Section {section} not found in {sections_dir}')
    texts = [(p.name, p.read_text(encoding='utf-8')) for p in paths]
    return {'status': 'passed', 'scope': 'section' if section else 'article', 'article': str(plan['_root']),
            'title': plan.get('title'), 'sections': [n for n, _ in texts], **measure(texts), 'note': NOTE}


def style_file(path: Path) -> dict:
    if not path.is_file():
        raise GrankiError(f'File not found: {path}')
    return {'status': 'passed', 'scope': 'file', 'file': str(path),
            **measure([(path.name, path.read_text(encoding='utf-8'))]), 'note': NOTE}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', type=Path, help='article plan.md')
    parser.add_argument('--section', help='one section file, for example 03-results.md')
    parser.add_argument('--file', type=Path, help='any Markdown file')
    args = parser.parse_args(argv)
    try:
        if bool(args.plan) == bool(args.file):
            raise GrankiError('Pass exactly one of --plan or --file')
        if args.section and not args.plan:
            raise GrankiError('--section needs --plan')
        section = Path(args.section).name if args.section else None
        report = style_plan(args.plan, section) if args.plan else style_file(args.file)
    except (GrankiError, OSError, UnicodeDecodeError) as error:
        sys.stdout.write(dump_json({'status': 'error', 'reason': str(error)}))
        return 2
    except Exception as error:  # unexpected input must not look like a finished count
        sys.stdout.write(dump_json({'status': 'error', 'reason': f'{type(error).__name__}: {error}'}))
        return 2
    sys.stdout.write(dump_json(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
