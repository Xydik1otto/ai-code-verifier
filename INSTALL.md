# Встановлення aicv — покрокова інструкція

Інструкція розрахована на людину без досвіду з Python. Ніяких залежностей,
окрім самого Python, не потрібно.

- [Windows](#windows)
- [Linux](#linux)
- [macOS](#macos)
- [Оновлення](#оновлення)
- [Перевірка, що все працює](#перевірка-що-все-працює)
- [Використання у своєму репозиторії](#використання-у-своєму-репозиторії)
- [Проблеми](#проблеми)

## Windows

1. **Встановіть Python 3.9+** (якщо його ще немає):
   завантажте з <https://www.python.org/downloads/>, при встановленні
   поставте галочку **«Add python.exe to PATH»**.
2. **Відкрийте PowerShell** (Win → введіть «powershell» → Enter).
3. **Завантажте та встановіть aicv:**

   ```powershell
   git clone https://github.com/bigpi/ai-code-verifier
   cd ai-code-verifier
   pip install -e .
   ```

   Якщо `git` не встановлений — завантажте ZIP зі сторінки репозиторію
   (Code → Download ZIP), розпакуйте і виконайте `pip install -e .`
   всередині розпакованої папки.
4. **Перевірте:**

   ```powershell
   aicv --version
   ```

   Має вивестись `aicv 1.0.0`.
5. *(Опційно, автозапуск не потрібен: aicv — це CLI-інструмент, який
   запускають вручну або з git hook / CI. Жодних служб він не створює.)*

## Linux

```bash
# Python 3.9+ майже завжди вже є; перевірте:
python3 --version

git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
python3 -m pip install --user -e .
```

Якщо `aicv` не знаходиться після встановлення — додайте `~/.local/bin`
у `PATH` (зазвичай достатньо перелогінитись) або викликайте як
`python3 -m aicv.cli`.

## macOS

```bash
xcode-select --install          # дасть git
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
python3 -m pip install --user -e .
```

## Оновлення

```bash
cd ai-code-verifier
git pull
pip install -e .         # перечитає код, версію покаже aicv --version
```

З PyPI (коли пакет там з'явиться): `pip install -U aicv`.

## Перевірка, що все працює

Створіть тестовий репозиторій і спробуйте aicv на навмисно поганому файлі:

```bash
mkdir aicv-demo && cd aicv-demo
git init
git config user.name demo && git config user.email demo@local
```

Створіть файл `bad.py` з таким вмістом:

```python
import os

API_KEY = "sk-liv...7890"

def run(cmd: str):
    os.system("ls " + cmd)
```

І запустіть:

```bash
aicv check
```

Очікувано: `aicv: checked 1 file(s) [diff HEAD] — 4 error(s), 0 warning(s)`
та код виходу `1`. Це означає, що aicv працює.

## Використання у своєму репозиторії

- `aicv check` — перевірити незакомічені зміни (розумні дефолти працюють
  без конфігу).
- `aicv init` — згенерувати стартовий конфіг `.aicv.toml`, коли захочете
  налаштувати правила.
- `aicv diff main feature` — перевірити всю гілку перед merge.
- `aicv ci --annotate` — у GitHub Actions: зауваження прямо на дифі PR.

Повний список команд — у [README.md](README.md).

## Проблеми

- **`aicv: command not found`** — Python Scripts-папка не у PATH;
  викличте `python -m aicv.cli` або перевстановіть з `--user`.
- **`fatal: not a git repository`** — aicv працює по git diff; запустіть
  у папці, де є `.git`.
- Баги та пропозиції —
  [шаблони issue](https://github.com/bigpi/ai-code-verifier/issues/new/choose).
