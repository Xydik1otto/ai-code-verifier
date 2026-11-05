# Каталог правил aicv

> Цей файл згенерований автоматично: `python scripts/gen_rules.py`.
> Не редагуйте вручну — зміни вносьте у словник `RULES` в `aicv/checks.py`,
> потім перегенеруйте й закомітьте результат.

## Правила

| Правило | Опис | Увімкнено за замовчуванням | Типовий severity |
|---|---|---|---|
| `dangerous_call` | Dynamic code execution (eval/exec/compile) | так | error |
| `dead_import` | Imported but never used | ні (opt-in) | warning |
| `hardcoded_secret` | Hardcoded secrets in source | так | error |
| `remote_exec` | Remote/shell code execution patterns | так | error |
| `shell_exec` | Shell execution from strings | так | error |
| `sql_string_format` | SQL built via string formatting | так | error |
| `syntax_error` | File does not parse/compile | так | error |
| `todo_fixme` | TODO/FIXME markers left in code | так | warning |

## Мови та рівень аналізу

| Мова | Python aicv | aicv-dotnet (C#) |
|---|---|---|
| `.py` | справжній AST (`ast.parse`) + ruff (опційно) | AST-lite (strings/comments вирізані + regex) |
| `.cs` | regex-fallback (Roslyn у Python недоступний) | **справжній AST (Roslyn, `Microsoft.CodeAnalysis.CSharp`) — авторитетний** |
| `.js` `.ts` `.mjs` `.jsx` `.tsx` | regex | regex |
| `.go` | regex + bracket-гейт | regex + bracket-гейт |
| `.java` | regex + bracket-гейт | regex + bracket-гейт |

### C#: AST (C#-порт) проти regex-fallback (Python)

Для `.cs` обидві реалізації маплять знахідки на ті самі id правил, тож
агентний пайплайн отримує однаковий вердикт від будь-якої з них. C#-порт
сканує через Roslyn і є **авторитетним** для мови:

- точні row/col із вузлів AST (`column` у JSON — лише коли сканер її знає;
  Python-side regex дає тільки рядок);
- синтаксис-гейт — справжні Roslyn-діагностики парсера (CS1xxx), а не
  евристика балансу дужок; знахідка `syntax_error` — надмножина regex-гейту;
- коментарі та рядкові літерали не можуть викликати спрацювання
  dangerous/shell/SQL правил (regex-fallback може дати хибне спрацювання
  на згадку API в коментарі — задокументоване обмеження fallback'у).

Паритет-політика (`tests/test_dotnet_parity.py`): множина знахідок
Python-regex для `.cs` має бути підмножиною знахідок AST (AST точніший —
допустима надмножина); порівняння на рівні (file, rule), рядок/колонка
можуть відрізнятися.

## Severity

- **error** — валить перевірку (exit code 1): блокує commit / CI.
- **warning** — лише повідомляє; на exit code не впливає.
- **info** — суто інформаційне.

Типовий severity кожного правила можна перевизначити у `.aicv.toml`:

```toml
[severity]
dead_import = "error"   # підняти dead_import до рівня error
dangerous_call = "warning"  # опустити до warning — не валити збірку
```

## Конфігурація

Увімкнення/вимкнення правил — секція `[rules]` у `.aicv.toml`
(згенерувати стартовий конфіг: `aicv init`):

```toml
[rules]
dead_import = false
hardcoded_secret = true
```

Окреме знаходження можна приглушити inline-коментарем
`# aicv: ignore` (всі правила на рядку) або `# aicv: ignore[rule1, rule2]`.
