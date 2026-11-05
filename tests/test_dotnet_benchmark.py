"""Benchmark smoke test for the C# port (aicv-dotnet).

Runs scripts/benchmark_dotnet.py with a small file count and a generous
target — this must stay green on slow CI machines. The full 1000-file
benchmark with the real timing is run manually/locally and recorded in the
README (see `python scripts/benchmark.py` vs
`python scripts/benchmark_dotnet.py`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
EXE = PROJECT_ROOT / "dotnet" / "artifacts" / "exe" / "aicv.exe"


@pytest.mark.skipif(not EXE.is_file(),
                    reason="aicv-dotnet exe not built (see dotnet/README.md)")
def test_dotnet_benchmark_200_files():
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "benchmark_dotnet.py"),
         "--files", "200", "--target", "10"],
        capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    assert "generated 200 changed .py files" in out, out
    assert "target 10.0s -> PASS" in out, out
    # the synthetic corpus is ~2% bad -> the scan must still FAIL (find errors)
    assert "-> FAIL" in out, out
