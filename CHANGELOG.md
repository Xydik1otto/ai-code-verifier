# Changelog

Усі помітні зміни проєкту aicv документуються у цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/),
версіювання — [Semantic Versioning](https://semver.org/lang/uk/).

## [0.4.0] — 2026-11-05

### Додано
- **Baseline mode**: `aicv baseline` фіксує поточні знахідки у
  `.aicv/baseline.json`; `aicv check --baseline` фейлить **тільки нові**
  знахідки — типовий патерн прийняття legacy-боргу без блокування команди.
- **PR annotations**: `aicv ci --annotate` виводить GitHub Actions
  workflow-команди `::error file=...,line=...::message` — зауваження прямо
  на дифі PR (error→error, warning→warning, info→notice).
- **Severity per rule**: кожне правило має severity (error/warning/info);
  перевизначається секцією `[severity]` у `.aicv.toml`; exit code залежить
  тільки від error-рівня знахідок. SARIF: info → `note`.
- **TODO/FIXME детектор**: нове правило `todo_fixme` (warning) ловить
  маркери TODO/FIXME у змінених py/js/ts файлах; приглушується
  `# aicv: ignore`.
- **docs/rules.md**: автогенерований каталог правил
  (`python scripts/gen_rules.py`) — таблиця правило/опис/замовчування/severity
  + sync-тест, що не дає документації відстати від коду.
- **scripts/smoke.sh** — автоматичний smoke-тест CLI: check на відомо-бад-файлі
  → PASS/FAIL.
- **scripts/pypi_check.sh** — pypi-ready перевірка (`python -m build` +
  `twine check`, якщо доступні; інакше skip).
- CHANGELOG.md, FUNDING.yml (GitHub Sponsors), README-секція «Чому це існує».

## [0.3.0] — 2026-11-05

### Додано
- **SARIF 2.1.0**: `aicv check|ci|report --sarif` → `.aicv/latest.sarif`
  для GitHub code scanning.
- **`aicv init`**: генерує стартовий `.aicv.toml` з поточних правил
  (без `--force` відмовляється перезаписувати).
- **`aicv verdict`**: marker-вердикт для agent-loop
  (`=== AICV VERDICT: PASS/FAIL | ... ===`), `--summary` — один рядок,
  без запису звітів.

## [0.2.0] — 2026-11-05

### Додано
- Нові патерни секретів: AWS `AKIA…` standalone, Slack `xox*`, Bearer-токени.
- **`remote_exec`**: curl/wget `| sh`, `bash -c`, `powershell -enc`,
  `subprocess(..., shell=True)`.
- **py_compile гейт**: байткод-компіляція змінених .py файлів — незалежна
  від `ast.parse` перевірка синтаксису з діагностикою файл/рядок.

## [0.1.0-alpha] — 2026-11-05

### Додано
- AST-евристики: `dangerous_call` (eval/exec/compile/`__import__`),
  `shell_exec` (`os.system`/`os.popen`/subprocess зі строкою),
  `sql_string_format` (SQL через f-string/.format/%), `dead_import` (opt-in),
  `hardcoded_secret`, `syntax_error`.
- git-інтеграція: `aicv check [--staged]`, `aicv ci` (diff від
  `GITHUB_BASE_REF`), звіти `.aicv/latest.md` + `.aicv/latest.json`.
- Inline-супресії: `# aicv: ignore`, `# aicv: ignore[rule1, rule2]`.
- Machine-readable вердикт: `aicv check --json`.
- Групований markdown-звіт (по файлах, errors перед warnings).
- pre-commit hook (`a .pre-commit-hooks.yaml`), приклад GitHub Action,
  конфіг `.aicv.toml`, ruff-адаптер з graceful fallback.

[0.4.0]: https://github.com/bigpi/ai-code-verifier/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bigpi/ai-code-verifier/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bigpi/ai-code-verifier/compare/v0.1.0-alpha...v0.2.0
[0.1.0-alpha]: https://github.com/bigpi/ai-code-verifier/releases/tag/v0.1.0-alpha
