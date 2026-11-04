# aicv — AI Code Verifier

Verification gate для AI-згенерованого коду: CLI + GitHub Action.

## Проблема

AI пише дедалі більше коду, але людина мусить його перевіряти вручну — і саме це
стало головним вузьким місцем розробки:

- **Qodo State of AI Code Quality 2026**: рев'ю/валідація AI-коду — bottleneck #1
  (26% розробників і 26% лідерів називають це головною проблемою).
- **36% розробників** кажуть, що рев'ю AI-коду потребує **більше** когнітивних
  зусиль, ніж звичайного — «trust tax»: спочатку сумніваєшся, потім читаєш.
- **Sonar**: 96% розробників **не вірять**, що AI-код коректний одразу.
- **Sonar / JetBrains**: «acceptance gap» — верифікацію треба зсувати вгору по
  пайплайну (IDE → pre-commit → agent loop), а не залишати її на кінцевому рев'ю.

`aicv` відповідає саме на це: автоматичний, детермінований, дешевий фільтр,
який стоїть **до** людського рев'ю й знімає з нього рутинну частину.

## Що перевіряє (MVP)

| Правило | Що ловить |
|---|---|
| `syntax_error` | файл взагалі не парситься |
| `dangerous_call` | `eval`, `exec`, `compile`, `__import__` |
| `shell_exec` | `os.system`, `os.popen`, `subprocess` зі строковим аргументом |
| `hardcoded_secret` | API-ключі, токени, паролі регулярками |
| `sql_string_format` | SQL через f-string / `.format` / `%` |
| `dead_import` | імпорти, які ніде не використовуються (opt-in) |
| `ruff:*` | все, що знайде ruff, якщо він встановлений (graceful fallback) |

## Швидкий старт

```bash
cd ai-code-verifier
pip install -e .          # або: pip install -r requirements.txt && pip install -e .
pytest                    # тести

# використання у своєму репозиторії:
aicv check                # git diff HEAD (робоче дерево)
aicv check --staged       # лише staged-зміни
aicv report               # показати останній звіт
aicv report --json
aicv ci                   # CI: diff від GITHUB_BASE_REF
```

Exit codes: `0` — pass, `1` — є error-рівня знахідки. Звіти пишуться в
`.aicv/latest.md` та `.aicv/latest.json`.

Конфіг: `.aicv.toml` у корені репозиторію — вмикайте/вимикайте правила:

```toml
[rules]
dead_import = false
hardcoded_secret = true
```

## GitHub Action

Дивіться готовий приклад: [`.github/workflows/aicv.yml`](.github/workflows/aicv.yml) —
ставиться на `pull_request`, бере diff від `github.base_ref` і валить PR,
якщо знайдено error-рівня проблему.

## Архітектура

- `aicv/checks.py` — AST-евристики + regex-секрети + ruff-адаптер (stdlib only).
- `aicv/engine.py` — git diff → файли → перевірки → markdown/JSON звіт.
- `aicv/cli.py` — `check` / `report` / `ci`.

Zero runtime dependencies — працює навіть у мінімальному CI-образі.

## Статус

MVP v0.1.0: Python-файли (AST) + JS/TS (regex-секрети), git-інтеграція, звіти,
конфіг, GitHub Action приклад, pytest-набір. Дорожня карта — у [PLAN.md](PLAN.md).
