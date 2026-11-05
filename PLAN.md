# PLAN — aicv (AI Code Verifier)

## 1. Цільова аудиторія

- **Solo-розробники та small teams**, які щодня приймають AI-код (Copilot,
  Cursor, Claude Code) і хочуть автоматичний фільтр перед рев'ю.
- **Платформи/агентні пайплайни** (автономні кодинг-агенти), яким потрібна
  машиночитана верифікація (JSON verdict) у циклі agent-loop.
- **Team leads / eng managers**, які хочуть метрики якості AI-коду по командах.

## 2. MVP scope (реалізовано, v0.1.0)

- CLI `aicv` з командами `check` (diff HEAD / `--staged`), `report` (останній
  звіт, md/json), `ci` (diff від `GITHUB_BASE_REF`).
- Ланцюжок перевірок: py_compile/AST syntax, ruff (якщо встановлений, з
  graceful fallback), вбудовані евристики security (eval/exec, exec-into-shell,
  hardcoded secrets, SQL string formatting), dead imports.
- Звіт у markdown + JSON, exit code 0/1.
- Конфіг `.aicv.toml` (увімк/вимк правил).
- Приклад GitHub Action `.github/workflows/aicv.yml`.
- pytest: поганий код детектується, чистий проходить, exit codes правильні.

## 3. Архітектура

```
git diff ──▶ changed_files() ──▶ per-file check chain ──▶ findings[]
                                        │
                    Python: ast.parse → AST rules → regex secrets → ruff
                    JS/TS:  regex secret scan (MVP)
                                        │
             ──▶ render_markdown / JSON ──▶ .aicv/latest.{md,json}
                                        │
             ──▶ exit_code(findings): 1 якщо є error-рівень ──▶ gate
```

Принципи: stdlib-only core; ruff/інші лінтери — опціональні адаптери, падіння
адаптера ніколи не блокує скан; детермінованість (без LLM у критичному шляху).

## 4. Roadmap

- **v0.2 — pre-commit** ✅: `.pre-commit-hooks.yaml` + README-інструкція.
- **v0.2/0.3 — нові правила** ✅: `remote_exec` (curl|sh, bash -c,
  powershell -enc, shell=True), secret-патерни AKIA / xox* / Bearer;
  py_compile-гейт синтаксису ✅.
- **v0.3 — SARIF** ✅: `aicv check --sarif` → `.aicv/latest.sarif` для
  GitHub code scanning.
- **v0.3 — agent-loop API** ✅: `aicv check --json` (вердикт), `aicv verdict
  --summary` (marker-блок), inline-супресії `# aicv: ignore[rule]`, `aicv init`.
- **v1.1 — C# AST (Roslyn, stage 2)** ✅: `aicv-dotnet` сканує `.cs`
  справжнім AST (`Microsoft.CodeAnalysis.CSharp`) — dangerous API
  (Roslyn-scripting Eval, CodeDom, CompilerServices), `Process.Start` з
  shell-ціллю, інтерпольований SQL, secrets, TODO; синтаксис-гейт —
  діагностики парсера Roslyn з точними row/col (`column` у JSON).
  Python-реалізація лишає для `.cs` regex-fallback з тими самими id правил;
  паритет-політика — AST ⊇ regex (документовано в `docs/rules.md`).
- **v0.4 — JS/TS AST**: tree-sitter або esprima для справжнього парсингу JS/TS
  (eval/child_process/небезпечні патерни, не лише regex).
- **v0.5 — PR-анотації**: comments на diff у PR через GitHub API.
- **v0.6 — baseline**: baseline-файл для легасі-коду, щоб не шуміти на старих
  файлах (suppressions per-line вже є).
- **v1.0 — team mode (SaaS)**: дашборд по PR, тренд «AI-code trust score»,
  політики на рівні org, інтеграції Slack/GitHub comments.

## 5. Монетизація

- **OSS core (завжди безкоштовний)**: CLI, базові правила, GitHub Action —
  двигун поширення і довіри.
- **Paid team SaaS**: centralized policies (спільний .aicv.toml для org),
  дашборд трендів якості, командні baseline, SSO/SCIM, SLA.
  Орієнтир: $10–15/user/міс для команд 10+, безкоштовно до 5 користувачів.
- Можливий marketplace-канал: GitHub App з перевірками на PR.

## 6. Ризики та мітигація

| Ризик | Мітигація |
|---|---|
| Шум (false positives) знищить довіру до інструменту | warnings vs errors; per-repo конфіг; suppressions; правило за замовчуванням dead_import=off |
| Правила легко обійти / обмежена глибина AST | чесно позиціювати як «швидкий фільтр перед рев'ю», а не security-аудит; roadmap → tree-sitter |
| Конкуренція з лінтерами/CI-сканерами | фокус на diff-based workflow саме для AI-коду + agent-loop вердикт, якого немає в linters |
| Статичні евристики не ловлять логічні баги | roadmap v1.x: інтеграція запуску тестів як додатковий «gate» у ланцюжку |
| GitHub Action поширення повільне | публікація на PyPI + власний composite action |

## 7. Метрики успіху

- Встановлення/тиждень у CI (GitHub Action usage).
- % PR, де aicv знайшов ≥1 error до людського рев'ю (precision > 80% ціль).
- Час до першого зовнішнього контриб'ютора (здоров'я OSS).
