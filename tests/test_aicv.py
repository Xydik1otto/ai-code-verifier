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
