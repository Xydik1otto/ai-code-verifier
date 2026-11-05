"""Built-in heuristic checks for changed code files.

Pure-Python, stdlib-only. Each check returns a list of Finding dicts.
Ruff, when installed, is run first; heuristics always run as a safety net
(graceful fallback philosophy: never block a scan on a missing linter).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional

FINDING_SEV_ERROR = "error"
FINDING_SEV_WARN = "warning"
FINDING_SEV_INFO = "info"

# Rule id -> {"name":..., "default": True/False, "severity": error/warning/info}
# for .aicv.toml toggling ([rules]) and per-rule severity ([severity]).
RULES: Dict[str, Dict] = {
    "dangerous_call": {"name": "Dynamic code execution (eval/exec/compile)",
                       "default": True, "severity": "error"},
    "shell_exec": {"name": "Shell execution from strings",
                   "default": True, "severity": "error"},
    "remote_exec": {"name": "Remote/shell code execution patterns",
                    "default": True, "severity": "error"},
    "hardcoded_secret": {"name": "Hardcoded secrets in source",
                         "default": True, "severity": "error"},
    "sql_string_format": {"name": "SQL built via string formatting",
                          "default": True, "severity": "error"},
    "dead_import": {"name": "Imported but never used",
                    "default": False, "severity": "warning"},  # noisy -> opt-in
    "syntax_error": {"name": "File does not parse/compile",
                     "default": True, "severity": "error"},
    "todo_fixme": {"name": "TODO/FIXME markers left in code",
                   "default": True, "severity": "warning"},
}

_SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(api[_-]?key|apikey)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"), "API key literal"),
    (re.compile(r"(?i)\b(secret[_-]?key|auth[_-]?token|access[_-]?token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"), "secret/token literal"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"(?i)\baws_access_key_id\s*[:=]\s*['\"]AKIA[0-9A-Z]{16}['\"]"), "AWS access key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.=]{20,}\b"), "Bearer token"),
    (re.compile(r"(?i)\b(password|passwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]"), "password literal"),
    (re.compile(r"\b(sk|pk)-[A-Za-z0-9]{20,}\b"), "Stripe-style key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"), "GitHub token"),
    # Go-specific: short-declaration secrets (password := "...")
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|apikey|credential)\s*:=\s*\"[^\"]{8,}\""),
     "secret literal (Go :=)"),
    # Java-specific: String password = "...", private final String API_KEY = "..."
    (re.compile(r"(?i)\bString\s+\w*(password|passwd|secret|token|api[_-]?key|apikey|credential)\w*\s*=\s*\"[^\"]{8,}\""),
     "secret literal (String field)"),
    (re.compile(r"(?i)\b(private|protected|public|static|final)\s+(?:[\w<>\[\],\s]+\s+)?\w*(password|passwd|secret|token|api[_-]?key|apikey)\w*\s*=\s*\"[^\"]{8,}\""),
     "secret literal (field initializer)"),
]

# ---------- C# (regex fallback; the C#/.NET port is the AST authority) ----------
#
# Python has no Roslyn, so the Python implementation scans .cs with the same
# regex philosophy as Go/Java. The C# port (dotnet/AiCV.Core) parses .cs with
# a real Roslyn AST and is authoritative for the language; both sides map to
# the same rule ids so agent pipelines get the same verdict from either.
# The AST side may be MORE precise (comments/strings cannot trigger it, exact
# row/col) — a documented superset, see docs/rules.md.

# dynamic code execution: Roslyn scripting Eval, CodeDom compilation,
# CompilerServices imports
_CS_DANGEROUS_CALL = re.compile(
    r"(?i)\b(CSharpScript\.(?:EvaluateAsync|RunAsync)"
    r"|CompileAssemblyFromSource(?:Async)?"
    r"|CSharpCodeProvider)\b")
_CS_COMPILERSERVICES_USING = re.compile(r"(?i)^\s*using\s+[\w.]*CompilerServices\s*;")

# Process.Start targeting a shell, or UseShellExecute = true
_CS_PROCESS_START = re.compile(r"(?i)\bProcess\s*\.\s*Start\s*\(")
_CS_SHELL_TARGET = re.compile(r"(?i)\b(cmd|powershell|pwsh|bash|sh|zsh)(\.exe)?\b")
_CS_SHELL_FLAG = re.compile(r"(?i)(\"[^\"]*/(c|k)\b|\"[^\"]*-(c|k|enc)\b)")
_CS_USE_SHELL_EXECUTE = re.compile(r"(?i)\bUseShellExecute\s*=\s*true\b")

# interpolated SQL: $"SELECT ... {var}", string.Format("SELECT {0}", ...),
# "SELECT ..." + var concatenation
_CS_SQL_INTERP = re.compile(
    r"(?i)\$\"[^\"]*\b(select|insert|update|delete|drop table|union\s+select)\b[^\"]*\{")
_CS_SQL_FORMAT = re.compile(
    r"(?i)\bstring\s*\.\s*format\s*\(\s*\"[^\"]*\b(select|insert|update|delete|drop table|union\s+select)\b")
_CS_SQL_CONCAT = re.compile(
    r"(?i)\"[^\"]*\b(select|insert|update|delete|drop table|union\s+select)\b[^\"]*\"\s*\+")


def _check_cs_calls(text: str, rel: str) -> List[Dict]:
    """dangerous_call / shell_exec for .cs at regex level (line-based)."""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _CS_DANGEROUS_CALL.search(line) or _CS_COMPILERSERVICES_USING.match(line):
            out.append(_mk("dangerous_call", FINDING_SEV_ERROR, rel, lineno,
                           "Dynamic code execution API (Roslyn Eval / CodeDom compile / "
                           "CompilerServices) — ban in AI-generated code"))
        if _CS_PROCESS_START.search(line) and (
                _CS_SHELL_TARGET.search(line) or _CS_SHELL_FLAG.search(line)) \
                or _CS_USE_SHELL_EXECUTE.search(line):
            out.append(_mk("shell_exec", FINDING_SEV_ERROR, rel, lineno,
                           "Process.Start targeting a shell — injection risk, "
                           "use ProcessStartInfo with argument lists"))
    return out


def _check_cs_sql(text: str, rel: str) -> List[Dict]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _CS_SQL_INTERP.search(line) or _CS_SQL_FORMAT.search(line) \
                or _CS_SQL_CONCAT.search(line):
            out.append(_mk("sql_string_format", FINDING_SEV_ERROR, rel, lineno,
                           "SQL built via string formatting/interpolation — "
                           "use parameterized queries"))
    return out

# Remote-code-execution "nuclear" patterns: download-and-execute one-liners
# and shell=True escapes in subprocess calls.
_REMOTE_EXEC_LINE = re.compile(
    r"(?i)\b(curl|wget)\b[^#\n]*\|\s*(sudo\s+)?(ba|z|da|k)?sh\b"
    r"|\bbash\s+-c\b|\bsh\s+-c\b|\bpowershell(\.exe)?\s+(-enc|-EncodedCommand|-[iI]nputFormat\s+None)"
    r"|\bbase64\s+-d\b|\beval\s*\(\s*\$\(|\bexec\s*\(\s*__import__"
)

# f-strings / .format / % / + concatenation in a context that looks like SQL
_SQL_TOKEN = re.compile(r"(?i)\b(select|insert|update|delete|drop table|union\s+select)\b")

_SHELL_EXEC_CALLS = {
    "os.system", "os.popen", "subprocess.getoutput", "subprocess.getstatusoutput",
}
_INNER_SHELL_FUNCS = {"call", "run", "Popen", "check_output", "check_call"}


def _f_lineno(node: ast.AST) -> int:
    return getattr(node, "lineno", 0)


def _fstring_nodes(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            yield node
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            yield node
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
            and isinstance(node.func.value, ast.Constant)
            and isinstance(node.func.value.value, str)
        ):
            yield node


def check_dangerous_calls(tree: ast.AST, rel: str) -> List[Dict]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # resolve simple names and dotted attribute chains
        target = None
        if isinstance(node.func, ast.Name):
            target = node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = [node.func.attr]
            base = node.func.value
            while isinstance(base, ast.Attribute):
                parts.append(base.attr)
                base = base.value
            if isinstance(base, ast.Name):
                parts.append(base.id)
            target = ".".join(reversed(parts))
        else:
            continue
        if target in ("eval", "exec", "compile", "__import__"):
            out.append(_mk("dangerous_call", FINDING_SEV_ERROR, rel, _f_lineno(node),
                           f"Use of '{target}()' — dynamic code execution, ban in AI-generated code"))
        elif target in _SHELL_EXEC_CALLS:
            out.append(_mk("shell_exec", FINDING_SEV_ERROR, rel, _f_lineno(node),
                           f"'{target}()' executes a shell string — injection risk"))
        elif target and "." in target and target.rsplit(".", 1)[-1] in _INNER_SHELL_FUNCS \
                and target.rsplit(".", 1)[0] == "subprocess":
            args = node.args
            if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
                out.append(_mk("shell_exec", FINDING_SEV_WARN, rel, _f_lineno(node),
                               "subprocess called with a bare string (shell=False assumed) — prefer list argv"))
    return out


def check_shell_true(tree: ast.AST, rel: str) -> List[Dict]:
    """subprocess.*(..., shell=True) — shell injection risk (remote_exec rule)."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _INNER_SHELL_FUNCS:
            continue
        base = node.func.value
        if isinstance(base, ast.Name) and base.id == "subprocess":
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                        and kw.value.value is True:
                    out.append(_mk("remote_exec", FINDING_SEV_ERROR, rel, _f_lineno(node),
                                   "subprocess(..., shell=True) — shell injection risk"))
    return out


