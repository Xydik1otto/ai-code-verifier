# Contributing / Як долучитися

Дякуємо за інтерес до **aicv**! Будь-який внесок вітають: баг-репорти,
ідеї фіч, документація, код.

Thank you for your interest in **aicv**! All contributions are welcome:
bug reports, feature ideas, documentation, code.

---

## Українською

### Швидкий старт для розробника

```bash
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
pip install -e .
pytest
```

Zero runtime dependencies — проєкт використовує лише стандартну бібліотеку
Python (3.9+). Не додавайте залежностей без попереднього обговорення.

### Правила

1. **Кожна фіча/фікса — окремий commit** із зрозумілим повідомленням
   (див. історію: `feature: …`, `docs: …`, `vX.Y feature: …`).
2. **Тести обов'язкові**: кожна нова поведінка покривається pytest-тестом
   (`tests/test_aicv.py`). PR без тестів не мержиться.
3. **Документація не відстає від коду**: додавши/змінивши правило у
   `aicv/checks.py` (`RULES`), перегенеруйте `python scripts/gen_rules.py`
   і закомітьте оновлений `docs/rules.md` (є sync-тест).
4. **Стиль**: звичайний PEP 8 без нав'язливих форматтерів; літери у
   повідомленнях знахідок — англійською (їх парсять агенти й CI), документація
   — українською та/або англійською. **Російську локалізацію не додаємо**
   (політичне рішення власника проєкту).
5. **Graceful fallback**: будь-яка опційна інтеграція (ruff, tomllib у
   старих Python) має м'яко деградувати, а не падати.
6. Оновіть `CHANGELOG.md` у секції `Unreleased`/поточної версії.

### Процес

1. Fork → гілка `feature/<коротка-назва>`.
2. `pytest` зелений локально.
3. PR з описом: що і навіщо, як перевірено.
4. Обговорення → мерж.

### Баг-репорти

Використовуйте шаблони
[bug_report](https://github.com/bigpi/ai-code-verifier/issues/new?template=bug_report.md)
та [feature_request](https://github.com/bigpi/ai-code-verifier/issues/new?template=feature_request.md).

---

## In English

### Developer quick start

```bash
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
pip install -e .
pytest
```

Zero runtime dependencies — the project uses only the Python standard
library (3.9+). Don't add dependencies without prior discussion.

### Ground rules

1. **One feature/fix per commit**, with a clear message (see history:
   `feature: …`, `docs: …`, `vX.Y feature: …`).
2. **Tests are mandatory**: every behavior change needs a pytest test in
   `tests/test_aicv.py`. PRs without tests are not merged.
3. **Docs never drift from code**: if you add/change a rule in
   `aicv/checks.py` (`RULES`), re-run `python scripts/gen_rules.py` and
   commit the updated `docs/rules.md` (a sync test enforces this).
4. **Style**: plain PEP 8, no opinionated formatters; finding messages are
   in English (agents and CI parse them), documentation in Ukrainian
   and/or English. **No Russian localization** (project owner's policy).
5. **Graceful fallback**: optional integrations (ruff, tomllib on older
   Pythons) must degrade softly, never crash the scan.
6. Update `CHANGELOG.md` under the current/Unreleased section.

### Process

1. Fork → branch `feature/<short-name>`.
2. `pytest` green locally.
3. PR describing what, why, and how it was verified.
4. Discussion → merge.

### Bug reports

Use the
[bug_report](https://github.com/bigpi/ai-code-verifier/issues/new?template=bug_report.md)
and
[feature_request](https://github.com/bigpi/ai-code-verifier/issues/new?template=feature_request.md)
issue templates.

## Licensing

Вносячи код, ви погоджуєтесь віддати його під ліцензію проєкту (MIT).
By contributing code you agree to license it under the project license (MIT).
