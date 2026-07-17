using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Services.Email.Adapters.Memory;

/// <summary>
/// Captures rendered messages inside the process so automated tests can inspect them
/// without making network calls or delivering real email.
/// </summary>
internal sealed class CapturingEmailTransport : IEmailTransport
{
    private readonly List<TransactionalEmail> messages = [];
    private readonly Lock sync = new();

    /// <summary>Gets an immutable snapshot of the messages captured so far.</summary>
    public IReadOnlyList<TransactionalEmail> Messages
    {
        get
        {
            lock (sync) return messages.ToArray();
        }
    }

    /// <inheritdoc />
    Task<string> IEmailTransport.SendAsync(TransactionalEmail email, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (sync) messages.Add(email);
        return Task.FromResult($"capture-{email.MessageId}");
    }
}

/// <summary>
/// Provides process-local delivery reservations for automated tests and capture mode.
/// State intentionally disappears when the process exits.
/// </summary>
internal sealed class InMemoryEmailDeliveryLedger : IEmailDeliveryLedger
{
    private readonly Dictionary<string, DeliveryState> deliveries = [];
    private readonly Lock sync = new();

    /// <inheritdoc />
    public Task<bool> TryBeginAsync(TransactionalEmail email, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (sync)
        {
            if (deliveries.TryGetValue(email.MessageId, out var state) && state != DeliveryState.Failed)
                return Task.FromResult(false);

            deliveries[email.MessageId] = DeliveryState.Sending;
            return Task.FromResult(true);
        }
    }

    /// <inheritdoc />
    public Task MarkAcceptedAsync(string messageId, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (sync) deliveries[messageId] = DeliveryState.Sent;
        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task MarkFailedAsync(string messageId, CancellationToken cancellationToken)
    {
        lock (sync) deliveries[messageId] = DeliveryState.Failed;
        return Task.CompletedTask;
    }

    private enum DeliveryState
    {
        Sending,
        Sent,
        Failed
    }
}
