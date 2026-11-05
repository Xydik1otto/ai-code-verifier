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
