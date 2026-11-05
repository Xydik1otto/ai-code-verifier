# aicv-dotnet — C#/.NET port of aicv

Друга реалізація aicv мовою C# (.NET 10), без зовнішніх залежностей.
Ті самі правила, той самий JSON-вердикт, той самий exit-code контракт —
але один самодостатній `.exe`, який не потребує ані Python, ані .NET runtime.

## Структура

- `AiCV.Core` — бібліотека: реєстр правил, секрети/remote-exec/TODO regex,
  dangerous/shell-call евристики, SQL-format, `# aicv: ignore` suppression,
  bracket-balance syntax-гейт, `.aicv.toml` конфіг, SARIF/annotations/звіти.
- `AiCV.Cli` — CLI: `check`, `report`, `ci`, `diff`, `verdict` (+ `init`,
  `baseline`), прапорці `--json`, `--sarif`, `--annotate`, `--staged`,
  `--summary`, `--baseline`.

## Збірка

```bash
cd dotnet
dotnet publish AiCV.Cli -c Release -r win-x64 \
    --self-contained true \
    -p:PublishSingleFile=true \
    -p:PublishReadyToRun=true \
    -o artifacts/exe
# -> artifacts/exe/aicv.exe (~70-90 MB, самодостатній)
```

### AOT

`-p:PublishAot=true` дає ще швидший старт, але потребує нативний тулчейн
(MSVC linker — Desktop Development for C++ у Visual Studio). Якщо він
відсутній, збірка падає з `Platform linker not found` — тоді використовуйте
команду вище (self-contained single-file + ReadyToRun); різниця у старті
~50-80 мс, для сканування це несуттєво.

## Паритет із Python-реалізацією

`tests/test_dotnet_parity.py` генерує корпус (bad / clean / suppression /
todo), проганяє і Python `aicv`, і C# exe на тому самому git-дифі та
порівнює вердикти: файли, exit-code, множина знахідок `(file, line, rule)`,
severity per finding. Допустимі відмінності — лише текст повідомлень і
номер рядка `syntax_error` (Python парсить справжнім AST, C# використовує
lightweight bracket-гейт — знахідка та сама, рядок може відрізнятись).

Задокументовані відмінності (обмеження lightweight-підходу):

- `syntax_error` для Python у C# ловить тільки дисбаланс дужок — не будь-яку
  синтаксичну помилку (для Go/Java обидві реалізації однаково роблять
  bracket-гейт).
- `subprocess.run("...")` з конкатенацією рядків (`"ls " + cmd`) C# не
  прапорцює як bare-string warning — Python бачить через AST, що перший
  аргумент не є константою.
- `ruff` інтеграції в C# немає (прапорець `--no-ruff` приймається для
  сумісності CLI).
- `dead_import` у C# — regex-наближення (импорта-рядки виключаються зі
  скану використань).

## Бенчмарк

```bash
python scripts/benchmark.py          # Python-реалізація (існуюча)
python scripts/benchmark_dotnet.py   # C# exe (best of N прогонів)
```

Актуальні числа — в основному README (розділ «Швидкодія» / «Speed»).
