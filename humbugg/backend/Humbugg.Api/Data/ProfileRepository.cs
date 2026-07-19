using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal interface IProfileRepository
{
    Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default);
    Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default);
    Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default);
    Task DeleteAsync(string userId, CancellationToken cancellationToken = default);
}

internal sealed class ProfileRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IProfileRepository
{
    public async Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.ProfilesTable,
            Key = new() { ["user_id"] = DynamoValues.S(userId) },
            ConsistentRead = true
        }, cancellationToken);
        return response.IsItemSet ? Read(response.Item) : null;
    }

    public async Task<ProfileRecord> UpsertAsync(string userId, string displayName, bool? nonEssentialEmailsEnabled = null, Consent? consent = null, CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var values = new Dictionary<string, AttributeValue>
        {
            [":name"] = DynamoValues.S(displayName),
            [":now"] = DynamoValues.S(now),
        };
        // Only overwrite the opt-out flag when the caller supplied one; otherwise seed it to enabled on
        // first write and leave any existing preference untouched, so a display-name save never resets it.
        string emailPreferenceAssignment;
        if (nonEssentialEmailsEnabled is bool preference)
        {
            values[":ne"] = DynamoValues.B(preference);
            emailPreferenceAssignment = "non_essential_emails_enabled = :ne";
        }
        else
        {
            values[":neDefault"] = DynamoValues.B(true);
            emailPreferenceAssignment = "non_essential_emails_enabled = if_not_exists(non_essential_emails_enabled, :neDefault)";
        }

        // Consent is written once and never overwritten (if_not_exists), so the original signup version
        // and timestamp remain the immutable record even if the profile is saved again later.
        var consentAssignment = "";
        if (consent is not null)
        {
            values[":cv"] = DynamoValues.S(consent.Version);
            values[":ca"] = DynamoValues.S(consent.AcceptedAt);
            consentAssignment =
                ", consent_version = if_not_exists(consent_version, :cv), consent_accepted_at = if_not_exists(consent_accepted_at, :ca)";
        }

        var response = await db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.ProfilesTable,
            Key = new() { ["user_id"] = DynamoValues.S(userId) },
            UpdateExpression =
                $"SET display_name = :name, updated_at = :now, created_at = if_not_exists(created_at, :now), {emailPreferenceAssignment}{consentAssignment}",
            ExpressionAttributeValues = values,
            ReturnValues = ReturnValue.ALL_NEW
        }, cancellationToken);
        return Read(response.Attributes);
    }

    // Sets or clears the avatar reference on an existing profile. Requires the profile to exist (the
    // display name is set first), so a conditional check guards against creating a nameless row here.
    public async Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var request = new UpdateItemRequest
        {
            TableName = settings.ProfilesTable,
            Key = new() { ["user_id"] = DynamoValues.S(userId) },
            ConditionExpression = "attribute_exists(user_id)",
            ExpressionAttributeValues = new() { [":now"] = DynamoValues.S(now) },
            ReturnValues = ReturnValue.ALL_NEW,
        };
        if (string.IsNullOrEmpty(avatarKey))
        {
            request.UpdateExpression = "SET updated_at = :now REMOVE avatar_key";
        }
        else
        {
            request.UpdateExpression = "SET avatar_key = :key, updated_at = :now";
            request.ExpressionAttributeValues[":key"] = DynamoValues.S(avatarKey);
        }
        try
        {
            var response = await db.UpdateItemAsync(request, cancellationToken);
            return Read(response.Attributes);
        }
        catch (ConditionalCheckFailedException)
        {
            throw ApiException.NotFound("Complete your profile before adding a photo.");
        }
    }

    // Unconditional delete so account deletion is idempotent: removing an already-absent
    // profile succeeds and is a no-op, making a retried deletion safe.
    public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) => db.DeleteItemAsync(
        settings.ProfilesTable, new Dictionary<string, AttributeValue> { ["user_id"] = DynamoValues.S(userId) }, cancellationToken);

    private static ProfileRecord Read(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("user_id"), item.String("display_name"), item.String("created_at"), item.String("updated_at"),
        item.TryGetValue("avatar_key", out var avatar) ? avatar.S : null,
        item.BoolOrDefault("non_essential_emails_enabled", true),
        item.TryGetValue("consent_version", out var consentVersion) ? consentVersion.S : null,
        item.TryGetValue("consent_accepted_at", out var consentAcceptedAt) ? consentAcceptedAt.S : null);
}
