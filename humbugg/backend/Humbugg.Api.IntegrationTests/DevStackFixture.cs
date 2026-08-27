using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;

using Xunit;

namespace Humbugg.Api.IntegrationTests;

[CollectionDefinition("dev-stack")]
public sealed class DevStackCollection : ICollectionFixture<DevStackFixture>;

/// <summary>
/// The one connection to the per-machine dev stack. Reads the same
/// <c>humbugg/backend/.env</c> that <c>dev-up-backend.sh</c> feeds the backend container, so
/// the tests exercise the exact tables the local backend uses — real AWS, real GSIs, real
/// marshalling, under the developer's own credentials. Nothing here ever points at prod:
/// the .env is written by <c>dev-aws-setup.sh</c> from the machine-scoped Terraform outputs.
/// </summary>
public sealed class DevStackFixture : IAsyncLifetime
{
    public HumbuggSettings Settings { get; private set; } = null!;
    public IAmazonDynamoDB Db { get; private set; } = null!;

    public async ValueTask InitializeAsync()
    {
        ApplyDevEnv();
        try
        {
            Settings = HumbuggSettings.FromEnvironment();
        }
        catch (InvalidOperationException error)
        {
            throw new InvalidOperationException(
                "humbugg/backend/.env is missing a value the integration tier needs — it is probably " +
                "stale. Re-run humbugg/scripts/dev-aws-setup.sh to refresh it from Terraform outputs. " +
                $"Underlying error: {error.Message}", error);
        }

        Db = new AmazonDynamoDBClient(new AmazonDynamoDBConfig
        {
            RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(Settings.AwsRegion)
        });

        // One old table and one newer table: if either is absent the stack itself is stale,
        // and the fix is a Terraform converge, not a test change.
        await AssertTableExists(Settings.ProfilesTable);
        await AssertTableExists(Settings.WishesTable);
    }

    public ValueTask DisposeAsync()
    {
        Db.Dispose();
        return ValueTask.CompletedTask;
    }

    private async Task AssertTableExists(string table)
    {
        try
        {
            await Db.DescribeTableAsync(table);
        }
        catch (ResourceNotFoundException)
        {
            throw new InvalidOperationException(
                $"DynamoDB table '{table}' does not exist in the dev stack. " +
                "Run humbugg/scripts/dev-aws-setup.sh to converge this machine's resources.");
        }
    }

    private static void ApplyDevEnv() => DevEnv.Apply();
}

/// <summary>
/// Loads <c>humbugg/backend/.env</c> into the process environment — only the configuration the
/// settings record reads. Credential selection stays with the ambient environment (the
/// default profile per the repo rule), so AWS_PROFILE and ASPNETCORE_* lines are skipped.
/// Shared by the Data fixture and the HTTP fixture, which both need the app's own settings.
/// </summary>
internal static class DevEnv
{
    public static void Apply()
    {
        var envFile = Path.Combine(BackendDirectory(), ".env");
        if (!File.Exists(envFile))
            throw new InvalidOperationException(
                $"{envFile} not found. The integration tier runs against the per-machine dev " +
                "stack; run humbugg/scripts/dev-aws-setup.sh to provision it and write the env file.");

        foreach (var line in File.ReadAllLines(envFile))
        {
            var trimmed = line.Trim();
            if (trimmed.Length == 0 || trimmed.StartsWith('#')) continue;
            var separator = trimmed.IndexOf('=');
            if (separator <= 0) continue;
            var key = trimmed[..separator].Trim();
            if (key is "AWS_PROFILE" || key.StartsWith("ASPNETCORE_", StringComparison.Ordinal)) continue;
            var value = trimmed[(separator + 1)..].Trim();
            // An empty value (DYNAMODB_ENDPOINT_URL=) unsets rather than sets: the settings
            // record treats null and empty alike, and clearing keeps a stale shell export
            // from silently pointing the suite somewhere else.
            Environment.SetEnvironmentVariable(key, value.Length == 0 ? null : value);
        }
    }

    private static string BackendDirectory()
    {
        // Walk up from the test assembly (bin/<config>/net10.0) to the directory holding the
        // solution file — counted once here, the way studio's tests/paths.py counts once.
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            if (File.Exists(Path.Combine(dir.FullName, "Humbugg.slnx"))) return dir.FullName;
        }
        throw new InvalidOperationException("Could not locate humbugg/backend (no Humbugg.slnx above the test assembly).");
    }
}

/// <summary>
/// Base class for every test in this assembly: joins the dev-stack collection and carries
/// best-effort cleanup so the shared per-machine tables do not accumulate test residue.
/// Every id a test writes starts with <c>itest-</c>, so stray rows are recognizable and
/// <c>dev-aws-reset.sh</c> remains the blunt fallback.
/// </summary>
[Collection("dev-stack")]
public abstract class DevStackTest(DevStackFixture stack) : IAsyncLifetime
{
    private readonly List<Func<Task>> _undo = [];

    protected DevStackFixture Stack { get; } = stack;
    protected IAmazonDynamoDB Db => Stack.Db;
    protected HumbuggSettings Settings => Stack.Settings;

    protected static string Uid(string prefix) => $"itest-{prefix}-{Guid.NewGuid():N}";
    protected static string Now() => DateTimeOffset.UtcNow.ToString("O");

    /// <summary>Registers a delete for a single-attribute-keyed item, run when the test ends.</summary>
    protected void CleanupItem(string table, string keyName, string keyValue) =>
        _undo.Add(() => Db.DeleteItemAsync(table, new Dictionary<string, AttributeValue>
        {
            [keyName] = new(keyValue)
        }));

    /// <summary>Registers a delete for a composite-keyed item, run when the test ends.</summary>
    protected void CleanupItem(string table, string hashName, string hashValue, string rangeName, string rangeValue) =>
        _undo.Add(() => Db.DeleteItemAsync(table, new Dictionary<string, AttributeValue>
        {
            [hashName] = new(hashValue),
            [rangeName] = new(rangeValue)
        }));

    protected void Cleanup(Func<Task> action) => _undo.Add(action);

    /// <summary>
    /// Polls until the assertion passes — for reads through a GSI, which is eventually
    /// consistent: a query issued immediately after a write may legitimately miss the row.
    /// </summary>
    protected static async Task Eventually(Func<Task> assertion, int timeoutSeconds = 10)
    {
        var deadline = DateTimeOffset.UtcNow.AddSeconds(timeoutSeconds);
        while (true)
        {
            try
            {
                await assertion();
                return;
            }
            catch (Xunit.Sdk.XunitException) when (DateTimeOffset.UtcNow < deadline)
            {
                await Task.Delay(250);
            }
        }
    }

    public ValueTask InitializeAsync() => ValueTask.CompletedTask;

    public async ValueTask DisposeAsync()
    {
        for (var i = _undo.Count - 1; i >= 0; i--)
        {
            try
            {
                await _undo[i]();
            }
            catch (AmazonDynamoDBException)
            {
                // Best-effort: cleanup must never turn a passing test red or mask a failure.
            }
        }
    }
}
