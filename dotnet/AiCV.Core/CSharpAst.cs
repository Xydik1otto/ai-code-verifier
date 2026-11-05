using System.Text.RegularExpressions;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace AiCV.Core;

/// <summary>Real AST checks for C# via Roslyn (Microsoft.CodeAnalysis.CSharp).
/// The authoritative implementation for .cs files: findings carry exact
/// row/col taken from syntax nodes, and comments/strings cannot trigger
/// them (unlike the Python-side regex fallback for .cs, which is a
/// documented approximation — see docs/rules.md).</summary>
public static class CSharpAst
{
    private static readonly Regex ShellTarget =
        new(@"(?i)^(cmd|powershell|pwsh|bash|sh|zsh)(\.exe)?$");

    /// <summary>Shell escape flags inside a string literal: "/c", "/k", "-enc".</summary>
    private static readonly Regex ShellFlag =
        new("(?i)\"[^\"]*/[ck]\\b|\"[^\"]*-(c|k|enc)\\b");

    private static readonly Regex SqlToken =
        new(@"(?i)\b(select|insert|update|delete|drop table|union\s+select)\b");

    private static readonly Regex CompilerServicesUsing =
        new(@"(?i)compilerservices|reflection\.emit");

    public static List<Finding> Check(string text, string rel,
        IReadOnlyDictionary<string, bool> enabled)
    {
        var findings = new List<Finding>();
        bool On(string rule) => enabled.TryGetValue(rule, out var on) ? on : true;
        SyntaxTree tree;
        try { tree = CSharpSyntaxTree.ParseText(text); }
        catch { return findings; } // never block a scan on tooling failure

        // syntax gate: real Roslyn parse diagnostics with exact row/col
        if (On("syntax_error"))
        {
            var seen = new HashSet<(int Line, int Col, string Id)>();
            foreach (var d in tree.GetDiagnostics())
            {
                if (d.Severity != DiagnosticSeverity.Error) continue;
                var p = d.Location.GetLineSpan().StartLinePosition;
                var key = (p.Line + 1, p.Character + 1, d.Id);
                if (!seen.Add(key)) continue; // Roslyn may repeat one error twice
                findings.Add(Checks.Mk("syntax_error", Sev.Error, rel, p.Line + 1,
                    $"Roslyn parse: {d.Id} {d.GetMessage()}", p.Character + 1));
            }
        }

        SyntaxNode root;
        try { root = tree.GetRoot(); }
        catch { return findings; }

        foreach (var node in root.DescendantNodes())
        {
            // using System.Runtime.CompilerServices / System.Reflection.Emit —
            // low-level compiler-internals surface in AI-generated code
            if (node is UsingDirectiveSyntax u && On("dangerous_call"))
            {
                var ns = Regex.Replace(u.Name?.ToString() ?? "", @"\s+", "");
                if (CompilerServicesUsing.IsMatch(ns))
                    findings.Add(At(node, "dangerous_call", rel,
                        "using CompilerServices/Reflection.Emit — dynamic code " +
                        "generation surface, ban in AI-generated code"));
            }

            if (node is InvocationExpressionSyntax inv)
            {
                var target = Regex.Replace(DottedName(inv.Expression), @"\s+", "");
                var last = target.Split('.').Last().ToLowerInvariant();

                // dynamic code execution: Roslyn scripting Eval, CodeDom compile
                if (On("dangerous_call") && last is "evaluateasync" or "runasync" or
                    "compileassemblyfromsource" or "compileassemblyfromsourceasync")
                    findings.Add(At(node, "dangerous_call", rel,
                        $"'{target}()' — dynamic code execution (Roslyn Eval / " +
                        "CodeDom compile), ban in AI-generated code"));

                // Process.Start targeting a shell
                if (On("shell_exec") && target.ToLowerInvariant().EndsWith("process.start"))
                {
                    var shell = false;
                    foreach (var arg in inv.ArgumentList.Arguments)
                        if (arg.Expression is LiteralExpressionSyntax lit &&
                            lit.IsKind(SyntaxKind.StringLiteralExpression) &&
                            (ShellTarget.IsMatch(lit.Token.ValueText) ||
                             ShellFlag.IsMatch(lit.Token.ValueText)))
                        { shell = true; break; }
                    if (shell)
                        findings.Add(At(node, "shell_exec", rel,
                            "Process.Start targeting a shell — injection risk, use " +
                            "ProcessStartInfo with argument lists"));
                }

                // SQL built via string.Format("SELECT {0}", ...)
                if (On("sql_string_format") &&
                    target.ToLowerInvariant() == "string.format" &&
                    inv.ArgumentList.Arguments.Count > 1 &&
                    inv.ArgumentList.Arguments[0].Expression is LiteralExpressionSyntax f0 &&
                    f0.IsKind(SyntaxKind.StringLiteralExpression) &&
                    SqlToken.IsMatch(f0.Token.ValueText))
                    findings.Add(At(node, "sql_string_format", rel,
                        "SQL built via string.Format — use parameterized queries"));
            }

            if (node is ObjectCreationExpressionSyntax o && On("dangerous_call"))
            {
                var typeName = Regex.Replace(o.Type.ToString(), @"\s+", "");
                if (Regex.IsMatch(typeName, @"(?i)CSharpCodeProvider$"))
                    findings.Add(At(node, "dangerous_call", rel,
                        $"new {typeName}() — runtime C# compilation (eval-equivalent), " +
                        "ban in AI-generated code"));
            }

            // UseShellExecute = true — shell resolution on ProcessStartInfo
            if (node is AssignmentExpressionSyntax a && On("shell_exec") &&
                a.Left is IdentifierNameSyntax id &&
                id.Identifier.ValueText == "UseShellExecute" &&
                a.Right is LiteralExpressionSyntax litR &&
                litR.IsKind(SyntaxKind.TrueLiteralExpression))
                findings.Add(At(node, "shell_exec", rel,
                    "UseShellExecute = true — shell resolution on the launched " +
                    "process; prefer an explicit executable + argument list"));

            // SQL built via interpolation: $"SELECT ... {var}"
            if (node is InterpolatedStringExpressionSyntax interp && On("sql_string_format"))
            {
                var hasHole = interp.DescendantNodes().Any(n => n is InterpolationSyntax);
                var staticText = string.Concat(interp.ChildNodes()
                    .OfType<InterpolatedStringTextSyntax>()
                    .Select(t => t.TextToken.ValueText));
                if (hasHole && SqlToken.IsMatch(staticText))
                    findings.Add(At(node, "sql_string_format", rel,
                        "SQL built via string interpolation — use parameterized queries"));
            }

            // SQL built via concatenation: "SELECT ..." + var
            if (node is BinaryExpressionSyntax b && On("sql_string_format") &&
                b.IsKind(SyntaxKind.AddExpression))
            {
                var l = b.Left as LiteralExpressionSyntax;
                var r = b.Right as LiteralExpressionSyntax;
                bool IsSqlLit(LiteralExpressionSyntax? x) =>
                    x != null && x.IsKind(SyntaxKind.StringLiteralExpression) &&
                    SqlToken.IsMatch(x.Token.ValueText);
                if ((IsSqlLit(l) && r == null) || (IsSqlLit(r) && l == null))
                    findings.Add(At(node, "sql_string_format", rel,
                        "SQL built via string concatenation — use parameterized queries"));
            }
        }
        return findings;
    }

    private static string DottedName(ExpressionSyntax? e)
    {
        if (e is IdentifierNameSyntax id) return id.Identifier.ValueText;
        if (e is MemberAccessExpressionSyntax ma)
        {
            var left = DottedName(ma.Expression);
            var name = ma.Name.Identifier.ValueText;
            return left.Length == 0 ? name : left + "." + name;
        }
        return e?.ToString() ?? "";
    }

    /// <summary>Finding at the exact start position of a syntax node (row/col
    /// from the AST — the advantage over line-level regex scanning).</summary>
    private static Finding At(SyntaxNode node, string rule, string rel, string message)
    {
        var p = node.GetLocation().GetLineSpan().StartLinePosition;
        return Checks.Mk(rule, Sev.Error, rel, p.Line + 1, message, p.Character + 1);
    }
}
