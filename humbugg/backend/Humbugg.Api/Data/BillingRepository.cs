using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal interface IBillingRepository
{
    Task<bool> ReserveAsync(PaymentRecord payment, CancellationToken cancellationToken = default);
    Task AttachCheckoutAsync(
        string purchaseId,
        string checkoutSessionId,
        string checkoutUrl,
        CancellationToken cancellationToken = default);
    Task<PaymentRecord?> GetLatestForGroupAsync(string groupId, CancellationToken cancellationToken = default);
    Task<bool> ApplyEventAsync(BillingWebhookEvent billingEvent, CancellationToken cancellationToken = default);
}

internal sealed class BillingRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IBillingRepository
{
    public async Task<bool> ReserveAsync(PaymentRecord payment, CancellationToken cancellationToken = default)
    {
        try
        {
            await db.TransactWriteItemsAsync(new TransactWriteItemsRequest
            {
                TransactItems =
                [
                    new()
                    {
                        Put = new Put
                        {
                            TableName = settings.BillingRecordsTable,
                            Item = Write(payment),
                            ConditionExpression = "attribute_not_exists(record_id)",
                        },
                    },
                    new()
                    {
                        Put = new Put
                        {
                            TableName = settings.BillingRecordsTable,
                            Item = new()
                            {
                                ["record_id"] = DynamoValues.S($"active#{payment.GroupId}"),
                                ["record_type"] = DynamoValues.S("active_purchase"),
                                ["group_id"] = DynamoValues.S(payment.GroupId),
                                ["purchase_id"] = DynamoValues.S(payment.PurchaseId),
                                ["created_at"] = DynamoValues.S(payment.CreatedAt),
                            },
                            ConditionExpression = "attribute_not_exists(record_id)",
                        },
                    },
                ],
            }, cancellationToken);
            return true;
        }
        catch (TransactionCanceledException)
        {
            return false;
        }
    }

