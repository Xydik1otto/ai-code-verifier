"""C# (.cs) scanning tests — Python-side regex fallback.

Python has no Roslyn: the C#/.NET port (dotnet/AiCV.Core) parses .cs with a
real Roslyn AST and is the authoritative implementation for the language
(exact row/col, comment/string-proof). These tests cover the Python fallback:
same rule ids, same fixtures. The regex-vs-AST parity lives in
tests/test_dotnet_parity.py.
"""
from pathlib import Path

from aicv.checks import CS_EXT, check_cs_file

FIXTURES = Path(__file__).parent / "fixtures"

ENABLED = {
    "dangerous_call": True, "shell_exec": True, "remote_exec": True,
    "hardcoded_secret": True, "sql_string_format": True,
    "dead_import": False, "syntax_error": True, "todo_fixme": True,
}


def check(rel: str, enabled=None):
    return check_cs_file(FIXTURES / rel, rel, enabled or ENABLED)


def findings_by_rule(findings, rule):
    return [f for f in findings if f["rule"] == rule]


# ---------- heuristics on known-bad fixture ----------

def test_bad_cs_detects_shell_exec():
    fs = check("bad_code.cs")
    assert findings_by_rule(fs, "shell_exec"), "Process.Start with a shell must be flagged"


def test_bad_cs_detects_dangerous_call():
    fs = check("bad_code.cs")
    assert findings_by_rule(fs, "dangerous_call"), "CSharpScript.EvaluateAsync must be flagged"


def test_bad_cs_detects_interpolated_sql():
    fs = check("bad_code.cs")
    sql = findings_by_rule(fs, "sql_string_format")
    assert len(sql) >= 3, "interpolated / string.Format / concatenated SQL must be flagged"


def test_bad_cs_detects_hardcoded_secret():
    fs = check("bad_code.cs")
    assert findings_by_rule(fs, "hardcoded_secret")


def test_bad_cs_detects_todo():
    fs = check("bad_code.cs")
    assert findings_by_rule(fs, "todo_fixme")


def test_bad_secrets_cs():
    fs = check("bad_secrets.cs")
    secrets = findings_by_rule(fs, "hardcoded_secret")
    lines = {f["line"] for f in secrets}
    assert {8, 9} <= lines, f"authToken (line 8) and Password (line 9) must fire: {lines}"


def test_clean_cs_has_no_errors():
    fs = check("clean_code.cs")
    assert not fs, f"clean parameterized C# must produce no findings: {fs}"


def test_todo_cs():
    fs = check("todo_code.cs")
    assert len(findings_by_rule(fs, "todo_fixme")) == 2


def test_syntax_error_cs_bracket_gate():
    fs = check("syntax_error.cs")
    assert findings_by_rule(fs, "syntax_error")


def test_cs_rule_toggles_off():
    disabled = dict(ENABLED, sql_string_format=False, dangerous_call=False,
                    shell_exec=False)
    fs = check("bad_code.cs", disabled)
    assert not findings_by_rule(fs, "sql_string_format")
    assert not findings_by_rule(fs, "dangerous_call")
    assert not findings_by_rule(fs, "shell_exec")
    assert findings_by_rule(fs, "hardcoded_secret")  # untouched rule still fires


def test_cs_suppression_comment():
    """`// aicv: ignore` (all rules on the line) and per-rule ignore[]."""
    import tempfile

    src = (FIXTURES / "bad_code.cs").read_text(encoding="utf-8")
    src = src.replace(
        "// TODO: rotate the leaked key",
        "// TODO: rotate the leaked key  // aicv: ignore")
    src = src.replace(
        'var rows = $"SELECT * FROM users WHERE name={user}";',
        'var rows = $"SELECT * FROM users WHERE name={user}";  // aicv: ignore[sql_string_format]')
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sup.cs"
        p.write_text(src, encoding="utf-8")
        fs = check_cs_file(p, "sup.cs", ENABLED)
    got = {(f["rule"], f["line"]) for f in fs}
    assert ("todo_fixme", 12) not in got, "full-line ignore must suppress TODO"
    assert ("sql_string_format", 14) not in got, "per-rule ignore[] must suppress SQL"
    assert ("sql_string_format", 15) in got, "other SQL findings stay"


def test_cs_ext_registered():
    assert ".cs" in CS_EXT
