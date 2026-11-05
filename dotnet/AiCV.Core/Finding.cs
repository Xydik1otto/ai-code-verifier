namespace AiCV.Core;

/// <summary>One verification finding. Field names mirror the Python engine's
/// finding dicts (rule/severity/file/line/message) so JSON verdicts stay
/// structurally identical between the two implementations.</summary>
public sealed record Finding(string Rule, string Severity, string File, int Line, string Message);

public static class Sev
{
    public const string Error = "error";
    public const string Warn = "warning";
    public const string Info = "info";
}
