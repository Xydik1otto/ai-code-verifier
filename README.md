# aicv — AI Code Verifier

[![CI](https://github.com/bigpi/ai-code-verifier/actions/workflows/tests.yml/badge.svg)](https://github.com/bigpi/ai-code-verifier/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Status: Beta](https://img.shields.io/badge/status-beta-blue.svg)](PLAN.md)

Verification gate для AI-згенерованого коду: CLI + GitHub Action + pre-commit hook.

## Чому це існує

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

## Що перевіряє

| Правило | Що ловить |
|---|---|
| `syntax_error` | файл взагалі не парситься |
| `dangerous_call` | `eval`, `exec`, `compile`, `__import__` |
| `shell_exec` | `os.system`, `os.popen`, `subprocess` зі строковим аргументом |
| `remote_exec` | `curl… \| sh`, `bash -c`, `powershell -enc`, `subprocess(shell=True)` |
| `hardcoded_secret` | API-ключі, токени (Slack `xox*`, Bearer, AWS `AKIA*`, GitHub, Stripe), паролі |
| `sql_string_format` | SQL через f-string / `.format` / `%` |
| `dead_import` | імпорти, які ніде не використовуються (opt-in) |
| `todo_fixme` | маркери TODO/FIXME, залишені в коді (warning) |
| `ruff:*` | все, що знайде ruff, якщо він встановлений (graceful fallback) |

Мови: **Python** (AST + py_compile), **JS/TS, Go, Java** (regex pre-scan:
секрети, remote-exec, TODO/FIXME, баланс дужок).

## Встановлення

```bash
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
pip install -e .        # (згодом: pip install aicv з PyPI)
pytest                  # опційно: прогнати тести
```

Zero runtime dependencies — працює навіть у мінімальному CI-образі.

## Використання

```bash
aicv check                # git diff HEAD (робоче дерево)
aicv check --staged       # лише staged-зміни
aicv check --json         # machine-readable вердикт для agent-loop
aicv check --sarif        # SARIF 2.1.0 -> .aicv/latest.sarif (GitHub code scanning)
aicv report               # показати останній звіт
aicv report --json
aicv report --sarif
aicv verdict              # marker-вердикт для агентів (без запису звітів)
aicv verdict --summary    # один marker-рядок
aicv init                 # згенерувати .aicv.toml
aicv ci                   # CI: diff від GITHUB_BASE_REF
aicv ci --annotate        # + workflow-команди ::error file=,line=:: (PR annotations)
aicv baseline             # зафіксувати поточні знахідки як legacy-борг
aicv check --baseline     # фейлити тільки НОВІ знахідки
```

### Baseline (legacy-борг)

На живому репозиторії історичні знахідки не дають ввести гейт «з нуля».
`aicv baseline` записує поточні знахідки у `.aicv/baseline.json`, після чого
`aicv check --baseline` фейлиться лише на **нових** знахідках — борг
зафіксований, новий код чистий:

```bash
aicv baseline             # один раз: зафіксувати поточний стан
aicv check --baseline     # далі в CI: PASS, доки не з'явиться нова знахідка
```

Знаххідка ідентифікується парою (файл, рядок, правило); закомітьте
`.aicv/baseline.json` разом із конфігом.

### PR annotations

`aicv ci --annotate` виводить стандартні GitHub Actions workflow-команди —
додайте крок у workflow, і кожна знахідка з'явиться як анотація прямо
на рядку дифу PR:

```text
::error file=bad.py,line=9::shell_exec: 'os.system()' executes a shell string — injection risk
```

### Severity per rule

Кожне правило має severity: **error** (валить перевірку, exit code 1),
**warning** та **info** (лише повідомляють). Типові рівні — у каталозі
правил [docs/rules.md](docs/rules.md) (автогенерований з `RULES` через
`python scripts/gen_rules.py`). Перевизначення — секція `[severity]`
у `.aicv.toml`:

```toml
[severity]
dead_import = "error"       # підняти до error
dangerous_call = "warning"  # опустити — не валити збірку
```

Реальний вивід на файлі з типовими AI-помилками (`exit code 1`):

```text
$ aicv check --no-ruff
aicv: checked 1 file(s) [diff HEAD] — 4 error(s), 0 warning(s)
  [ERROR] bad.py:6 (hardcoded_secret) Possible API key literal hardcoded in source
  [ERROR] bad.py:9 (shell_exec) 'os.system()' executes a shell string — injection risk
  [ERROR] bad.py:15 (sql_string_format) SQL built via string formatting — use parameterized queries
  [ERROR] bad.py:19 (dangerous_call) Use of 'eval()' — dynamic code execution, ban in AI-generated code
report: …\.aicv\latest.md
```

Exit codes: `0` — pass, `1` — є error-рівня знахідка. Звіти пишуться в
`.aicv/latest.md` та `.aicv/latest.json` (у звіті знахідки згруповані по файлах,
errors перед warnings).

### Machine-readable вердикт для agent-loop

`aicv check --json` друкує на stdout лише JSON (людський вивід іде у stderr) —
зручно парсити автономним агентом, який читає знахідки і виправляє код:

```json
{
  "files_checked": 1,
  "errors": [
    {"file": "bad.py", "line": 19, "rule": "dangerous_call",
     "message": "Use of 'eval()' — dynamic code execution, ban in AI-generated code"}
  ],
  "exit_code": 1
}
```

### Inline-супресії

Коментар `# aicv: ignore` на рядку приглушує всі знахідки на цьому рядку;
`# aicv: ignore[rule1, rule2]` — лише вказані правила:

```python
API_KEY = "sk-abcdefghijklmnopqrstuv"  # aicv: ignore[hardcoded_secret]
result = eval(expr)                    # aicv: ignore
```

### Конфіг

`.aicv.toml` у корені репозиторію — вмикайте/вимикайте правила:

```toml
[rules]
dead_import = false
hardcoded_secret = true
```

## pre-commit hook

aicv має готовий хук для [pre-commit framework](https://pre-commit.com).
У своєму репозиторії додайте у `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/bigpi/ai-code-verifier
    rev: v0.1.0-alpha        # тег релізу
    hooks:
      - id: aicv
```

Хук запускає `aicv check --staged`: якщо у staged-змінах є error-рівня
знахідка — commit блокується. Альтернатива без фреймворку — просто викликати
`aicv check --staged` у власному git hook.

## GitHub Action

Дивіться готовий приклад: [`.github/workflows/aicv.yml`](.github/workflows/aicv.yml) —
ставиться на `pull_request`, бере diff від `github.base_ref` і валить PR,
якщо знайдено error-рівня проблему.

Власні тести проєкту живуть у [`.github/workflows/tests.yml`](.github/workflows/tests.yml)
(Python 3.12 + 3.13, `pip install -e .` + `pytest`).

## Архітектура

- `aicv/checks.py` — AST-евристики + regex-секрети + ruff-адаптер (stdlib only).
- `aicv/engine.py` — git diff → файли → перевірки → markdown/JSON звіт.
- `aicv/cli.py` — `check` / `report` / `ci`.

## GitHub code scanning (SARIF)

`aicv check --sarif` пише `.aicv/latest.sarif` (SARIF 2.1.0). Завантажте його
у GitHub code scanning у CI-джобі:

```yaml
      - run: aicv ci --sarif
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: .aicv/latest.sarif
```

## Статус

**v0.4.0**: Python-файли (AST + py_compile) + JS/TS (regex-секрети),
git-інтеграція, звіти (групування по файлах + severity), inline-супресії,
machine-readable вердикт (`--json`), SARIF 2.1.0, `aicv init`, `aicv verdict`,
baseline mode, PR annotations (`ci --annotate`), severity per rule
(`[severity]`), TODO/FIXME детектор, автогенерований
[docs/rules.md](docs/rules.md), pre-commit hook, конфіг, GitHub Action
приклад, smoke/pypi-скрипти, pytest-набір.
Дорожня карта — у [PLAN.md](PLAN.md), історія — у [CHANGELOG.md](CHANGELOG.md).
