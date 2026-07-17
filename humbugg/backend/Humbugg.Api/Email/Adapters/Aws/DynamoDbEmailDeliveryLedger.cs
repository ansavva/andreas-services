using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Email.Core;

namespace Humbugg.Api.Email.Adapters.Aws;

internal sealed class DynamoDbEmailDeliveryLedger(
    IAmazonDynamoDB db,
    HumbuggSettings settings) : IEmailDeliveryLedger
{
    public async Task<bool> TryBeginAsync(TransactionalEmail email, CancellationToken cancellationToken)
    {
        var timestamp = DateTimeOffset.UtcNow;
        var now = timestamp.ToString("O");
        try
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = settings.EmailMessagesTable,
                Key = new() { ["message_id"] = new AttributeValue { S = email.MessageId } },
                UpdateExpression = "SET #status = :submitting, category = :category, updated_at = :now, expires_at = :expires, attempts = if_not_exists(attempts, :zero) + :one",
                ConditionExpression = "attribute_not_exists(message_id) OR #status = :failed",
                ExpressionAttributeNames = new() { ["#status"] = "status" },
                ExpressionAttributeValues = new()
                {
                    [":submitting"] = new AttributeValue { S = "submitting" },
                    [":failed"] = new AttributeValue { S = "failed" },
                    [":category"] = new AttributeValue { S = EmailMessageId.CategoryName(email.Category) },
                    [":now"] = new AttributeValue { S = now },
                    [":zero"] = new AttributeValue { N = "0" },
                    [":one"] = new AttributeValue { N = "1" },
                    [":expires"] = new AttributeValue
                    {
                        N = timestamp.AddDays(90).ToUnixTimeSeconds().ToString()
                    }
                }
            }, cancellationToken);
            return true;
        }
        catch (ConditionalCheckFailedException)
        {
            return false;
        }
    }

    public Task MarkAcceptedAsync(string messageId, CancellationToken cancellationToken) =>
        SetStatusAsync(messageId, "accepted", cancellationToken);

    public Task MarkFailedAsync(string messageId, CancellationToken cancellationToken) =>
        SetStatusAsync(messageId, "failed", cancellationToken);

    private Task SetStatusAsync(
        string messageId,
        string status,
        CancellationToken cancellationToken)
    {
        var values = new Dictionary<string, AttributeValue>
        {
            [":status"] = new AttributeValue { S = status },
            [":now"] = new AttributeValue { S = DateTimeOffset.UtcNow.ToString("O") }
        };
        var update = "SET #status = :status, updated_at = :now";
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
