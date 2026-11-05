# Contributing / Розробка aicv

Дякуємо за інтерес до **aicv** — zero-dependency верифікатора коду для
AI-агентів і CI. Цей документ розрахований на контриб'юторів, які збираються
лізти в код: спершу архітектура, потім процес.

Thank you for your interest in **aicv** — a zero-dependency code verifier for
AI agents and CI. This document targets contributors who intend to work on the
code: architecture first, process after.

> Англомовне дзеркало цього документа: [CONTRIBUTING.en.md](CONTRIBUTING.en.md).
> English mirror: [CONTRIBUTING.en.md](CONTRIBUTING.en.md).

---

## 1. Архітектура

Проєкт має **дві реалізації одного контракту**:

| Реалізація | Розташування | Роль |
|---|---|---|
| Python (еталон) | `aicv/` | Еталонна логіка, публікується на PyPI |
| C#/.NET порт | `dotnet/` | Самодостатній `aicv.exe` без Python і без .NET runtime |

Обидві реалізації зобов'язані видавати **однаковий набір знахідок** на тому
самому git-дифі. Це закріплено golden-паритетними тестами
(`tests/test_dotnet_parity.py`) — вони мержать PR, а не «бажання».

### 1.1 Реєстр правил — `aicv/checks.py`

Центральний стан усього сканера — словник `RULES`:

```python
RULES: Dict[str, Dict] = {
    "dangerous_call": {"name": "Dynamic code execution (eval/exec/compile)",
                       "default": True, "severity": "error"},
    ...
}
```

Кожне правило описують поля:

- **`id`** (ключ словника) — snake_case, **незмінний назавжди**. Він тікає у
  JSON-вердикт, SARIF, `.aicv.toml`, `# aicv: ignore[id]`, baseline —
  перейменування правила ламає користувачів.
- **`name`** — короткий людський опис **англійською** (парситься агентами,
  потрапляє в SARIF `shortDescription`). Рядок має бути **ідентичним** у
  Python- і C#-реалізаціях.
- **`default`** — чи правило увімкнене без конфіга. Шумні правила (наприклад
  `dead_import`) робіть `False` — opt-in.
- **`severity`** — дефолтний рівень: `error` (валить перевірку, exit 1),
  `warning` (лише повідомляє), `info`.

Самі детектори — чисті функції поруч зі словником, двох типів:

- **AST-детектори** (тільки Python): `check_dangerous_calls`,
  `check_sql_string_format`, `check_shell_true`, `check_dead_imports` —
  ходять по `ast.walk(tree)`.
- **Рядкові/regex-детектори** (всі мови): `check_hardcoded_secrets`,
  `check_remote_exec_lines`, `check_todo_fixme` — проходять
  `text.splitlines()`.

Кожен детектор повертає список Finding-словників через `_mk()`:

```python
{"rule": ..., "severity": ..., "file": ..., "line": ..., "message": ...}
```

**Suppression**: перед виходом з `check_*_file` усе пропускається через
`filter_suppressed()` — inline-коментар `# aicv: ignore` (всі правила на
рядку) або `# aicv: ignore[rule1, rule2]`. `suppression_map()` будує
мапу `рядок -> "*" | {rule_ids}`; це працює для всіх мов, включно з
ruff-знахідками.

### 1.2 Пайплайн — `aicv/engine.py`

Прямування даних в `aicv check`:

```
git diff (--staged | HEAD | base_ref...HEAD) + untracked
  → changed_files(): фільтр (існує, не прихований файл, не .aicv/)
  → розподіл за розширенням:
      .py                → check_python_file  (AST + regex + compile-гейт)
      .js .ts .mjs ...   → check_js_ts_file   (regex)
      .go                → check_go_file      (regex + bracket-гейт)
      .java              → check_java_file    (regex + bracket-гейт)
  → ruff (опційно; знахідки теж проходять filter_suppressed)
  → apply_severities(): перевизначення з .aicv.toml [severity]
  → apply_baseline(): відсів записів .aicv/baseline.json (тільки для --baseline)
  → вивід: текст / --json вердикт / --sarif / --annotate
```

Ключові моменти:

- **`changed_files()`** ніколи не сканує `.aicv/` (власні артефакти звітів)
  і файли, що починаються з крапки. У режимі робочого дерева додає
  untracked-файли — свіжі AI-файли ще не staged.
