# Changelog

Усі помітні зміни проєкту aicv документуються у цьому файлі.

Формат базується на [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/),
версіювання — [Semantic Versioning](https://semver.org/lang/uk/).

## [Unreleased]

### Додано
- **C#-скан через Roslyn AST (stage 2)** — `aicv-dotnet` сканує `.cs`
  справжнім AST (`Microsoft.CodeAnalysis.CSharp`, MIT): dangerous API
  (Roslyn-scripting Eval `CSharpScript.EvaluateAsync/RunAsync`, CodeDom
  `CompileAssemblyFromSource`, `using CompilerServices`/`Reflection.Emit`),
  `Process.Start` із shell-ціллю та `UseShellExecute = true`, інтерпольований
  SQL `$"SELECT ... {var}"` (+ `string.Format`, конкатенація), TODO/FIXME,
  hardcoded secrets; синтаксис-гейт — справжні діагностики парсера Roslyn
  з точними row/col (поле `column` у JSON — лише для AST-знахідок).
  C#-порт є авторитетною реалізацією для `.cs`.
- **`.cs` regex-fallback у Python-реалізації** — Python не має Roslyn, тому
  `aicv.checks.check_cs_file` сканує `.cs` regex-рівнем з тими самими id
  правил; паритет-політика: regex-знахідки — підмножина AST-знахідок
  (документовано в `docs/rules.md`).
- C#-фікстури (`tests/fixtures/*.cs`: dangerous / interpolated-sql /
  secrets / clean / todo / syntax) + `tests/test_cs_scan.py`; паритет-тести
  розширені `.cs`-корпусом (regex vs AST, superset-політика, `column`).
- Форма suppression `// aicv: ignore` для C-подібних мов (поряд із `#`).
- `docs/rules.md`: автогенерована таблиця «Мови та рівень аналізу»
  (розширено `scripts/gen_rules.py`).
- **C# .NET 10 порт (aicv-dotnet)** — друга реалізація aicv у `dotnet/`:
  бібліотека `AiCV.Core` (усі правила v1.0: secrets regex, dangerous/shell/
  remote-exec, SQL-format, TODO/FIXME, `# aicv: ignore` suppressions,
  bracket-balance syntax-гейт, `.aicv.toml` конфіг) + CLI `AiCV.Cli`
  (`check`/`report`/`ci`/`diff`/`verdict`/`init`/`baseline`, `--json`,
  `--sarif`, `--annotate`), без зовнішніх залежностей (до stage 2).
  Публікація — self-contained single-file `aicv.exe` (ReadyToRun; Native AOT
  потребує MSVC-лінкера — задокументовано в `dotnet/README.md`).
- **Golden-паритет тести** `tests/test_dotnet_parity.py`: корпус
  bad/clean/suppression/todo проганяється і Python `aicv`, і C# exe;
  звіряються файли, exit-code, множина знахідок (file, line, rule) і
  severity (допустимі відмінності — текст повідомлень і рядок
  `syntax_error`: AST проти bracket-гейту).
- **Бенчмарк** `scripts/benchmark_dotnet.py`: 1000-файловий диф, best-of-3
  методологія (перший прогін платить одноразовий Defender-скан нових
  файлів). C#: **0.34 s** (ціль <1 s — PASS) проти Python ~1.0 s (best of 3)
  / 3.93 s (холодний прогін) — README (UA+EN) оновлено, C# рекомендовано
  для великих репозиторіїв.
- `INSTALL.md`: розділ «C#-версія (aicv-dotnet) — без Python».

### Змінено
- README (UA+EN): розділ «Мови» тепер описує `.cs`-скан (Roslyn AST у
  `aicv-dotnet` — авторитетний; Python-side regex-fallback); розділ
  «Швидкодія»/«Speed» порівнює обидві реалізації; «Встановлення»/
  «Installation» — два варіанти (Python, C# exe).

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
