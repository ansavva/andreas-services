using Xunit;

namespace Humbugg.Api.Tests;

public sealed class EmailArchitectureTests
{
    [Fact]
    public void EmailFoldersAreOrganizedByResponsibility()
    {
        var email = Path.Combine(BackendRoot(), "Humbugg.Api", "Email");

        Assert.True(Directory.Exists(Path.Combine(email, "Core")));
        Assert.True(Directory.Exists(Path.Combine(email, "Adapters", "Aws")));
        Assert.True(Directory.Exists(Path.Combine(email, "Adapters", "Http")));
        Assert.True(Directory.Exists(Path.Combine(email, "Adapters", "Memory")));
        Assert.True(Directory.Exists(Path.Combine(email, "StatusProcessing")));
        Assert.False(Directory.Exists(Path.Combine(email, "Local")));
        Assert.False(Directory.Exists(Path.Combine(email, "Production")));
        Assert.False(Directory.Exists(Path.Combine(email, "Entrypoints")));
        Assert.False(Directory.Exists(Path.Combine(email, "Functions")));
    }

    [Fact]
    public void EmailCoreDoesNotDependOnAdaptersOrAws()
    {
        var core = Path.Combine(BackendRoot(), "Humbugg.Api", "Email", "Core");

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
