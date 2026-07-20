using Humbugg.Api.Consumers.EmailStatus;
using Humbugg.Api.Consumers.Reminders;

namespace Humbugg.Api.Consumers;

/// <summary>
/// Selects and starts the background consumer assigned to the current Lambda process.
/// This is the single registry for all Humbugg consumers.
/// </summary>
internal static class ConsumerHost
{
    private const string ConsumerEnvironmentVariable = "HUMBUGG_CONSUMER";
    private static readonly IReadOnlyDictionary<string, Func<Task>> Consumers =
        new Dictionary<string, Func<Task>>(StringComparer.OrdinalIgnoreCase)
        {
            [AwsLambdaEmailStatusConsumer.ConsumerName] =
                AwsLambdaEmailStatusConsumer.RunAsync,
            [AwsLambdaReminderConsumer.ConsumerName] =
                AwsLambdaReminderConsumer.RunAsync
        };

    /// <summary>
    /// Gets the names accepted by <c>HUMBUGG_CONSUMER</c>.
    /// </summary>
    internal static IReadOnlyCollection<string> RegisteredConsumerNames =>
        Consumers.Keys.ToArray();

    /// <summary>
    /// Gets whether this process was configured to host a background consumer instead
    /// of the HTTP API.
    /// </summary>
    public static bool IsConsumerProcess =>
        !string.IsNullOrWhiteSpace(
            Environment.GetEnvironmentVariable(ConsumerEnvironmentVariable));

    /// <summary>
    /// Runs the consumer named by <c>HUMBUGG_CONSUMER</c>.
    /// </summary>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the environment variable is missing or names an unregistered consumer.
    /// </exception>
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
