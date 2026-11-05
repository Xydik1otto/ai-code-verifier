using System.Text.RegularExpressions;
using System.Text;
namespace AiCV.Core;

/// <summary>Built-in heuristic checks, ported 1:1 from aicv.checks (Python).
/// Zero external dependencies: line/regex scanning plus a lightweight
/// brace/bracket balance gate — the same philosophy as the Python original,
/// minus the full AST (see docs/rules.md for the documented deltas).</summary>
public static class Checks
{
    public static Finding Mk(string rule, string severity, string file, int line, string message) =>
        new(rule, severity, file, line, message);

    // ---------- shared regex patterns (mirrors of the Python originals) ----------

    private static readonly (Regex Pat, string Label)[] SecretPatterns =
    {
        new(new Regex(@"(?i)\b(api[_-]?key|apikey)\s*[:=]\s*['""][A-Za-z0-9_\-]{16,}['""]"), "API key literal"),
        new(new Regex(@"(?i)\b(secret[_-]?key|auth[_-]?token|access[_-]?token)\s*[:=]\s*['""][^'""]{12,}['""]"), "secret/token literal"),
        new(new Regex(@"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
        new(new Regex(@"(?i)\baws_access_key_id\s*[:=]\s*['""]AKIA[0-9A-Z]{16}['""]"), "AWS access key"),
        new(new Regex(@"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
        new(new Regex(@"(?i)\bBearer\s+[A-Za-z0-9_\-\.=]{20,}\b"), "Bearer token"),
        new(new Regex(@"(?i)\b(password|passwd)\s*[:=]\s*['""][^'""]{8,}['""]"), "password literal"),
        new(new Regex(@"\b(sk|pk)-[A-Za-z0-9]{20,}\b"), "Stripe-style key"),
        new(new Regex(@"\bghp_[A-Za-z0-9]{30,}\b"), "GitHub token"),
        // Go-specific: short-declaration secrets (password := "...")
        new(new Regex(@"(?i)\b(password|passwd|secret|token|api[_-]?key|apikey|credential)\s*:=\s*""[^""]{8,}"""), "secret literal (Go :=)"),
        // Java-specific: String password = "...", private final String API_KEY = "..."
        new(new Regex(@"(?i)\bString\s+\w*(password|passwd|secret|token|api[_-]?key|apikey|credential)\w*\s*=\s*""[^""]{8,}"""), "secret literal (String field)"),
        new(new Regex(@"(?i)\b(private|protected|public|static|final)\s+(?:[\w<>\[\],\s]+\s+)?\w*(password|passwd|secret|token|api[_-]?key|apikey)\w*\s*=\s*""[^""]{8,}"""), "secret literal (field initializer)"),
    };

    /// <summary>Download-and-execute / shell-escape one-liners.</summary>
    private static readonly Regex RemoteExecLine = new(
        @"(?i)\b(curl|wget)\b[^#\n]*\|\s*(sudo\s+)?(ba|z|da|k)?sh\b" +
        @"|\bbash\s+-c\b|\bsh\s+-c\b|\bpowershell(\.exe)?\s+(-enc|-EncodedCommand|-[iI]nputFormat\s+None)" +
        @"|\bbase64\s+-d\b|\beval\s*\(\s*\$(|\bexec\s*\(\s*__import__)");

    /// <summary>SQL keywords inside a string-formatting context.</summary>
    private static readonly Regex SqlToken =
        new(@"(?i)\b(select|insert|update|delete|drop table|union\s+select)\b");

    private static readonly Regex TodoMarker = new(@"(?i)\b(TODO|FIXME)\b(?::|\b)");

    /// <summary>`# aicv: ignore` (all rules on the line) or `# aicv: ignore[r1, r2]`.</summary>
    private static readonly Regex SuppressRe =
        new(@"#\s*aicv:\s*ignore(?:\[(?<rules>[^\]]*)\])?");

    public const string SuppressAll = "*";

    private static readonly string[] PyExt = { ".py" };
    public static readonly string[] JsExt = { ".js", ".ts", ".mjs", ".jsx", ".tsx" };
    public static readonly string[] GoExt = { ".go" };
    public static readonly string[] JavaExt = { ".java" };
    public static readonly HashSet<string> ScanExts =
        new(PyExt.Concat(JsExt).Concat(GoExt).Concat(JavaExt), StringComparer.OrdinalIgnoreCase);

    private static string[] SplitLines(string text) =>
        text.Replace("\r\n", "\n").Replace("\r", "\n").Split('\n');

    // ---------- suppression ----------

    /// <summary>line number -> SuppressAll or set of rule ids suppressed on that line.</summary>
    public static Dictionary<int, object> SuppressionMap(string text)
    {
        var map = new Dictionary<int, object>();
        int lineno = 0;
        foreach (var line in SplitLines(text))
        {
            lineno++;
            var m = SuppressRe.Match(line);
            if (!m.Success) continue;
            var rules = (m.Groups["rules"].Success ? m.Groups["rules"].Value : "").Trim();
            if (rules.Length == 0)
                map[lineno] = SuppressAll;
            else
                map[lineno] = rules.Split(',')
                    .Select(r => r.Trim())
                    .Where(r => r.Length > 0)
                    .ToHashSet(StringComparer.Ordinal);
        }
        return map;
    }

    /// <summary>Drop findings suppressed by an `# aicv: ignore` comment on their line.</summary>
    public static List<Finding> FilterSuppressed(List<Finding> findings, string text)
    {
        var map = SuppressionMap(text);
        if (map.Count == 0) return findings;
        var keep = new List<Finding>();
        foreach (var f in findings)
        {
            if (!map.TryGetValue(f.Line, out var rules)) { keep.Add(f); continue; }
            if (rules is string s && s == SuppressAll) continue;
            if (rules is HashSet<string> set && set.Contains(f.Rule)) continue;
            keep.Add(f);
        }
        return keep;
    }

    // ---------- text-level checks ----------

    public static List<Finding> CheckRemoteExecLines(string text, string rel)
    {
        var list = new List<Finding>();
        int lineno = 0;
        foreach (var line in SplitLines(text))
        {
            lineno++;
            if (RemoteExecLine.IsMatch(line))
                list.Add(Mk("remote_exec", Sev.Error, rel, lineno,
                    "Download-and-execute / shell-escape pattern — remote code execution risk"));
        }
        return list;
    }

    public static List<Finding> CheckHardcodedSecrets(string text, string rel, bool skipDummy)
    {
        var list = new List<Finding>();
        int lineno = 0;
        foreach (var line in SplitLines(text))
        {
            lineno++;
            var low = line.ToLowerInvariant();
            if (low.Contains("example") || low.Contains("xxx") || (skipDummy && low.Contains("dummy")))
                continue;
            foreach (var (pat, label) in SecretPatterns)
                if (pat.IsMatch(line))
                    list.Add(Mk("hardcoded_secret", Sev.Error, rel, lineno,
                        $"Possible {label} hardcoded in source"));
        }
        return list;
    }

    public static List<Finding> CheckTodoFixme(string text, string rel)
    {
        var list = new List<Finding>();
        int lineno = 0;
        foreach (var line in SplitLines(text))
        {
            lineno++;
            var m = TodoMarker.Match(line);
            if (m.Success)
                list.Add(Mk("todo_fixme", Sev.Warn, rel, lineno,
                    $"{m.Groups[1].Value.ToUpperInvariant()} marker left in code — " +
                    "resolve or move to the tracker before merge"));
        }
        return list;
    }

    // ---------- Python: AST-lite (strings/comments stripped, then regex) ----------

    /// <summary>Blank out # comments, triple-quoted and single-quoted literals so
    /// call-pattern matching and bracket counting see only code structure.</summary>
    public static string StripPythonCode(string text)
    {
        var sb = new StringBuilder(text.Length);
        int i = 0, n = text.Length;
        while (i < n)
        {
            char ch = text[i];
            // triple-quoted literal (optionally f/r/b prefixed — the prefix
            // chars were already emitted as ordinary code, which is fine)
            if (ch == '"' || ch == '\'')
            {
                bool triple = i + 2 < n && text[i + 1] == ch && text[i + 2] == ch;
                char quote = ch;
                if (triple)
                {
                    i += 3;
                    int end = text.IndexOf(new string(quote, 3), i, StringComparison.Ordinal);
                    int stop = end == -1 ? n : end;
                    for (int j = i; j < stop; j++) sb.Append(text[j] == '\n' ? '\n' : ' ');
                    sb.Append(' ');
                    i = end == -1 ? n : end + 3;
                    continue;
                }
                i++;
                while (i < n)
                {
                    if (text[i] == '\\' && i + 1 < n) { i += 2; continue; }
                    if (text[i] == quote) { i++; break; }
                    if (text[i] == '\n') break; // unterminated single-line literal
                    i++;
                }
                sb.Append(' ');
                continue;
            }
            if (ch == '#')
            {
                while (i < n && text[i] != '\n') i++;
                continue; // newline handled on the next iteration
            }
            sb.Append(ch);
            i++;
        }
        return sb.ToString();
    }

    private static readonly Regex DangerousCall =
        new(@"\b(eval|exec|compile|__import__)\s*\(");
    private static readonly Regex ShellExecCall =
        new(@"\b(os\.(?:system|popen)|subprocess\.(?:getoutput|getstatusoutput))\s*\(");
    private static readonly Regex SubprocessStringArg =
        new(@"\bsubprocess\.(call|run|Popen|check_output|check_call)\s*\(\s*['""][^'""]*['""]\s*[,)]");
    private static readonly Regex ShellTrue =
        new(@"\bsubprocess\.(call|run|Popen|check_output|check_call)\s*\([^)]*shell\s*=\s*True\b");

    public static List<Finding> CheckDangerousCalls(string stripped, string rel)
    {
        var list = new List<Finding>();
        int lineno = 0;
        foreach (var line in SplitLines(stripped))
        {
            lineno++;
            var dm = DangerousCall.Match(line);
            if (dm.Success)
                list.Add(Mk("dangerous_call", Sev.Error, rel, lineno,
                    $"Use of '{dm.Groups[1].Value}()' — dynamic code execution, ban in AI-generated code"));
            var sm = ShellExecCall.Match(line);
            if (sm.Success)
                list.Add(Mk("shell_exec", Sev.Error, rel, lineno,
                    $"'{sm.Groups[1].Value}()' executes a shell string — injection risk"));
        }
        return list;
    }

    public static List<Finding> CheckShellTrue(string text, string rel)
    {
        var list = new List<Finding>();
        int lineno = 0;
        foreach (var line in SplitLines(text))
        {
            lineno++;
            if (ShellTrue.IsMatch(line))
                list.Add(Mk("remote_exec", Sev.Error, rel, lineno,
                    "subprocess(..., shell=True) — shell injection risk"));
            // first argument is a plain string literal (Python checks the AST:
            // args[0] must be a Constant str — the `[,)]` lookahead mirrors that)
            if (SubprocessStringArg.IsMatch(line))
                list.Add(Mk("shell_exec", Sev.Warn, rel, lineno,
                    "subprocess called with a bare string (shell=False assumed) — prefer list argv"));
        }
        return list;
    }

    private static readonly Regex FStringSql = new(
        @"(?i)f['""].*?\b(select|insert|update|delete|drop table|union\s+select)\b");
    private static readonly Regex PercentSql = new(
        @"(?i)['""][^'""]*\b(select|insert|update|delete|drop table|union\s+select)\b[^'""]*['""]\s*%");
    private static readonly Regex FormatSql = new(
        @"(?i)['""][^'""]*\b(select|insert|update|delete|drop table|union\s+select)\b[^'""]*['""]\s*\.format\s*\(");

    public static List<Finding> CheckSqlStringFormat(string text, string rel)
    {
        var list = new List<Finding>();
        int lineno = 0;
        foreach (var line in SplitLines(text))
        {
            lineno++;
            if (FStringSql.IsMatch(line) || PercentSql.IsMatch(line) || FormatSql.IsMatch(line))
                list.Add(Mk("sql_string_format", Sev.Error, rel, lineno,
                    "SQL built via string formatting — use parameterized queries"));
        }
        return list;
    }

    // ---------- dead_import (opt-in) ----------

    private static readonly Regex ImportStmt =
        new(@"^\s*(?:import\s+(?<mods>[\w.,\s]+)|from\s+[\w.]+\s+import\s+(?<names>[\w*,.\s()\\]+))");

    public static List<Finding> CheckDeadImports(string text, string rel)
    {
        var stripped = StripPythonCode(text);
        var lines = SplitLines(stripped);
        var imported = new List<(string Name, int Line)>();
        var importLines = new HashSet<int>();
        int lineno = 0;
        foreach (var line in lines)
        {
            lineno++;
            var m = ImportStmt.Match(line);
            if (!m.Success) continue;
            importLines.Add(lineno);
            var group = m.Groups["mods"].Success ? m.Groups["mods"] : m.Groups["names"];
            foreach (var part in group.Value.Split(','))
            {
                var name = part.Trim().Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                if (name.Length == 0) continue;
                var alias = name[^1]; // trailing "as alias" wins
                if (alias == "*") continue;
                imported.Add((alias.Split('.')[0], lineno));
            }
        }
        var usedBody = new StringBuilder();
        lineno = 0;
        foreach (var line in lines)
        {
            lineno++;
            if (importLines.Contains(lineno)) continue;
            usedBody.Append(line).Append('\n');
        }
        var list = new List<Finding>();
        foreach (var (name, line) in imported)
            if (!Regex.IsMatch(usedBody.ToString(), $@"\b{Regex.Escape(name)}\b"))
                list.Add(Mk("dead_import", Sev.Warn, rel, line, $"Imported '{name}' is never used"));
        return list;
    }

    // ---------- lightweight syntax gate (brace/bracket balance) ----------

    private static readonly Dictionary<char, char> Brackets = new()
    { ['('] = ')', ['['] = ']', ['{'] = '}' };

    /// <summary>Blank out // and /* */ comments and "..."/`...`/'...' literals
    /// (the shared JS/TS/Go/Java stripper from the Python original).</summary>
    public static string StripCommentsAndStrings(string text)
    {
        var sb = new StringBuilder(text.Length);
        int i = 0, n = text.Length;
        while (i < n)
        {
            char ch = text[i];
            char nxt = i + 1 < n ? text[i + 1] : '\0';
            if (ch == '/' && nxt == '/')
            {
                while (i < n && text[i] != '\n') i++;
                if (i < n) sb.Append('\n');
            }
            else if (ch == '/' && nxt == '*')
            {
                int end = text.IndexOf("*/", i + 2, StringComparison.Ordinal);
                int stop = end == -1 ? n : end;
                for (int j = i; j < stop; j++)
                    if (text[j] == '\n') sb.Append('\n');
                i = end == -1 ? n : end + 2;
            }
            else if (ch == '"' || ch == '\'' || ch == '`')
            {
                char quote = ch;
                i++;
                while (i < n)
                {
                    if (text[i] == '\\') { i += 2; continue; }
                    if (text[i] == quote) { i++; break; }
                    if (text[i] == '\n') break; // unterminated single-line literal
                    i++;
                }
                sb.Append(' ');
            }
            else
            {
                sb.Append(ch);
                i++;
            }
        }
        return sb.ToString();
    }

    public static List<Finding> CheckBracketBalance(string text, string rel)
    {
        var stripped = StripCommentsAndStrings(text);
        var stack = new List<(char Open, int Line)>();
        int lineno = 1;
        foreach (var ch in stripped)
        {
            if (ch == '\n') lineno++;
            else if (Brackets.ContainsKey(ch)) stack.Add((ch, lineno));
            else if (Brackets.ContainsValue(ch))
            {
                if (stack.Count == 0 || Brackets[stack[^1].Open] != ch)
                    return new List<Finding>
                    {
                        Mk("syntax_error", Sev.Error, rel, lineno,
                            $"Unbalanced '{ch}' — bracket/brace mismatch " +
                            "(pre-scan; run gofmt/javac for a full parse)")
                    };
                stack.RemoveAt(stack.Count - 1);
            }
        }
        if (stack.Count > 0)
        {
            var (open, ln) = stack[^1];
            return new List<Finding>
            {
                Mk("syntax_error", Sev.Error, rel, ln,
                    $"Unclosed '{open}' — bracket/brace mismatch at end of file " +
                    "(pre-scan; run gofmt/javac for a full parse)")
            };
        }
        return new List<Finding>();
    }

    // ---------- per-language entry points ----------

    public static List<Finding> CheckPythonFile(string text, string rel, IReadOnlyDictionary<string, bool> enabled)
    {
        var findings = new List<Finding>();
        var stripped = StripPythonCode(text);
        if (enabled.TryGetValue("syntax_error", out var se) ? se : true)
            findings.AddRange(CheckBracketBalance(stripped, rel));
        if ((enabled.TryGetValue("dangerous_call", out var dc) ? dc : true) ||
            (enabled.TryGetValue("shell_exec", out var sh) ? sh : true) ||
            (enabled.TryGetValue("sql_string_format", out var sq) ? sq : true))
        {
            findings.AddRange(CheckDangerousCalls(stripped, rel));
            findings.AddRange(CheckSqlStringFormat(text, rel));
        }
        if (enabled.TryGetValue("remote_exec", out var re) ? re : true)
        {
            findings.AddRange(CheckRemoteExecLines(text, rel));
            findings.AddRange(CheckShellTrue(text, rel));
        }
        if (enabled.TryGetValue("hardcoded_secret", out var hs) ? hs : true)
            findings.AddRange(CheckHardcodedSecrets(text, rel, skipDummy: true));
        if (enabled.TryGetValue("dead_import", out var di) && di)
            findings.AddRange(CheckDeadImports(text, rel));
        if (enabled.TryGetValue("todo_fixme", out var tf) ? tf : true)
            findings.AddRange(CheckTodoFixme(text, rel));
        return FilterSuppressed(findings, text);
    }

    public static List<Finding> CheckJsTsFile(string text, string rel, IReadOnlyDictionary<string, bool> enabled)
    {
        var findings = new List<Finding>();
        if (enabled.TryGetValue("hardcoded_secret", out var hs) ? hs : true)
            findings.AddRange(CheckHardcodedSecrets(text, rel, skipDummy: false));
        if (enabled.TryGetValue("remote_exec", out var re) ? re : true)
            findings.AddRange(CheckRemoteExecLines(text, rel));
        if (enabled.TryGetValue("todo_fixme", out var tf) ? tf : true)
            findings.AddRange(CheckTodoFixme(text, rel));
        return FilterSuppressed(findings, text);
    }

    private static List<Finding> CheckTextLanguage(string text, string rel, IReadOnlyDictionary<string, bool> enabled)
    {
        var findings = new List<Finding>();
        if (enabled.TryGetValue("hardcoded_secret", out var hs) ? hs : true)
            findings.AddRange(CheckHardcodedSecrets(text, rel, skipDummy: false));
        if (enabled.TryGetValue("remote_exec", out var re) ? re : true)
            findings.AddRange(CheckRemoteExecLines(text, rel));
        if (enabled.TryGetValue("todo_fixme", out var tf) ? tf : true)
            findings.AddRange(CheckTodoFixme(text, rel));
        return findings;
    }

    public static List<Finding> CheckGoFile(string text, string rel, IReadOnlyDictionary<string, bool> enabled)
    {
        var findings = CheckTextLanguage(text, rel, enabled);
        if (enabled.TryGetValue("syntax_error", out var se) ? se : true)
            findings.AddRange(CheckBracketBalance(text, rel));
        return FilterSuppressed(findings, text);
    }

    public static List<Finding> CheckJavaFile(string text, string rel, IReadOnlyDictionary<string, bool> enabled)
    {
        var findings = CheckTextLanguage(text, rel, enabled);
        if (enabled.TryGetValue("syntax_error", out var se) ? se : true)
            findings.AddRange(CheckBracketBalance(text, rel));
        return FilterSuppressed(findings, text);
    }
}
