"""A small fictional series for tests: two articles about tea brewing."""
from __future__ import annotations

import base64
import textwrap
from pathlib import Path

# A 1x1 transparent PNG.
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')

SERIES = """\
---
granki: 1
title: Заварка чая
status: writing
articles: [01-green, 02-black]
known_divergences: []
policy: project-redpolitika.md
html: {brand: Чай, tagline: Опыты на кухне, index_kicker: Серия о чае}
---

# Заварка чая

План серии для тестов.
"""

GREEN_PLAN = """\
---
granki: 1
title: Зелёный чай
status: writing
version: 1
description: Сколько держать зелёный чай.
length: {min: 50, max: 2000}
claims: [data/claims.csv]
numbers: {decimal: ",", renderers: ["percent:2", "fixed:1"], allow: ["2,5"]}
caveats:
  C1: {text: Пробовали один сорт чая}
required_caveats: [C1]
public: {forbidden: ['секретн'], assets_dir: assets}
sections:
  - {file: 00-intro.md, status: accepted, accepted_sha: SHA_INTRO, caveats: [C1]}
  - {file: 01-results.md, status: drafted, claims: [T-best-share]}
---

# План статьи

Раздел 00 — вступление, раздел 01 — результаты.
"""

INTRO = """\
# Зелёный чай: сколько держать

Я заваривал один сорт три раза подряд. <!-- caveat:C1 --> Пробовал только один сорт, поэтому выводы скромные.
"""

RESULTS = """\
## Результаты

Лучше всего вышло за 2,5 минуты: 87,50% гостей выбрали эту чашку, вода была 80,0 градусов.

| Время | Доля |
|---|---|
| 2,5 | 87,50% |

![График](../assets/chart.png)
"""

CLAIMS = """\
ID,formulation,value,source
T-best-share,Доля за лучшую чашку,0.875,tasting.csv: cup=b; column=share
T-best-temp,Температура лучшей чашки,80,tasting.csv: row=3; column=temperature
T-derived,Разница долей,0.5,derived: share(b) minus share(a)
"""

TASTING = """\
cup,minutes,temperature,share
a,1.5,80,0.375
b,2.5,80,0.875
"""

BLACK_PLAN = """\
---
granki: 1
title: Чёрный чай
status: published
version: 1
claims: [data/claims.csv]
published:
  - {version: 1, date: 2026-01-01, sections: {00-intro.md: SHA_BLACK}}
sections:
  - {file: 00-intro.md, status: accepted, accepted_sha: SHA_BLACK}
---
"""

BLACK = """\
# Чёрный чай

Здесь 87,50% гостей тоже выбрали вторую чашку.
"""

BLACK_CLAIMS = """\
ID,formulation,value,source
T-best-share,Доля за лучшую чашку,0.875,tasting.csv: cup=b; column=share
"""


PROJECT_POLICY = """\
# Редполитика проекта

Общие правила для всех текстов.

## Регистр

Авторский, на «ты».

## Как я говорю и не говорю

- Не пишу «интервал включает ноль».

## Площадки

Блог.
"""

SERIES_POLICY = """\
## Как я говорю и не говорю (+)

- В серии о чае не называю сорта брендами.

## Площадки (-)

## Читатель серии

Любители чая без опыта дегустаций.
"""

ARTICLE_POLICY = """\
## Регистр

Строгий, без обращения к читателю.
"""


def write(path: Path, text) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(textwrap.dedent(text), encoding='utf-8')


def make_series(root: Path) -> Path:
    """Write the fixture series under root and return series-plan.md."""
    import hashlib
    sha = lambda t: hashlib.sha256(t.encode()).hexdigest()  # noqa: E731
    write(root / 'series-plan.md', SERIES)
    write(root / 'project-redpolitika.md', PROJECT_POLICY)
    write(root / 'redpolitika.md', SERIES_POLICY)
    write(root / '01-green/redpolitika.md', ARTICLE_POLICY)
    green = root / '01-green'
    write(green / 'plan.md', GREEN_PLAN.replace('SHA_INTRO', sha(INTRO)))
    write(green / 'sections/00-intro.md', INTRO)
    write(green / 'sections/01-results.md', RESULTS)
    write(green / 'data/claims.csv', CLAIMS)
    write(green / 'data/tasting.csv', TASTING)
    write(green / 'assets/chart.png', PNG)
    black = root / '02-black'
    write(black / 'plan.md', BLACK_PLAN.replace('SHA_BLACK', sha(BLACK)))
    write(black / 'sections/00-intro.md', BLACK)
    write(black / 'data/claims.csv', BLACK_CLAIMS)
    write(black / 'data/tasting.csv', TASTING)
    return root / 'series-plan.md'
