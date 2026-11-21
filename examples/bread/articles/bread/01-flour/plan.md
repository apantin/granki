---
granki: 1
title: Какая мука лучше для хлеба на закваске
status: writing
version: 1
description: Три вида муки и две расстойки на одной домашней закваске.
sections_dir: sections
length:
  min: 800
  max: 4000
claims:
- data/claims.csv
data_dirs:
- data
claims_build:
- source: bake.csv
  key:
  - flour_id
  - hours
  id: B-{flour_id}-{hours}-{column}
  formulation: '{flour}, {hours} ч: {column}'
  columns:
  - rise
  - liked
numbers:
  decimal: ','
  renderers:
  - percent:0
  - fixed:1
  allow: []
  integers: true
caveats:
  C1:
    text: Одна духовка и одна закваска
  C2:
    text: 12 гостей — разница в один-два голоса может быть случайной
required_caveats:
- C1
- C2
public:
  forbidden:
  - марк[аи] муки
  allow_external_links: false
  assets_dir: assets
sections:
- file: 00-intro.md
  status: drafted
  caveats:
  - C1
  claims:
  - B-tasters
  - B-long
- file: 01-results.md
  status: drafted
  caveats:
  - C2
  claims:
  - B-wheat-12-rise
  - B-wheat-12-liked
  - B-rye-12-rise
  - B-rye-12-liked
  - B-whole-12-rise
  - B-whole-12-liked
  - B-wheat-8-rise
  - B-wheat-8-liked
- file: 02-advice.md
  status: drafted
  caveats:
  - C1
published: []
---

# План статьи: Какая мука лучше для хлеба на закваске

## Вопрос читателя и тезис

Какую муку взять и сколько держать тесто? На моей закваске и в моей духовке пшеничная мука после 12 часов поднялась выше всех и понравилась большинству гостей.

## Разделы

### 00-intro.md — как пекли

- Назначение: читатель понимает, что сравнивали и как пробовали.
- Тезисы: шесть буханок — три вида муки, две расстойки; 12 гостей вслепую; можно отметить несколько буханок.
- Опоры: [B-tasters], [B-long].
- Оговорки: C1.
- Переход: «что получилось».
- Объём: около 500 знаков.

### 01-results.md — что получилось

- Назначение: какая мука поднялась выше и какая понравилась.
- Тезисы: пшеничная после 12 часов — выше всех и 75% голосов; ржаная — ниже всех; короткая расстойка проиграла у всех видов муки.
- Опоры: [B-wheat-12-rise], [B-wheat-12-liked], [B-rye-12-rise], [B-rye-12-liked], [B-whole-12-rise], [B-whole-12-liked], [B-wheat-8-rise], [B-wheat-8-liked].
- Рисунок или таблица: таблица подъёма по муке и расстойке.
- Оговорки: C2 — рядом с процентами.
- Переход: что из этого взять.

### 02-advice.md — что из этого взять

- Назначение: что поменять в своём рецепте.
- Тезисы: пшеничной муке дай 12 часов; ржаную советовать или нет — решает автор.
- Оговорки: C1.

## Что уходит в другие статьи

Подкормка и возраст закваски — в 02-starter.

## Открытые вопросы

Нет.
