# Agent integrations: aicv in the Claude Code / Cursor loop

`aicv` is built to sit **inside the coding-agent loop**, not just in CI: the
agent writes code, `aicv` gives it a deterministic, machine-readable verdict
*before* a human ever reviews. This document shows the three integration
shapes that work today, with copy-paste examples.

Why: review/validation of AI-generated code is the #1 bottleneck (Qodo State
of AI Code Quality 2026), and "trust tax" makes human review of agent output
slower than human output. A cheap deterministic gate between the agent and
the human removes the routine part of that review.

## 1. The verdict contract (works with any agent)

`aicv check --json` prints **only** a JSON verdict on stdout (human-readable
output goes to stderr), so an agent can parse it safely:

```bash
aicv check --json
```

```json
{
  "files_checked": 1,
  "errors": [
    {"file": "bad.py", "line": 19, "rule": "dangerous_call",
     "message": "Use of 'eval()' — dynamic code execution, ban in AI-generated code"}
  ],
  "exit_code": 1
}
```

The agent loop is then trivially: **generate → verify → read `errors[]` →
fix → repeat**, stop when `exit_code == 0`.

For log-based agents (or when you grep transcripts instead of parsing
stdout), `aicv verdict` emits a single marker line that is easy to spot:

```text
=== AICV VERDICT: FAIL | target=diff HEAD | files=1 errors=4 warnings=0 ===
```

`aicv verdict --summary` prints just that one line and writes no files.
`aicv check` (without `--json`) also writes `.aicv/latest.md` / `.json`
reports an agent can read afterwards with its file tools.

`aicv diff main feature-x` supports the same flags, so an agent can verify a
whole branch without checking it out.

## 2. Claude Code: automatic gate on every edit

Claude Code runs [hooks](https://docs.claude.com/en/docs/claude-code/hooks) —
shell commands triggered by agent events. Put this in your project's
`.claude/settings.json` and every file the agent writes gets verified
immediately; a non-zero exit code feeds the finding list back into the
agent's context, so it fixes itself without being asked:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "aicv check --no-ruff || true"
          }
        ]
      }
    ]
  }
}
```

Stricter variant — make verification part of *stopping* (Stop hook): the
loop only ends when the verdict is PASS:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "aicv check --no-ruff --json > .aicv-verdict.json || exit 2" }
        ]
      }
    ]
  }
}
```

Then ask Claude (once, in `CLAUDE.md`) to honor the gate:

```markdown
## Verification gate
After finishing code changes, run `aicv check --no-ruff --json`.
- If `exit_code` is 1: fix every entry in `errors[]` (file, line, rule,
  message), then re-run until it is 0. Do not suppress findings with
  `# aicv: ignore` unless the user explicitly asks.
```

## 3. Cursor: rules + terminal

In Cursor, add a project rule (`.cursor/rules/aicv.mdc`) that teaches the
agent the verify-fix loop — the agent already has a terminal, so the verdict
contract in section 1 is all it needs:

```markdown
---
description: Verify AI-generated code with aicv before declaring a task done
alwaysApply: true
---
When you finish writing or editing code in this repo:
1. Run `aicv check --no-ruff --json` in the terminal.
2. If `exit_code` != 0, fix each entry in `errors[]` and re-run.
3. Only report the task as complete when `exit_code == 0`.
Rules live in docs/rules.md. Never add `# aicv: ignore` without asking.
```

For a manual checkpoint, Cursor's terminal is enough:

```bash
aicv check --json | python -c "import json,sys; v=json.load(sys.stdin); print(v['exit_code'], len(v['errors']))"
```

## 4. CI as the backstop

Keep the agent-loop gate fast and local; let CI be the independent backstop
(same tool, so results match):

```yaml
# .github/workflows/aicv.yml
- run: pip install aicv
- run: aicv ci --annotate   # diff vs GITHUB_BASE_REF + PR annotations
```

## Notes

- `aicv` is a zero-dependency Python CLI (`pip install aicv`); it never
  phones home and reads only the files in your diff.
- Findings are deterministic: the same diff always produces the same verdict,
  which is what makes it usable as a loop condition.
- `# aicv: ignore[rule]` inline suppression exists for legit exceptions —
  instruct agents to treat it as a last resort requiring user consent.
