# Granki

Скиллы для ИИ-агентов, которые ведут серию статей от плана до публикации. Автор утверждает планы, текст пишется и проверяется по разделам, роли агентов спорят, решает автор. Совместимо с BMad Method v6.

> **Статус: ранняя версия 0.1.0.** Скиллы, скрипты и комнаты готовы и проверены на тестовой серии. Пилот на реальной серии ещё идёт, форматы могут меняться.

Гранки — пробные оттиски, которые редактор вычитывает по частям до окончательной вёрстки. Granki работает так же: сначала автор утверждает планы, потом агенты и автор проверяют каждый раздел, а в конце отдельно проверяются статья целиком и вся серия.

## Как устроена работа

| Уровень | Что получается | Кто первый |
|---|---|---|
| План серии | `series-plan.md` | автор, затем ревью агентами |
| План статьи | `NN-slug/plan.md` | автор, затем ревью агентами |
| Раздел | `NN-slug/sections/NN-*.md` | ревью агентами, затем автор |
| Ревью статьи | `reviews/article-*.md` | агенты, затем решения автора |
| Ревью серии | `reviews/series-*.md` | агенты, затем решения автора |

Принципы:

- **План и текст разделены.** План пишется для человека: его читают, обсуждают с агентом и перестраивают. Раздел пишется по своей записи в плане. Если план надо менять, агент это предлагает, а не меняет молча.
- **Работа по одному разделу.** Один раздел легко прочитать и прокомментировать. Если план меняется, на доработку уходят только задетые разделы.
- **Числа проверяют скрипты.** Каждое число в тексте прослеживается до таблицы утверждений, собранной из исходных данных. Обязательные оговорки отслеживаются по ID, а не по дословной формулировке, поэтому редактура их не ломает.
- **Роли агентов спорят, решает автор.** Фокусник хочет, чтобы всё было легко и волшебно, Зануда требует фактов, объёма выборки и интервалов. Им помогают Голос автора, Практик, Скептик из комментариев и Структурщик. Обсуждение заканчивается не голосованием, а вопросами автору по одному.
- **Опубликованные статьи версионируются.** Разделы опубликованной статьи заблокированы. Изменение на уровне серии оформляется запросом: неопубликованные статьи получают правку сразу, а для каждой опубликованной автор выбирает одно из трёх — новая версия, записанное расхождение или без изменений.

## Состав

| Скилл | Что делает |
|---|---|
| [`granki-agent-editor`](skills/granki-agent-editor/SKILL.md) | Главред: состояние серии, нерешённые находки, следующий шаг, комнаты |
| [`granki-series`](skills/granki-series/SKILL.md) | Замысел и план серии, состав статей, изменения на несколько статей, ревью серии |
| [`granki-intake`](skills/granki-intake/SKILL.md) | Интервью автора, материалы, таблица утверждений, кандидаты в тезисы |
| [`granki-article-plan`](skills/granki-article-plan/SKILL.md) | План статьи по разделам: черновик, обсуждение, ревью, утверждение, перестройка |
| [`granki-section`](skills/granki-section/SKILL.md) | Раздел: написать, разобрать замечания автора, принять |
| [`granki-review`](skills/granki-review/SKILL.md) | Ревью раздела, статьи или серии независимыми линзами и решение по находкам |
| [`granki-publish`](skills/granki-publish/SKILL.md) | HTML, проверка перед публикацией, отметка публикации, новая версия |
| [`granki-editorial`](skills/granki-editorial/SKILL.md) | Проход редактуры, правила письма, голос автора и канон; справочники адаптированы из redaktura-skills, см. [NOTICE.md](skills/granki-editorial/NOTICE.md) |
| [`granki-tools`](skills/granki-tools/SKILL.md) | Скрипты, [шаблоны](skills/granki-tools/assets/templates/) и составы комнат; форматы файлов — в [formats.md](skills/granki-tools/references/formats.md) |