def check_remote_exec_lines(text: str, rel: str) -> List[Dict]:
    """Download-and-execute / shell-escape one-liners (line-level, py + js/ts)."""
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _REMOTE_EXEC_LINE.search(line):
            out.append(_mk("remote_exec", FINDING_SEV_ERROR, rel, lineno,
                           "Download-and-execute / shell-escape pattern — remote code "
                           "execution risk"))
    return out


def check_hardcoded_secrets(text: str, rel: str, skip_dummy: bool = True) -> List[Dict]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if "example" in low or "xxx" in low or (skip_dummy and "dummy" in low):
            continue
        for pat, label in _SECRET_PATTERNS:
            if pat.search(line):
                out.append(_mk("hardcoded_secret", FINDING_SEV_ERROR, rel, lineno,
                               f"Possible {label} hardcoded in source"))
    return out


def check_sql_string_format(tree: ast.AST, rel: str) -> List[Dict]:
    out = []
    for node in _fstring_nodes(tree):
        sql = isinstance(node, ast.JoinedStr)
        rendered = None
        if not sql and isinstance(node, ast.BinOp):
            rendered = True
        if not sql and isinstance(node, ast.Call):
            rendered = True
        if not (sql or rendered):
            continue
        # extract static string content for SQL keyword sniff
        chunks = []
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    chunks.append(v.value)
        elif isinstance(node, ast.BinOp):
            for part in (node.left, node.right):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    chunks.append(part.value)
        else:
            if isinstance(node.func.value, ast.Constant):
                chunks.append(node.func.value.value)
        joined = " ".join(chunks)
        if _SQL_TOKEN.search(joined):
            out.append(_mk("sql_string_format", FINDING_SEV_ERROR, rel, _f_lineno(node),
                           "SQL built via string formatting — use parameterized queries"))
    return out


