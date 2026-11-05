# Contributing

Thanks for your interest in **aicv** — a zero-dependency code verifier for
AI agents and CI. This document targets contributors who intend to work on
the code: architecture first, process after.

> Українська версія цього документа: [CONTRIBUTING.md](CONTRIBUTING.md).
> Ukrainian version: [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 1. Architecture

The project has **two implementations of one contract**:

| Implementation | Location | Role |
|---|---|---|
| Python (reference) | `aicv/` | The reference logic, published on PyPI |
| C#/.NET port | `dotnet/` | A self-contained `aicv.exe` — no Python, no .NET runtime required |

Both implementations must produce **the same set of findings** on the same
git diff. This is enforced by the golden parity tests
(`tests/test_dotnet_parity.py`) — they merge PRs, not wishes.

### 1.1 The rule registry — `aicv/checks.py`

The central state of the whole scanner is the `RULES` dict:

```python
RULES: Dict[str, Dict] = {
    "dangerous_call": {"name": "Dynamic code execution (eval/exec/compile)",
                       "default": True, "severity": "error"},
    ...
}
```

Each rule is described by:

- **`id`** (the dict key) — snake_case, **immutable forever**. It leaks into
  the JSON verdict, SARIF, `.aicv.toml`, `# aicv: ignore[id]`, the baseline —
  renaming a rule breaks users.
- **`name`** — a short human description **in English** (agents and CI parse
  it; it becomes the SARIF `shortDescription`). The string must be
  **identical** in both the Python and C# implementations.
- **`default`** — whether the rule is enabled without config. Noisy rules
  (e.g. `dead_import`) should be `False` — opt-in.
- **`severity`** — the default level: `error` (fails the check, exit 1),
  `warning` (reports only), `info`.

The detectors themselves are pure functions next to the dict, of two kinds:

- **AST detectors** (Python only): `check_dangerous_calls`,
  `check_sql_string_format`, `check_shell_true`, `check_dead_imports` —
  they walk `ast.walk(tree)`.
- **Line/regex detectors** (all languages): `check_hardcoded_secrets`,
  `check_remote_exec_lines`, `check_todo_fixme` — they iterate
  `text.splitlines()`.

Every detector returns a list of Finding dicts via `_mk()`:

```python
{"rule": ..., "severity": ..., "file": ..., "line": ..., "message": ...}
```

**Suppression**: before returning, every `check_*_file` passes its findings
through `filter_suppressed()` — the inline comment `# aicv: ignore` (all
rules on the line) or `# aicv: ignore[rule1, rule2]`. `suppression_map()`
builds a `line -> "*" | {rule_ids}` map; this works for all languages,
including ruff findings.

### 1.2 The pipeline — `aicv/engine.py`

Data flow in `aicv check`:

```
git diff (--staged | HEAD | base_ref...HEAD) + untracked
  → changed_files(): filter (exists, not a dotfile, not .aicv/)
  → dispatch by extension:
      .py                → check_python_file  (AST + regex + compile gate)
      .js .ts .mjs ...   → check_js_ts_file   (regex)
      .go                → check_go_file      (regex + bracket gate)
      .java              → check_java_file    (regex + bracket gate)
  → ruff (optional; its findings also pass filter_suppressed)
  → apply_severities(): overrides from .aicv.toml [severity]
  → apply_baseline(): drop entries recorded in .aicv/baseline.json (--baseline only)
  → output: text / --json verdict / --sarif / --annotate
```

Key points:

- **`changed_files()`** never scans `.aicv/` (the tool's own report
  artifacts) or dotfiles. In working-tree mode it also includes untracked
  files — fresh AI-generated files are not staged yet.
- **`diff_refs()` / `run_checks_between()`** (`aicv diff ref1 ref2`):
  a merge-base diff `ref1...ref2`; blobs are materialized into a temp
  directory so all regular checkers run without a checkout. Finding paths
  are repo-relative.
- **Config**: `load_config()` reads `.aicv.toml` `[rules]` (toggles);
  `load_severities()` — `[severity]` (per-rule overrides). Both degrade
  softly to defaults on any error (missing tomllib, broken TOML) —
  **graceful fallback is a contract**: an optional integration never
  breaks the scan.
- **Exit code**: `1` if any finding has severity `error`, otherwise `0`.
  Warnings/info do not affect it.

### 1.3 Output formats

- **JSON verdict** (`aicv verdict --json`): `{"files_checked", "errors":
  [{file, line, rule, message}], "exit_code"}` — the machine contract for
  agent loops.
- **SARIF 2.1.0** (`render_sarif`): for GitHub code scanning upload.
  Every rule from `RULES` lands in `tool.driver.rules`
  (`shortDescription` = `name`); ruff findings get the id `ruff:<rule>`.
  Severity mapping: `error→error`, `warning→warning`, `info→note`.
- **GitHub Annotations** (`render_annotations`): lines of the form
  `::error file=...,line=...::rule: message` — printed by `aicv ci
  --annotate` inside a GitHub Actions workflow, they become inline
  annotations on the PR diff. Messages are escaped (`%`→`%25`,
  newlines→`%0A/%0D`); paths use forward slashes only.
- **Baseline**: `aicv baseline` records the current findings into
  `.aicv/baseline.json`; afterwards `aicv check --baseline` fails only on
  **new** findings. A finding key is the tuple `(file, line, rule)`; pin
  your lines — a line shift "re-opens" old debt.
- **Report**: `save_report()` writes `.aicv/latest.json` +
  `.aicv/latest.md` (markdown, grouped by file, errors before warnings).

### 1.4 The C# port — `dotnet/AiCV.Core`

The structure mirrors Python:

| Python | C# | Note |
|---|---|---|
| `checks.RULES` | `Rules.All` (`RuleSpec(Name, Default, Severity)`) | identical id/name/default/severity |
| detectors | `Checks` (regex port) | 1:1 regexes, `RegexOptions.IgnoreCase` instead of `(?i)` |
| `engine.py` | `Engine.cs` | the same pipeline and output formats |
| Finding dict | `Finding.cs` (record) | the same fields |

Intentional differences (documented in `dotnet/README.md`, accepted by the
parity tests):

- `syntax_error`: Python parses with the real AST; C# uses a lightweight
  bracket-balance gate (same finding, the line number may differ).
- `subprocess.run("ls " + cmd)` (concatenation in a bare string) is not
  flagged by C# — Python sees via the AST that the argument is not a
  constant.
- No ruff integration (`--no-ruff` is accepted for CLI compatibility).
- `dead_import` in C# is a regex approximation.

### 1.5 The parity contract: how to add a rule to BOTH implementations

Parity is tested at the level of the **finding set** `(file, line, rule)`
plus severity per finding. So the golden sequence is:

**Step 1 — Python, `aicv/checks.py`.** Add an entry to `RULES`:

```python
"debug_print": {"name": "Debug print left in code",
                "default": True, "severity": "warning"},
```

**Step 2 — Python, detector.** Write a pure function next to it:

```python
_DEBUG_PRINT = re.compile(r"^\s*(print|console\.log)\s*\(")

def check_debug_prints(text: str, rel: str) -> List[Dict]:
    out = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _DEBUG_PRINT.search(line):
            out.append(_mk("debug_print", FINDING_SEV_WARN, rel, lineno,
                           "Debug print left in code — remove before merge"))
    return out
```

**Step 3 — Python, wiring.** Call the detector in every
`check_<lang>_file`, behind `enabled.get("debug_print", True)`, **before**
`filter_suppressed(...)`. Cover both branches (AST languages may want the
lineno from the AST; for line rules take it from splitlines).

**Step 4 — C#, `dotnet/AiCV.Core/Rules.cs`.** The mirrored entry with an
**identical** name, default and severity:

```csharp
["debug_print"] = new("Debug print left in code", true, Sev.Warn),
```

**Step 5 — C#, `dotnet/AiCV.Core/Checks.cs`.** Port the detector. Write
regexes in the **common subset** of Python `re` and .NET `Regex`:
inline `(?i)`, `\b`, classes `[…]`, quantifiers `{n,}` — fine;
possessive quantifiers, variable-length lookbehind, `(?(x)...)` — no.
Wire it into the same extension dispatch (`ScanExts` and the per-language
methods), **before** suppression.

**Step 6 — the parity corpus.** In `tests/test_dotnet_parity.py`, add lines
that trigger the new rule to the `BAD_*` templates (and, if applicable, a
suppression example to `SUPPRESSED_*`). Without this the parity test is
physically unable to catch a divergence in your rule.

**Step 7 — docs and tests.**

- `python scripts/gen_rules.py` → commit the updated `docs/rules.md`
  (the sync test fails if you forget).
- A golden fixture + assertions in `tests/test_aicv.py` for the Python side.
- A line in `CHANGELOG.md`.
- Run `pytest` (everything); `pytest tests/test_dotnet_parity.py` alone
  gives a faster loop when debugging parity.

**What the parity test does NOT forgive**: a different rule id in the two
implementations; a different `default`/`severity`; a detector that fires on
one side and stays silent on the other (same file, same line). **What it
forgives**: the message wording (English in both, but phrasing may differ)
and the `syntax_error` line number (AST vs the bracket gate).

## 2. Development environment

### Python

```bash
git clone https://github.com/bigpi/ai-code-verifier
cd ai-code-verifier
pip install -e .
pytest
```

Zero runtime dependencies — the Python standard library only (3.9+).
Don't add dependencies without prior discussion in an issue. Optional
integrations (ruff, tomllib on older Pythons) come only with graceful
fallback.

### C# port

```bash
cd dotnet
dotnet build AiCV.sln -c Release
dotnet publish AiCV.Cli -c Release -r win-x64 \
    --self-contained true \
    -p:PublishSingleFile=true \
    -p:PublishReadyToRun=true \
    -o artifacts/exe
# -> dotnet/artifacts/exe/aicv.exe (self-contained, ~70-90 MB)
```

The parity and benchmark tests look for the exe at `$AICV_DOTNET_EXE` or
`dotnet/artifacts/exe/aicv.exe`. AOT (`-p:PublishAot=true`) starts faster
but requires the MSVC linker; without it the build fails with
`Platform linker not found` — use the command above (details:
`dotnet/README.md`).

## 3. Tests

- `tests/test_aicv.py` — the main suite: rules, config, suppression,
  ref-diff, output formats, CLI. **Tests are mandatory**: every behavior
  change is covered by a pytest test; PRs without tests are not merged.
- `tests/fixtures/` — golden fixtures (bad/clean per language:
  `bad_code.py`, `bad_secrets.go`, `clean_code.java`, ...). When adding a
  rule or a language, add a bad/clean fixture pair and assertions on exact
  `(rule, line)` pairs.
- `tests/test_dotnet_parity.py` — the golden Python ↔ C# parity suite
  (the corpus is generated on the fly, verdicts are compared; details in
  §1.5).
- `tests/test_dotnet_benchmark.py` — the benchmark smoke test (200 files).

### Updating the benchmark

`scripts/benchmark.py` (Python) and `scripts/benchmark_dotnet.py` (C# exe)
build a throwaway 1000-file git repo (98% clean, 2% with classic AI
mistakes) and time the real CLI. Methodology:

- One subprocess per run, startup included — exactly what a user or an
  agent loop experiences.
- `benchmark_dotnet.py` runs **best-of-3** (the minimum): the first run
  pays a one-time Windows Defender scan of fresh files (~2.5 s) — a cost
  the tool itself does not control. `--runs 1` shows the cold number.
- Targets: Python ~10 s, C# ~1 s for 1000 files (exit 1 when exceeded).

If your change moves performance: re-run both benchmarks
(`python scripts/benchmark.py`, `python scripts/benchmark_dotnet.py`) and
update the numbers in the "Швидкодія" / "Speed" section of the main README.
Do not change the methodology (file count, best-of, corpus templates)
without discussion — otherwise the numbers are no longer comparable with
history.

## 4. How to add a new scanning language

The reference is how Go and Java landed in v1.0. Step by step (example:
language `lang`, extension `.lang`):

1. **Extension**: in `aicv/checks.py` — `LANG_EXT = {".lang"}`.
2. **Shared pre-scan**: most rules (secrets, remote-exec, TODO/FIXME) are
   line-based and already language-agnostic. Use
   `_check_text_language(path, rel, enabled)` — that is exactly what
   `check_go_file` and `check_java_file` do.
3. **Language-specific patterns**: language-shaped secret patterns
   (`password := "..."` in Go, `String password = "..."` in Java) go into
   `_SECRET_PATTERNS` with a label — necessarily in **both**
   implementations (step 5 of §1.5).
4. **Syntax gate**: no full parser in a zero-dep tool —
   `check_bracket_balance(text, rel)` after
   `_strip_comments_and_strings()` (bracket balance with comments and
   string literals stripped).
5. **Wiring**: `SCAN_EXTS` in `engine.py` (`PY_EXT | JS_EXT | GO_EXT |
   JAVA_EXT | LANG_EXT`) plus an `elif ext in LANG_EXT:` branch in
   `run_checks()`.
6. **The C# mirror**: an extension array and a per-language method in
   `Checks.cs`, plus the same extensions in `ScanExts`.
7. **Fixtures + parity**: `tests/fixtures/clean_code.lang`,
   `bad_secrets.lang`; corpus templates in `test_dotnet_parity.py`; tests
   in `test_aicv.py`.
8. **Docs**: `docs/rules.md` (regenerate), README (the language list),
   `CHANGELOG.md`.

Do not take on a full parser in the MVP — rules a regex can catch reliably
cost less than a 50 MB dependency.

## 5. Branches and commits

- **`master` is the stable branch**: green pytest, working docs, releasable
  at any moment. Direct pushes to `master` are reserved for the owner's
  small stuff (docs, typos); features go through PRs.
- Working branches: `feature/<short-name>`, `fix/<short-name>`.
- **Conventional commits**: `feature: …`, `fix: …`, `docs: …`,
  `test: …`, `refactor: …`; release commits use `vX.Y feature: …`
  (see history). One logical change — one commit.
- PR process: fork/branch → `pytest` green locally → a PR describing what,
  why and how it was verified → discussion → merge. For C# changes, include
  the parity test output.

## 6. Documentation and i18n

- Documentation is maintained **in Ukrainian and English**: paired files
  (`README.md` ↔ `README.en.md`, `CONTRIBUTING.md` ↔
  `CONTRIBUTING.en.md`). If you change one, mirror the other in the same PR.
- `docs/rules.md` is **generated** (`python scripts/gen_rules.py`) — do
  not edit it by hand; the source of truth is `RULES` in `aicv/checks.py`.
- Finding messages, rule ids and commit messages are in English (agents
  and CI parse them).
- **No Russian localization, ever** (the project owner's policy). PRs with
  Russian in docs or UI are rejected regardless of technical quality.

## 7. Bug reports and feature requests

Use the
[bug_report](https://github.com/bigpi/ai-code-verifier/issues/new?template=bug_report.md)
and
[feature_request](https://github.com/bigpi/ai-code-verifier/issues/new?template=feature_request.md)
templates. What adds value in a bug report: the version (`aicv --version` /
the exe name), the output of `aicv check --json`, a minimal example file
that triggers the bug. For the C# port, state whether it reproduces in both
implementations — if only in one, it is a parity bug and takes priority.

## 8. Licensing

By contributing code you agree to license it under the project license (MIT).
