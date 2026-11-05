using System.Text;
using System.Text.Json;
using AiCV.Core;

namespace AiCV.Cli;

/// <summary>aicv CLI (C#/.NET port of the Python aicv CLI): check, report,
/// ci, diff, verdict. Machine flags: --json, --sarif, --annotate.</summary>
internal static class Program
{
    private const string Version = "1.0.0";
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private sealed class Args
    {
        public string Command = "";
        public bool Staged;
        public bool NoRuff;
        public bool Json;
        public bool Sarif;
        public bool Annotate;
        public bool Baseline;
        public bool Summary;
        public bool Force;
    }

    private static int Main(string[] argvRaw)
    {
        // Unicode-safe output even when redirected (Windows console codepage
        // would otherwise substitute the em dashes used in finding messages).
        try { Console.OutputEncoding = Encoding.UTF8; } catch { /* non-console host */ }
        var argv = argvRaw.ToList();
        if (argv.Contains("--version"))
        {
            Console.Out.WriteLine($"aicv {Version}");
            return 0;
        }
        if (argv.Count == 0 || (argv[0].StartsWith('-') && argv[0] != "--version"))
        {
            Usage();
            return 2;
        }
        var args = new Args { Command = argv[0] };
        var positional = new List<string>();
        foreach (var a in argv.Skip(1))
        {
            switch (a)
            {
                case "--staged": args.Staged = true; break;
                case "--no-ruff": args.NoRuff = true; break; // accepted for CLI parity; the C# port never invokes ruff
                case "--json": args.Json = true; break;
                case "--sarif": args.Sarif = true; break;
                case "--annotate": args.Annotate = true; break;
                case "--baseline": args.Baseline = true; break;
                case "--summary": args.Summary = true; break;
                case "--force": args.Force = true; break;
                default:
                    if (a.StartsWith("--")) { Usage(); return 2; }
                    positional.Add(a);
                    break;
            }
        }
        var root = Directory.GetCurrentDirectory();
        switch (args.Command)
        {
            case "check": return CmdCheck(args, root);
            case "report": return CmdReport(args, root);
            case "ci": return CmdCi(args, root);
            case "diff": return CmdDiff(args, root, positional);
            case "verdict": return CmdVerdict(args, root);
            case "init": return CmdInit(args, root);
            case "baseline": return CmdBaseline(args, root);
            case "-h": case "--help": case "help": return Help();
            default: Usage(); return 2;
        }
    }

    private static void Usage() => Console.Error.WriteLine(
        "usage: aicv <check|report|ci|diff|verdict|init|baseline> [options]\n" +
        "  check [--staged] [--json] [--sarif] [--baseline]\n" +
        "  report [--json] [--sarif]\n" +
        "  ci [--json] [--sarif] [--annotate]\n" +
        "  diff <ref1> <ref2> [--json] [--sarif] [--annotate]\n" +
        "  verdict [--staged] [--summary]");

    private static int Help() { Usage(); return 0; }

    // ---------- check ----------

    private static int CmdCheck(Args args, string root)
    {
        var files = Engine.ChangedFiles(root, staged: args.Staged);
        if (files.Count == 0)
        {
            var target = args.Staged ? "staged" : "diff HEAD";
            Console.Out.WriteLine(
                "aicv: no changed .py/.js/.ts/.go/.java files for target '" + target +
                "' — nothing to verify.");
            return 0;
        }
        return ScanAndEmit(args, root, files, args.Staged ? "staged" : "diff HEAD");
    }

    private static int CmdCi(Args args, string root)
    {
        var baseRef = Environment.GetEnvironmentVariable("GITHUB_BASE_REF");
        if (string.IsNullOrEmpty(baseRef))
        {
            Console.Error.WriteLine("aicv ci: GITHUB_BASE_REF is not set; falling back to 'origin/main'.");
            baseRef = "origin/main";
        }
        var files = Engine.ChangedFiles(root, baseRef: baseRef);
        if (files.Count == 0)
        {
            Console.Out.WriteLine($"aicv ci: no changed files vs {baseRef} — nothing to verify.");
            return 0;
        }
        return ScanAndEmit(args, root, files, $"ci vs {baseRef}");
    }

