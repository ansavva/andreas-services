using Xunit;

namespace Humbugg.Api.Tests;

// DynamoDB table names are per-environment: prod, each developer's isolated dev
// stack, and CI all name them differently. HumbuggSettings.FromEnvironment()
// therefore refuses to guess — a missing variable is a misconfigured
// environment, and failing at startup beats pointing the service at a table
// that does not exist and discovering it on the first write.
public class HumbuggSettingsTests
{
    private static readonly string[] RequiredTableVariables =
    [
        "HUMBUGG_PROFILES_TABLE",
        "HUMBUGG_GROUPS_TABLE",
        "HUMBUGG_GROUPMEMBERS_TABLE",
        "HUMBUGG_DRAWS_TABLE",
        "HUMBUGG_AUDIT_EVENTS_TABLE",
        "HUMBUGG_ANALYTICS_EVENTS_TABLE",
        "HUMBUGG_EMAIL_MESSAGES_TABLE",
        "HUMBUGG_BILLING_TABLE",
    ];

    [Fact]
    public void ReadsEveryTableNameFromTheEnvironment()
    {
        WithTablesSet(() =>
        {
            var settings = HumbuggSettings.FromEnvironment();

            Assert.Equal("set-HUMBUGG_PROFILES_TABLE", settings.ProfilesTable);
            Assert.Equal("set-HUMBUGG_GROUPS_TABLE", settings.GroupsTable);
            Assert.Equal("set-HUMBUGG_GROUPMEMBERS_TABLE", settings.GroupMembersTable);
            Assert.Equal("set-HUMBUGG_DRAWS_TABLE", settings.DrawsTable);
            Assert.Equal("set-HUMBUGG_AUDIT_EVENTS_TABLE", settings.AuditEventsTable);
            Assert.Equal("set-HUMBUGG_ANALYTICS_EVENTS_TABLE", settings.AnalyticsEventsTable);
            Assert.Equal("set-HUMBUGG_EMAIL_MESSAGES_TABLE", settings.EmailMessagesTable);
            Assert.Equal("set-HUMBUGG_BILLING_TABLE", settings.BillingRecordsTable);
        });
    }

    [Theory]
    [InlineData("HUMBUGG_PROFILES_TABLE")]
    [InlineData("HUMBUGG_GROUPS_TABLE")]
    [InlineData("HUMBUGG_GROUPMEMBERS_TABLE")]
    [InlineData("HUMBUGG_DRAWS_TABLE")]
    [InlineData("HUMBUGG_AUDIT_EVENTS_TABLE")]
    [InlineData("HUMBUGG_ANALYTICS_EVENTS_TABLE")]
    [InlineData("HUMBUGG_EMAIL_MESSAGES_TABLE")]
    [InlineData("HUMBUGG_BILLING_TABLE")]
    public void ThrowsWhenATableVariableIsMissing(string missing)
    {
        WithTablesSet(() =>
        {
            Environment.SetEnvironmentVariable(missing, null);

            var error = Assert.Throws<InvalidOperationException>(HumbuggSettings.FromEnvironment);

            // The message has to name the offending variable — a generic
            // "configuration error" sends the reader hunting through eight.
            Assert.Contains(missing, error.Message, StringComparison.Ordinal);
        });
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void TreatsBlankAsMissing(string blank)
    {
        WithTablesSet(() =>
        {
            Environment.SetEnvironmentVariable("HUMBUGG_BILLING_TABLE", blank);

            var error = Assert.Throws<InvalidOperationException>(HumbuggSettings.FromEnvironment);

            Assert.Contains("HUMBUGG_BILLING_TABLE", error.Message, StringComparison.Ordinal);
        });
    }

    // Sets every required table variable, runs the body, and always restores the
    // previous values — these are process-global, so leaking one would silently
    // change the behaviour of whatever test ran next.
    private static void WithTablesSet(Action body)
    {
        var previous = RequiredTableVariables
            .ToDictionary(name => name, Environment.GetEnvironmentVariable, StringComparer.Ordinal);
        try
        {
            foreach (var name in RequiredTableVariables)
            {
                Environment.SetEnvironmentVariable(name, $"set-{name}");
            }

            body();
        }
        finally
        {
            foreach (var (name, value) in previous)
            {
                Environment.SetEnvironmentVariable(name, value);
            }
        }
    }
}
