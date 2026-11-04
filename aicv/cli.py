"""aicv CLI — `check`, `report`, `ci` commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine import (changed_files, exit_code, load_config, run_checks,
                     save_report)


def _cmd_check(args, root: Path) -> int:
    files = changed_files(root, staged=args.staged)
    if not files:
        target = "staged" if args.staged else "diff HEAD"
        print(f"aicv: no changed .py/.js/.ts files for target '{target}' — nothing to verify.")
        return 0
    return _scan(args, root, files, "staged" if args.staged else "diff HEAD")


def _cmd_ci(args, root: Path) -> int:
    import os
    base = os.environ.get("GITHUB_BASE_REF")
    if not base:
        print("aicv ci: GITHUB_BASE_REF is not set; falling back to 'origin/main'.",
              file=sys.stderr)
        base = "origin/main"
    files = changed_files(root, base_ref=base)
    if not files:
        print(f"aicv ci: no changed files vs {base} — nothing to verify.")
        return 0
    return _scan(args, root, files, f"ci vs {base}")


def _scan(args, root: Path, files, target: str) -> int:
    enabled = load_config(root)
    findings = run_checks(root, files, enabled, use_ruff=not args.no_ruff)
    md = save_report(root, target, files, findings)
    counts = {"error": 0, "warning": 0}
    for f in findings:
        counts[f["severity"]] += 1
    print(f"aicv: checked {len(files)} file(s) [{target}] — "
          f"{counts['error']} error(s), {counts['warning']} warning(s)")
    for f in sorted(findings, key=lambda x: (x["severity"], x["file"], x["line"])):
        print(f"  [{f['severity'].upper()}] {f['file']}:{f['line']} ({f['rule']}) {f['message']}")
    print(f"report: {md}")
    if args.json:
        import json as _j
        d = root / ".aicv" / "latest.json"
        print(_j.dumps(_j.loads(d.read_text(encoding="utf-8")), ensure_ascii=False))
    return exit_code(findings)


def _cmd_report(args, root: Path) -> int:
    d = root / ".aicv"
    if args.json:
        p = d / "latest.json"
    else:
        p = d / "latest.md"
    if not p.is_file():
        print(f"aicv report: no report found at {p} — run `aicv check` first.")
        return 2
    print(p.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="aicv",
                                 description="Verification gate for AI-generated code")
    ap.add_argument("--version", action="version", version=f"aicv {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="verify changed files (git diff HEAD or --staged)")
    p_check.add_argument("--staged", action="store_true", help="only staged changes")
    p_check.add_argument("--no-ruff", action="store_true", help="skip ruff even if installed")
    p_check.add_argument("--json", action="store_true", help="also print the JSON report")
    p_check.set_defaults(func=_cmd_check)

    p_rep = sub.add_parser("report", help="print the latest verification report")
    p_rep.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    p_rep.set_defaults(func=_cmd_report)

    p_ci = sub.add_parser("ci", help="CI mode: diff vs GITHUB_BASE_REF")
    p_ci.add_argument("--no-ruff", action="store_true")
    p_ci.add_argument("--json", action="store_true")
    p_ci.set_defaults(func=_cmd_ci)
    return ap


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd()
    return args.func(args, root)


if __name__ == "__main__":
    sys.exit(main())