    public Task AttachCheckoutAsync(
        string purchaseId,
        string checkoutSessionId,
        string checkoutUrl,
        CancellationToken cancellationToken = default) =>
        db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.BillingRecordsTable,
            Key = new() { ["record_id"] = DynamoValues.S($"payment#{purchaseId}") },
            UpdateExpression = "SET checkout_session_id = :session, checkout_url = :url, updated_at = :now",
            ConditionExpression =
                "attribute_exists(record_id) AND #status = :pending AND checkout_session_id = :empty",
            ExpressionAttributeNames = new() { ["#status"] = "status" },
            ExpressionAttributeValues = new()
            {
                [":session"] = DynamoValues.S(checkoutSessionId),
                [":url"] = DynamoValues.S(checkoutUrl),
                [":now"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O")),
                [":pending"] = DynamoValues.S("pending"),
                [":empty"] = DynamoValues.S(""),
            },
        }, cancellationToken);

    public async Task<PaymentRecord?> GetLatestForGroupAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var active = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.BillingRecordsTable,
            Key = new() { ["record_id"] = DynamoValues.S($"active#{groupId}") },
            ConsistentRead = true,
        }, cancellationToken);
        if (active.IsItemSet)
        {
            var current = await db.GetItemAsync(new GetItemRequest
            {
                TableName = settings.BillingRecordsTable,
                Key = new()
                {
                    ["record_id"] = DynamoValues.S($"payment#{active.Item.String("purchase_id")}"),
                },
                ConsistentRead = true,
            }, cancellationToken);
            if (current.IsItemSet) return Read(current.Item);
        }
        var response = await db.QueryAsync(new QueryRequest
        {
            TableName = settings.BillingRecordsTable,
            IndexName = "group_id-index",
            KeyConditionExpression = "group_id = :group",
            ExpressionAttributeValues = new() { [":group"] = DynamoValues.S(groupId) },
        }, cancellationToken);
        return response.Items
            .Where(item => item.String("record_type") == "payment")
            .Select(Read)
            .OrderByDescending(item => item.CreatedAt, StringComparer.Ordinal)
            .FirstOrDefault();
    }

    public async Task<bool> ApplyEventAsync(BillingWebhookEvent billingEvent, CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var paymentResponse = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.BillingRecordsTable,
            Key = new() { ["record_id"] = DynamoValues.S($"payment#{billingEvent.PurchaseId}") },
            ConsistentRead = true,
        }, cancellationToken);
        if (!paymentResponse.IsItemSet)
            throw ApiException.Conflict("The Stripe event arrived before its Humbugg purchase was reserved.");
        var payment = Read(paymentResponse.Item);
        ValidateEvent(payment, billingEvent);
        var nextStatus = NextStatus(payment.Status, billingEvent.Status);

        var paymentValues = new Dictionary<string, AttributeValue>
        {
            [":group"] = DynamoValues.S(billingEvent.GroupId),
            [":user"] = DynamoValues.S(billingEvent.UserId),
            [":status"] = DynamoValues.S(Status(nextStatus)),
            [":current"] = DynamoValues.S(Status(payment.Status)),
            [":now"] = DynamoValues.S(now),
            [":eventCreated"] = DynamoValues.S(billingEvent.EventCreatedAt),
            [":price"] = DynamoValues.S(billingEvent.PriceId),
            [":amount"] = DynamoValues.N(billingEvent.AmountCents),
            [":currency"] = DynamoValues.S(billingEvent.Currency),
            [":environment"] = DynamoValues.S(billingEvent.Environment),
        };
        var paymentSet = new List<string>
        {
            "#status = :status",
            "updated_at = :now",
            "last_event_created_at = :eventCreated",
        };
        AddOptional(paymentSet, paymentValues, "checkout_session_id", ":session", billingEvent.CheckoutSessionId);
        AddOptional(paymentSet, paymentValues, "payment_intent_id", ":intent", billingEvent.PaymentIntentId);
        AddOptional(paymentSet, paymentValues, "receipt_url", ":receipt", billingEvent.ReceiptUrl);

        var items = new List<TransactWriteItem>
        {
            new()
            {
                Put = new Put
                {
                    TableName = settings.BillingRecordsTable,
                    Item = new()
                    {
                        ["record_id"] = DynamoValues.S($"event#{billingEvent.EventId}"),
                        ["record_type"] = DynamoValues.S("event"),
                        ["stripe_event_id"] = DynamoValues.S(billingEvent.EventId),
                        ["created_at"] = DynamoValues.S(now),
                    },
                    ConditionExpression = "attribute_not_exists(record_id)",
                },
            },
            new()
            {
                Update = new Update
                {
                    TableName = settings.BillingRecordsTable,
                    Key = new() { ["record_id"] = DynamoValues.S($"payment#{billingEvent.PurchaseId}") },
                    UpdateExpression = $"SET {string.Join(", ", paymentSet)}",
                    ConditionExpression =
                        "attribute_exists(record_id) AND group_id = :group AND user_id = :user AND " +
                        "price_id = :price AND amount_cents = :amount AND currency = :currency AND " +
                        "environment = :environment AND #status = :current",
                    ExpressionAttributeNames = new() { ["#status"] = "status" },
                    ExpressionAttributeValues = paymentValues,
                },
            },
        };

        // A Checkout can complete while the exchange is concurrently deleted. Always persist the
        // payment/event; include the entitlement mutation only when the target exchange still exists,
        // belongs to the metadata owner, and does not carry an unrelated entitlement.
        var groupResponse = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.GroupsTable,
            Key = new() { ["group_id"] = DynamoValues.S(billingEvent.GroupId) },
            ConsistentRead = true,
            ProjectionExpression = "owner_user_id, entitlement_id",
        }, cancellationToken);
        var currentEntitlement = groupResponse.IsItemSet
            ? Optional(groupResponse.Item, "entitlement_id")
            : null;
        var isMetadataOwner = groupResponse.IsItemSet &&
            groupResponse.Item.String("owner_user_id") == billingEvent.UserId;
        var expectedEntitlement = $"plus:{billingEvent.GroupId}";

        if (nextStatus == PaymentStatus.Paid &&
            isMetadataOwner &&
            (currentEntitlement is null || currentEntitlement == expectedEntitlement))
        {
            items.Add(new()
            {
                Update = new Update
                {
                    TableName = settings.GroupsTable,
                    Key = new() { ["group_id"] = DynamoValues.S(billingEvent.GroupId) },
                    UpdateExpression = "SET #plan = :plus, entitlement_id = :entitlement, updated_at = :now",
                    ConditionExpression =
                        "attribute_exists(group_id) AND owner_user_id = :user AND " +
                        "(attribute_not_exists(entitlement_id) OR attribute_type(entitlement_id, :nulltype) OR " +
                        "entitlement_id = :entitlement)",
                    ExpressionAttributeNames = new() { ["#plan"] = "plan" },
                    ExpressionAttributeValues = new()
                    {
                        [":plus"] = DynamoValues.S("plus"),
                        [":entitlement"] = DynamoValues.S(expectedEntitlement),
                        [":user"] = DynamoValues.S(billingEvent.UserId),
                        [":now"] = DynamoValues.S(now),
                        [":nulltype"] = DynamoValues.S("NULL"),
                    },
                },
            });
        }
        else if (nextStatus == PaymentStatus.Refunded &&
                 isMetadataOwner &&
                 currentEntitlement == expectedEntitlement)
        {
            items.Add(new()
            {
                Update = new Update
                {
                    TableName = settings.GroupsTable,
                    Key = new() { ["group_id"] = DynamoValues.S(billingEvent.GroupId) },
                    UpdateExpression = "SET #plan = :free, updated_at = :now REMOVE entitlement_id",
                    ConditionExpression = "owner_user_id = :user AND entitlement_id = :entitlement",
                    ExpressionAttributeNames = new() { ["#plan"] = "plan" },
                    ExpressionAttributeValues = new()
                    {
                        [":free"] = DynamoValues.S("free"),
                        [":entitlement"] = DynamoValues.S(expectedEntitlement),
                        [":user"] = DynamoValues.S(billingEvent.UserId),
                        [":now"] = DynamoValues.S(now),
                    },
                },
            });
        }
        if (nextStatus is PaymentStatus.Failed or PaymentStatus.Expired or PaymentStatus.Refunded)
        {
            var activeResponse = await db.GetItemAsync(new GetItemRequest
            {
                TableName = settings.BillingRecordsTable,
                Key = new() { ["record_id"] = DynamoValues.S($"active#{billingEvent.GroupId}") },
                ConsistentRead = true,
                ProjectionExpression = "purchase_id",
            }, cancellationToken);
            if (activeResponse.IsItemSet &&
                activeResponse.Item.String("purchase_id") == billingEvent.PurchaseId)
                items.Add(ActivePurchaseDelete(billingEvent.GroupId, billingEvent.PurchaseId));
        }

        try
        {
            await db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems = items }, cancellationToken);
            return true;
        }
        catch (TransactionCanceledException)
        {
            var duplicate = await db.GetItemAsync(settings.BillingRecordsTable,
                new Dictionary<string, AttributeValue> { ["record_id"] = DynamoValues.S($"event#{billingEvent.EventId}") },
                cancellationToken);
            if (duplicate.IsItemSet) return false;
            throw;
        }
    }

    private static Dictionary<string, AttributeValue> Write(PaymentRecord payment) => new()
    {
        ["record_id"] = DynamoValues.S($"payment#{payment.PurchaseId}"),
        ["record_type"] = DynamoValues.S("payment"),
        ["purchase_id"] = DynamoValues.S(payment.PurchaseId),
        ["group_id"] = DynamoValues.S(payment.GroupId),
        ["user_id"] = DynamoValues.S(payment.UserId),
        ["checkout_session_id"] = DynamoValues.S(payment.CheckoutSessionId),
        ["checkout_url"] = DynamoValues.S(payment.CheckoutUrl),
        ["payment_intent_id"] = payment.PaymentIntentId is null ? new AttributeValue { NULL = true } : DynamoValues.S(payment.PaymentIntentId),
        ["price_id"] = DynamoValues.S(payment.PriceId),
        ["amount_cents"] = DynamoValues.N(payment.AmountCents),
        ["currency"] = DynamoValues.S(payment.Currency),
        ["environment"] = DynamoValues.S(payment.Environment),
        ["status"] = DynamoValues.S(Status(payment.Status)),
        ["receipt_url"] = payment.ReceiptUrl is null ? new AttributeValue { NULL = true } : DynamoValues.S(payment.ReceiptUrl),
        ["created_at"] = DynamoValues.S(payment.CreatedAt),
        ["updated_at"] = DynamoValues.S(payment.UpdatedAt),
    };

    private static PaymentRecord Read(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("purchase_id"),
        item.String("group_id"),
        item.String("user_id"),
        item.String("checkout_session_id"),
        item.String("checkout_url"),
        Optional(item, "payment_intent_id"),
        item.String("price_id"),
        item.Long("amount_cents") ?? 0,
        item.String("currency", "USD"),
        item.String("environment"),
        Enum.TryParse<PaymentStatus>(item.String("status"), true, out var status) ? status : PaymentStatus.Pending,
        Optional(item, "receipt_url"),
        item.String("created_at"),
        item.String("updated_at"));

    private static void ValidateEvent(PaymentRecord payment, BillingWebhookEvent billingEvent)
    {
        if (payment.GroupId != billingEvent.GroupId ||
            payment.UserId != billingEvent.UserId ||
            payment.PriceId != billingEvent.PriceId ||
            payment.AmountCents != billingEvent.AmountCents ||
            !payment.Currency.Equals(billingEvent.Currency, StringComparison.OrdinalIgnoreCase) ||
            payment.Environment != billingEvent.Environment)
            throw ApiException.BadRequest("Stripe event does not match the reserved Humbugg purchase.");
        if (billingEvent.CheckoutSessionId is not null &&
            payment.CheckoutSessionId != billingEvent.CheckoutSessionId)
            throw ApiException.BadRequest("Stripe event contains the wrong Checkout Session.");
        if (billingEvent.CheckoutSessionId is null &&
            (payment.PaymentIntentId is null || payment.PaymentIntentId != billingEvent.PaymentIntentId))
            throw ApiException.Conflict("Stripe charge arrived before its Checkout Session was confirmed.");
    }

    private static PaymentStatus NextStatus(PaymentStatus current, PaymentStatus incoming)
    {
        if (current == PaymentStatus.Refunded) return PaymentStatus.Refunded;
        if (current == PaymentStatus.Paid &&
            incoming is PaymentStatus.Pending or PaymentStatus.Failed or PaymentStatus.Expired)
            return PaymentStatus.Paid;
        if (incoming == PaymentStatus.Refunded && current != PaymentStatus.Paid)
            throw ApiException.Conflict("A refund arrived before the payment confirmation.");
        return incoming;
    }

    private static string Status(PaymentStatus status) => status.ToString().ToLowerInvariant();

    private static string? Optional(IReadOnlyDictionary<string, AttributeValue> item, string name) =>
        item.TryGetValue(name, out var value) && value.NULL != true && !string.IsNullOrWhiteSpace(value.S) ? value.S : null;

    private static void AddOptional(
        ICollection<string> setters,
        IDictionary<string, AttributeValue> values,
        string field,
        string placeholder,
        string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return;
        setters.Add($"{field} = {placeholder}");
        values[placeholder] = DynamoValues.S(value);
    }

    private TransactWriteItem ActivePurchaseDelete(string groupId, string purchaseId) => new()
    {
        Delete = new Delete
        {
            TableName = settings.BillingRecordsTable,
            Key = new() { ["record_id"] = DynamoValues.S($"active#{groupId}") },
            ConditionExpression = "purchase_id = :purchase",
            ExpressionAttributeValues = new() { [":purchase"] = DynamoValues.S(purchaseId) },
        },
    };
}
