"""Tests for aicv: heuristics, engine, CLI exit codes."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).parent.parent

from aicv.checks import check_python_file
from aicv.engine import exit_code, load_config, run_checks, severity_counts
from aicv.cli import main

DEFAULT_RULES = {rid: spec["default"] for rid, spec in {
    "dangerous_call": {"default": True}, "shell_exec": {"default": True},
    "hardcoded_secret": {"default": True}, "sql_string_format": {"default": True},
    "dead_import": {"default": False}, "syntax_error": {"default": True},
}.items()}


def findings_by_rule(findings, rule):
    return [f for f in findings if f["rule"] == rule]


def check(rel: str, rules=None):
    path = FIXTURES / rel
    return check_python_file(path, rel, rules or DEFAULT_RULES)


# ---------- heuristics on known-bad fixture ----------

def test_bad_code_detects_eval_exec():
    fs = check("bad_code.py")
    rules = {f["rule"] for f in fs}
    assert "dangerous_call" in rules


def test_bad_code_detects_shell_exec():
    fs = check("bad_code.py")
    assert findings_by_rule(fs, "shell_exec"), "os.system must be flagged"


def test_bad_code_detects_hardcoded_secret():
    fs = check("bad_code.py")
    assert findings_by_rule(fs, "hardcoded_secret")


def test_bad_code_detects_sql_fstring():
    fs = check("bad_code.py")
    assert findings_by_rule(fs, "sql_string_format")


def test_clean_code_has_no_errors():
    fs = check("clean_code.py")
    assert not [f for f in fs if f["severity"] == "error"]


def test_syntax_error_detected():
    fs = check("syntax_error.py")
    assert findings_by_rule(fs, "syntax_error")


def test_dead_import_only_when_enabled():
    disabled = dict(DEFAULT_RULES, dead_import=False)
    assert findings_by_rule(check("dead_import_code.py", disabled), "dead_import") == []
    enabled = dict(DEFAULT_RULES, dead_import=True)
    assert findings_by_rule(check("dead_import_code.py", enabled), "dead_import")


def test_example_placeholder_secret_not_flagged():
    fs = check("secret_example_ok.py")
    assert findings_by_rule(fs, "hardcoded_secret") == []


# ---------- engine ----------

def test_exit_codes():
    assert exit_code([]) == 0
    assert exit_code([{"severity": "warning"}]) == 0
    assert exit_code([{"severity": "error"}]) == 1


def test_run_checks_severity_counts():
    findings = run_checks(FIXTURES.parent, [FIXTURES / "bad_code.py"], DEFAULT_RULES)
    counts = severity_counts(findings)
    assert counts["error"] >= 4
    assert exit_code(findings) == 1


def test_config_disables_rule(tmp_path):
    (tmp_path / ".aicv.toml").write_text("[rules]\nhardcoded_secret = false\n")
    cfg = load_config(tmp_path)
    assert cfg["hardcoded_secret"] is False
    assert cfg["dangerous_call"] is True
    findings = run_checks(tmp_path, [FIXTURES / "bad_code.py"], cfg)
    assert findings_by_rule(findings, "hardcoded_secret") == []


# ---------- CLI end-to-end in a scratch git repo ----------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git not available")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "user.email", "test@local")
    (tmp_path / ".gitignore").write_text(".aicv/\n__pycache__/\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_cli_clean_repo_exit_zero(git_repo, capsys):
    shutil.copy(FIXTURES / "clean_code.py", git_repo / "clean.py")
    rc = main(["check", "--no-ruff"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "0 error(s)" in out


def test_cli_bad_file_exit_one(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    rc = main(["check", "--no-ruff"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "error(s)" in out and "[ERROR]" in out


def test_cli_report_after_check(git_repo, capsys):
    shutil.copy(FIXTURES / "clean_code.py", git_repo / "clean.py")
    main(["check", "--no-ruff"])
    capsys.readouterr()
    rc = main(["report"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "aicv verification report" in out


def test_cli_report_json(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    main(["check", "--no-ruff"])
    capsys.readouterr()
    rc = main(["report", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["exit_code"] == 1
    assert payload["counts"]["error"] >= 4


def test_cli_no_changes_exit_zero(git_repo, capsys):
    rc = main(["check", "--no-ruff"])
    assert rc == 0
    assert "nothing to verify" in capsys.readouterr().out


# ---------- v0.1.0-alpha: inline suppressions ----------

def test_suppression_bare_ignore_drops_finding():
    fs = check("suppressed_code.py")
    evals = [f for f in fs if f["rule"] == "dangerous_call"]
    assert evals == [], "eval line has `# aicv: ignore` -> must be suppressed"


def test_suppression_rule_specific_only_listed_rule():
    fs = check("suppressed_code.py")
    os_system = [f for f in fs if f["line"] == 9 and f["rule"] == "shell_exec"]
    assert os_system == [], "line 9 suppresses shell_exec explicitly"


def test_suppression_unlisted_rule_still_fires():
    fs = check("suppressed_code.py")
    # line 13 has no marker -> sql_string_format must fire
    assert any(f["line"] == 13 and f["rule"] == "sql_string_format" for f in fs)
    # line 17: `# aicv: ignore[shell_exec]` -> hardcoded_secret must survive
    line17 = [f for f in fs if f["line"] == 17]
    assert [f["rule"] for f in line17] == ["hardcoded_secret"]


def test_suppression_marker_without_finding_is_harmless():
    from aicv.checks import filter_suppressed, suppression_map
    text = "x = 1  # aicv: ignore\n"
    assert suppression_map(text) == {1: "*"}
    f0 = [{"rule": "dead_import", "severity": "warning", "file": "a.py", "line": 1,
           "message": "m"}]
    assert filter_suppressed(f0, text) == []


# ---------- v0.1.0-alpha: `aicv check --json` machine verdict ----------

def test_cli_json_verdict_schema(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    rc = main(["check", "--no-ruff", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"files_checked", "errors", "exit_code"}
    assert payload["files_checked"] == 1
    assert payload["exit_code"] == rc == 1
    assert payload["errors"], "bad_code.py must produce errors"
    for e in payload["errors"]:
        assert set(e) == {"file", "line", "rule", "message"}
        assert isinstance(e["line"], int)


def test_cli_json_verdict_clean_pass(git_repo, capsys):
    shutil.copy(FIXTURES / "clean_code.py", git_repo / "clean.py")
    rc = main(["check", "--no-ruff", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload == {"files_checked": 1, "errors": [], "exit_code": 0}


def test_cli_json_suppressed_findings_not_in_verdict(git_repo, capsys):
    shutil.copy(FIXTURES / "suppressed_code.py", git_repo / "sup.py")
    rc = main(["check", "--no-ruff", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1  # unsuppressed sql finding remains
    assert not any(e["rule"] == "dangerous_call" for e in payload["errors"])
    assert any(e["rule"] == "sql_string_format" for e in payload["errors"])


# ---------- v0.1.0-alpha: pre-commit hook config validity ----------

def test_pre_commit_hooks_yaml_structure():
    p = PROJECT_ROOT / ".pre-commit-hooks.yaml"
    assert p.is_file(), ".pre-commit-hooks.yaml must exist at repo root"
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # optional dependency
        hooks = yaml.safe_load(text)
    except ImportError:
        hooks = None
    if hooks is not None:
        assert isinstance(hooks, list) and len(hooks) == 1
        h = hooks[0]
        assert h["id"] == "aicv"
        assert h["language"] == "python"
        assert h["entry"].startswith("aicv check")
        assert h["pass_filenames"] is False
    else:
        # dependency-free structural check
        assert "id: aicv" in text
        assert "language: python" in text
        assert "entry: aicv check --staged" in text
        assert "pass_filenames: false" in text


def test_pre_commit_hook_command_exits_zero_when_nothing_staged(git_repo, capsys):
    # the exact command .pre-commit-hooks.yaml runs must not block an empty commit
    rc = main(["check", "--staged", "--no-ruff"])
    assert rc == 0
    assert "nothing to verify" in capsys.readouterr().out


# ---------- v0.1.0-alpha: grouped markdown report ----------

def test_report_groups_findings_by_file(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    main(["check", "--no-ruff"])
    capsys.readouterr()
    main(["report"])
    md = capsys.readouterr().out
    assert "### `bad.py`" in md
    assert md.count("### ") == 1, "one file -> one group header"


def test_report_orders_errors_before_warnings(git_repo, capsys):
    (git_repo / "mixed.py").write_text(
        "import subprocess\n"
        "subprocess.run('ls -la')  # bare string -> warning\n"
        "eval('1 + 1')  # dynamic exec -> error\n"
    )
    main(["check", "--no-ruff"])
    capsys.readouterr()
    main(["report"])
    md = capsys.readouterr().out
    first_error = md.index("[ERROR]")
    first_warning = md.index("[WARNING]")
    assert first_error < first_warning, "errors must be listed before warnings"
    assert "**[ERROR]**" in md and "line " in md  # new grouped line format
