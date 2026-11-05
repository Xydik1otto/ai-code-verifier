#!/usr/bin/env python3
"""Generate docs/rules.md from aicv.checks.RULES.

The rule catalog documentation must never drift from the code: run this
script after changing RULES (adding/removing rules, renaming, changing
defaults or severities) and commit the result.

Usage: python scripts/gen_rules.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aicv.checks import RULES  # noqa: E402

HEADER = """\
# Каталог правил aicv

> Цей файл згенерований автоматично: `python scripts/gen_rules.py`.
> Не редагуйте вручну — зміни вносьте у словник `RULES` в `aicv/checks.py`,
> потім перегенеруйте й закомітьте результат.

## Правила

| Правило | Опис | Увімкнено за замовчуванням | Типовий severity |
|---|---|---|---|
"""

FOOTER = """
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
"""


def main() -> int:
    lines = [HEADER]
    for rid, spec in sorted(RULES.items()):
        default = "так" if spec.get("default") else "ні (opt-in)"
        sev = spec.get("severity", "error")
        lines.append(f"| `{rid}` | {spec['name']} | {default} | {sev} |\n")
    lines.append(FOOTER)
    out = ROOT / "docs" / "rules.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")
    print(f"gen_rules: wrote {out} ({len(RULES)} rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
