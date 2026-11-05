#!/usr/bin/env bash
# Smoke-тест aicv: перевіряє, що CLI справді ловить відомо-бад-код
# і пропускає чистий. Виводить SMOKE: PASS або SMOKE: FAIL.
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PYTHON="${PYTHON:-python}"

tmp="$(mktemp -d)"
# git-bash/MSYS: native git.exe can't use /tmp/... paths — convert to a
# Windows-mixed path when cygpath is available (no-op on real Unix).
command -v cygpath >/dev/null 2>&1 && tmp="$(cygpath -m "$tmp")"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
git -C "$tmp" -c user.name=smoke -c user.email=smoke@local commit -q --allow-empty -m init

fail() { echo "SMOKE: FAIL — $1"; exit 1; }

# 1) відомо-бад-файл -> exit 1 + [ERROR] у виводі
cp tests/fixtures/bad_code.py "$tmp/bad.py"
out="$(cd "$tmp" && PYTHONPATH="$ROOT" $PYTHON -m aicv.cli check --no-ruff 2>&1)"
rc=$?
[ $rc -eq 1 ] || fail "bad_code.py: очікували exit 1, отримали $rc"
echo "$out" | grep -q "\[ERROR\]" || fail "bad_code.py: у виводі немає [ERROR]"
echo "$out" | grep -q "dangerous_call" || fail "bad_code.py: не знайдено dangerous_call"

# 2) чистий файл -> exit 0
rm "$tmp/bad.py"
cp tests/fixtures/clean_code.py "$tmp/clean.py"
out="$(cd "$tmp" && PYTHONPATH="$ROOT" $PYTHON -m aicv.cli check --no-ruff 2>&1)"
rc=$?
[ $rc -eq 0 ] || fail "clean_code.py: очікували exit 0, отримали $rc"
echo "$out" | grep -q "0 error(s)" || fail "clean_code.py: очікували '0 error(s)'"

# 3) verdict marker присутній
echo "$out" | grep -q "AICV" || true  # verdict окремо:
out="$(cd "$tmp" && PYTHONPATH="$ROOT" $PYTHON -m aicv.cli verdict --no-ruff --summary 2>&1)"
echo "$out" | grep -q "=== AICV VERDICT: PASS" || fail "verdict: очікували PASS marker"

echo "SMOKE: PASS"
