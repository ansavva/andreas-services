using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Services.Email.Adapters.Aws;
using Humbugg.Api.Services.Email.Core;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class EmailDeliveryLedgerTests(DevStackFixture stack) : DevStackTest(stack)
{
    private DynamoDbEmailDeliveryLedger Ledger => new(Db, Settings);

    private static TransactionalEmail NewEmail(string messageId) => new(
        messageId, EmailCategory.Invitation, "invitee@example.test",
        "You are invited", "<p>hi</p>", "hi");

    [IntegrationFact]
    public async Task The_reservation_admits_one_sender_until_it_fails()
    {
        var messageId = Uid("msg");
        CleanupItem(Settings.EmailMessagesTable, "message_id", messageId);
        var email = NewEmail(messageId);

        Assert.True(await Ledger.TryBeginAsync(email, TestContext.Current.CancellationToken));
        // Reserved and submitting: a duplicate send attempt must lose.
        Assert.False(await Ledger.TryBeginAsync(email, TestContext.Current.CancellationToken));

        await Ledger.MarkFailedAsync(messageId, TestContext.Current.CancellationToken);
        // A failed message may be retried, and the attempt counter keeps the history.
        Assert.True(await Ledger.TryBeginAsync(email, TestContext.Current.CancellationToken));

        var row = await Db.GetItemAsync(Settings.EmailMessagesTable,
            new Dictionary<string, AttributeValue> { ["message_id"] = new(messageId) });
        Assert.Equal("submitting", row.Item["status"].S);
        Assert.Equal("2", row.Item["attempts"].N);
        Assert.Equal("invitation", row.Item["category"].S);
        Assert.True(long.Parse(row.Item["expires_at"].N) > DateTimeOffset.UtcNow.ToUnixTimeSeconds());
    }

    [IntegrationFact]
    public async Task Accepted_is_terminal_for_new_reservations()
    {
        var messageId = Uid("msg");
        CleanupItem(Settings.EmailMessagesTable, "message_id", messageId);
        var email = NewEmail(messageId);

        Assert.True(await Ledger.TryBeginAsync(email, TestContext.Current.CancellationToken));
        await Ledger.MarkAcceptedAsync(messageId, TestContext.Current.CancellationToken);

        Assert.False(await Ledger.TryBeginAsync(email, TestContext.Current.CancellationToken));
        var row = await Db.GetItemAsync(Settings.EmailMessagesTable,
            new Dictionary<string, AttributeValue> { ["message_id"] = new(messageId) });
        Assert.Equal("accepted", row.Item["status"].S);
    }

    [IntegrationFact]
    public async Task Status_updates_require_an_existing_reservation()
    {
        await Assert.ThrowsAsync<ConditionalCheckFailedException>(
            () => Ledger.MarkAcceptedAsync("itest-msg-never-reserved", TestContext.Current.CancellationToken));
    }
}