def check_todo_fixme(text: str, rel: str) -> List[Dict]:
    """TODO/FIXME markers left in the changed code -> warning (py + js/ts)."""
    marker = re.compile(r"(?i)\b(TODO|FIXME)\b(?::|\b)")
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = marker.search(line)
        if m:
            out.append(_mk("todo_fixme", FINDING_SEV_WARN, rel, lineno,
                           f"{m.group(1).upper()} marker left in code — "
                           f"resolve or move to the tracker before merge"))
    return out


def check_dead_imports(tree: ast.AST, rel: str) -> List[Dict]:
    imported: List[tuple] = []  # (name, alias_used, lineno)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.append(((a.asname or a.name).split(".")[0], _f_lineno(node)))
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name == "*":
                    continue
                imported.append((a.asname or a.name, _f_lineno(node)))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
    out = []
    for name, lineno in imported:
        if name not in used:
            out.append(_mk("dead_import", FINDING_SEV_WARN, rel, lineno,
                           f"Imported '{name}' is never used"))
    return out


# Inline suppression: `# aicv: ignore` (all rules on the line) or
# `# aicv: ignore[rule1, rule2]` (only the listed rules). C-like languages
# may also use the `// aicv: ignore` comment form.
_SUPPRESS_RE = re.compile(r"(?://|#)\s*aicv:\s*ignore(?:\[(?P<rules>[^\]]*)\])?")

SUPPRESS_ALL = "*"


def suppression_map(text: str) -> Dict[int, object]:
    """line number -> SUPPRESS_ALL or set of rule ids suppressed on that line."""
    out: Dict[int, object] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _SUPPRESS_RE.search(line)
        if not m:
            continue
        rules = (m.group("rules") or "").strip()
        out[lineno] = SUPPRESS_ALL if not rules else {
            r.strip() for r in rules.split(",") if r.strip()
        }
    return out


