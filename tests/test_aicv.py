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
from aicv.engine import exit_code, load_config, render_sarif, run_checks, severity_counts
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


# ---------- v0.2: new secret rules + remote-exec patterns ----------

def test_new_secret_patterns_detected():
    fs = check("exec_patterns.py")
    secrets = findings_by_rule(fs, "hardcoded_secret")
    labels = " ".join(f["message"] for f in secrets)
    assert "Slack token" in labels, secrets
    assert "Bearer token" in labels, secrets
    assert "AWS access key id" in labels, secrets


def test_remote_exec_curl_pipe_sh():
    fs = check("exec_patterns.py")
    remote = findings_by_rule(fs, "remote_exec")
    assert any(f["line"] == 13 for f in remote), remote  # curl | sh line


def test_subprocess_shell_true_flagged():
    fs = check("exec_patterns.py")
    remote = findings_by_rule(fs, "remote_exec")
    assert any("shell=True" in f["message"] for f in remote), remote


def test_remote_exec_clean_code_not_flagged():
    fs = check("clean_code.py")
    assert findings_by_rule(fs, "remote_exec") == []


def test_remote_exec_rule_toggleable():
    disabled = dict(DEFAULT_RULES, remote_exec=False)
    fs = check("exec_patterns.py", disabled)
    assert findings_by_rule(fs, "remote_exec") == []
    assert findings_by_rule(fs, "hardcoded_secret")  # other rules unaffected


# ---------- v0.2: py_compile syntax gate ----------

def test_py_compile_clean_file_no_finding():
    fs = check("clean_code.py")
    assert findings_by_rule(fs, "syntax_error") == []


def test_py_compile_syntax_error_message():
    from aicv.checks import check_py_compile
    fs = check_py_compile(FIXTURES / "syntax_error.py", "syntax_error.py")
    assert len(fs) == 1
    assert fs[0]["rule"] == "syntax_error"
    assert "py_compile" in fs[0]["message"]
    assert fs[0]["line"] >= 1, "py_compile error must carry a line number"


def test_py_compile_syntax_gate_toggleable():
    disabled = dict(DEFAULT_RULES, syntax_error=False)
    fs = check("syntax_error.py", disabled)
    assert findings_by_rule(fs, "syntax_error") == []


# ---------- v0.3: SARIF output ----------

def _sample_findings():
    return [
        {"rule": "dangerous_call", "severity": "error", "file": "a\\b.py", "line": 7,
         "message": "Use of 'eval()'"},
        {"rule": "ruff:F401", "severity": "warning", "file": "a/b.py", "line": 2,
         "message": "unused import"},
    ]


def test_sarif_structure():
    doc = render_sarif(_sample_findings())
    assert doc["version"] == "2.1.0"
    assert doc["$schema"].endswith(".json")
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "aicv"
    assert {r["id"] for r in run["tool"]["driver"]["rules"]} >= {"dangerous_call"}
    assert len(run["results"]) == 2
    by_rule = {r["ruleId"]: r for r in run["results"]}
    res = by_rule["dangerous_call"]
    assert set(res) == {"ruleId", "level", "message", "locations"}
    assert res["level"] == "error"
    assert res["message"]["text"] == "Use of 'eval()'"
    assert by_rule["ruff:F401"]["level"] == "warning"


