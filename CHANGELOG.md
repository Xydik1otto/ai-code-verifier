# Changelog

Усі помітні зміни проєкту aicv документуються у цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/),
версіювання — [Semantic Versioning](https://semver.org/lang/uk/).

## [1.0.0] — 2026-11-05

### Додано
- **Go + Java pre-scan** (regex-рівень): hardcoded secrets (спільні патерни
  + Go `:=` та Java `String`-поля), remote-exec one-liners, TODO/FIXME,
  баланс дужок як syntax-гейт (коментарі та строки вирізаються перед
  підрахунком). `aicv` тепер сканує `.py`, `.js/.ts`, `.go`, `.java`.
- **`aicv diff ref1 ref2`**: верифікація файлів між двома гілками/тегами —
  merge-base diff, контент береться з другого ref'а (без checkout),
  підтримує `--json`/`--sarif`/`--annotate`.
- **Бенчмарк** `scripts/benchmark.py`: синтетичний диф із 1000 файлів,
  замір реального CLI-прогону. Результат: **4.35 s** (ціль <10 s — виконана
  з ~3× запасом); число опубліковане у README. Гейт `py_compile` замінено
  на in-memory `compile()` без дискового I/O (12.7 s → 4.35 s на 1000 файлів).
- **docs/agent-integration.md**: recipes інтеграції в агентний цикл —
  verdict-контракт, Claude Code (PostToolUse/Stop hooks), Cursor rules,
  CI-backstop.
- **First-run UX** задокументований і закритий тестами: без `.aicv.toml`
  aicv працює з розумними дефолтами (усі security-правила ON, шумне
  `dead_import` OFF).
- **README.en.md** — англомовна версія README (міжнародна аудиторія).
- **INSTALL.md** — покрокове встановлення для не-програміста
  (Windows/Linux/macOS, оновлення, перевірка працездатності).
- Open-source hygiene: CONTRIBUTING.md, SECURITY.md, шаблони issue
  (bug report + feature request), `.gitignore` покриває `.env`,
  секція Contributing + GitHub topics у README.

### Змінено
- Повідомлення синтакс-гейту тепер `compile: …` замість `py_compile: …`.

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

[1.0.0]: https://github.com/bigpi/ai-code-verifier/compare/v0.4.0...v1.0.0
[0.4.0]: https://github.com/bigpi/ai-code-verifier/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bigpi/ai-code-verifier/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bigpi/ai-code-verifier/compare/v0.1.0-alpha...v0.2.0
[0.1.0-alpha]: https://github.com/bigpi/ai-code-verifier/releases/tag/v0.1.0-alpha
