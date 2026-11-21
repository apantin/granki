# ADR 0001: основа — BMad Method v6.12

Дата: 2026-11-21. Статус: принято.

## Контекст

Granki нужны ролевые обсуждения агентов, независимое ревью, подсказка следующего шага и установщик для Claude Code и Codex. Всё это есть в BMad Method. На момент решения стабильная ветка — v6.12 (6.12.4), а v7 вышла в preview alpha.

## Решение

1. Основа — **BMad Method v6.12** без модуля BMM. Используются `bmad-party-mode`, `bmad-review`, `bmad-help`, `bmad-advanced-elicitation`, `bmad-customize` и общие скрипты `_bmad/scripts`. Скиллы BMad не меняются; составы комнат задаются через customize (`_bmad/custom/bmad-party-mode.toml`).
2. Granki — отдельный модуль с кодом и префиксом `granki`, ставится установщиком BMad через `--custom-source`.
3. Числа, таблицы, метки оговорок и блокировку опубликованных статей проверяют скрипты Granki, а не скиллы BMad.

## Проверка установки

Пробная установка в песочнице (`npx bmad-method@6.12.4 install --yes --modules core --tools claude-code,codex --no-shims`):

| Проверка | Результат |
|---|---|
| Ядро ставится без BMM | passed: 8 скиллов core в `.claude/skills` и `.agents/skills` |
| `_bmad/` | 136 КБ: `config.toml` и `config.user.toml` (перезаписываются установщиком), `custom/` (не трогается установщиком, `*.user.toml` игнорируется), `scripts/`, `core/`, `_config/` |
| `resolve_customization.py` для `bmad-party-mode` | passed |
| Свой состав комнаты из `_bmad/custom/bmad-party-mode.toml` | passed: `resolve_party.py` вернул всех участников, `unresolved` пуст |
| Модуль Granki через `--custom-source <локальный путь>` | passed: 9 скиллов в обеих папках инструментов, этапы Granki в `bmad-help` |
| `rooms.py install`, затем `resolve_party.py` для 5 комнат | passed |

## Альтернативы

- **BMad v7.** Нужные механизмы те же, но версия в preview alpha, ожидаются ломающие изменения. Отвергнуто. Переход позже — через `bmad migrate`.
- **Самостоятельные скиллы без BMad.** Пришлось бы заново писать party mode, customize и установщик. Отвергнуто.
- **Зависимость от плагина redaktura-skills.** Нет контроля над версией, знание не адаптировать под жанр. Отвергнуто: справочники скопированы и адаптированы в `granki-editorial` под CC BY 4.0.

## Последствия

- Granki требует установленного ядра BMad v6. Как самостоятельный плагин Claude Code без BMad он не работает; это указано в README.
- Составы комнат живут в `_bmad/custom/bmad-party-mode.toml` проекта-пользователя. Granki поставляет их сам: `rooms.py install`, Главред предлагает это при первом запуске.
- В проекте-пользователе коммитятся `_bmad/custom/*.toml`, кроме `*.user.toml`. Установленные скиллы BMad, `_bmad/scripts`, `_bmad/core` и `_bmad/_config` воспроизводит установщик.
- Установщик 6.12.4 пишет конфигурацию в `config.toml`, а шаблоны bmad-builder v2.2.2 — в `config.yaml`. Ориентир для Granki — фактическое поведение 6.12.4.
- Вместо `memlog.py` у каждой статьи и серии ведётся журнал `journal.md`. Скрипты `_bmad/scripts` по-прежнему нужны скиллам BMad.