**Канон** — редакционные правила: читатель, площадки, регистр, словарь, голос автора. Он собирается из трёх слоёв: проект, серия, статья. Более частный слой перекрывает общий по разделам: тот же заголовок заменяет раздел, `(+)` дописывает, `(-)` убирает.

У каждой статьи есть журнал `journal.md`: реестр находок со сквозными ID и статусами и хронология действий. После ревью агент предлагает применить все находки, обсудить их по одной, применить только критичные или отложить. К отложенным находкам возвращаются в следующей сессии через `journal.py list`.

Обсуждения с ролями идут в комнатах `bmad-party-mode`: Планёрка серии, Планёрка статьи, Разбор раздела, Совет по находкам, Фокус-группа читателей.

| Скрипт | Что делает |
|---|---|
| `check.py` | Проверяет раздел, статью или серию: объём, происхождение чисел, актуальность утверждений, оговорки, ссылки, запрещённое содержимое, рисунки, неизменность опубликованного |
| `claims.py` | Строит таблицу утверждений из CSV и сверяет её с источником |
| `plan.py` | Меняет статус статьи и разделов по жизненному циклу, отмечает публикацию и новую версию |
| `journal.py` | Ведёт журнал статьи: реестр находок и хронологию; находит нерешённые находки во всей серии |
| `status.py` | Статусы статей и разделов, изменения после приёмки, устаревшие ревью, нерешённые находки |
| `impact.py` | Какие разделы задевает изменение и какие варианты есть для каждой статьи |
| `canon.py` | Собирает канон статьи из слоёв проекта, серии и статьи |
| `rooms.py` | Ставит составы комнат Granki в настройки party mode проекта |
| `build_html.py` | Собирает автономный HTML статей и указатель, сверяет результат с исходным текстом |

## Что нужно для работы

