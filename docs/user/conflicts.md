# Конфликты с другими скиллами

Агент выбирает скилл по его описанию. Если в той же среде стоят другие наборы скиллов с похожими описаниями — редактура текстов, написание статей, правила стиля, — агент может взять чужой скилл вместо скилла Granki. Совпадения имён маловероятны: у всех скиллов Granki префикс `granki-`. Мешают именно похожие описания.

Признаки конфликта:
- агент правит текст серии без журнала и без проверки `check.py`;
- создаёт файлы, которых нет в Granki, например свою памятку о стиле вместо `canon.md`;
- в списке активных скиллов рядом с Granki есть скиллы с похожим назначением.

Редакторские справочники уже входят в Granki (`granki-editorial`), поэтому другие наборы для редактуры в проекте с серией не нужны. Надёжнее всего отключить их в этом проекте и оставить включёнными в остальных.

Если отключить нельзя, называй скилл явно: «Главред, …» или «granki-editorial, проход редактуры раздела 02».

## Как отключить в своей среде

Сведения сверены с документацией сред 2026-11-21. Настройки сред меняются, поэтому у каждой среды дана ссылка на первоисточник. Пометка «не показано в документации» значит, что способ следует из общих правил настроек, но примера в документации нет: проверь результат списком скиллов.

### Claude Code

- **Посмотреть:** `/skills` в сессии, `claude plugin list` в терминале.
- **Отключить плагин в проекте:**
  ```bash
  claude plugin disable <плагин>@<маркетплейс> --scope project   # запишет в .claude/settings.json, увидят все, кто клонирует проект
  claude plugin disable <плагин>@<маркетплейс> --scope local     # .claude/settings.local.json, только у тебя
  ```
  То же вручную: `{"enabledPlugins": {"<плагин>@<маркетплейс>": false}}` в одном из этих файлов. Значение проекта перекрывает глобальное `~/.claude/settings.json` для этого плагина, остальные плагины не меняются. Затем `/reload-plugins` или новая сессия.
- **Отключить личный скилл из `~/.claude/skills/`:** в `/skills` выдели скилл, переключи пробелом, сохрани Esc. Меню записывает в `.claude/settings.local.json` проекта `{"skillOverrides": {"<скилл>": "off"}}`.
- **Если имена совпали:** личный скилл побеждает проектный.
- [Скиллы](https://code.claude.com/docs/en/skills), [настройки](https://code.claude.com/docs/en/settings), [команды плагинов](https://code.claude.com/docs/en/plugins/cli-reference).

### Codex

- **Посмотреть:** `/skills`.
- **Отключить плагин в проекте:** в `.codex/config.toml` проекта (проект должен быть доверенным):
  ```toml
  [plugins."<плагин>@<маркетплейс>"]
  enabled = false
  ```
  Или `/plugins`, пробел на плагине.
- **Отключить скилл:** запись в `~/.codex/config.toml`, после неё перезапусти Codex:
  ```toml
  [[skills.config]]
  path = "/абсолютный/путь/к/скиллу/SKILL.md"
  enabled = false
  ```
  Выбирай скилл по `path`, а не по `name`: `name` отключает все скиллы с этим именем. В документации запись показана для пользовательского файла. В `.codex/config.toml` проекта она должна действовать только на проект, но это не показано в документации.
- **Если имена совпали:** Codex показывает оба скилла и не объединяет их.
- [Скиллы](https://developers.openai.com/codex/skills), [справочник настроек](https://developers.openai.com/codex/config-reference).

### Gemini CLI

- **Посмотреть:** `/skills list` в сессии или `gemini skills list --all` в терминале.
- **Отключить скилл в проекте:** `/skills disable <скилл> --scope workspace`. Без `--scope` скилл отключится для всех проектов. Команда пишет в `.gemini/settings.json`: `{"skills": {"disabled": ["<скилл>"]}}`.
- **Отключить расширение в проекте:** `gemini extensions disable <расширение> --scope workspace`.
- **Если имена совпали:** проектный скилл побеждает пользовательский.
- [Скиллы](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md), [команды](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/commands.md).

### GitHub Copilot CLI

- **Посмотреть:** `/skills list` или `copilot skill list`.
- **Отключить скилл в проекте:** `.github/copilot/settings.json` (общий) или `.github/copilot/settings.local.json` (личный, добавь в `.gitignore`):
  ```json
  { "disabledSkills": ["<скилл>"] }
  ```
- **Отключить плагин в проекте:** `{"enabledPlugins": {"<плагин>@<маркетплейс>": false}}` в тех же файлах. Для плагина, установленного глобально, это не показано в документации.
- **Если имена совпали:** проектный скилл побеждает личный, плагинный скилл с тем же именем пропускается.
- [Справочник CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference), [настройки](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference).

### GitHub Copilot в VS Code

- **Посмотреть:** палитра команд → «Chat: Open Customizations» → Skills.
- **Отключить плагин в проекте:** Agent Customizations → Plugins → меню плагина → «Manage Enablement for This Workspace». Работает для плагинов из маркетплейса.
- **Отключить один скилл в проекте:** способа в документации нет. Остаётся убрать мешающий скилл из личной папки (`~/.copilot/skills/`, `~/.agents/skills/`, `~/.claude/skills/`).
- [Скиллы](https://code.visualstudio.com/docs/copilot/customization/agent-skills), [плагины](https://code.visualstudio.com/docs/copilot/customization/agent-plugins).

### OpenCode

- **Посмотреть:** отдельной команды в документации нет.
- **Отключить скилл в проекте:** запрет в `opencode.json` проекта. Скилл перестаёт быть виден модели:
  ```json
  { "permissions": [ { "action": "skill", "resource": "<скилл>", "effect": "deny" } ] }
  ```
  Синтаксис приведён по текущей документации, в старых версиях OpenCode он другой.
- **Отключить плагин:** `{"plugins": ["*", "-<плагин>"]}`.
- **Если имена совпали:** глобальный скилл из `~/.config/opencode/skills` перекрывает проектный из `.agents/skills`.
- [Скиллы](https://opencode.ai/docs/skills), [разрешения](https://opencode.ai/docs/permissions).

### Cursor и Windsurf (Devin Desktop)

- **Посмотреть:** боковая панель Customize → Skills.
- **Отключить в проекте:** способа в документации нет. Варианты:
  - убрать мешающий скилл из личной папки (`~/.agents/skills/`, `~/.cursor/skills/`, `~/.claude/skills/` или `~/.config/devin/skills/`);
  - в Cursor — дописать мешающему скиллу в его `SKILL.md` строку `disable-model-invocation: true`. Тогда он будет запускаться только по явной команде `/имя`, но во всех проектах сразу.
- [Скиллы Cursor](https://cursor.com/docs/skills), [скиллы Windsurf](https://docs.devin.ai/desktop/cascade/skills).
