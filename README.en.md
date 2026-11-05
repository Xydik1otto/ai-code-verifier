# aicv — AI Code Verifier

[![CI](https://github.com/bigpi/ai-code-verifier/actions/workflows/tests.yml/badge.svg)](https://github.com/bigpi/ai-code-verifier/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Status: 1.0.0](https://img.shields.io/badge/status-1.0.0-blue.svg)](CHANGELOG.md)

Verification gate for AI-generated code: CLI + GitHub Action + pre-commit hook.

> Українська версія: [README.md](README.md)

## Why this exists

AI writes more and more of the code, but humans still have to review it
manually — and that has become the main development bottleneck:

- **Qodo State of AI Code Quality 2026**: reviewing/validating AI code is
  bottleneck #1 (26% of developers and 26% of leaders call it the top problem).
- **36% of developers** say reviewing AI code takes **more** cognitive effort
  than regular code — a "trust tax": doubt first, read second.
- **Sonar**: 96% of developers **don't trust** AI code to be correct as written.
- **Sonar / JetBrains**: the "acceptance gap" — verification must move earlier
  in the pipeline (IDE → pre-commit → agent loop), not stay at final review.

`aicv` answers exactly that: an automatic, deterministic, cheap filter that
sits **before** human review and takes the routine part off its plate.

## What it checks

| Rule | What it catches |
|---|---|
| `syntax_error` | file doesn't parse/compile at all |
| `dangerous_call` | `eval`, `exec`, `compile`, `__import__` |
| `shell_exec` | `os.system`, `os.popen`, `subprocess` with a string argument |
| `remote_exec` | `curl… \| sh`, `bash -c`, `powershell -enc`, `subprocess(shell=True)` |
| `hardcoded_secret` | API keys, tokens (Slack `xox*`, Bearer, AWS `AKIA*`, GitHub, Stripe), passwords |
| `sql_string_format` | SQL built via f-string / `.format` / `%` |
| `dead_import` | imports never used (opt-in) |
| `todo_fixme` | TODO/FIXME markers left in code (warning) |
| `ruff:*` | everything ruff finds, when installed (graceful fallback) |

Languages: **Python** (AST + compile gate), **JS/TS, Go, Java** (regex
pre-scan: secrets, remote-exec, TODO/FIXME, bracket balance).

## Speed

Benchmark on a synthetic **1000-file diff** (98% clean, 2% with classic AI
mistakes; the CLI is timed as a real agent loop would run it —
`python scripts/benchmark.py`):

```text
benchmark: generated 1000 changed .py files
benchmark: aicv check finished in 4.35s -> exit=1
benchmark: aicv: checked 1000 file(s) [diff HEAD] — 40 error(s), 0 warning(s)
benchmark: target 10.0s -> PASS
```

The "1000-file diff in <10 s" target is met with ~3x headroom (4.35 s on a
Windows laptop; repo setup is not part of the measurement).

### C# implementation (aicv-dotnet)

The same 1000-file diff, the same corpus — `aicv-dotnet` (C# .NET 10,
self-contained single-file exe, ReadyToRun; `python scripts/benchmark_dotnet.py`):

```text
benchmark: run 1/3: 2.78s -> FAIL (1000 file(s), 40 error(s))   # first run
benchmark: run 2/3: 0.34s -> FAIL (1000 file(s), 40 error(s))
benchmark: run 3/3: 0.35s -> FAIL (1000 file(s), 40 error(s))
benchmark: aicv-dotnet best of 3: 0.34s
benchmark: target 1.0s -> PASS
```

| methodology | Python | C# (aicv-dotnet) | speedup |
|---|---|---|---|
| single cold run (like CI on fresh files) | 3.93 s | 2.78 s | ~1.4× |
| best of 3 on the same diff | ~1.0 s | **0.34 s** | **~3×** |

Note: the first run over freshly written files pays a one-time Windows
Defender real-time scan of every new file (~2.5 s for 1000 files) — both
implementations pay it and no tool controls it; that is why the C# benchmark
judges by the minimum of 3 runs (warm cache, like a real agent loop). The
"C# <1 s on a 1000-file diff" target is met (0.34 s). For large repositories
the recommended implementation is **C#**: no Python dependency, no
interpreter, a single exe (details in [dotnet/README.md](dotnet/README.md)).

## Installation

**Option 1 — Python (pip-style, classic):**

```bash
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
pip install -e .        # (later: pip install aicv from PyPI)
pytest                  # optional: run the test suite
```

Zero runtime dependencies — works even in a minimal CI image.

**Option 2 — C# exe (recommended for large repos):**

```bash
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier/dotnet
dotnet publish AiCV.Cli -c Release -r win-x64 \
    --self-contained true -p:PublishSingleFile=true \
    -p:PublishReadyToRun=true -o artifacts/exe
./artifacts/exe/aicv.exe check          # same contract as aicv
```

Only the .NET SDK is needed to build — the resulting exe runs without .NET
and without Python. Details and AOT caveats — [dotnet/README.md](dotnet/README.md).

A step-by-step guide for non-developers (Windows/Linux/macOS, updates,
pre-commit, CI) — [INSTALL.md](INSTALL.md).

## First run

Configuration is **optional**: without `.aicv.toml` aicv runs with sensible
defaults — every security rule is on, the noisy `dead_import` is off.
Just run `aicv check` in your repository. When you want to tune rules,
`aicv init` generates a starter config.

## Usage

```bash
aicv check                # git diff HEAD (working tree)
aicv check --staged       # only staged changes
aicv diff main feature    # verify files changed between two refs
aicv check --json         # machine-readable verdict for agent-loop
aicv check --sarif        # SARIF 2.1.0 -> .aicv/latest.sarif (GitHub code scanning)
aicv report               # print the latest report
aicv report --json
aicv report --sarif
aicv verdict              # marker verdict for agents (no report files written)
aicv verdict --summary    # a single marker line
aicv init                 # generate .aicv.toml
aicv ci                   # CI: diff from GITHUB_BASE_REF
aicv ci --annotate        # + ::error file=,line=:: workflow commands (PR annotations)
aicv baseline             # record current findings as accepted legacy debt
aicv check --baseline     # fail only on NEW findings
```

### Baseline (legacy debt)

On a live repository, historical findings make a from-zero gate impossible.
`aicv baseline` records the current findings in `.aicv/baseline.json`, after
which `aicv check --baseline` fails only on **new** findings — the debt is
frozen, new code stays clean:

```bash
aicv baseline             # once: freeze the current state
aicv check --baseline     # then in CI: PASS until a new finding appears
```

A finding is identified by (file, line, rule); commit `.aicv/baseline.json`
together with the config.

### PR annotations

`aicv ci --annotate` prints standard GitHub Actions workflow commands — add
one step to your workflow and every finding appears as an annotation right
on the PR diff line:

```text
::error file=bad.py,line=9::shell_exec: 'os.system()' executes a shell string — injection risk
```

### Severity per rule

Every rule has a severity: **error** (fails the run, exit code 1),
**warning** and **info** (report only). The defaults are listed in the rule
catalog [docs/rules.md](docs/rules.md) (auto-generated from `RULES` via
`python scripts/gen_rules.py`). Override them in the `[severity]` section
of `.aicv.toml`:

```toml
[severity]
dead_import = "error"       # promote to error
dangerous_call = "warning"  # demote — don't fail the build
```

Real output on a file with typical AI mistakes (`exit code 1`):

```text
$ aicv check --no-ruff
aicv: checked 1 file(s) [diff HEAD] — 4 error(s), 0 warning(s)
  [ERROR] bad.py:6 (hardcoded_secret) Possible API key literal hardcoded in source
  [ERROR] bad.py:9 (shell_exec) 'os.system()' executes a shell string — injection risk
  [ERROR] bad.py:15 (sql_string_format) SQL built via string formatting — use parameterized queries
  [ERROR] bad.py:19 (dangerous_call) Use of 'eval()' — dynamic code execution, ban in AI-generated code
report: …\.aicv\latest.md
```

Exit codes: `0` — pass, `1` — at least one error-level finding. Reports are
written to `.aicv/latest.md` and `.aicv/latest.json` (findings grouped by
file, errors before warnings).

### Machine-readable verdict for the agent loop

Ready-made integration recipes (Claude Code hooks, Cursor rules, the verdict
contract) — [docs/agent-integration.md](docs/agent-integration.md).

`aicv check --json` prints only JSON on stdout (human-readable output goes
to stderr) — easy for an autonomous agent to parse, read the findings and
fix the code:

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

### Inline suppressions

A `# aicv: ignore` comment on a line silences all findings on that line;
`# aicv: ignore[rule1, rule2]` silences only the listed rules:

```python
API_KEY = "«redacted:sk-…»"  # aicv: ignore[hardcoded_secret]
result = eval(expr)                    # aicv: ignore
```

### Config

`.aicv.toml` in the repository root — toggle rules:

```toml
[rules]
dead_import = false
hardcoded_secret = true
```

## pre-commit hook

aicv ships a ready hook for the [pre-commit framework](https://pre-commit.com).
In your repository, add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/bigpi/ai-code-verifier
    rev: v1.0.0              # release tag
    hooks:
      - id: aicv
```

The hook runs `aicv check --staged`: if the staged changes contain an
error-level finding, the commit is blocked. Without the framework, simply
call `aicv check --staged` from your own git hook.

## GitHub Action

See the ready example: [`.github/workflows/aicv.yml`](.github/workflows/aicv.yml) —
runs on `pull_request`, takes the diff from `github.base_ref` and fails the
PR when an error-level problem is found.

The project's own tests live in
[`.github/workflows/tests.yml`](.github/workflows/tests.yml)
(Python 3.12 + 3.13, `pip install -e .` + `pytest`).

## Architecture

- `aicv/checks.py` — AST heuristics + regex secrets + ruff adapter (stdlib only).
- `aicv/engine.py` — git diff → files → checks → markdown/JSON report.
- `aicv/cli.py` — `check` / `report` / `ci`.

## GitHub code scanning (SARIF)

`aicv check --sarif` writes `.aicv/latest.sarif` (SARIF 2.1.0). Upload it to
GitHub code scanning in a CI job:

```yaml
      - run: aicv ci --sarif
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: .aicv/latest.sarif
```

## Contributing

Contributions are welcome: bug reports (issue templates in Ukrainian and
English), features, docs, code. See [CONTRIBUTING.md](CONTRIBUTING.md)
(one commit + one test per change, regenerate `docs/rules.md` via
`scripts/gen_rules.py`).

Security: found a vulnerability — **don't** open a public issue, see
[SECURITY.md](SECURITY.md).

## Status

**v1.0.0**: Python files (AST + compile gate) + JS/TS, **Go, Java** (regex
pre-scan), git integration, reports (grouped by file + severity), inline
suppressions, machine-readable verdict (`--json`), SARIF 2.1.0, `aicv init`,
`aicv verdict`, `aicv diff` (two branches), baseline mode, PR annotations
(`ci --annotate`), severity per rule (`[severity]`), TODO/FIXME detector,
auto-generated [docs/rules.md](docs/rules.md), benchmark
(`scripts/benchmark.py`: 1000 files < 10 s), agent-integration docs
([docs/agent-integration.md](docs/agent-integration.md)), pre-commit hook,
config, GitHub Action example, smoke/pypi scripts, pytest suite.
topics: python, code-review, static-analysis, ai-tools, cli, security, sarif

Roadmap — [PLAN.md](PLAN.md), history — [CHANGELOG.md](CHANGELOG.md).
