namespace Humbugg.Api.Email;

internal sealed class CapturingEmailTransport : IEmailTransport
{
    private readonly List<TransactionalEmail> messages = [];
    private readonly Lock sync = new();

    public IReadOnlyList<TransactionalEmail> Messages
    {
        get
        {
            lock (sync) return messages.ToArray();
        }
    }

    Task<string> IEmailTransport.SendAsync(TransactionalEmail email, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (sync) messages.Add(email);
        return Task.FromResult($"capture-{email.MessageId}");
    }
}

internal sealed class InMemoryEmailDeliveryLedger : IEmailDeliveryLedger
{
    private readonly Dictionary<string, DeliveryState> deliveries = [];
    private readonly Lock sync = new();

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

    public Task MarkSentAsync(string messageId, string providerMessageId, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (sync) deliveries[messageId] = DeliveryState.Sent;
        return Task.CompletedTask;
    }

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
