using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;

namespace Humbugg.Api.Email;

internal sealed class DynamoDbEmailDeliveryLedger(
    IAmazonDynamoDB db,
    HumbuggSettings settings) : IEmailDeliveryLedger
{
    public async Task<bool> TryBeginAsync(TransactionalEmail email, CancellationToken cancellationToken)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        try
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = settings.EmailMessagesTable,
                Key = new() { ["message_id"] = new AttributeValue { S = email.MessageId } },
                UpdateExpression = "SET #status = :sending, category = :category, updated_at = :now, attempts = if_not_exists(attempts, :zero) + :one",
                ConditionExpression = "attribute_not_exists(message_id) OR #status = :failed",
                ExpressionAttributeNames = new() { ["#status"] = "status" },
                ExpressionAttributeValues = new()
                {
                    [":sending"] = new AttributeValue { S = "sending" },
                    [":failed"] = new AttributeValue { S = "failed" },
                    [":category"] = new AttributeValue { S = EmailMessageId.CategoryName(email.Category) },
                    [":now"] = new AttributeValue { S = now },
                    [":zero"] = new AttributeValue { N = "0" },
                    [":one"] = new AttributeValue { N = "1" }
                }
            }, cancellationToken);
            return true;
        }
        catch (ConditionalCheckFailedException)
        {
            return false;
        }
    }

    public Task MarkSentAsync(string messageId, string providerMessageId, CancellationToken cancellationToken) =>
        SetStatusAsync(messageId, "sent", providerMessageId, cancellationToken);

    public Task MarkFailedAsync(string messageId, CancellationToken cancellationToken) =>
        SetStatusAsync(messageId, "failed", null, cancellationToken);

    private Task SetStatusAsync(
        string messageId,
        string status,
        string? providerMessageId,
        CancellationToken cancellationToken)
    {
        var values = new Dictionary<string, AttributeValue>
        {
            [":status"] = new AttributeValue { S = status },
            [":now"] = new AttributeValue { S = DateTimeOffset.UtcNow.ToString("O") }
        };
        var update = "SET #status = :status, updated_at = :now";
        if (providerMessageId is not null)
        {
            update += ", provider_message_id = :provider_message_id";
            values[":provider_message_id"] = new AttributeValue { S = providerMessageId };
        }

        return db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.EmailMessagesTable,
            Key = new() { ["message_id"] = new AttributeValue { S = messageId } },
            UpdateExpression = update,
            ConditionExpression = "attribute_exists(message_id)",
            ExpressionAttributeNames = new() { ["#status"] = "status" },
            ExpressionAttributeValues = values
        }, cancellationToken);
    }
}
