using System.Text.RegularExpressions;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// The PR workflow's smoke step starts the API and must therefore supply every
/// table variable <see cref="HumbuggSettings.FromEnvironment"/> requires.
/// </summary>
/// <remarks>
/// Three PRs in the Plus stack (#142, #143, #147) each added a RequiredTable and
/// updated humbugg-prod.yaml without touching humbugg-pr.yml. Every one of them
/// failed identically: the container threw at startup, and because the smoke step
/// ran it under `docker run --rm`, the container was reaped before `docker logs`
/// could read it, so CI reported "No such container" and named nothing. Three
/// separate branches sat red for weeks on a one-line omission.
///
/// Asserted against the workflow text rather than by running it, so the failure
/// arrives in the unit suite naming the missing variable, instead of as a dead
/// container in a job that takes minutes to reach.
/// </remarks>
public sealed class CiSmokeEnvironmentTests
{
    [Fact]
    public void TheSmokeStepSuppliesEveryRequiredTableVariable()
    {
        var required = RequiredTableVariables();
        var supplied = SmokeStepVariables();

        Assert.NotEmpty(required);

        var missing = required.Except(supplied).OrderBy(name => name, StringComparer.Ordinal).ToArray();

        Assert.True(
            missing.Length == 0,
            $"HumbuggSettings.FromEnvironment() requires {string.Join(", ", missing)}, which the " +
            "smoke step in .github/workflows/humbugg-pr.yml does not set. The API throws at startup " +
            "when a required table variable is missing, so the container dies before /health answers. " +
            "Add a matching '-e NAME=ci-smoke-...' line to that step. Adding it to humbugg-prod.yaml " +
            "alone is what left #142, #143 and #147 red.");
    }

    // Quoted literals only: the declaration `RequiredTable(string variable)` and the
    // prose above it both name the method without one, and neither is a call site.
    private static HashSet<string> RequiredTableVariables()
    {
        var program = Path.Combine(BackendRoot(), "Humbugg.Api", "Program.cs");
        var source = WithoutCommentLines(File.ReadAllLines(program));

        return Regex.Matches(source, @"RequiredTable\(""([A-Z0-9_]+)""\)")
            .Select(match => match.Groups[1].Value)
            .ToHashSet(StringComparer.Ordinal);
    }

    private static HashSet<string> SmokeStepVariables()
    {
        var workflow = Path.Combine(RepositoryRoot(), ".github", "workflows", "humbugg-pr.yml");
        var text = File.ReadAllText(workflow);

        // Scoped to the smoke container's own run block. The file configures several
        // other containers, and counting their variables would let a genuinely missing
        // one pass because some unrelated step happened to name it.
        var start = text.IndexOf("--name humbugg-backend-smoke", StringComparison.Ordinal);
        Assert.True(start >= 0, "Could not find the humbugg-backend-smoke container in humbugg-pr.yml.");

        var end = text.IndexOf("humbugg-backend:ci-verify", start, StringComparison.Ordinal);
        Assert.True(end > start, "Could not find the end of the smoke container's docker run block.");

        return Regex.Matches(text[start..end], @"-e\s+([A-Z0-9_]+)=")
            .Select(match => match.Groups[1].Value)
            .ToHashSet(StringComparer.Ordinal);
    }

    private static string WithoutCommentLines(IEnumerable<string> lines) =>
        string.Join('\n', lines.Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));

    private static string BackendRoot() => FindAncestorContaining("Humbugg.Api");

    private static string RepositoryRoot() => FindAncestorContaining(Path.Combine(".github", "workflows"));

    private static string FindAncestorContaining(string relativePath)
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (Directory.Exists(Path.Combine(directory.FullName, relativePath)))
                return directory.FullName;
            directory = directory.Parent;
        }
        throw new DirectoryNotFoundException($"Could not locate an ancestor containing '{relativePath}'.");
    }
}
