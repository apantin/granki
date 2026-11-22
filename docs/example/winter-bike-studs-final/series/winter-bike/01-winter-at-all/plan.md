---
granki: 1
title: "Зимой вообще можно?"
status: plan-draft            # planned | plan-draft | plan-approved | writing | article-review | ready | published | revising
version: 1
description: "Сколько дней доехал, когда не поехал и во сколько обходится снег и лёд по времени"
sections_dir: sections
length: {}                    # необязательно: {min: …, max: …, strict: false}
claims: [data/claims.csv]
data_dirs: [data, ../shared/data, ../../../materials/bike]
claims_build:
  - {source: summary.csv, key: key, where: {group: all}, id: "R-{key}-{column}", formulation: "Все поездки, {sub}: {column}", columns: [trips, detours, minutes_mean, minutes_min, minutes_max, falls, fall_days, skids, skids_per_trip, temp_mean, temp_min, temp_max]}
  - {source: summary.csv, key: key, where: {group: обычные}, id: "R-{key}-{column}", formulation: "Обычная резина, {sub}: {column}", columns: [trips, minutes_mean]}
  - {source: summary.csv, key: key, where: {group: шипы}, id: "R-{key}-{column}", formulation: "Шипы, {sub}: {column}", columns: [trips, minutes_mean]}
  - {source: summary.csv, key: key, where: {group: дни}, id: "R-{key}-{column}", formulation: "Дней в дневнике: {column}", columns: [days]}
  - {source: summary.csv, key: key, where: {group: пропуск}, id: "R-{key}-{column}", formulation: "Пропуск, {sub}: {column}", columns: [days]}
numbers: {decimal: ",", renderers: ["percent:1", "percent:2", "fixed:1", "fixed:2"], allow: [], integers: true}
caveats: {}                   # C1: {text: "…"}
required_caveats: []
public: {forbidden: [], allow_external_links: false, assets_dir: assets}
sections: []                  # {file: 00-intro.md, status: planned, caveats: [], claims: []}
published: []
---

# План статьи: {title}

<!-- План читает и обсуждает автор до текста. Раздел пишется по своей записи здесь; если раздел надо строить иначе, сначала меняется план. -->

## Вопрос читателя и тезис
<!-- Какой вопрос закрывает статья и какой ответ даёт. Готово, когда тезис помещается в одну фразу с условиями: «на этих текстах…». -->

## Разделы
<!-- Для каждого раздела: файл, назначение (какой вопрос закрывает), 3–6 тезисов, опоры [ID утверждений], рисунок или таблица с требованиями, оговорки [ID], переход к следующему разделу, примерный объём. -->

### 00-intro.md — 
- Назначение:
- Тезисы:
- Опоры:
- Рисунок или таблица:
- Оговорки:
- Переход:

## Что уходит в другие статьи

## Открытые вопросы
