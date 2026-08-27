using Xunit;

namespace Humbugg.Api.IntegrationTests;

// Deliberately an ordinary [Fact]: this test always runs, in CI included.
//
// It exists for two reasons. First, it pins the gate: [IntegrationFact] must skip
// exactly when HUMBUGG_INTEGRATION is unset, and this is the only place that behavior
// is asserted rather than assumed. Second, it keeps the assembly from reporting
// "zero tests ran" — Microsoft.Testing.Platform treats an all-skipped module as a
// failed run, so without one ungated test a plain `dotnet test Humbugg.slnx` on a
// machine without the flag would go red for the wrong reason.
public sealed class GateTests
{
    [Fact]
    public void The_gate_follows_the_environment_flag()
    {
        var attribute = new IntegrationFactAttribute();
        if (Environment.GetEnvironmentVariable("HUMBUGG_INTEGRATION") == "1")
            Assert.Null(attribute.Skip);
        else
            Assert.Contains("dev-test-integration.sh", attribute.Skip);
    }
}
