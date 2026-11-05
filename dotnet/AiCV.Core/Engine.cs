namespace AiCV.Core;

/// <summary>Core engine: git diff -> changed files -> checks -> report.
/// Port of aicv.engine (Python) — zero external dependencies.</summary>
public static class Engine
{
    public const string ReportDir = ".aicv";
    public const string ReportLatest = "latest";
    public const string SarifVersion = "2.1.0";
    public const string SarifSchema = "https://json.schemastore.org/sarif-2.1.0.json";

    // ---------- git plumbing ----------

    public static string? Git(string[] args, string cwd)
    {
        try
        {
            var psi = new System.Diagnostics.ProcessStartInfo("git")
            {
                Arguments = string.Join(' ', args.Select(Quote)),
                WorkingDirectory = cwd,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using var proc = System.Diagnostics.Process.Start(psi);
            if (proc is null) return null;
            var stdout = proc.StandardOutput.ReadToEnd();
            proc.StandardError.ReadToEnd();
            proc.WaitForExit();
            return proc.ExitCode != 0 ? null : stdout;
        }
        catch (Exception)
        {
            return null;
        }
    }

    private static string Quote(string s) =>
        s.Contains(' ') || s.Contains('"') ? '"' + s.Replace("\"", "\\\"") + '"' : s;

    private static List<string> Lines(string? s) =>
        string.IsNullOrEmpty(s)
            ? new List<string>()
            : s.Replace("\r\n", "\n").Split('\n')
                .Select(l => l.Trim()).Where(l => l.Length > 0).ToList();

    /// <summary>Files touched by git diff (working tree vs HEAD, staged, or vs base_ref).</summary>
    public static List<string> ChangedFiles(string root, bool staged = false, string? baseRef = null)
    {
        var names = new List<string>();
        if (baseRef is not null)
        {
            var diff = Git(new[] { "diff", "--name-only", $"{baseRef}...HEAD" }, root);
            if (diff is null) return names;
            names.AddRange(Lines(diff));
        }
        else if (staged)
        {
            var diff = Git(new[] { "diff", "--cached", "--name-only" }, root);
            if (diff is null) return names;
            names.AddRange(Lines(diff));
        }
        else
        {
            names.AddRange(Lines(Git(new[] { "diff", "HEAD", "--name-only" }, root)));
            // untracked AI-generated files belong to the working-tree scan too
            names.AddRange(Lines(Git(new[] { "ls-files", "--others", "--exclude-standard" }, root)));
        }
        var reportDir = Path.GetFullPath(Path.Combine(root, ReportDir));
        var files = new List<string>();
        foreach (var name in names)
        {
            var full = Path.GetFullPath(Path.Combine(root, name));
            if (!File.Exists(full)) continue;
            if (Path.GetFileName(full).StartsWith(".")) continue;
            if (full.StartsWith(reportDir + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                continue; // never scan aicv's own report artifacts
            files.Add(full);
        }
        return files;
    }

    /// <summary>Relative paths changed between two git refs (merge-base diff).</summary>
    public static List<string> DiffRefs(string root, string ref1, string ref2)
    {
        var diff = Git(new[] { "diff", "--name-only", $"{ref1}...{ref2}" }, root);
        if (diff is null) return new List<string>();
        var exts = Checks.ScanExts;
        var rels = new List<string>();
        foreach (var rel in Lines(diff))
        {
            if (rel.StartsWith(".aicv/") || rel.Replace('\\', '/').Contains("..")) continue;
            var ext = Path.GetExtension(rel);
            if (exts.Contains(ext)) rels.Add(rel);
        }
        return rels;
    }

    /// <summary>Scan files changed between ref1...ref2, content taken from ref2,
    /// materialized into a temp tree; findings carry repo-relative paths.</summary>
    public static (List<Finding> Findings, List<string> Rels) RunChecksBetween(
        string root, string ref1, string ref2,
        IReadOnlyDictionary<string, bool> enabled, IReadOnlyDictionary<string, string>? severities = null)
    {
        var rels = DiffRefs(root, ref1, ref2);
        if (rels.Count == 0) return (new List<Finding>(), rels);
        var tmp = Path.Combine(Path.GetTempPath(), "aicv-dotnet-diff-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(tmp);
            var files = new List<string>();
            foreach (var rel in rels)
            {
                var blob = Git(new[] { "show", $"{ref2}:{rel}" }, root);
                if (blob is null) continue; // deleted/binary at ref2 — skip gracefully
                var target = Path.Combine(tmp, rel.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.WriteAllText(target, blob, new System.Text.UTF8Encoding(false));
                files.Add(target);
            }
            var findings = RunChecks(tmp, files, enabled, severities);
            return (findings, rels);
        }
        finally
        {
            try { Directory.Delete(tmp, recursive: true); } catch { /* best effort */ }
        }
    }

    // ---------- config ----------

    /// <summary>Minimal TOML reader for .aicv.toml: [rules] toggles and
    /// [severity] overrides. Unknown keys/sections are ignored (mirrors the
    /// Python loader's tolerance). Falls back to defaults on any problem.</summary>
    public static (Dictionary<string, bool> Rules, Dictionary<string, string> Severities) LoadConfig(string root)
    {
        var rules = Rules.Defaults();
        var severities = new Dictionary<string, string>(StringComparer.Ordinal);
        var cfg = Path.Combine(root, ".aicv.toml");
        if (!File.Exists(cfg)) return (rules, severities);
        string[] lines;
        try { lines = File.ReadAllLines(cfg); } catch { return (rules, severities); }
        var section = "";
        foreach (var raw in lines)
        {
            var line = raw.Trim();
            if (line.Length == 0 || line.StartsWith('#')) continue;
            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                section = line[1..^1].Trim().ToLowerInvariant();
                continue;
            }
            int eq = line.IndexOf('=');
            if (eq <= 0) continue;
            var key = line[..eq].Trim();
            var value = line[(eq + 1)..].Trim();
            var comment = value.IndexOf('#');
            if (comment >= 0) value = value[..comment].Trim();
            if (section == "rules")
            {
                if (rules.ContainsKey(key) && bool.TryParse(value, out var b)) rules[key] = b;
            }
            else if (section == "severity")
            {
                var unquoted = value.Trim('"', '\'');
                if (Rules.All.ContainsKey(key) &&
                    (unquoted == Sev.Error || unquoted == Sev.Warn || unquoted == Sev.Info))
                    severities[key] = unquoted;
            }
        }
        return (rules, severities);
    }

    // ---------- checks driver ----------

    private static string ReadAllText(string path) =>
        File.ReadAllText(path, System.Text.Encoding.UTF8);

    public static List<Finding> RunChecks(string root, List<string> files,
        IReadOnlyDictionary<string, bool> enabled, IReadOnlyDictionary<string, string>? severities = null)
    {
        var findings = new List<Finding>();
        foreach (var path in files)
        {
            string rel;
            var fullRoot = Path.GetFullPath(root);
            var fullPath = Path.GetFullPath(path);
            if (fullPath.StartsWith(fullRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                rel = fullPath[(fullRoot.Length + 1)..].Replace('\\', '/');
            else
                rel = Path.GetFileName(fullPath);
            string text;
            try { text = ReadAllText(fullPath); }
            catch { continue; } // unreadable/binary — never block on tooling failure
            var ext = Path.GetExtension(fullPath).ToLowerInvariant();
            if (ext == ".py") findings.AddRange(Checks.CheckPythonFile(text, rel, enabled));
            else if (Checks.JsExt.Contains(ext)) findings.AddRange(Checks.CheckJsTsFile(text, rel, enabled));
            else if (Checks.GoExt.Contains(ext)) findings.AddRange(Checks.CheckGoFile(text, rel, enabled));
            else if (Checks.JavaExt.Contains(ext)) findings.AddRange(Checks.CheckJavaFile(text, rel, enabled));
        }
        if (severities is { Count: > 0 })
            findings = findings
                .Select(f => severities.TryGetValue(f.Rule, out var sev) ? f with { Severity = sev } : f)
                .ToList();
        return findings;
    }

    // ---------- verdict / counts ----------

    public static Dictionary<string, int> SeverityCounts(List<Finding> findings)
    {
        var counts = new Dictionary<string, int> { [Sev.Error] = 0, [Sev.Warn] = 0, [Sev.Info] = 0 };
        foreach (var f in findings)
            counts[f.Severity] = counts.TryGetValue(f.Severity, out var c) ? c + 1 : 1;
        return counts;
    }

    public static int ExitCode(List<Finding> findings) =>
        findings.Any(f => f.Severity == Sev.Error) ? 1 : 0;

    public static object BuildVerdict(List<string> files, List<Finding> findings) => new
    {
        files_checked = files.Count,
        errors = findings
            .Where(f => f.Severity == Sev.Error)
            .OrderBy(f => f.File, StringComparer.Ordinal)
            .ThenBy(f => f.Line)
            .ThenBy(f => f.Rule, StringComparer.Ordinal)
            .Select(f => new { file = f.File, line = f.Line, rule = f.Rule, message = f.Message })
            .ToList(),
        exit_code = ExitCode(findings),
    };

    // ---------- SARIF 2.1.0 ----------

    public static System.Text.Json.Nodes.JsonObject RenderSarif(List<Finding> findings)
    {
        static string ToSarifLevel(string sev) => sev switch
        {
            Sev.Error => "error",
            Sev.Warn => "warning",
            _ => "note",
        };
        var ruleIds = Rules.All.Keys.ToHashSet(StringComparer.Ordinal);
        var results = new System.Text.Json.Nodes.JsonArray();
        foreach (var f in findings
                     .OrderBy(f => f.File, StringComparer.Ordinal)
                     .ThenBy(f => f.Line)
                     .ThenBy(f => f.Rule, StringComparer.Ordinal))
        {
            results.Add(new System.Text.Json.Nodes.JsonObject
            {
                ["ruleId"] = ruleIds.Contains(f.Rule) || f.Rule.StartsWith("ruff:") ? f.Rule : $"ruff:{f.Rule}",
                ["level"] = ToSarifLevel(f.Severity),
                ["message"] = new System.Text.Json.Nodes.JsonObject { ["text"] = f.Message },
                ["locations"] = new System.Text.Json.Nodes.JsonArray
                {
                    new System.Text.Json.Nodes.JsonObject
                    {
                        ["physicalLocation"] = new System.Text.Json.Nodes.JsonObject
                        {
                            ["artifactLocation"] = new System.Text.Json.Nodes.JsonObject
                            {
                                ["uri"] = f.File.Replace('\\', '/'),
                            },
                            ["region"] = new System.Text.Json.Nodes.JsonObject
                            {
                                ["startLine"] = f.Line,
                            },
                        },
                    },
                },
            });
        }
        var rulesArr = new System.Text.Json.Nodes.JsonArray();
        foreach (var kv in Rules.All.OrderBy(x => x.Key, StringComparer.Ordinal))
            rulesArr.Add(new System.Text.Json.Nodes.JsonObject
            {
                ["id"] = kv.Key,
                ["shortDescription"] = new System.Text.Json.Nodes.JsonObject { ["text"] = kv.Value.Name },
            });
        return new System.Text.Json.Nodes.JsonObject
        {
            ["$schema"] = SarifSchema,
            ["version"] = SarifVersion,
            ["runs"] = new System.Text.Json.Nodes.JsonArray
            {
                new System.Text.Json.Nodes.JsonObject
                {
                    ["tool"] = new System.Text.Json.Nodes.JsonObject
                    {
                        ["driver"] = new System.Text.Json.Nodes.JsonObject
                        {
                            ["name"] = "aicv",
                            ["informationUri"] = "https://github.com/bigpi/ai-code-verifier",
                            ["rules"] = rulesArr,
                        },
                    },
                    ["results"] = results,
                },
            },
        };
    }

    // ---------- GitHub Actions annotations ----------

    public static List<string> RenderAnnotations(List<Finding> findings)
    {
        static string Level(string sev) => sev switch
        {
            Sev.Error => "error",
            Sev.Warn => "warning",
            _ => "notice",
        };
        var outLines = new List<string>();
        foreach (var f in findings.OrderBy(f => f.File, StringComparer.Ordinal)
                                 .ThenBy(f => f.Line).ThenBy(f => f.Rule, StringComparer.Ordinal))
        {
            var msg = f.Message.Replace("%", "%25").Replace("\r", "%0D").Replace("\n", "%0A");
            var file = f.File.Replace('\\', '/');
            outLines.Add($"::{Level(f.Severity)} file={file},line={f.Line}::{f.Rule}: {msg}");
        }
        return outLines;
    }

    // ---------- report artifacts ----------

    public static string RenderMarkdown(string target, List<string> rels, List<Finding> findings, string root)
    {
        var counts = SeverityCounts(findings);
        var lines = new List<string>
        {
            "# aicv verification report",
            "",
            $"- Target: `{target}`",
            $"- Date: {DateTime.UtcNow:yyyy-MM-ddTHH:mm:ssK}",
            $"- Files checked: {rels.Count}",
            $"- Findings: **{counts.GetValueOrDefault(Sev.Error)} errors**, {counts.GetValueOrDefault(Sev.Warn)} warnings",
            $"- Verdict: {(ExitCode(findings) != 0 ? "FAIL" : "PASS")}",
            "",
        };
        if (rels.Count > 0)
        {
            lines.Add("## Files");
            foreach (var rel in rels) lines.Add($"- `{rel}`");
            lines.Add("");
        }
        lines.Add("## Findings");
        if (findings.Count == 0)
        {
            lines.Add("No issues detected.");
            return string.Join("\n", lines) + "\n";
        }
        var byFile = findings.GroupBy(f => f.File).OrderBy(g => g.Key, StringComparer.Ordinal);
        int SevRank(string s) => s switch { Sev.Error => 0, Sev.Warn => 1, Sev.Info => 2, _ => 9 };
        foreach (var group in byFile)
        {
            lines.Add($"### `{group.Key}`");
            foreach (var f in group.OrderBy(f => SevRank(f.Severity)).ThenBy(f => f.Line))
            {
                var icon = f.Severity switch { Sev.Error => "🔴", Sev.Warn => "🟡", Sev.Info => "🔵", _ => "⚪" };
                lines.Add($"- {icon} **[{f.Severity.ToUpperInvariant()}]** line {f.Line} `{f.Rule}`: {f.Message}");
            }
            lines.Add("");
        }
        return string.Join("\n", lines) + "\n";
    }

    public static string SaveReport(string root, string target, List<string> rels, List<Finding> findings)
    {
        var dir = Path.Combine(root, ReportDir);
        Directory.CreateDirectory(dir);
        var payload = new
        {
            target,
            generated_at = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssK"),
            files = rels,
            findings = findings.Select(f => new { f.Rule, f.Severity, f.File, f.Line, f.Message }).ToList(),
            counts = SeverityCounts(findings),
            exit_code = ExitCode(findings),
        };
        var jsonOpts = new System.Text.Json.JsonSerializerOptions
        {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };
        File.WriteAllText(Path.Combine(dir, ReportLatest + ".json"),
            System.Text.Json.JsonSerializer.Serialize(payload, jsonOpts),
            new System.Text.UTF8Encoding(false));
        var md = Path.Combine(dir, ReportLatest + ".md");
        File.WriteAllText(md, RenderMarkdown(target, rels, findings, root), new System.Text.UTF8Encoding(false));
        return md;
    }
}
