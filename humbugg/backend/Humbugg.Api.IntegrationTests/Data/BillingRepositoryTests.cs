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
    public async Task A_fully_refunded_charge_removes_the_entitlement_and_reverts_the_plan()
    {
        var userId = Uid("user");
        var groupId = Uid("group");
        var purchaseId = Uid("purchase");
        var paidEventId = Uid("event");
        var refundEventId = Uid("event");
        TrackBillingRecords(purchaseId, groupId);
        CleanupItem(Settings.BillingRecordsTable, "record_id", $"event#{paidEventId}");
        CleanupItem(Settings.BillingRecordsTable, "record_id", $"event#{refundEventId}");
        CleanupItem(Settings.GroupsTable, "group_id", groupId);
        CleanupItem(Settings.DrawsTable, "group_id", groupId);

        await Groups.CreateAsync(new GroupRecord(groupId, userId, "Refunded Group", "", null, null, null,
            "USD", PlanCode.Free, null, GroupStatus.Open, "hash", [], Now(), Now()));
        await Repository.ReserveAsync(NewPayment(purchaseId, groupId, userId));
        await Repository.AttachCheckoutAsync(purchaseId, "cs_test_refund", "https://checkout.test/refund");
        await Repository.ApplyEventAsync(new BillingWebhookEvent(paidEventId, purchaseId, groupId, userId,
            CheckoutSessionId: "cs_test_refund", PaymentIntentId: "pi_refund", PriceId: "price_test",
            AmountCents: 1200, Currency: "USD", Environment: "test",
            Status: PaymentStatus.Paid, ReceiptUrl: "https://receipt.test/1", EventCreatedAt: Now()));
        Assert.Equal(PlanCode.Plus, (await Groups.GetAsync(groupId))!.Plan);

        // charge.refunded carries the charge, not the Checkout Session — CheckoutSessionId is
        // null and the match is against the PaymentIntent recorded on the paid event instead.
        var refunded = new BillingWebhookEvent(refundEventId, purchaseId, groupId, userId,
            CheckoutSessionId: null, PaymentIntentId: "pi_refund", PriceId: "price_test",
            AmountCents: 1200, Currency: "USD", Environment: "test",
            Status: PaymentStatus.Refunded, ReceiptUrl: "https://receipt.test/1", EventCreatedAt: Now());

        Assert.True(await Repository.ApplyEventAsync(refunded));

        // The code's documented answer: a full refund removes the entitlement and drops the
        // group back to Free — Plus is not kept once Stripe has given the money back.
        var payment = await Repository.GetLatestForGroupAsync(groupId);
        Assert.Equal(PaymentStatus.Refunded, payment!.Status);
        var group = await Groups.GetAsync(groupId);
        Assert.Equal(PlanCode.Free, group!.Plan);
        Assert.Null(group.EntitlementId);
    }

    [IntegrationFact]
    public async Task A_late_paid_event_still_applies_the_entitlement_after_the_group_has_filled_its_free_cap()
    {
        var userId = Uid("user");
        var groupId = Uid("group");
        var purchaseId = Uid("purchase");
        var eventId = Uid("event");
        TrackBillingRecords(purchaseId, groupId);
        CleanupItem(Settings.BillingRecordsTable, "record_id", $"event#{eventId}");
        CleanupItem(Settings.GroupsTable, "group_id", groupId);
        CleanupItem(Settings.DrawsTable, "group_id", groupId);
        var members = new MembershipRepository(Db, Settings);

        await Groups.CreateAsync(new GroupRecord(groupId, userId, "Capped Group", "", null, null, null,
            "USD", PlanCode.Free, null, GroupStatus.Open, "hash", [], Now(), Now()));
        // Fill the Free cap (6 active participants) directly — PlanCatalog would have refused a
        // 7th join over HTTP while the purchase was still pending, so this is the roster a Free
        // group is actually at when its Plus webhook is running late.
        for (var i = 0; i < 6; i++)
        {
            var record = await members.CreateAsync(groupId, Uid("user"), $"Member {i}", organizer: false);
            CleanupItem(Settings.GroupMembersTable, "member_id", record.MemberId);
        }
        await Repository.ReserveAsync(NewPayment(purchaseId, groupId, userId));
        await Repository.AttachCheckoutAsync(purchaseId, "cs_test_late", "https://checkout.test/late");

        var lateEvent = new BillingWebhookEvent(eventId, purchaseId, groupId, userId,
            CheckoutSessionId: "cs_test_late", PaymentIntentId: "pi_late", PriceId: "price_test",
            AmountCents: 1200, Currency: "USD", Environment: "test",
            Status: PaymentStatus.Paid, ReceiptUrl: "https://receipt.test/1", EventCreatedAt: Now());

        // ApplyEventAsync never reads the roster — the entitlement lands regardless of how full
        // the group already is. It is participant-capacity checks (PlanCatalog, at join time)
        // that read the entitlement, not the other way around, so the group is simply unblocked
        // for its 7th participant onward the moment this transaction commits.
        Assert.True(await Repository.ApplyEventAsync(lateEvent));

        var group = await Groups.GetAsync(groupId);
        Assert.Equal(PlanCode.Plus, group!.Plan);
        Assert.Equal($"plus:{groupId}", group.EntitlementId);
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
