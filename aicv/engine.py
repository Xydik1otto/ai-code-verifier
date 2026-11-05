"""Core engine: git diff -> changed files -> checks -> report."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .checks import RULES, check_js_ts_file, check_python_file, run_ruff

PY_EXT = {".py"}
JS_EXT = {".js", ".ts", ".mjs", ".jsx", ".tsx"}
REPORT_DIR = ".aicv"
REPORT_LATEST = "latest"


def _git(args: List[str], cwd: Path) -> Optional[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def changed_files(root: Path, staged: bool = False, base_ref: Optional[str] = None) -> List[Path]:
    """Files touched by git diff (working tree vs HEAD, or staged, or vs base_ref)."""
    names = []
    if base_ref:
        diff = _git(["diff", "--name-only", f"{base_ref}...HEAD"], root)
        if diff is None:
            return []
        names += [line.strip() for line in diff.splitlines() if line.strip()]
    elif staged:
        diff = _git(["diff", "--cached", "--name-only"], root)
        if diff is None:
            return []
        names += [line.strip() for line in diff.splitlines() if line.strip()]
    else:
        # tracked modifications (may fail in a repo with no commits yet)
        diff = _git(["diff", "HEAD", "--name-only"], root)
        if diff:
            names += [line.strip() for line in diff.splitlines() if line.strip()]
        # New AI-generated files are usually untracked before staging; include
        # them for the working-tree target regardless of diff success.
        untracked = _git(["ls-files", "--others", "--exclude-standard"], root) or ""
        names += [line.strip() for line in untracked.splitlines() if line.strip()]
    files = []
    for line in names:
        p = (root / line).resolve()
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            p.relative_to((root / REPORT_DIR).resolve())
        except ValueError:
            pass
        else:
            continue  # never scan aicv's own report artifacts
        files.append(p)
    return files


def load_config(root: Path) -> Dict[str, bool]:
    """Read .aicv.toml if present: [rules] section with rule_id = true/false."""
    enabled = {rid: spec["default"] for rid, spec in RULES.items()}
    cfg = root / ".aicv.toml"
    if not cfg.is_file():
        return enabled
    try:
        import tomllib
        data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return enabled
    for rid, val in (data.get("rules") or {}).items():
        if rid in enabled:
            enabled[rid] = bool(val)
    return enabled


def run_checks(root: Path, files: List[Path], enabled: Dict[str, bool],
               use_ruff: bool = True) -> List[Dict]:
    findings: List[Dict] = []
    py_paths: List[Path] = []
    for path in files:
        try:
            rel = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = path.name
        ext = path.suffix.lower()
        if ext in PY_EXT:
            findings += check_python_file(path, rel, enabled)
            py_paths.append(path)
        elif ext in JS_EXT:
            findings += check_js_ts_file(path, rel, enabled)
    if use_ruff and py_paths:
        ruff_findings = run_ruff(py_paths)
        if ruff_findings:
            # apply `# aicv: ignore` to ruff findings as well
            from .checks import filter_suppressed
            by_path: Dict[str, List[Dict]] = {}
            for f in ruff_findings:
                by_path.setdefault(f["file"], []).append(f)
            for p in py_paths:
                key = str(p)
                group = by_path.get(key)
                if not group:
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                findings += filter_suppressed(group, text)
    return findings


SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = ("https://json.schemastore.org/sarif-2.1.0.json")

_SEV_TO_SARIF = {"error": "error", "warning": "warning"}


def render_sarif(findings: List[Dict]) -> Dict:
    """SARIF 2.1.0 document for GitHub code scanning upload."""
    rules = [
        {"id": rid, "shortDescription": {"text": spec.get("name", rid)}}
        for rid, spec in sorted(RULES.items())
    ]
    rule_ids = {r["id"] for r in rules}
    results = []
    for f in sorted(findings, key=lambda x: (x["file"], x["line"], x["rule"])):
        results.append({
            "ruleId": f["rule"] if f["rule"] in rule_ids or f["rule"].startswith("ruff:")
                      else f"ruff:{f['rule']}",
            "level": _SEV_TO_SARIF.get(f["severity"], "note"),
            "message": {"text": f["message"]},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f["file"].replace("\\", "/")},
                    "region": {"startLine": int(f["line"])},
                }
            }],
        })
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {"driver": {"name": "aicv", "informationUri":
                                "https://github.com/bigpi/ai-code-verifier",
                                "rules": rules}},
            "results": results,
        }],
    }


def severity_counts(findings: List[Dict]) -> Dict[str, int]:
    counts = {"error": 0, "warning": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return counts


def exit_code(findings: List[Dict]) -> int:
    return 1 if any(f["severity"] == "error" for f in findings) else 0


def build_verdict(files: List[Path], findings: List[Dict]) -> Dict:
    """Machine-readable verdict for agent-loop integration."""
    errors = [
        {"file": f["file"], "line": f["line"], "rule": f["rule"], "message": f["message"]}
        for f in sorted(findings, key=lambda x: (x["file"], x["line"], x["rule"]))
        if f["severity"] == "error"
    ]
    return {
        "files_checked": len(files),
        "errors": errors,
        "exit_code": exit_code(findings),
    }


def render_markdown(target: str, files: List[Path], findings: List[Dict], root: Path) -> str:
    counts = severity_counts(findings)
    lines = [
        "# aicv verification report",
        "",
        f"- Target: `{target}`",
        f"- Date: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Files checked: {len(files)}",
        f"- Findings: **{counts.get('error', 0)} errors**, {counts.get('warning', 0)} warnings",
        f"- Verdict: {'FAIL' if exit_code(findings) else 'PASS'}",
        "",
    ]
    if files:
        lines.append("## Files")
        for p in files:
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                rel = p.name
            lines.append(f"- `{rel}`")
        lines.append("")
    lines.append("## Findings")
    if not findings:
        lines.append("No issues detected.")
        return "\n".join(lines) + "\n"
    # group by file; within a file: errors before warnings, then by line
    by_file: Dict[str, List[Dict]] = {}
    for f in findings:
        by_file.setdefault(f["file"], []).append(f)
    sev_rank = {"error": 0, "warning": 1}
    for rel in sorted(by_file):
        lines.append(f"### `{rel}`")
        for f in sorted(by_file[rel], key=lambda x: (sev_rank.get(x["severity"], 9), x["line"])):
            icon = "🔴" if f["severity"] == "error" else "🟡"
            lines.append(f"- {icon} **[{f['severity'].upper()}]** line {f['line']} "
                         f"`{f['rule']}`: {f['message']}")
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------- baseline mode ----------
# `aicv baseline` records the current findings as accepted legacy debt;
# `check --baseline` then fails only on NEW findings (not present in the
# baseline). A finding is identified by (file, line, rule).


def _finding_key(f: Dict) -> tuple:
    return (f["file"], int(f["line"]), f["rule"])


def save_baseline(root: Path, findings: List[Dict]) -> Path:
    d = root / REPORT_DIR
    d.mkdir(exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "findings": findings,
    }
    p = d / "baseline.json"
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def load_baseline(root: Path) -> Optional[set]:
    """Set of baseline finding keys, or None when no baseline exists."""
    p = root / REPORT_DIR / "baseline.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return {_finding_key(f) for f in data.get("findings", [])}
    except (KeyError, TypeError, ValueError):
        return None


def apply_baseline(findings: List[Dict], baseline_keys: set) -> List[Dict]:
    """Keep only findings that are NOT recorded in the baseline (new ones)."""
    return [f for f in findings if _finding_key(f) not in baseline_keys]


def save_report(root: Path, target: str, files: List[Path], findings: List[Dict]) -> Path:
    d = root / REPORT_DIR
    d.mkdir(exist_ok=True)
    payload = {
        "target": target,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [str(p.relative_to(root)).replace("\\", "/") for p in files],
        "findings": findings,
        "counts": severity_counts(findings),
        "exit_code": exit_code(findings),
    }
    (d / f"{REPORT_LATEST}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md = d / f"{REPORT_LATEST}.md"
    md.write_text(render_markdown(target, files, findings, root), encoding="utf-8")
    return md
