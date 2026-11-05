#!/usr/bin/env python3
"""Benchmark: aicv scan speed on a large N-file diff (default 1000 files).

Builds a throwaway git repo, commits an empty base, then writes N Python
files (mostly clean, ~2% with classic AI mistakes) as the "diff" and times
the real CLI (`aicv check --no-ruff`) on it. Prints elapsed seconds and the
verdict; exits 1 if the target time is exceeded.

Usage:
    python scripts/benchmark.py                 # 1000 files, target 10 s
    python scripts/benchmark.py --files 200 --target 5

Note: one subprocess is timed per run, startup included — this mirrors what
a user or an agent loop actually experiences.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CLEAN_TEMPLATE = '''"""Generated clean module {i}."""
import os


def read_config(name: str) -> str:
    return os.environ.get(name, "")


def compute(values):
    return [v * 2 for v in values if v is not None]
'''

BAD_TEMPLATE = '''"""Generated module {i} with a classic AI mistake."""
import os
import subprocess


API_KEY = "sk-live-benchmark-not-a-real-key-0001"


def run(cmd: str):
    os.system("ls " + cmd)
'''


def build_repo(root: Path, n_files: int) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=str(root), check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.name", "benchmark")
    git("config", "user.email", "benchmark@local")
    (root / ".gitignore").write_text(".aicv/\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    for i in range(n_files):
        # ~2% of files carry classic findings — realistic AI-output mix
        body = BAD_TEMPLATE.format(i=i) if i % 50 == 0 else CLEAN_TEMPLATE.format(i=i)
        (root / f"mod_{i:05d}.py").write_text(body, encoding="utf-8")


def resolve_cli() -> list:
    exe = shutil.which("aicv")
    if exe:
        return [exe]
    # editable install present but entry point not on PATH -> module fallback
    return [sys.executable, "-m", "aicv.cli"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", type=int, default=1000,
                    help="number of files in the generated diff (default 1000)")
    ap.add_argument("--target", type=float, default=10.0,
                    help="target wall time in seconds (default 10)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="aicv-bench-") as td:
        root = Path(td)
        build_repo(root, args.files)
        print(f"benchmark: generated {args.files} changed .py files in {root}")

        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent))
        t0 = time.perf_counter()
        proc = subprocess.run([*resolve_cli(), "check", "--no-ruff"],
                              cwd=str(root), capture_output=True, text=True,
                              env=env)
        elapsed = time.perf_counter() - t0
        out = (proc.stdout or "") + (proc.stderr or "")
        verdict = "FAIL" if proc.returncode == 1 else f"exit={proc.returncode}"
        head = next((ln for ln in out.splitlines() if ln.startswith("aicv:")), "")
        print(f"benchmark: aicv check finished in {elapsed:.2f}s -> {verdict}")
        if head:
            print(f"benchmark: {head}")
        status = "PASS" if elapsed <= args.target else "FAIL"
        print(f"benchmark: target {args.target}s -> {status}")
        return 0 if elapsed <= args.target else 1


if __name__ == "__main__":
    sys.exit(main())
