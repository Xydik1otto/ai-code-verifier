#!/usr/bin/env bash
# pypi-ready перевірка: збирає sdist/wheel і проганяє twine check,
# якщо build/twine встановлені; інакше — skip (zero-dep проєкт має і так
# робочий pyproject). Виводить PYPI-CHECK: PASS / SKIP / FAIL.
set -u
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python}"

if ! $PYTHON -c "import build" 2>/dev/null; then
    echo "PYPI-CHECK: SKIP — 'build' не встановлений (pip install build twine)"
    exit 0
fi

rm -rf dist
if ! $PYTHON -m build >/dev/null 2>&1; then
    echo "PYPI-CHECK: FAIL — python -m build завершився з помилкою"
    exit 1
fi

if $PYTHON -c "import twine" 2>/dev/null; then
    if ! $PYTHON -m twine check dist/* ; then
        echo "PYPI-CHECK: FAIL — twine check знайшов проблеми"
        exit 1
    fi
else
    echo "PYPI-CHECK: SKIP (twine не встановлений) — але збірка успішна:"
    ls -1 dist
fi

echo "PYPI-CHECK: PASS"
