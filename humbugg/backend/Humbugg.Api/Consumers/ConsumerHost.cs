using Humbugg.Api.Consumers.EmailStatus;

namespace Humbugg.Api.Consumers;

internal static class ConsumerHost
{
    private const string ConsumerEnvironmentVariable = "HUMBUGG_CONSUMER";
    private static readonly IReadOnlyDictionary<string, Func<Task>> Consumers =
        new Dictionary<string, Func<Task>>(StringComparer.OrdinalIgnoreCase)
        {
            [AwsLambdaEmailStatusConsumer.ConsumerName] =
                AwsLambdaEmailStatusConsumer.RunAsync
        };

    internal static IReadOnlyCollection<string> RegisteredConsumerNames =>
        Consumers.Keys.ToArray();

    public static bool IsConsumerProcess =>
        !string.IsNullOrWhiteSpace(
            Environment.GetEnvironmentVariable(ConsumerEnvironmentVariable));

    public static Task RunConfiguredAsync()
    {
        var name = Environment.GetEnvironmentVariable(ConsumerEnvironmentVariable);
        if (string.IsNullOrWhiteSpace(name))
            throw new InvalidOperationException(
                $"{ConsumerEnvironmentVariable} is required for a consumer process.");
        if (!Consumers.TryGetValue(name, out var run))
        {
            throw new InvalidOperationException(
                $"Unknown consumer '{name}'. Registered consumers: " +
                string.Join(", ", Consumers.Keys.Order(StringComparer.Ordinal)));
        }
        return run();
    }
}
