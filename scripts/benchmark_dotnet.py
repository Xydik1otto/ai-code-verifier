#!/usr/bin/env python3
"""Benchmark: aicv-dotnet (C# single-file exe) scan speed on an N-file diff.

Builds the same throwaway 1000-file git repo as scripts/benchmark.py (98%
clean, 2% with classic AI mistakes) and times the C# exe on it, so the two
implementations can be compared like-for-like.

The FIRST run on a freshly written corpus pays a one-time Windows Defender
real-time scan of every new file (~2.5 s for 1000 files) — a cost the tool
itself does not control. The benchmark therefore runs the scan --runs times
(default 3) on the SAME repo and judges by the minimum, like a warm cache in
CI. Pass --runs 1 to see the cold number.

Usage:
    python scripts/benchmark_dotnet.py                 # 1000 files, target 1 s
    python scripts/benchmark_dotnet.py --files 200 --target 5 --runs 1

The exe is resolved from $AICV_DOTNET_EXE or dotnet/artifacts/exe/aicv.exe
(see dotnet/README.md for the publish command).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTNET_DIR = PROJECT_ROOT / "dotnet"


def load_benchmark_helpers():
    """Import build_repo from the existing scripts/benchmark.py."""
    spec = importlib.util.spec_from_file_location(
        "aicv_benchmark", PROJECT_ROOT / "scripts" / "benchmark.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_repo


def resolve_exe() -> str:
    env = os.environ.get("AICV_DOTNET_EXE")
    if env:
        return env
    exe = DOTNET_DIR / "artifacts" / "exe" / "aicv.exe"
    if exe.is_file():
        return str(exe)
    sys.exit("aicv-dotnet exe not found — build it first:\n"
             "  cd dotnet && dotnet publish AiCV.Cli -c Release -r win-x64 "
             "--self-contained true -p:PublishSingleFile=true -o artifacts/exe")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--files", type=int, default=1000,
                    help="number of files in the generated diff (default 1000)")
    ap.add_argument("--target", type=float, default=1.0,
                    help="target wall time in seconds for the MIN of runs (default 1)")
    ap.add_argument("--runs", type=int, default=3,
                    help="scan runs on the same repo; the min is judged (default 3)")
    args = ap.parse_args()

    build_repo = load_benchmark_helpers()
    exe = resolve_exe()

    with tempfile.TemporaryDirectory(prefix="aicv-bench-dotnet-") as td:
        root = Path(td)
        build_repo(root, args.files)
        print(f"benchmark: generated {args.files} changed .py files in {root}")

        elapsed = []
        for i in range(args.runs):
            t0 = time.perf_counter()
            proc = subprocess.run([exe, "check", "--json"],
                                  cwd=str(root), capture_output=True, text=True)
            dt = time.perf_counter() - t0
            elapsed.append(dt)
            verdict = "FAIL" if proc.returncode == 1 else f"exit={proc.returncode}"
            try:
                verdict_json = json.loads(proc.stdout or "{}")
                n_errors = len(verdict_json.get("errors", []))
                files = verdict_json.get("files_checked", "?")
            except ValueError:
                n_errors, files = "?", "?"
            print(f"benchmark: run {i + 1}/{args.runs}: {dt:.2f}s -> {verdict} "
                  f"({files} file(s), {n_errors} error(s))")
        best = min(elapsed)
        print(f"benchmark: aicv-dotnet best of {args.runs}: {best:.2f}s")
        status = "PASS" if best <= args.target else "FAIL"
        print(f"benchmark: target {args.target}s -> {status}")
        return 0 if best <= args.target else 1


if __name__ == "__main__":
    sys.exit(main())