    private static int CmdDiff(Args args, string root, List<string> positional)
    {
        if (positional.Count < 2) { Usage(); return 2; }
        var (ref1, ref2) = (positional[0], positional[1]);
        if (ref1 == ref2)
        {
            Console.Out.WriteLine($"aicv diff: both refs are '{ref1}' — nothing to compare.");
            return 2;
        }
        var (rules, severities) = Engine.LoadConfig(root);
        var (findings, rels) = Engine.RunChecksBetween(root, ref1, ref2, rules, severities);
        if (rels.Count == 0)
        {
            Console.Out.WriteLine(
                "aicv diff: no changed .py/.js/.ts/.go/.java files between " +
                $"{ref1}...{ref2} — nothing to verify.");
            return 0;
        }
        return Emit(args, root, rels, findings, $"diff {ref1}...{ref2}");
    }

    private static int ScanAndEmit(Args args, string root, List<string> files, string target)
    {
        var (rules, severities) = Engine.LoadConfig(root);
        var findings = Engine.RunChecks(root, files, rules, severities);
        return Emit(args, root, files.Select(f => Path.GetRelativePath(root, f).Replace('\\', '/')).ToList(),
            findings, target);
    }

    private static int Emit(Args args, string root, List<string> rels, List<Finding> findings, string target)
    {
        if (args.Baseline)
        {
            var keys = LoadBaselineKeys(root);
            if (keys is null)
            {
                Console.Error.WriteLine(
                    "aicv: --baseline set but .aicv/baseline.json not found — run `aicv baseline` first.");
                return 2;
            }
            findings = findings
                .Where(f => !keys.Contains($"{f.File}:{f.Line}:{f.Rule}"))
                .ToList();
        }
        var md = Engine.SaveReport(root, target, rels, findings);
        var counts = new Dictionary<string, int> { ["error"] = 0, ["warning"] = 0 };
        foreach (var f in findings)
            counts[f.Severity] = counts.TryGetValue(f.Severity, out var c) ? c + 1 : 1;
        var human = new List<string>
        {
            $"aicv: checked {rels.Count} file(s) [{target}] — " +
            $"{counts.GetValueOrDefault("error")} error(s), {counts.GetValueOrDefault("warning")} warning(s)",
        };
        human.AddRange(findings.OrderBy(f => f.Severity, StringComparer.Ordinal)
            .ThenBy(f => f.File, StringComparer.Ordinal)
            .ThenBy(f => f.Line)
            .Select(f => $"  [{f.Severity.ToUpperInvariant()}] {f.File}:{f.Line} ({f.Rule}) {f.Message}"));
        human.Add($"report: {md}");
        if (args.Annotate)
        {
            var stream = args.Json ? Console.Error : Console.Out;
            foreach (var ann in Engine.RenderAnnotations(findings))
                stream.WriteLine(ann);
        }
        var rc = Engine.ExitCode(findings);
        if (args.Sarif)
        {
            var sarifPath = Path.Combine(root, Engine.ReportDir, "latest.sarif");
            Directory.CreateDirectory(Path.GetDirectoryName(sarifPath)!);
            File.WriteAllText(sarifPath,
                JsonSerializer.Serialize(Engine.RenderSarif(findings), JsonOpts),
                new UTF8Encoding(false));
            human.Add($"sarif: {sarifPath}");
        }
        if (args.Json)
        {
            Console.Out.WriteLine(JsonSerializer.Serialize(Engine.BuildVerdict(rels, findings), JsonOpts));
            foreach (var line in human) Console.Error.WriteLine(line);
        }
        else
        {
            foreach (var line in human) Console.Out.WriteLine(line);
        }
        return rc;
    }

    // ---------- report ----------

    private static int CmdReport(Args args, string root)
    {
        var name = args.Json ? "latest.json" : args.Sarif ? "latest.sarif" : "latest.md";
        var p = Path.Combine(root, Engine.ReportDir, name);
        if (!File.Exists(p))
        {
            Console.Out.WriteLine($"aicv report: no report found at {p} — run `aicv check` first.");
            return 2;
        }
        Console.Out.WriteLine(File.ReadAllText(p));
        return 0;
    }

    // ---------- verdict ----------