- **`diff_refs()` / `run_checks_between()`** (`aicv diff ref1 ref2`):
  merge-base diff `ref1...ref2`, блоби materializуються в temp-каталог,
  тому всі звичайні чекери працюють без checkout. Шляхи знахідок —
  repo-relative.
- **Конфіг**: `load_config()` читає `.aicv.toml` `[rules]` (toggles),
  `load_severities()` — `[severity]` (per-rule override). Обидва м'яко
  деградують до дефолтів на будь-якій помилці (tomllib відсутній, битий
  TOML) — **graceful fallback є контрактом**: опційна інтеграція ніколи
  не ламає скан.
- **Exit code**: `1` якщо є хоч одна знахідка severity `error`, інакше `0`.
  Warnings/info на код не впливають.

### 1.3 Вихідні формати

- **JSON-вердикт** (`aicv verdict --json`): `{"files_checked", "errors":
  [{file, line, rule, message}], "exit_code"}` — машинний контракт для
  agent-циклів.
- **SARIF 2.1.0** (`render_sarif`): для GitHub code scanning upload.
  Кожне правило з `RULES` потрапляє в `tool.driver.rules`
  (`shortDescription` = `name`); знахідки з ruff отримують id `ruff:<rule>`.
  Мапінг severity: `error→error`, `warning→warning`, `info→note`.
- **GitHub Annotations** (`render_annotations`): рядки
  `::error file=...,line=...::rule: message` — печатуються `aicv ci
  --annotate` всередині GitHub Actions і стають inline-анотаціями на PR.
  Повідомлення ескейпляються (`%`→`%25`, нові рядки→`%0A/%0D`), шляхи —
  строго forward slashes.
- **Baseline**: `aicv baseline` записує поточні знахідки у
  `.aicv/baseline.json`; далі `aicv check --baseline` падає лише на **нових**
  знахідках. Ключ знахідки — кортеж `(file, line, rule)`; рядок фіксуйте,
  бо зсув рядків «відкриває» старий борг наново.
- **Звіт**: `save_report()` пише `.aicv/latest.json` + `.aicv/latest.md`
  (markdown, згрупований по файлах, errors перед warnings).

### 1.4 C# порт — `dotnet/AiCV.Core`

Структура дзеркалить Python:

| Python | C# | Примітка |
|---|---|---|
| `checks.RULES` | `Rules.All` (`RuleSpec(Name, Default, Severity)`) | ідентичні id/name/default/severity |
| детектори | `Checks` (regex-порт) | 1:1 regex'и, `RegexOptions.IgnoreCase` замість `(?i)` |
| `engine.py` | `Engine.cs` | той самий пайплайн і ті самі формати виводу |
| Finding dict | `Finding.cs` (record) | ті самі поля |

Свідомі відмінності (задокументовані в `dotnet/README.md`, допустимі
паритетними тестами):

- `syntax_error`: Python парсить справжнім AST; C# — lightweight
  bracket-balance гейт (та сама знахідка, номер рядка може відрізнятись).
- `subprocess.run("ls " + cmd)` (конкатенація у bare string) C# не
  прапорцює — Python бачить через AST, що аргумент не константа.
- Немає ruff-інтеграції (`--no-ruff` приймається для сумісності CLI).
- `dead_import` у C# — regex-наближення.

### 1.5 Паритетний контракт: як додати правило в ОБИДВІ реалізації

Паритет тестується на рівні **набору знахідок** `(file, line, rule)` +
severity per finding. Тому золота послідовність:

**Крок 1 — Python, `aicv/checks.py`.** Додайте запис у `RULES`:

```python
"debug_print": {"name": "Debug print left in code",
                "default": True, "severity": "warning"},
```

**Крок 2 — Python, детектор.** Пишете чисту функцію поруч:

```python
_DEBUG_PRINT = re.compile(r"^\s*(print|console\.log)\s*\(")

def check_debug_prints(text: str, rel: str) -> List[Dict]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _DEBUG_PRINT.search(line):
            out.append(_mk("debug_print", FINDING_SEV_WARN, rel, lineno,
                           "Debug print left in code — remove before merge"))
    return out
```

**Крок 3 — Python, проводка.** Викличте детектор у кожному
`check_<lang>_file`, під прапорцем `enabled.get("debug_print", True)`,
**до** `filter_suppressed(...)`. Не забудьте обидві гілки (AST-мови
можуть хотіти lineno з AST; для рядкового правила — lineno з splitlines).

**Крок 4 — C#, `dotnet/AiCV.Core/Rules.cs`.** Дзеркальний запис з
**ідентичним** рядком name, default і severity:

