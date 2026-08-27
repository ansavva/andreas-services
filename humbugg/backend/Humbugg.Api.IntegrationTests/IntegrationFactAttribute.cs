using System.Runtime.CompilerServices;
using Xunit;

namespace Humbugg.Api.IntegrationTests;

// The integration tier's single gate, mirrored on studio's STUDIO_INTEGRATION env var.
// The project boundary is the tier — everything in this assembly talks to the per-machine
// dev stack in real AWS — and this attribute is what keeps a plain
// `dotnet test Humbugg.slnx` (CI included) reporting skips instead of credential failures.
// The flag is exported in exactly one place: humbugg/scripts/dev-test-integration.sh.
internal sealed class IntegrationFactAttribute : FactAttribute
{
    public IntegrationFactAttribute(
        [CallerFilePath] string? sourceFilePath = null,
        [CallerLineNumber] int sourceLineNumber = -1)
        : base(sourceFilePath, sourceLineNumber)
    {
        if (Environment.GetEnvironmentVariable("HUMBUGG_INTEGRATION") != "1")
            Skip = "integration tier: run humbugg/scripts/dev-test-integration.sh";
    }
}
