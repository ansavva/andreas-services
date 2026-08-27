using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class BillingRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private BillingRepository Repository => new(Db, Settings);
    private GroupRepository Groups => new(Db, Settings);

    private PaymentRecord NewPayment(string purchaseId, string groupId, string userId) => new(
        purchaseId, groupId, userId, CheckoutSessionId: "", CheckoutUrl: "",
        PaymentIntentId: null, PriceId: "price_test", AmountCents: 1200, Currency: "USD",
        Environment: "test", Status: PaymentStatus.Pending, ReceiptUrl: null,
        CreatedAt: Now(), UpdatedAt: Now());

    private void TrackBillingRecords(string purchaseId, string groupId)
    {
        CleanupItem(Settings.BillingRecordsTable, "record_id", $"payment#{purchaseId}");
        CleanupItem(Settings.BillingRecordsTable, "record_id", $"active#{groupId}");
    }

    [IntegrationFact]
    public async Task Reserve_wins_once_per_group()
    {
        var groupId = Uid("group");
        var purchaseA = Uid("purchase");
        var purchaseB = Uid("purchase");
        TrackBillingRecords(purchaseA, groupId);
        CleanupItem(Settings.BillingRecordsTable, "record_id", $"payment#{purchaseB}");

        Assert.True(await Repository.ReserveAsync(NewPayment(purchaseA, groupId, "user-1")));
        // The active# pointer already exists, so a concurrent purchase for the same group loses.
        Assert.False(await Repository.ReserveAsync(NewPayment(purchaseB, groupId, "user-1")));
    }

    [IntegrationFact]
    public async Task AttachCheckout_fills_the_empty_session_exactly_once()
    {
        var groupId = Uid("group");
        var purchaseId = Uid("purchase");
        TrackBillingRecords(purchaseId, groupId);
        await Repository.ReserveAsync(NewPayment(purchaseId, groupId, "user-1"));

        await Repository.AttachCheckoutAsync(purchaseId, "cs_test_123", "https://checkout.test/cs_test_123");
        var payment = await Repository.GetLatestForGroupAsync(groupId);
        Assert.Equal("cs_test_123", payment!.CheckoutSessionId);
        Assert.Equal(PaymentStatus.Pending, payment.Status);

        // The condition requires an empty checkout_session_id, so a second attach is refused.
        await Assert.ThrowsAsync<Amazon.DynamoDBv2.Model.ConditionalCheckFailedException>(
            () => Repository.AttachCheckoutAsync(purchaseId, "cs_test_456", "https://checkout.test/other"));
    }

    [IntegrationFact]
    public async Task A_paid_event_upgrades_the_group_and_is_idempotent_by_event_id()
    {
        var userId = Uid("user");
        var groupId = Uid("group");
        var purchaseId = Uid("purchase");
        var eventId = Uid("event");
        TrackBillingRecords(purchaseId, groupId);
        CleanupItem(Settings.BillingRecordsTable, "record_id", $"event#{eventId}");
        CleanupItem(Settings.GroupsTable, "group_id", groupId);
        CleanupItem(Settings.DrawsTable, "group_id", groupId);

        await Groups.CreateAsync(new GroupRecord(groupId, userId, "Paid Group", "", null, null, null,
            "USD", PlanCode.Free, null, GroupStatus.Open, "hash", [], Now(), Now()));
        await Repository.ReserveAsync(NewPayment(purchaseId, groupId, userId));
        await Repository.AttachCheckoutAsync(purchaseId, "cs_test_evt", "https://checkout.test/evt");

        var paidEvent = new BillingWebhookEvent(eventId, purchaseId, groupId, userId,
            CheckoutSessionId: "cs_test_evt", PaymentIntentId: "pi_test", PriceId: "price_test",
            AmountCents: 1200, Currency: "USD", Environment: "test",
            Status: PaymentStatus.Paid, ReceiptUrl: "https://receipt.test/1", EventCreatedAt: Now());

        Assert.True(await Repository.ApplyEventAsync(paidEvent));

        var payment = await Repository.GetLatestForGroupAsync(groupId);
        Assert.Equal(PaymentStatus.Paid, payment!.Status);
        Assert.Equal("https://receipt.test/1", payment.ReceiptUrl);
        var group = await Groups.GetAsync(groupId);
        Assert.Equal(PlanCode.Plus, group!.Plan);
        Assert.Equal($"plus:{groupId}", group.EntitlementId);

        // Stripe redelivers webhooks; the event# row makes the second apply a recognized duplicate.
        Assert.False(await Repository.ApplyEventAsync(paidEvent));
    }

    [IntegrationFact]
    public async Task An_event_for_a_mismatched_reservation_is_rejected()
    {
        var groupId = Uid("group");
        var purchaseId = Uid("purchase");
        TrackBillingRecords(purchaseId, groupId);
        await Repository.ReserveAsync(NewPayment(purchaseId, groupId, "user-1"));

        var tampered = new BillingWebhookEvent(Uid("event"), purchaseId, groupId, "user-1",
            CheckoutSessionId: null, PaymentIntentId: null, PriceId: "price_test",
            AmountCents: 99_00, // does not match the reserved 1200
            Currency: "USD", Environment: "test", Status: PaymentStatus.Paid,
            ReceiptUrl: null, EventCreatedAt: Now());

        var error = await Assert.ThrowsAsync<ApiException>(() => Repository.ApplyEventAsync(tampered));
        Assert.Equal(400, error.StatusCode);
    }
}