```csharp
["debug_print"] = new("Debug print left in code", true, Sev.Warn),
```

**Крок 5 — C#, `dotnet/AiCV.Core/Checks.cs`.** Порт детектора. Регекси
пишіть у **спільному підмножині** синтаксису Python `re` і .NET `Regex`:
`(?i)` inline, `\b`, класи `[…]`, квантифікатори `{n,}` — ок;
possessive quantifiers, lookbehind змінної довжини, `(?(x)...)` — ні.
Проводка — у той самий розподіл за розширеннями (`ScanExts` і методи
per-language), **до** suppression.

**Крок 6 — паритетний корпус.** У `tests/test_dotnet_parity.py` додайте
рядки нового правила до шаблонів `BAD_*` (і, за потреби, приклад
suppression у `SUPPRESSED_*`). Без цього паритет-тест фізично не зможе
зловити розбіжність по вашому правилу.

**Крок 7 — документація і тести.**

- `python scripts/gen_rules.py` → закомітьте оновлений `docs/rules.md`
  (sync-тест падає, якщо забули).
- Golden-фіксура + твердження в `tests/test_aicv.py` для Python-сайду.
- Рядок у `CHANGELOG.md`.
- Запустіть: `pytest` (все); окремо `pytest tests/test_dotnet_parity.py`
  дає швидший цикл при налагодженні паритету.

**Чого паритет-тест НЕ пробачає**: rule id різний у двох реалізаціях;
різний `default`/`severity`; детектор, що стріляє на одному боці й мовчить
на іншому (same file, same line). **Що пробачає**: текст повідомлення
(англійською в обох, але формулювання може відрізнятись) і номер рядка
`syntax_error` (AST vs bracket-гейт).

## 2. Середовище розробки

### Python

```bash
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
pip install -e .
pytest
```

Zero runtime dependencies — тільки стандартна бібліотека Python (3.9+).
Не додавайте залежностей без попереднього обговорення в issue. Опційні
інтеграції (ruff, tomllib на старих Python) — лише з graceful fallback.

### C# порт

```bash
cd dotnet
dotnet build AiCV.sln -c Release
dotnet publish AiCV.Cli -c Release -r win-x64 \
    --self-contained true \
    -p:PublishSingleFile=true \
    -p:PublishReadyToRun=true \
    -o artifacts/exe
# -> dotnet/artifacts/exe/aicv.exe (самодостатній, ~70-90 MB)
```

Паритетні й benchmark-тести шукають exe за `$AICV_DOTNET_EXE` або в
`dotnet/artifacts/exe/aicv.exe`. AOT (`-p:PublishAot=true`) швидший на
старті, але потребує MSVC-лінкер; без нього падає з
`Platform linker not found` — використовуйте команду вище (деталі:
`dotnet/README.md`).

## 3. Тести

- `tests/test_aicv.py` — основний suite: правила, конфіг, suppression,
  ref-diff, виводи, CLI. **Тести обов'язкові**: кожна зміна поведінки
  покривається pytest-тестом, PR без тестів не мержиться.
- `tests/fixtures/` — golden-фікстури (bad/clean per мову: `bad_code.py`,
  `bad_secrets.go`, `clean_code.java`, ...). Додаючи правило або мову —
  додайте пару bad/clean фіксур і твердження на точні `(rule, line)`.
- `tests/test_dotnet_parity.py` — golden-паритет Python ↔ C# (корпус
  генерується на льоду, порівнюються verdicts; деталі — п. 1.5).
- `tests/test_dotnet_benchmark.py` — smoke-тест бенчмарку (200 файлів).

### Оновлення benchmark

`scripts/benchmark.py` (Python) і `scripts/benchmark_dotnet.py` (C# exe)
будують викидний git-репо на 1000 файлів (98% чистих, 2% з класичними
AI-помилками) і часують реальний CLI. Методологія:

- Один subprocess на прогін, startup включено — так, як це бачить
  користувач/agent-цикл.
- `benchmark_dotnet.py` робить **best-of-3** (мінімум): перший прогін
  платить разову Windows Defender-скан-кару на свіжі файли (~2.5 s),
  яку сам інструмент не контролює. `--runs 1` — холодне число.
- Target: Python ~10 s, C# ~1 s на 1000 файлів (exit 1 при перевищенні).

Якщо ваша зміна рухає швидкодію: перегоніть обидва бенчмарки
(`python scripts/benchmark.py`, `python scripts/benchmark_dotnet.py`) і
оновіть числа в розділі «Швидкодія» / «Speed» головного README. Не міняйте
методологію (N файлів, best-of, шаблони корпусу) без обговорення — інакше
числа несумісні з історією.

## 4. Як додати нову мову сканування

Еталон — так у проєкт з'явилися Go і Java (v1.0). Покроково (приклад:
мова `lang`, розширення `.lang`):