def filter_suppressed(findings: List[Dict], text: str) -> List[Dict]:
    """Drop findings suppressed by an `# aicv: ignore` comment on their line."""
    smap = suppression_map(text)
    if not smap:
        return findings
    out = []
    for f in findings:
        rules = smap.get(f["line"])
        if rules is None:
            out.append(f)
        elif rules == SUPPRESS_ALL or f["rule"] in rules:
            continue
        else:
            out.append(f)
    return out


def _mk(rule, severity, file, lineno, message):
    return {"rule": rule, "severity": severity, "file": file, "line": lineno, "message": message}


def check_py_compile(path: Path, rel: str, text: Optional[str] = None) -> List[Dict]:
    """Syntax gate: compile the source in memory — the same parse+codegen pass
    py_compile performs, minus the disk I/O of writing a .pyc (which dominated
    runtime on 1000-file diffs). Keeps file/line diagnostics."""
    if text is None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    try:
        compile(text, str(path), "exec")
        return []
    except SyntaxError as e:
        lineno = e.lineno or 0
        detail = e.msg or "compilation failed"
        return [_mk("syntax_error", FINDING_SEV_ERROR, rel, lineno,
                    f"compile: {detail}")]
    except (ValueError, OSError):
        return []  # null bytes / unreadable file — never block on tooling failure


def check_python_file(path: Path, rel: str, enabled: Dict[str, bool]) -> List[Dict]:
    """Full check chain for one Python file."""
    findings: List[Dict] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        if enabled.get("syntax_error", True):
            findings.append(_mk("syntax_error", FINDING_SEV_ERROR, rel, e.lineno or 0,
                                f"SyntaxError: {e.msg}"))
        return filter_suppressed(findings, text)
    if enabled.get("syntax_error", True):
        findings += check_py_compile(path, rel, text=text)
    if enabled.get("dangerous_call", True) or enabled.get("shell_exec", True) \
            or enabled.get("sql_string_format", True):
        findings += check_dangerous_calls(tree, rel)
        findings += check_sql_string_format(tree, rel)
    if enabled.get("remote_exec", True):
        findings += check_remote_exec_lines(text, rel)
        findings += check_shell_true(tree, rel)
    if enabled.get("hardcoded_secret", True):
        findings += check_hardcoded_secrets(text, rel)
    if enabled.get("dead_import", False):
        findings += check_dead_imports(tree, rel)
    if enabled.get("todo_fixme", True):
        findings += check_todo_fixme(text, rel)
    return filter_suppressed(findings, text)


def check_js_ts_file(path: Path, rel: str, enabled: Dict[str, bool]) -> List[Dict]:
    """Regex-level checks for JS/TS (no full parser in MVP)."""
    findings: List[Dict] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if enabled.get("hardcoded_secret", True):
        for lineno, line in enumerate(text.splitlines(), 1):
            if "example" in line.lower() or "xxx" in line.lower():
                continue
            for pat, label in _SECRET_PATTERNS:
                if pat.search(line):
                    findings.append(_mk("hardcoded_secret", FINDING_SEV_ERROR, rel, lineno,
                                        f"Possible {label} hardcoded in source"))
    if enabled.get("remote_exec", True):
        findings += check_remote_exec_lines(text, rel)
    if enabled.get("todo_fixme", True):
        findings += check_todo_fixme(text, rel)
    return filter_suppressed(findings, text)


# ---------- Go / Java pre-scan (regex level, v1.0) ----------
#
# No full parser for Go/Java in a zero-dependency tool; the pre-scan covers
# what a regex can catch reliably: hardcoded secrets (shared + language-
# specific shapes), TODO/FIXME markers, remote-exec one-liners and a light
# bracket-balance syntax heuristic (comments and string literals stripped).

GO_EXT = {".go"}
JAVA_EXT = {".java"}


def _strip_comments_and_strings(text: str) -> str:
    """Blank out // and /* */ comments and "..." / `...` / '...' literals so
    bracket counting sees only code structure. Handles escape sequences;
    unterminated literals are treated as running to end of line."""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                i += 1
            out.append("\n" if i < n else "")
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            newlines = text.count("\n", i, n if end == -1 else end)
            out.append("\n" * newlines)
            i = n if end == -1 else end + 2
        elif ch in ('"', "'", "`"):
            quote = ch
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                if text[i] == "\n":  # unterminated single-line literal
                    break
                i += 1
            out.append(" ")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


_BRACKETS = {"(": ")", "[": "]", "{": "}"}