    private static int CmdVerdict(Args args, string root)
    {
        var files = Engine.ChangedFiles(root, staged: args.Staged);
        var target = args.Staged ? "staged" : "diff HEAD";
        if (files.Count == 0)
        {
            Console.Out.WriteLine($"=== AICV VERDICT: PASS | target={target} | files=0 errors=0 warnings=0 ===");
            return 0;
        }
        var (rules, severities) = Engine.LoadConfig(root);
        var findings = Engine.RunChecks(root, files, rules, severities);
        var counts = Engine.SeverityCounts(findings);
        var verdict = Engine.ExitCode(findings) != 0 ? "FAIL" : "PASS";
        Console.Out.WriteLine(
            $"=== AICV VERDICT: {verdict} | target={target} | files={files.Count} " +
            $"errors={counts.GetValueOrDefault(Sev.Error)} warnings={counts.GetValueOrDefault(Sev.Warn)} ===");
        if (!args.Summary)
        {
            foreach (var f in findings.OrderBy(f => f.Severity, StringComparer.Ordinal)
                                       .ThenBy(f => f.File, StringComparer.Ordinal).ThenBy(f => f.Line))
                Console.Out.WriteLine($"[{f.Severity.ToUpperInvariant()}] {f.File}:{f.Line} ({f.Rule}) {f.Message}");
            Console.Out.WriteLine("=== AICV VERDICT END ===");
        }
        return Engine.ExitCode(findings);
    }

    // ---------- init ----------

    private static int CmdInit(Args args, string root)
    {
        var target = Path.Combine(root, ".aicv.toml");
        if (File.Exists(target) && !args.Force)
        {
            Console.Out.WriteLine("aicv init: .aicv.toml already exists — use --force to overwrite.");
            return 2;
        }
        var lines = new List<string>
        {
            "# aicv configuration — generated by `aicv init`.",
            "# Toggle individual rules ([rules]); override per-rule severity ([severity]).",
            "# Missing keys fall back to defaults.",
            "",
            "[rules]",
        };
        foreach (var (rid, spec) in Rules.All.OrderBy(kv => kv.Key, StringComparer.Ordinal))
            lines.Add($"{rid} = {(spec.Default ? "true" : "false")}  # {spec.Name}");
        lines.Add("");
        lines.Add("[severity]");
        lines.Add("# Per-rule severity override: error | warning | info.");
        lines.Add("# error — fails the run (exit code 1); warning/info — report only.");
        lines.Add("# Uncomment a line to override that rule's severity (defaults shown).");
        foreach (var (rid, spec) in Rules.All.OrderBy(kv => kv.Key, StringComparer.Ordinal))
            lines.Add($"# {rid} = \"{spec.Severity}\"");
        File.WriteAllText(target, string.Join("\n", lines) + "\n", new UTF8Encoding(false));
        Console.Out.WriteLine($"aicv init: wrote {target}");
        return 0;
    }

    // ---------- baseline ----------

    private static int CmdBaseline(Args args, string root)
    {
        var files = Engine.ChangedFiles(root, staged: args.Staged);
        if (files.Count == 0)
        {
            var target = args.Staged ? "staged" : "diff HEAD";
            Console.Out.WriteLine(
                "aicv baseline: no changed .py/.js/.ts/.go/.java files for target '" +
                target + "' — nothing to record.");
            return 0;
        }
        var (rules, severities) = Engine.LoadConfig(root);
        var findings = Engine.RunChecks(root, files, rules, severities);
        var dir = Path.Combine(root, Engine.ReportDir);
        Directory.CreateDirectory(dir);
        var payload = new
        {
            generated_at = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssK"),
            findings = findings.Select(f => new
            {
                rule = f.Rule,
                severity = f.Severity,
                file = f.File,
                line = f.Line,
                message = f.Message,
            }).ToList(),
        };
        var p = Path.Combine(dir, "baseline.json");
        File.WriteAllText(p, JsonSerializer.Serialize(payload, JsonOpts), new UTF8Encoding(false));
        var counts = Engine.SeverityCounts(findings);
        Console.Out.WriteLine($"aicv baseline: recorded {findings.Count} finding(s) " +
            $"({counts.GetValueOrDefault(Sev.Error)} error(s), {counts.GetValueOrDefault(Sev.Warn)} warning(s)) -> {p}");
        Console.Out.WriteLine("aicv baseline: `aicv check --baseline` will now fail only on NEW findings.");
        return 0;
    }

    private static HashSet<string>? LoadBaselineKeys(string root)
    {
        var p = Path.Combine(root, Engine.ReportDir, "baseline.json");
        if (!File.Exists(p)) return null;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(p));
            var keys = new HashSet<string>(StringComparer.Ordinal);
            foreach (var el in doc.RootElement.GetProperty("findings").EnumerateArray())
                keys.Add($"{el.GetProperty("file").GetString()}:{el.GetProperty("line").GetInt32()}:{el.GetProperty("rule").GetString()}");
            return keys;
        }
        catch
        {
            return null;
        }
    }
}
