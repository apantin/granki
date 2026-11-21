# Выпуск версии

Как выпустить новую версию Granki: где прописать номер, что проверить, как поставить тег и оформить релиз на GitHub. Пользователи ставят Granki по тегу (`--custom-source https://github.com/apantin/granki@v0.2.0`, см. [README](../../README.md#обновление)), поэтому тег — это и есть выпуск.

## Номер версии

Версии нумеруются по [SemVer](https://semver.org/lang/ru/): `MAJOR.MINOR.PATCH`, тег — `vMAJOR.MINOR.PATCH`.

Пока версия 0.x:
- **MINOR** (0.1.0 → 0.2.0) — новые возможности или несовместимые изменения;
- **PATCH** (0.1.0 → 0.1.1) — исправления и документация, после которых статьи пользователей проходят проверки, как раньше.

После 1.0 несовместимое изменение поднимает MAJOR.

Несовместимым считается всё, из-за чего серия, сделанная прошлой версией, перестаёт разбираться или проходить проверки, а также всё, из-за чего ломаются привычные команды:
- формат файлов из [formats.md](../../skills/granki-tools/references/formats.md): фронтматтер `plan.md` и `series-plan.md`, журнал, таблица утверждений, отчёты ревью, слои редполитики;
- имена скриптов, их аргументы, коды выхода и поля JSON, на которые опираются скиллы;
- имена скиллов и пунктов меню Главреда, коды комнат.

Для такого изменения в `CHANGELOG.md` пишется, что сделать при обновлении. Если правка файлов статьи механическая, к выпуску прикладывается скрипт миграции.

## Где прописана версия

| Файл | Что поменять | Кто читает |
|---|---|---|
| `skills/module.yaml` | `module_version: "X.Y.Z"` | установщик BMad, `bmad-help` |
| `.claude-plugin/marketplace.json` | `"version": "X.Y.Z"` у плагина `granki` | установщик BMad, каталоги плагинов |
| `README.md` | строка статуса «ранняя версия X.Y.Z» | читатели |
| `CHANGELOG.md` | заголовок «## X.Y.Z — ГГГГ-ММ-ДД» вместо «Не выпущено» | читатели, текст релиза на GitHub |

Номер во всех четырёх местах проверяет `test_version.py`: тест падает, если где-то забыли поменять.

Номера в истории разработки (`history.md`, ADR) не меняются: это записи о конкретной версии.

Замена номера одной командой (Perl работает одинаково в Linux и macOS, в отличие от `sed -i`):

```bash
OLD=0.1.0 V=0.2.0
perl -pi -e "s/module_version: \"\Q$OLD\E\"/module_version: \"$V\"/" skills/module.yaml
perl -pi -e "s/\"version\": \"\Q$OLD\E\"/\"version\": \"$V\"/" .claude-plugin/marketplace.json
perl -pi -e "s/ранняя версия \Q$OLD\E/ранняя версия $V/" README.md
```

Заголовок в `CHANGELOG.md` правится вручную: «## Не выпущено» становится «## 0.2.0 — 2026-12-01».

## Версия BMad

Granki проверен на конкретной версии установщика BMad, и она прописана в командах: `bmad-method@6.12.4`. Переход на новую версию BMad — отдельное изменение, а не попутная правка при выпуске:
1. поставить ядро новой версии и Granki в песочнице (см. «Проверка установки» ниже) и убедиться, что комнаты ставятся и разбираются;
2. заменить номер везде, где он встречается: `git grep -n 'bmad-method@'`;
3. дописать в [ADR 0001](decisions/0001-bmad-v6-foundation.md) или в новый ADR, на какой версии проверено;
4. записать переход в `CHANGELOG.md`.

## Перед выпуском

1. **Рабочая копия.** Ветка `main`, всё закоммичено, ветка совпадает с GitHub:
   ```bash
   git switch main && git pull --ff-only && git status --short
   ```
2. **Тесты, все без пропусков.** Тесты HTML и туториала требуют Pandoc. Если в итоге есть `skipped`, укажи Pandoc через `GRANKI_PANDOC` и запусти снова:
   ```bash
   uv run --no-project --with pyyaml python -m unittest discover -s skills/granki-tools/scripts/tests
   ```
3. **Проверка установки** из рабочей копии в пустую папку:
   ```bash
   GRANKI=$(pwd) SANDBOX=$(mktemp -d)
   (cd "$SANDBOX" && npx bmad-method@6.12.4 install --directory . --modules core \
     --custom-source "$GRANKI" --tools claude-code,codex --yes)
   uv run "$SANDBOX/.claude/skills/granki-tools/scripts/rooms.py" install --project-root "$SANDBOX"
   ls "$SANDBOX/.claude/skills" | grep -c '^granki-'      # 9
   grep -A1 'name: granki' "$SANDBOX/_bmad/_config/manifest.yaml"
   rm -rf "$SANDBOX"
   ```
   Должны поставиться все 9 скиллов, `rooms.py install` должен вернуть `"status": "passed"`, а в манифесте должна стоять новая версия: установщик берёт её из `module.yaml`.
4. **Приватные данные.** Просмотри, что вошло в выпуск, и проверь, что в репозиторий не попали локальные пути и адреса почты. Вторая команда при чистом составе ничего не печатает:
   ```bash
   git diff --stat "$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)"..HEAD
   git grep -n -I -E '/home/[a-z]|/Users/[A-Za-z]|[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.(com|ru|me|org|net)\b'
   ```
   Примеры должны быть вымышленными, материалы серий, на которых проверялся Granki, в репозиторий не входят (см. [contributing.md](contributing.md#приватность)).
5. **CHANGELOG.** В разделе «Не выпущено» перечислено всё заметное. У несовместимых изменений написано, что сделать при обновлении.

## Выпуск

1. Поменяй номер версии (см. «Где прописана версия») и прогони тесты ещё раз.
2. Закоммить и поставь аннотированный тег на этот коммит:
   ```bash
   V=0.2.0
   git commit -am "Granki $V"
   git tag -a "v$V" -m "Granki $V"
   ```
3. Отправь коммит и тег:
   ```bash
   git push origin main
   git push origin "v$V"
   ```
4. Оформи релиз на GitHub. Текст берётся из раздела версии в `CHANGELOG.md`:
   ```bash
   NOTES=$(mktemp)
   awk -v v="$V" 'index($0, "## " v " ") == 1 {on=1; next} on && /^## / {exit} on' CHANGELOG.md > "$NOTES"
   gh release create "v$V" --verify-tag --title "Granki $V" --notes-file "$NOTES"
   ```

## После выпуска

1. **Установка по тегу.** Проверь в пустой папке, что версия ставится с GitHub:
   ```bash
   SANDBOX=$(mktemp -d)
   (cd "$SANDBOX" && npx bmad-method@6.12.4 install --directory . --modules core \
     --custom-source "https://github.com/apantin/granki@v$V" --tools claude-code,codex --yes)
   ls "$SANDBOX/.claude/skills" | grep -c '^granki-'      # 9
   grep -A1 'name: granki' "$SANDBOX/_bmad/_config/manifest.yaml"
   rm -rf "$SANDBOX"
   ```
2. **Новый раздел.** Добавь в `CHANGELOG.md` пустой раздел «## Не выпущено» над только что выпущенной версией.
3. **Свои проекты.** Обнови Granki в проектах, где он стоит, и прогони там `status.py` и `check.py` по сериям.

## Если ошибся

- **Тег ещё не отправлен.** Удали его, исправь, поставь заново:
  ```bash
  git tag -d "v$V"
  ```
- **Тег уже на GitHub.** Не переставляй его: у пользователей и в кеше установщика BMad он уже указывает на старый коммит. Выпусти исправление следующей версией PATCH. Если в выпуск попали приватные данные, одного нового выпуска мало: удали релиз и тег на GitHub, вычисти историю и считай данные раскрытыми.

## Первый выпуск 0.1.0

Тегов пока нет. Номер 0.1.0 уже прописан во всех четырёх местах, в `CHANGELOG.md` раздел называется «0.1.0 — не выпущена». При выпуске замени «не выпущена» на дату и пройди шаги с «Перед выпуском», пропустив замену номера.
