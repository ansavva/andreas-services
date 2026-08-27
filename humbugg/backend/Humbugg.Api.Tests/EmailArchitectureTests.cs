using Humbugg.Api.Consumers;
using Humbugg.Api.Consumers.EmailStatus;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class EmailArchitectureTests
{
    [Fact]
    public void EmailFoldersAreOrganizedByResponsibility()
    {
        var api = Path.Combine(BackendRoot(), "Humbugg.Api");
        var email = Path.Combine(api, "Services", "Email");

        Assert.True(Directory.Exists(Path.Combine(email, "Core")));
        Assert.True(Directory.Exists(Path.Combine(email, "Adapters", "Aws")));
        Assert.True(Directory.Exists(Path.Combine(email, "Adapters", "Http")));
        Assert.True(Directory.Exists(Path.Combine(email, "Adapters", "Memory")));
        Assert.True(Directory.Exists(Path.Combine(email, "StatusProcessing")));
        Assert.False(Directory.Exists(Path.Combine(api, "Email")));
    }

    [Fact]
    public void ApplicationConsumersAreDiscoverableFromOneDirectoryAndRegistry()
    {
        var consumers = Path.Combine(BackendRoot(), "Humbugg.Api", "Consumers");

        Assert.True(Directory.Exists(consumers));
        Assert.True(File.Exists(Path.Combine(consumers, "ConsumerHost.cs")));
        Assert.True(Directory.Exists(Path.Combine(consumers, "EmailStatus")));
        Assert.True(Directory.Exists(Path.Combine(consumers, "Reminders")));
        Assert.Equal(["email-status", "reminders"], ConsumerHost.RegisteredConsumerNames);
    }

    [Fact]
    public void EmailCoreDoesNotDependOnAdaptersOrAws()
    {
        var core = Path.Combine(
            BackendRoot(),
            "Humbugg.Api",
            "Services",
            "Email",
            "Core");

        foreach (var file in Directory.EnumerateFiles(core, "*.cs"))
        {
            var source = File.ReadAllText(file);
            Assert.DoesNotContain(".Adapters", source, StringComparison.Ordinal);
            Assert.DoesNotContain("Amazon.", source, StringComparison.Ordinal);
        }
    }

    /// <summary>
    /// A consumer reads only the configuration it uses.
    /// </summary>
    /// <remarks>
    /// This is the regression guard for #387. The email-status consumer called
    /// <c>HumbuggSettings.FromEnvironment()</c>, which is the API's contract and since
    /// #239 requires all eight DynamoDB table variables. The deploy sets two on that
    /// Lambda, so it threw at init on every invocation: the feedback queue was never
    /// drained and every humbugg prod deploy went red for six days.
    ///
    /// Asserted against the source rather than by starting the consumer, because the
    /// failure was at construction and the fix is that the call is not there at all.
    /// </remarks>
    [Fact]
    public void ConsumersDoNotReadTheApisFullSettingsContract()
    {
        var consumers = Path.Combine(BackendRoot(), "Humbugg.Api", "Consumers");

        foreach (var file in Directory.EnumerateFiles(consumers, "*.cs", SearchOption.AllDirectories))
        {
            // Comment lines are stripped first: the rule is about what the code calls,
            // and the comment explaining why it must not call this names it verbatim.
            var source = string.Join(
                '\n',
                File.ReadAllLines(file).Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));
            Assert.DoesNotContain("HumbuggSettings.FromEnvironment()", source, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void ARequiredTableNamesTheVariableItIsMissing()
    {
        const string variable = "HUMBUGG_TEST_ONLY_MISSING_TABLE";
        Environment.SetEnvironmentVariable(variable, null);

        var error = Assert.Throws<InvalidOperationException>(
            () => AwsLambdaEmailStatusConsumer.RequiredTable(variable));

        Assert.Contains(variable, error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ARequiredTableTrimsTheValueItReads()
    {
        const string variable = "HUMBUGG_TEST_ONLY_PRESENT_TABLE";
        Environment.SetEnvironmentVariable(variable, "  humbugg-prod-email-messages  ");
        try
        {
            Assert.Equal(
                "humbugg-prod-email-messages",
                AwsLambdaEmailStatusConsumer.RequiredTable(variable));
        }
        finally
        {
            Environment.SetEnvironmentVariable(variable, null);
        }
    }

    private static string BackendRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (Directory.Exists(Path.Combine(directory.FullName, "Humbugg.Api")))
                return directory.FullName;
            directory = directory.Parent;
        }
        throw new DirectoryNotFoundException("Could not locate the Humbugg backend source.");
    }
}