def test_sarif_locations_and_ruff_passthrough():
    doc = render_sarif(_sample_findings())
    by_rule = {r["ruleId"]: r for r in doc["runs"][0]["results"]}
    loc = by_rule["dangerous_call"]["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "a/b.py"  # forward slashes
    assert loc["region"]["startLine"] == 7
    assert "ruff:" in "".join(by_rule), "ruff rule ids must be preserved"


def test_cli_sarif_file_written(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    rc = main(["check", "--no-ruff", "--sarif"])
    assert rc == 1
    sarif_path = git_repo / ".aicv" / "latest.sarif"
    assert sarif_path.is_file()
    doc = json.loads(sarif_path.read_text(encoding="utf-8"))
    results = doc["runs"][0]["results"]
    assert len(results) >= 4
    assert all(r["level"] in {"error", "warning", "note"} for r in results)


# ---------- v0.3: aicv init ----------

def test_init_generates_valid_config(git_repo, capsys):
    rc = main(["init"])
    out = capsys.readouterr().out
    assert rc == 0 and "wrote" in out
    cfg = git_repo / ".aicv.toml"
    assert cfg.is_file()
    import tomllib
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    rules = data["rules"]
    assert rules["remote_exec"] is True
    assert rules["dead_import"] is False
    # generated config must be loadable by the engine
    loaded = load_config(git_repo)
    assert loaded == rules


def test_init_refuses_overwrite(git_repo, capsys):
    main(["init"])
    capsys.readouterr()
    (git_repo / ".aicv.toml").write_text("[rules]\ndead_import = true\n")
    rc = main(["init"])
    out = capsys.readouterr().out
    assert rc == 2 and "--force" in out
    assert "dead_import = true" in (git_repo / ".aicv.toml").read_text(encoding="utf-8")
    rc2 = main(["init", "--force"])
    assert rc2 == 0
    assert "dead_import = false" in (git_repo / ".aicv.toml").read_text(encoding="utf-8")


# ---------- v0.3: aicv verdict (agent-loop marker) ----------

def test_verdict_fail_block(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    rc = main(["verdict", "--no-ruff"])
    out = capsys.readouterr().out
    assert rc == 1
    assert out.startswith("=== AICV VERDICT: FAIL | target=diff HEAD | files=1 errors=")
    assert "[ERROR] bad.py:" in out
    assert out.rstrip().endswith("=== AICV VERDICT END ===")
    assert not (git_repo / ".aicv" / "latest.md").exists(), \
        "verdict must not write report artifacts"


def test_verdict_summary_single_line(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    rc = main(["verdict", "--no-ruff", "--summary"])
    out = capsys.readouterr().out
    assert rc == 1
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1, lines
    assert lines[0].startswith("=== AICV VERDICT: FAIL |")
    assert "errors=4" in lines[0]


def test_verdict_pass_and_empty(git_repo, capsys):
    shutil.copy(FIXTURES / "clean_code.py", git_repo / "clean.py")
    rc = main(["verdict", "--no-ruff"])
    out = capsys.readouterr().out
    assert rc == 0 and "AICV VERDICT: PASS" in out
    # empty repo state -> PASS with files=0
    (git_repo / "clean.py").unlink()
    rc2 = main(["verdict", "--no-ruff"])
    out2 = capsys.readouterr().out
    assert rc2 == 0 and "files=0 errors=0 warnings=0" in out2


# ---------- v0.4: baseline mode ----------

def test_baseline_roundtrip_and_apply():
    findings = [
        {"rule": "dangerous_call", "severity": "error", "file": "a.py", "line": 5,
         "message": "m1"},
        {"rule": "shell_exec", "severity": "error", "file": "b.py", "line": 9,
         "message": "m2"},
    ]
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        from aicv.engine import apply_baseline, load_baseline, save_baseline
        save_baseline(root, findings)
        keys = load_baseline(root)
        assert keys is not None and len(keys) == 2
        # identical findings -> all suppressed
        assert apply_baseline(findings, keys) == []
        # a NEW finding (different rule) survives
        new = [dict(findings[0], rule="hardcoded_secret")]
        assert apply_baseline(findings + new, keys) == new
        # line drift makes it a new finding
        drifted = [dict(findings[0], line=6)]
        assert apply_baseline(findings + drifted, keys) == drifted


def test_load_baseline_missing_returns_none(tmp_path):
    from aicv.engine import load_baseline
    assert load_baseline(tmp_path) is None


def test_baseline_corrupt_file_returns_none(tmp_path):
    from aicv.engine import load_baseline
    (tmp_path / ".aicv").mkdir()
    (tmp_path / ".aicv" / "baseline.json").write_text("not json{", encoding="utf-8")
    assert load_baseline(tmp_path) is None


def test_cli_baseline_then_check_passes_on_known_findings(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    rc = main(["baseline", "--no-ruff"])
    out = capsys.readouterr().out
    assert rc == 0 and "recorded" in out
    assert (git_repo / ".aicv" / "baseline.json").is_file()
    capsys.readouterr()
    # same findings again -> all known -> PASS
    rc2 = main(["check", "--no-ruff", "--baseline"])
    out2 = capsys.readouterr().out
    assert rc2 == 0, out2
    assert "known finding(s) suppressed" in out2
    assert "0 new" in out2


def test_cli_check_baseline_fails_only_on_new_finding(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    main(["baseline", "--no-ruff"])
    capsys.readouterr()
    # a NEW bad file with a finding not in the baseline
    (git_repo / "new_bad.py").write_text("import os\nos.system('ls ' + user_input)\n")
    rc = main(["check", "--no-ruff", "--baseline"])
    payload = None
    out = capsys.readouterr().out
    assert rc == 1
    assert "new_bad.py" in out
    assert "bad.py" not in out.replace("new_bad.py", ""), \
        "baseline findings must not be reported individually"


def test_cli_check_baseline_without_baseline_file(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    rc = main(["check", "--no-ruff", "--baseline"])
    capsys.readouterr()
    assert rc == 2, "--baseline without a recorded baseline must fail with usage error"


# ---------- v0.4: PR annotations (aicv ci --annotate) ----------

def test_render_annotations_format_and_escaping():
    from aicv.engine import render_annotations
    findings = [
        {"rule": "dangerous_call", "severity": "error", "file": "a\\b.py", "line": 7,
         "message": "Use of 'eval()' — 100% bad\nsecond line"},
        {"rule": "dead_import", "severity": "warning", "file": "a/b.py", "line": 2,
         "message": "unused import"},
        {"rule": "style", "severity": "info", "file": "c.py", "line": 3,
         "message": "note"},
    ]
    lines = render_annotations(findings)
    # sorted by (file, line, rule): a/b.py line 2 first, then line 7, then c.py
    assert lines[1] == ("::error file=a/b.py,line=7::dangerous_call: "
                        "Use of 'eval()' — 100%25 bad%0Asecond line")
    assert lines[0] == "::warning file=a/b.py,line=2::dead_import: unused import"
    assert lines[2] == "::notice file=c.py,line=3::style: note"


def test_cli_ci_annotate_prints_workflow_commands(git_repo, capsys, monkeypatch):
    import subprocess as sp
    base = sp.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(git_repo),
                  capture_output=True, text=True).stdout.strip()
    sp.run(["git", "checkout", "-q", "-b", "feature"], cwd=str(git_repo), check=True)
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    sp.run(["git", "add", "-A"], cwd=str(git_repo), check=True)
    sp.run(["git", "-c", "user.name=t", "-c", "user.email=t@l", "commit", "-qm", "feat"],
           cwd=str(git_repo), check=True)
    monkeypatch.setenv("GITHUB_BASE_REF", base)
    rc = main(["ci", "--no-ruff", "--annotate"])
    out = capsys.readouterr().out
    assert rc == 1
    anns = [ln for ln in out.splitlines() if ln.startswith("::")]
    assert anns, "must emit at least one workflow command"
    assert any(ln.startswith("::error file=bad.py,line=") for ln in anns)
    assert any("(dangerous_call)" in ln or "dangerous_call" in ln for ln in anns)
    # every annotation line must be well-formed: ::LEVEL file=...,line=...::msg
    for ln in anns:
        assert ln.count("::") >= 2
        assert "file=" in ln and "line=" in ln


# ---------- v0.4: TODO/FIXME detector (warning) ----------

def test_todo_fixme_detected_as_warning():
    fs = check("todo_code.py")
    todos = findings_by_rule(fs, "todo_fixme")
    # line 15 has `# aicv: ignore` -> suppressed; TODO (line 1) and FIXME (line 9) remain
    assert len(todos) == 2, todos
    assert all(f["severity"] == "warning" for f in todos)
    assert {f["line"] for f in todos} == {1, 9}
    assert exit_code(fs) == 0, "todo_fixme is a warning — must not fail the run"


def test_todo_fixme_toggleable():
    disabled = dict(DEFAULT_RULES, todo_fixme=False)
    fs = check("todo_code.py", disabled)
    assert findings_by_rule(fs, "todo_fixme") == []


def test_todo_fixme_runs_on_js_ts():
    from aicv.checks import check_js_ts_file
    p = FIXTURES / "todo_code.py"  # checker is text-based; reuse fixture text
    fs = check_js_ts_file(p, "todo.js", DEFAULT_RULES)
    assert findings_by_rule(fs, "todo_fixme")


def test_rules_registry_contains_todo_fixme():
    from aicv.checks import RULES
    assert RULES["todo_fixme"]["default"] is True
    assert RULES["todo_fixme"]["severity"] == "warning"


# ---------- v0.4: severity per rule ----------

def test_rules_have_severity_defaults():
    from aicv.checks import RULES
    for rid, spec in RULES.items():
        assert spec.get("severity") in {"error", "warning", "info"}, rid


def test_severity_defaults_error_for_security_rules():
    from aicv.checks import RULES
    for rid in ("dangerous_call", "shell_exec", "remote_exec",
                "hardcoded_secret", "sql_string_format", "syntax_error"):
        assert RULES[rid]["severity"] == "error", rid


def test_severity_override_demotes_to_warning(tmp_path):
    from aicv.engine import load_severities
    (tmp_path / ".aicv.toml").write_text('[severity]\ndangerous_call = "warning"\n')
    sev = load_severities(tmp_path)
    assert sev == {"dangerous_call": "warning"}  # only explicit overrides
    (tmp_path / "only_eval.py").write_text("result = eval('1 + 1')\n")
    findings = run_checks(tmp_path, [tmp_path / "only_eval.py"], DEFAULT_RULES,
                          severities=sev)
    dc = findings_by_rule(findings, "dangerous_call")
    assert dc and all(f["severity"] == "warning" for f in dc)
    assert exit_code(findings) == 0, "demoted rule must no longer fail the run"
    # untouched rules keep their built-in per-finding severity
    findings2 = run_checks(tmp_path, [FIXTURES / "bad_code.py"], DEFAULT_RULES,
                           severities=sev)
    assert exit_code(findings2) == 1  # other rules still error


def test_severity_no_config_keeps_builtin_finding_severities(tmp_path):
    # shell_exec fires as warning (bare-string subprocess) AND as error
    # (os.system). Without an explicit [severity] entry the built-in
    # per-finding severities must stay untouched.
    from aicv.engine import load_severities
    assert load_severities(tmp_path) == {}
    (tmp_path / "mixed.py").write_text(
        "import subprocess\n"
        "subprocess.run('ls -la')  # bare string -> builtin warning\n")
    findings = run_checks(tmp_path, [tmp_path / "mixed.py"], DEFAULT_RULES)
    shell = findings_by_rule(findings, "shell_exec")
    assert shell and all(f["severity"] == "warning" for f in shell)
    assert exit_code(findings) == 0


def test_severity_override_promotes_to_error_and_fails(tmp_path):
    from aicv.engine import load_severities
    (tmp_path / ".aicv.toml").write_text('[severity]\ndead_import = "error"\n')
    sev = load_severities(tmp_path)
    findings = run_checks(tmp_path, [FIXTURES / "dead_import_code.py"],
                          dict(DEFAULT_RULES, dead_import=True), severities=sev)
    di = findings_by_rule(findings, "dead_import")
    assert di and all(f["severity"] == "error" for f in di)
    assert exit_code(findings) == 1


def test_severity_override_invalid_value_and_unknown_rule_ignored(tmp_path):
    from aicv.engine import load_severities
    (tmp_path / ".aicv.toml").write_text(
        '[severity]\ndangerous_call = "banana"\nnot_a_rule = "info"\n')
    assert load_severities(tmp_path) == {}


def test_severity_info_level_in_sarif():
    doc = render_sarif([{"rule": "todo_fixme", "severity": "info", "file": "a.py",
                         "line": 1, "message": "m"}])
    assert doc["runs"][0]["results"][0]["level"] == "note"


def test_cli_severity_config_affects_exit_code(git_repo, capsys):
    shutil.copy(FIXTURES / "bad_code.py", git_repo / "bad.py")
    (git_repo / ".aicv.toml").write_text(
        "[severity]\n"
        'hardcoded_secret = "warning"\n'
        'shell_exec = "warning"\n'
        'sql_string_format = "warning"\n'
        'dangerous_call = "warning"\n')
    rc = main(["check", "--no-ruff"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "0 error(s)" in out


def test_init_generates_severity_section(git_repo, capsys):
    from aicv.engine import load_severities
    main(["init"])
    capsys.readouterr()
    import tomllib
    data = tomllib.loads((git_repo / ".aicv.toml").read_text(encoding="utf-8"))
    sev = data["severity"]
    assert sev == {}, "generated [severity] must be commented out by default"
    text = (git_repo / ".aicv.toml").read_text(encoding="utf-8")
    assert '# dangerous_call = "error"' in text
    assert '# dead_import = "warning"' in text
    # generated file carries no active overrides -> builtin severities intact
    assert load_severities(git_repo) == {}


# ---------- v0.4: docs/rules.md автогенерація ----------

def test_docs_rules_md_in_sync_with_rules_registry():
    from aicv.checks import RULES
    p = PROJECT_ROOT / "docs" / "rules.md"
    assert p.is_file(), "docs/rules.md must exist (run scripts/gen_rules.py)"
    text = p.read_text(encoding="utf-8")
    assert "scripts/gen_rules.py" in text, "must carry the generation notice"
    for rid, spec in RULES.items():
        assert f"`{rid}`" in text, f"rule {rid} missing from docs/rules.md"
        assert spec["name"] in text, f"description of {rid} missing from docs/rules.md"


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
