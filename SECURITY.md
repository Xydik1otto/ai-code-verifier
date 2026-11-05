# Security Policy / Політика безпеки

## Українською

### Як повідомити про вразливість

**Не створюйте публічний issue для вразливості.**

Пишіть на сторінку безпеки репозиторію:
<https://github.com/bigpi/ai-code-verifier/security/advisories/new>
(приватне повідомлення/Security advisory), або зв'яжіться із власником
через профіль GitHub.

Що вказати:

- версію aicv (`aicv --version`) та OS;
- кроки відтворення (мінімальний приклад файлу/дифу);
- очікувана vs фактична поведінка;
- якщо знаєте — ідею фіксу.

### Обсяг (in scope)

- Хибно-негативні детекти, що призводять до витоку секретів у CI
  (наприклад, патерн секретів легко обходиться на практиці).
- Инєкції через обробку шляхів/аргументів у CLI (`aicv diff`, git-виклики).
- Проблеми SARIF/JSON-виводу, що ламають парсери споживачів.

### Поза обсягом (out of scope)

- Регрес-шум (aicv — евристики, а не компілятор; хибні спрацювання —
  звичайний issue, не security).
- Вразливості в ruff або інших опційних інструментах.

aicv не виконує просканований код (тільки parse/compile у пам'яті), не
робить мережевих запитів і не збирає телеметрії — повідомлення про
«phone home» теж приймаємо як баг.

## In English

### How to report a vulnerability

**Do not open a public issue for vulnerabilities.**

Use the repository's private security advisory page:
<https://github.com/bigpi/ai-code-verifier/security/advisories/new>,
or reach the owner via their GitHub profile.

Please include: aicv version (`aicv --version`) and OS, minimal
reproduction steps (a file/diff), expected vs actual behavior, and — if
known — a suggested fix.

### Scope

- False-negative secret detection that would leak credentials through CI.
- Path/argument injection in the CLI (`aicv diff`, git invocations).
- SARIF/JSON output that breaks downstream parsers.

### Out of scope

- Detection noise (aicv is heuristics, not a compiler; false positives are
  regular issues, not security).
- Vulnerabilities in ruff or other optional third-party tools.

aicv never executes scanned code (parse/compile only, in memory), makes no
network requests and collects no telemetry — reports claiming otherwise are
treated as bugs.

## Supported versions / Підтримувані версії

| Version | Supported |
|---|---|
| 1.0.x | так / yes |
| < 1.0 | ні / no |