1. **Розширення**: у `aicv/checks.py` — `LANG_EXT = {".lang"}`.
2. **Спільний pre-scan**: більшість правил (secrets, remote-exec,
   TODO/FIXME) — рядкові й уже мовно-агностичні. Використайте
   `_check_text_language(path, rel, enabled)` — так роблять
   `check_go_file` і `check_java_file`.
3. **Мовно-специфічні патерни**: секретні шаблони конкретної мови
   (`password := "..."` у Go, `String password = "..."` у Java) додаються
   в `_SECRET_PATTERNS` з міткою — обов'язково в **обидві** реалізації
   (крок 5 п. 1.5).
4. **Syntax-гейт**: без парсера в zero-dep інструменті —
   `check_bracket_balance(text, rel)` після `_strip_comments_and_strings()`
   (баланс дужок із видаленими коментарями/рядками).
5. **Проводка**: `SCAN_EXTS` у `engine.py` (`PY_EXT | JS_EXT | GO_EXT |
   JAVA_EXT | LANG_EXT`) + гілка `elif ext in LANG_EXT:` у `run_checks()`.
6. **C# дзеркало**: масив розширень і метод per-language у `Checks.cs`,
   та самі розширення у `ScanExts`.
7. **Фікстури + паритет**: `tests/fixtures/clean_code.lang`,
   `bad_secrets.lang`; шаблони корпусу в `test_dotnet_parity.py`; тести
   в `test_aicv.py`.
8. **Документи**: `docs/rules.md` (перегенеруйте), README (список мов),
   `CHANGELOG.md`.

Не беріть у MVP повний парсер — правила, які regex ловить надійно,
коштують менше, ніж залежність на 50 MB.

## 5. Гілки та комміти

- **`master` — стабільна гілка**: зелений pytest, робочі доки, можна
  релізити в будь-який момент. Прямі push у `master` — лише для дрібниць
  (docs, typos) власником; фічі — через PR.
- Робочі гілки: `feature/<коротка-назва>`, `fix/<коротка-назва>`.
- **Conventional commits**: `feature: …`, `fix: …`, `docs: …`,
  `test: …`, `refactor: …`; для релізних комітів — `vX.Y feature: …`
  (див. історію). Одна логічна зміна — один commit.
- PR-процес: fork/гілка → `pytest` зелений локально → PR з описом «що,
  навіщо, як перевірено» → обговорення → merge. Для C#-змін додайте
  вивід паритетного тесту.

## 6. Документація та i18n

- Документація ведеться **українською та англійською**: парні файли
  (`README.md` ↔ `README.en.md`, `CONTRIBUTING.md` ↔ `CONTRIBUTING.en.md`).
  Змінивши один — дзеркальте в другий у тому самому PR.
- `docs/rules.md` **генерується** (`python scripts/gen_rules.py`) — не
  редагуйте вручну; джерело правди — `RULES` у `aicv/checks.py`.
- Повідомлення знахідок, ідентифікатори правил, commit-повідомлення —
  англійською (їх парсять агенти й CI).
- **Російську локалізацію не додаємо і не приймаємо** (політичне рішення
  власника проєкту). PR з російською мовою в документах чи UI буде
  відхилено незалежно від технічної якості.

## 7. Баг-репорти та пропозиції

Використовуйте шаблони
[bug_report](https://github.com/bigpi/ai-code-verifier/issues/new?template=bug_report.md)
та [feature_request](https://github.com/bigpi/ai-code-verifier/issues/new?template=feature_request.md).
У баг-репорті додають цінність: версія (`aicv --version` / назва exe),
вивід `aicv check --json`, мінімальний приклад файла, на якому зламалось.
Для C#-порту вкажіть, чи відтворюється в обох реалізаціях — якщо тільки
в одній, це паритет-баг і він має пріоритет.

## 8. Ліцензія

Вносячи код, ви погоджуєтесь віддати його під ліцензію проєкту (MIT).
By contributing code you agree to license it under the project license (MIT).
