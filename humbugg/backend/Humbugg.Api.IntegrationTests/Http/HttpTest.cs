using Amazon.DynamoDBv2.Model;
using System.Text;
using System.Text.Json;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

/// <summary>Base for the HTTP tier: one shared in-process app, best-effort dev-stack cleanup.</summary>
[Collection("dev-stack-http")]
public abstract class HttpTest(ApiFixture api) : IAsyncLifetime
{
    private readonly List<Func<Task>> _undo = [];

    protected ApiFixture Api { get; } = api;

    protected static string Uid(string prefix) => $"itest-{prefix}-{Guid.NewGuid():N}";

    protected void CleanupItem(string table, string keyName, string keyValue) =>
        _undo.Add(() => Api.Db.DeleteItemAsync(table, new Dictionary<string, AttributeValue>
        {
            [keyName] = new(keyValue)
        }));

    protected void Cleanup(Func<Task> action) => _undo.Add(action);

    protected static StringContent Json(string body) => new(body, Encoding.UTF8, "application/json");

    protected static async Task<JsonElement> ReadJson(HttpResponseMessage response)
    {
        var body = await response.Content.ReadAsStringAsync();
        return JsonDocument.Parse(body).RootElement.Clone();
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
            catch (Exception)
            {
                // Best-effort: cleanup must never turn a passing test red or mask a failure.
            }
        }
    }
}
