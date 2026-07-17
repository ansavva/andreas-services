using Humbugg.Api.Consumers;
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
        Assert.Equal(["email-status"], ConsumerHost.RegisteredConsumerNames);
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
