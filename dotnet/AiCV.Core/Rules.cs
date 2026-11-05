namespace AiCV.Core;

/// <summary>Rule registry: id -> (name, default on/off, builtin severity).
/// Mirrors aicv.checks.RULES in the Python implementation.</summary>
public static class Rules
{
    public sealed record RuleSpec(string Name, bool Default, string Severity);

    public static readonly IReadOnlyDictionary<string, RuleSpec> All =
        new Dictionary<string, RuleSpec>(StringComparer.Ordinal)
        {
            ["dangerous_call"] = new("Dynamic code execution (eval/exec/compile)", true, Sev.Error),
            ["shell_exec"] = new("Shell execution from strings", true, Sev.Error),
            ["remote_exec"] = new("Remote/shell code execution patterns", true, Sev.Error),
            ["hardcoded_secret"] = new("Hardcoded secrets in source", true, Sev.Error),
            ["sql_string_format"] = new("SQL built via string formatting", true, Sev.Error),
            ["dead_import"] = new("Imported but never used", false, Sev.Warn),
            ["syntax_error"] = new("File does not parse/compile", true, Sev.Error),
            ["todo_fixme"] = new("TODO/FIXME markers left in code", true, Sev.Warn),
        };

    public static Dictionary<string, bool> Defaults() =>
        All.ToDictionary(kv => kv.Key, kv => kv.Value.Default, StringComparer.Ordinal);
}