- Ядро [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD) v6.12: party mode, ревью, подсказки по шагам и общие скрипты. Модуль BMM для разработки софта не нужен.
- Node.js 20.12+, Python 3.11+, [uv](https://docs.astral.sh/uv/). Для HTML — [Pandoc](https://pandoc.org/).
- Claude Code или Codex.

## Установка

```bash
npx bmad-method@6.12.4 install --directory . --modules core \
  --custom-source https://github.com/apantin/granki \
  --tools claude-code,codex --yes
```

Для локальной разработки вместо URL укажи путь к копии репозитория. Затем поставь комнаты:

```bash
uv run .claude/skills/granki-tools/scripts/rooms.py install --project-root .
```

Главред сам предложит это при первом запуске, если комнат нет.

> **Возможен конфликт с другими скиллами.** Если в среде стоят другие наборы для редактуры, статей или правил стиля, агент может выбрать их скилл вместо скилла Granki. Редакторские справочники уже входят в Granki, поэтому такие наборы лучше отключить в проекте с серией. Как это сделать в Claude Code, Codex, Gemini CLI, Copilot, OpenCode, Cursor и Windsurf — в [conflicts.md](docs/user/conflicts.md).

## Обновление

До последней версии из `main` — та же команда установки, она обновит уже стоящие модули:

```bash
npx bmad-method@6.12.4 install --directory . --modules core \
  --custom-source https://github.com/apantin/granki \
  --tools claude-code,codex --yes
uv run .claude/skills/granki-tools/scripts/rooms.py install --project-root .
```

До конкретной версии — допиши к адресу `@` и тег релиза (список — в [тегах репозитория](https://github.com/apantin/granki/tags)), например `@v0.1.0`. Вместо тега можно указать ветку; хеш коммита установщик не принимает.

```bash
npx bmad-method@6.12.4 install --directory . --modules core \
  --custom-source https://github.com/apantin/granki@v0.1.0 \
  --tools claude-code,codex --yes
uv run .claude/skills/granki-tools/scripts/rooms.py install --project-root .
```

Что происходит при обновлении:
- скиллы в `.claude/skills` и `.agents/skills` заменяются целиком: файлы, удалённые из Granki, удаляются и у тебя;
- настройки в `_bmad/custom/` сохраняются;
- `rooms.py install` переписывает только составы комнат Granki, повторный запуск ничего не дублирует;
- после обновления начни новую сессию агента: `SKILL.md` читается при её старте.

Серии и статьи установщик не трогает. После обновления прогони `status.py` и `check.py` по своей серии: если формат плана поменялся, скрипт вернёт код 2 и причину в поле `reason`.

При установке из локальной копии (путь вместо URL) суффикс `@` не работает: переключи версию в самой копии (`git checkout v0.1.0`) и запусти установку с путём.

Какая версия стоит в проекте: `grep -A1 'name: granki' _bmad/_config/manifest.yaml`. Что изменилось между версиями и что сделать при обновлении — в [CHANGELOG.md](CHANGELOG.md).

## Как начать

Позови Главреда («Главред, начнём серию») или сразу `granki-series`. Главред покажет, где серия, и предложит следующий шаг.

Как выглядит весь цикл на примере — в [туториале](docs/user/tutorial.md): вымышленная серия «Хлеб на закваске» из [examples/bread/](examples/bread/), раздел за разделом до публикации.

## Известные ограничения

- Таблицы рукописи пока не сверяются с CSV по ячейкам. Проверяются числа прозы.
- Слова вместо чисел («в три раза») и однозначные числа скрипт не видит. Их ловят линзы ревью.
- Сборки PDF нет.
- Что ещё не сделано и что дальше — в [roadmap.md](docs/dev/roadmap.md).
- Фокус-группа читателей проверена в режиме субагентов: у каждой роли был свой агент, оркестратор действовал по правилам `bmad-party-mode`. Интерактивные комнаты (планёрки, разбор раздела) в живой сессии с автором ещё не проводились.

## Оглавление

Все Markdown-файлы репозитория. Тест `test_readme.py` проверяет, что новый файл не забыли добавить сюда.

**Для пользователя** ([docs/](docs/README.md))
- [tutorial.md](docs/user/tutorial.md) — туториал: статья от плана до публикации на примере
- [process.md](docs/user/process.md) — уровни работы, циклы плана и раздела, ревью, журнал, статусы
- [roles.md](docs/user/roles.md) — роли агентов и комнаты
- [conflicts.md](docs/user/conflicts.md) — конфликты с другими скиллами и как их отключить в разных средах
- [CHANGELOG.md](CHANGELOG.md) — изменения по версиям и что сделать при обновлении

**Для разработчика**
- [contributing.md](docs/dev/contributing.md) — рабочее место, тесты, что обновить вместе с изменением, приватность
- [release.md](docs/dev/release.md) — выпуск версии: номер, проверки, тег, релиз на GitHub
- [design.md](docs/dev/design.md) — замысел, принятые решения, изученные источники
- [architecture.md](docs/dev/architecture.md) — устройство модуля, скрипты, раскладка артефактов, лицензии
- [lessons.md](docs/dev/lessons.md) — уроки первой серии
- [decisions/0001-bmad-v6-foundation.md](docs/dev/decisions/0001-bmad-v6-foundation.md) — ADR: основа на BMad Method v6.12
- [history.md](docs/dev/history.md) — как собиралась и проверялась версия 0.1.0
- [roadmap.md](docs/dev/roadmap.md) — пилот и то, что не сделано

**Скиллы**
- [granki-agent-editor](skills/granki-agent-editor/SKILL.md) — Главред
- [granki-series](skills/granki-series/SKILL.md) — серия
- [granki-intake](skills/granki-intake/SKILL.md) — интервью и материалы
- [granki-article-plan](skills/granki-article-plan/SKILL.md) — план статьи
- [granki-section](skills/granki-section/SKILL.md) — раздел
- [granki-review](skills/granki-review/SKILL.md) — ревью:
  - [decisions.md](skills/granki-review/references/decisions.md) — решение по находкам;
  - линзы: [опора и оверклейм](skills/granki-review/references/lenses/evidence.md), [свежий читатель](skills/granki-review/references/lenses/fresh-reader.md), [структура](skills/granki-review/references/lenses/structure.md), [согласованность серии](skills/granki-review/references/lenses/series.md)
- [granki-publish](skills/granki-publish/SKILL.md) — публикация
- [granki-editorial](skills/granki-editorial/SKILL.md) — редактура, [NOTICE.md](skills/granki-editorial/NOTICE.md) — авторство и изменения справочников:
  - проходы: [1 смысл и фактура](skills/granki-editorial/references/passes/1-smysl-i-faktura.md), [2 структура](skills/granki-editorial/references/passes/2-struktura.md), [3 тональность](skills/granki-editorial/references/passes/3-tonalnost.md), [4 предложение](skills/granki-editorial/references/passes/4-predlozhenie.md), [5 слово](skills/granki-editorial/references/passes/5-slovo.md), [6 ритм](skills/granki-editorial/references/passes/6-ritm.md), [7 следы нейросети](skills/granki-editorial/references/passes/7-neirotekst.md), [оценки](skills/granki-editorial/references/passes/otsenki.md), [штампы](skills/granki-editorial/references/passes/shtampy.md);
  - письмо статьи: [бриф](skills/granki-editorial/references/writing/brif.md), [фактура](skills/granki-editorial/references/writing/faktura.md), [организация](skills/granki-editorial/references/writing/organizatsiya.md), [драматургия](skills/granki-editorial/references/writing/dramaturgia.md), [оформление](skills/granki-editorial/references/writing/oformlenie.md);
  - [жанр «обзор результатов эксперимента»](skills/granki-editorial/references/genre-experiment.md), [голос автора и слои канона](skills/granki-editorial/references/voice.md)
- [granki-tools](skills/granki-tools/SKILL.md) — скрипты:
  - [formats.md](skills/granki-tools/references/formats.md) — точные форматы файлов;
  - [dialog.md](skills/granki-tools/references/dialog.md) — как агент разговаривает с автором: что писать, как спрашивать;
  - шаблоны: [план серии](skills/granki-tools/assets/templates/series-plan.md), [план статьи](skills/granki-tools/assets/templates/plan.md), [заметки автора](skills/granki-tools/assets/templates/author-notes.md), [канон](skills/granki-tools/assets/templates/canon.md)

**Пример** ([examples/bread/](examples/bread/README.md)) — вымышленная серия «Хлеб на закваске»
- [канон проекта](examples/bread/.agents/canon.md)
- серия: [план](examples/bread/articles/bread/series-plan.md), [журнал](examples/bread/articles/bread/journal.md), [заметки автора](examples/bread/articles/bread/author-notes.md), [канон серии](examples/bread/articles/bread/canon.md)
- статья 01-flour: [план](examples/bread/articles/bread/01-flour/plan.md), [журнал](examples/bread/articles/bread/01-flour/journal.md), разделы [00-intro](examples/bread/articles/bread/01-flour/sections/00-intro.md), [01-results](examples/bread/articles/bread/01-flour/sections/01-results.md), [02-advice](examples/bread/articles/bread/01-flour/sections/02-advice.md)

## Тесты

```bash
uv run --no-project --with pyyaml python -m unittest discover -s skills/granki-tools/scripts/tests
```

Тесты сборки HTML и прогон туториала (`test_tutorial.py` выполняет все команды из [docs/user/tutorial.md](docs/user/tutorial.md)) запускаются, если доступен Pandoc: в `PATH` или в переменной `GRANKI_PANDOC`. Что проверяет каждый тест и как вносить изменения — в [contributing.md](docs/dev/contributing.md).

## Лицензия

Код, скиллы и шаблоны — [MIT](LICENSE).

Редакторские справочники в `granki-editorial` адаптированы из [redaktura-skills](https://github.com/N1arko/redaktura-skills) Людмилы Сарычевой и Никиты Архипова ([gladlax.ru](https://gladlax.ru)). Они распространяются под [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ru), авторство и перечень изменений — в [NOTICE.md](skills/granki-editorial/NOTICE.md). Авторы оригинала Granki не одобряли и за него не отвечают.

Granki — независимый проект, не связанный с BMad Code, LLC и не одобренный ею.