def check_bracket_balance(text: str, rel: str) -> List[Dict]:
    """Light regex-level syntax gate: unbalanced ()/[]{} after stripping
    comments and string literals -> syntax_error. Line number points at the
    last line of the file (where the mismatch becomes visible)."""
    stripped = _strip_comments_and_strings(text)
    stack: List[tuple] = []
    lineno = 1
    for ch in stripped:
        if ch == "\n":
            lineno += 1
        elif ch in _BRACKETS:
            stack.append((ch, lineno))
        elif ch in _BRACKETS.values():
            if not stack or _BRACKETS[stack[-1][0]] != ch:
                return [_mk("syntax_error", FINDING_SEV_ERROR, rel, lineno,
                            f"Unbalanced '{ch}' — bracket/brace mismatch "
                            f"(pre-scan; run gofmt/javac for a full parse)")]
            stack.pop()
    if stack:
        ch, ln = stack[-1]
        return [_mk("syntax_error", FINDING_SEV_ERROR, rel, ln,
                    f"Unclosed '{ch}' — bracket/brace mismatch at end of file "
                    f"(pre-scan; run gofmt/javac for a full parse)")]
    return []


def _check_text_language(path: Path, rel: str, enabled: Dict[str, bool]) -> List[Dict]:
    """Shared text-level chain for Go/Java: secrets, remote exec, TODO/FIXME."""
    findings: List[Dict] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if enabled.get("hardcoded_secret", True):
        findings += check_hardcoded_secrets(text, rel, skip_dummy=False)
    if enabled.get("remote_exec", True):
        findings += check_remote_exec_lines(text, rel)
    if enabled.get("todo_fixme", True):
        findings += check_todo_fixme(text, rel)
    return filter_suppressed(findings, text)


CS_EXT = {".cs"}


def check_cs_file(path: Path, rel: str, enabled: Dict[str, bool]) -> List[Dict]:
    """Regex-level fallback scan for C# — Python has no Roslyn.

    The C#/.NET port (dotnet/AiCV.Core) scans .cs with a real Roslyn AST and
    is authoritative for the language (exact row/col, comment/string-proof).
    This fallback keeps the same rule ids so agent pipelines get the same
    verdict from either implementation; the AST side may be a documented
    superset (see docs/rules.md).
    """
    findings: List[Dict] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if enabled.get("dangerous_call", True) or enabled.get("shell_exec", True) \
            or enabled.get("sql_string_format", True):
        findings += _check_cs_calls(text, rel)
        findings += _check_cs_sql(text, rel)
    if enabled.get("hardcoded_secret", True):
        findings += check_hardcoded_secrets(text, rel, skip_dummy=False)
    if enabled.get("remote_exec", True):
        findings += check_remote_exec_lines(text, rel)
    if enabled.get("todo_fixme", True):
        findings += check_todo_fixme(text, rel)
    if enabled.get("syntax_error", True):
        findings += check_bracket_balance(text, rel)
    return filter_suppressed(findings, text)


def check_go_file(path: Path, rel: str, enabled: Dict[str, bool]) -> List[Dict]:
    """Regex-level pre-scan for Go: secrets, remote exec, TODO/FIXME,
    bracket-balance syntax heuristic."""
    findings = _check_text_language(path, rel, enabled)
    text = path.read_text(encoding="utf-8", errors="replace")
    if enabled.get("syntax_error", True):
        findings += check_bracket_balance(text, rel)
    return findings


def check_java_file(path: Path, rel: str, enabled: Dict[str, bool]) -> List[Dict]:
    """Regex-level pre-scan for Java: secrets, remote exec, TODO/FIXME,
    bracket-balance syntax heuristic."""
    findings = _check_text_language(path, rel, enabled)
    text = path.read_text(encoding="utf-8", errors="replace")
    if enabled.get("syntax_error", True):
        findings += check_bracket_balance(text, rel)
    return findings


def run_ruff(paths: List[Path]) -> List[Dict]:
    """Run ruff if installed; return [] findings when absent (graceful fallback)."""
    import shutil
    import subprocess
    ruff = shutil.which("ruff")
    if not ruff:
        return []
    try:
        proc = subprocess.run([ruff, "check", "--output-format", "concise", *map(str, paths)],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = []
    for line in (proc.stdout or "").splitlines():
        # format: path:line:col: CODE message
        try:
            filepart, rest = line.split(":", 1)
            lineno, col, rest = rest.split(":", 2)
            code, msg = rest.strip().split(" ", 1)
        except ValueError:
            continue
        out.append({"rule": f"ruff:{code}", "severity": FINDING_SEV_WARN,
                    "file": filepart, "line": int(lineno), "message": msg})
    return out
