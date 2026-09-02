using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;
using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Data;

internal interface IMembershipRepository
{
    Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default);
    Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default);
    Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default);
    Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default);
    Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default);
    Task<MembershipRecord> UpdateOrganizerAsync(string memberId, bool organizer, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("This membership repository does not support organizer role updates.");
    Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default);
    Task SetWishClaimAsync(string memberId, string drawId, string wishId, WishClaimRecord claim, CancellationToken cancellationToken = default);
    Task RemoveWishClaimAsync(string memberId, string drawId, string wishId, CancellationToken cancellationToken = default);
    Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default);
    Task SetGiftStageAsync(string memberId, string drawId, GiftStage stage, CancellationToken cancellationToken = default);
    Task SetGiftReceivedAsync(string memberId, string drawId, bool received, CancellationToken cancellationToken = default);
    Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default);
    Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default);
    Task DeleteAsync(string memberId, CancellationToken cancellationToken = default);
    Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default);
}

internal sealed class MembershipRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IMembershipRepository
{
    public async Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = new() { ["member_id"] = DynamoValues.S(memberId) },
            ConsistentRead = true
        }, cancellationToken);
        return response.IsItemSet ? Read(response.Item) : null;
    }

    public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) =>
        QueryAsync("user_id-index", "user_id", userId, cancellationToken);

    public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
        QueryAsync("group_id-index", "group_id", groupId, cancellationToken);

    public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) =>
        GetAsync(MemberId(groupId, userId), cancellationToken);

    private async Task<IReadOnlyList<MembershipRecord>> QueryAsync(string index, string key, string value, CancellationToken cancellationToken)
    {
        var response = await db.QueryAsync(new QueryRequest
        {
            TableName = settings.GroupMembersTable,
            IndexName = index,
            KeyConditionExpression = "#key = :value",
            ExpressionAttributeNames = new() { ["#key"] = key },
            ExpressionAttributeValues = new() { [":value"] = DynamoValues.S(value) }
        }, cancellationToken);
        return response.Items.Select(Read).ToList();
    }

    public async Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default)
    {
        var record = NewRecord(groupId, userId, displayName, organizer);
        await db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.GroupMembersTable,
            Item = Write(record),
            ConditionExpression = "attribute_not_exists(member_id)"
        }, cancellationToken);
        return record;
    }

    public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) =>
        UpdateAsync(memberId, "SET wishlist = :wishlist, avoidances = :avoidances, address = :address, updated_at = :now",
            new() { [":wishlist"] = DynamoValues.S(wishlist), [":avoidances"] = DynamoValues.S(avoidances), [":address"] = DynamoValues.AddressValue(address) }, cancellationToken);

    public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) =>
        UpdateAsync(memberId, "SET is_participating = :participating, updated_at = :now",
            new() { [":participating"] = DynamoValues.B(participating) }, cancellationToken);

    public Task<MembershipRecord> UpdateOrganizerAsync(string memberId, bool organizer, CancellationToken cancellationToken = default) =>
        UpdateAsync(
            memberId,
            "SET is_organizer = :organizer, updated_at = :now",
            new() { [":organizer"] = DynamoValues.B(organizer) },
            cancellationToken);

    // Records that this member has opened their assignment for this draw. Deliberately NOT routed
    // through UpdateAsync: that touches updated_at, and reading your own assignment is not an edit
    // to your membership — it would move a timestamp the organizer dashboard reads as activity.
    public Task MarkAssignmentViewedAsync(string memberId, string drawId, CancellationToken cancellationToken = default) =>
        db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = new() { ["member_id"] = DynamoValues.S(memberId) },
            UpdateExpression = "SET assignment_viewed_draw_id = :draw",
            ExpressionAttributeValues = new() { [":draw"] = DynamoValues.S(drawId) },
            ConditionExpression = "attribute_exists(member_id)"
        }, cancellationToken);

    /// <summary>
    /// Records one purchase claim, scoped to the draw it was made under.
    /// </summary>
    /// <remarks>
    /// Two shapes, and the split is what makes concurrent claims safe rather than merely unlikely.
    ///
    /// The common path writes a NESTED map key — <c>SET wish_claims.#wish = :claim</c> — which
    /// DynamoDB applies to that key alone. Two claims on different wishes therefore both land, with
    /// no read-modify-write window to lose one in; two claims on the SAME wish resolve
    /// last-writer-wins on that key, which is the correct answer for one person double-submitting.
    ///
    /// A nested SET fails when <c>wish_claims</c> does not exist, so the first claim of a draw
    /// writes the whole map instead, conditioned on the draw id still being what the caller read. If
    /// that condition fails, another request created the map first and the nested write is retried —
    /// which now succeeds, because the map exists.
    ///
    /// Deliberately NOT routed through <see cref="UpdateAsync"/>: that moves <c>updated_at</c>, and
    /// buying a gift for somebody else is not an edit to your own membership. It would show up on
    /// the organizer's dashboard as activity on the giver's row.
    /// </remarks>
    public async Task SetWishClaimAsync(
        string memberId,
        string drawId,
        string wishId,
        WishClaimRecord claim,
        CancellationToken cancellationToken = default)
    {
        var value = ClaimValue(claim);
        try
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = settings.GroupMembersTable,
                Key = Key(memberId),
                UpdateExpression = "SET wish_claims.#wish = :claim",
                ExpressionAttributeNames = new() { ["#wish"] = wishId },
                ExpressionAttributeValues = new() { [":claim"] = value, [":draw"] = DynamoValues.S(drawId) },
                ConditionExpression = "attribute_exists(member_id) AND wish_claims_draw_id = :draw"
            }, cancellationToken);
            return;
        }
        catch (Exception exception) when (exception is ConditionalCheckFailedException or AmazonDynamoDBException)
        {
            // Either no map yet, or one belonging to an earlier draw. Both mean: start this draw's
            // map from scratch. A nested SET on a missing path is a ValidationException rather than
            // a condition failure, which is why both are caught here.
            if (exception is AmazonDynamoDBException dynamo and not ConditionalCheckFailedException &&
                dynamo.ErrorCode != "ValidationException")
                throw;
        }

        await db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = Key(memberId),
            UpdateExpression = "SET wish_claims = :map, wish_claims_draw_id = :draw",
            ExpressionAttributeValues = new()
            {
                [":map"] = new AttributeValue
                {
                    M = new Dictionary<string, AttributeValue>(StringComparer.Ordinal) { [wishId] = value }
                },
                [":draw"] = DynamoValues.S(drawId)
            },
            ConditionExpression = "attribute_exists(member_id)"
        }, cancellationToken);
    }

    /// <summary>Releases one claim. A claim that is not there is not an error — releasing twice is
    /// the same outcome as releasing once, and a client retrying a lost response should not see a
    /// failure for reaching the state it asked for.</summary>
    public async Task RemoveWishClaimAsync(
        string memberId,
        string drawId,
        string wishId,
        CancellationToken cancellationToken = default)
    {
        try
        {
            await db.UpdateItemAsync(new UpdateItemRequest
            {
                TableName = settings.GroupMembersTable,
                Key = Key(memberId),
                UpdateExpression = "REMOVE wish_claims.#wish",
                ExpressionAttributeNames = new() { ["#wish"] = wishId },
                ExpressionAttributeValues = new() { [":draw"] = DynamoValues.S(drawId) },
                ConditionExpression = "attribute_exists(member_id) AND wish_claims_draw_id = :draw"
            }, cancellationToken);
        }
        catch (ConditionalCheckFailedException)
        {
            // No claims for this draw at all. Nothing to release.
        }
    }

    /// <summary>Drops every claim on this row — the self-service data clear and the anonymize path.</summary>
    public Task ClearWishClaimsAsync(string memberId, CancellationToken cancellationToken = default) =>
        db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = Key(memberId),
            UpdateExpression = "REMOVE wish_claims, wish_claims_draw_id",
            ConditionExpression = "attribute_exists(member_id)"
        }, cancellationToken);

    /// <summary>
    /// Records how far along the gift this member is giving has got (#132).
    /// </summary>
    /// <remarks>
    /// Writes the draw id alongside the stage in one update, so a stage can never be left scoped to
    /// a draw it did not come from. The recipient's confirmation is REMOVEd rather than kept: it
    /// belongs to whatever the giver had done at the time, and moving the stage is only permitted
    /// while it is unset anyway — the service refuses the write otherwise.
    ///
    /// Deliberately not routed through <see cref="UpdateAsync"/>: that moves <c>updated_at</c>, and
    /// buying a gift is not an edit to your membership.
    /// </remarks>
    public Task SetGiftStageAsync(
        string memberId,
        string drawId,
        GiftStage stage,
        CancellationToken cancellationToken = default) =>
        db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = Key(memberId),
            UpdateExpression =
                "SET gift_stage = :stage, gift_stage_at = :at, gift_progress_draw_id = :draw REMOVE gift_received_at",
            ExpressionAttributeValues = new()
            {
                [":stage"] = DynamoValues.S(stage.ToString()),
                [":at"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O")),
                [":draw"] = DynamoValues.S(drawId),
            },
            ConditionExpression = "attribute_exists(member_id)",
        }, cancellationToken);

    /// <summary>
    /// Records that the person this member gives to has confirmed the gift arrived.
    /// </summary>
    /// <remarks>
    /// Called with the GIVER's member id, which the service resolved by inverting the draw — the
    /// recipient never learns whose row this was. The stage is left alone: what the giver did is
    /// their own record, and "received" is a second fact about the same gift, not a fourth stage
    /// overwriting the first three.
    /// </remarks>
    public Task SetGiftReceivedAsync(
        string memberId,
        string drawId,
        bool received,
        CancellationToken cancellationToken = default) =>
        db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = Key(memberId),
            UpdateExpression = received
                ? "SET gift_received_at = :at, gift_progress_draw_id = :draw"
                : "SET gift_progress_draw_id = :draw REMOVE gift_received_at",
            ExpressionAttributeValues = received
                ? new()
                {
                    [":at"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O")),
                    [":draw"] = DynamoValues.S(drawId),
                }
                : new() { [":draw"] = DynamoValues.S(drawId) },
            ConditionExpression = "attribute_exists(member_id)",
        }, cancellationToken);

    /// <summary>Drops the gift progress on this row — the self-service clear and the anonymize path.</summary>
    public Task ClearGiftProgressAsync(string memberId, CancellationToken cancellationToken = default) =>
        db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = Key(memberId),
            UpdateExpression = "REMOVE gift_stage, gift_stage_at, gift_received_at, gift_progress_draw_id",
            ConditionExpression = "attribute_exists(member_id)",
        }, cancellationToken);

    private static Dictionary<string, AttributeValue> Key(string memberId) =>
        new() { ["member_id"] = DynamoValues.S(memberId) };

    private static AttributeValue ClaimValue(WishClaimRecord claim) => new()
    {
        M = new Dictionary<string, AttributeValue>(StringComparer.Ordinal)
        {
            ["state"] = DynamoValues.S(claim.State.ToString()),
            ["quantity"] = DynamoValues.N(claim.Quantity),
            ["updated_at"] = DynamoValues.S(claim.UpdatedAt)
        }
    };

    private async Task<MembershipRecord> UpdateAsync(string memberId, string expression, Dictionary<string, AttributeValue> values, CancellationToken cancellationToken)
    {
        values[":now"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O"));
        var response = await db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = new() { ["member_id"] = DynamoValues.S(memberId) },
            UpdateExpression = expression,
            ExpressionAttributeValues = values,
            ConditionExpression = "attribute_exists(member_id)",
            ReturnValues = ReturnValue.ALL_NEW
        }, cancellationToken);
        return Read(response.Attributes);
    }

    // Strips the participant's product-profile data (name, wishlist, avoidances, address) and moves
    // the row off the real Cognito subject onto an irreversible pseudonym, while keeping member_id so
    // a completed draw that references it stays valid. Re-pointing user_id also makes account deletion
    // idempotent: a retried deletion no longer finds the row through the user_id GSI.
    public async Task AnonymizeAsync(string memberId, string pseudonym, string displayName, CancellationToken cancellationToken = default)
    {
        await db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.GroupMembersTable,
            Key = new() { ["member_id"] = DynamoValues.S(memberId) },
            UpdateExpression = "SET user_id = :user, display_name = :name, is_organizer = :notOrganizer, wishlist = :empty, avoidances = :empty, address = :address, updated_at = :now REMOVE assignment_viewed_draw_id, wish_claims, wish_claims_draw_id, gift_stage, gift_stage_at, gift_received_at, gift_progress_draw_id",
            ExpressionAttributeValues = new()
            {
                [":user"] = DynamoValues.S(pseudonym),
                [":name"] = DynamoValues.S(displayName),
                [":notOrganizer"] = DynamoValues.B(false),
                [":empty"] = DynamoValues.S(""),
                [":address"] = DynamoValues.AddressValue(new Address()),
                [":now"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O"))
            },
            ConditionExpression = "attribute_exists(member_id)"
        }, cancellationToken);
    }

    public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => db.DeleteItemAsync(
        settings.GroupMembersTable, new Dictionary<string, AttributeValue> { ["member_id"] = DynamoValues.S(memberId) }, cancellationToken);

    public async Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default)
    {
        foreach (var batch in (await GetByGroupAsync(groupId, cancellationToken)).Chunk(25))
        {
            var pending = new Dictionary<string, List<WriteRequest>>
            {
                [settings.GroupMembersTable] = batch.Select(item => new WriteRequest(new DeleteRequest(
                    new Dictionary<string, AttributeValue> { ["member_id"] = DynamoValues.S(item.MemberId) }))).ToList()
            };
            for (var attempt = 0; pending.Count > 0; attempt++)
            {
                if (attempt == 6) throw new InvalidOperationException("DynamoDB did not complete the group-member deletion batch.");
                var response = await db.BatchWriteItemAsync(new BatchWriteItemRequest { RequestItems = pending }, cancellationToken);
                pending = response.UnprocessedItems;
                if (pending.Count > 0) await Task.Delay(TimeSpan.FromMilliseconds(50 * (attempt + 1)), cancellationToken);
            }
        }
    }

    internal static Dictionary<string, AttributeValue> Write(MembershipRecord record)
    {
        var item = new Dictionary<string, AttributeValue>(StringComparer.Ordinal)
        {
            ["member_id"] = DynamoValues.S(record.MemberId),
            ["group_id"] = DynamoValues.S(record.GroupId),
            ["user_id"] = DynamoValues.S(record.UserId),
            ["display_name"] = DynamoValues.S(record.DisplayName),
            ["is_organizer"] = DynamoValues.B(record.IsOrganizer),
            ["is_participating"] = DynamoValues.B(record.IsParticipating),
            ["wishlist"] = DynamoValues.S(record.Wishlist),
            ["avoidances"] = DynamoValues.S(record.Avoidances),
            ["address"] = DynamoValues.AddressValue(record.Address),
            ["created_at"] = DynamoValues.S(record.CreatedAt),
            ["updated_at"] = DynamoValues.S(record.UpdatedAt)
        };
        // Absent rather than empty when nobody has looked: the attribute's absence is what
        // AnonymizeAsync's REMOVE leaves behind, so the two paths agree on what "never viewed" is.
        if (record.AssignmentViewedDrawId is not null)
            item["assignment_viewed_draw_id"] = DynamoValues.S(record.AssignmentViewedDrawId);
        // Same rule for the claims: absent, not an empty map, so a row that has never had one and a
        // row whose claims were removed read identically.
        if (record.WishClaims is { Count: > 0 } claims && record.WishClaimsDrawId is not null)
        {
            item["wish_claims"] = new AttributeValue
            {
                M = claims.ToDictionary(pair => pair.Key, pair => ClaimValue(pair.Value), StringComparer.Ordinal)
            };
            item["wish_claims_draw_id"] = DynamoValues.S(record.WishClaimsDrawId);
        }
        if (record.GiftProgressDrawId is not null)
        {
            item["gift_progress_draw_id"] = DynamoValues.S(record.GiftProgressDrawId);
            if (record.GiftStage is { } stage) item["gift_stage"] = DynamoValues.S(stage.ToString());
            if (record.GiftStageAt is not null) item["gift_stage_at"] = DynamoValues.S(record.GiftStageAt);
            if (record.GiftReceivedAt is not null) item["gift_received_at"] = DynamoValues.S(record.GiftReceivedAt);
        }
        return item;
    }

    private static MembershipRecord Read(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("member_id"), item.String("group_id"), item.String("user_id"), item.String("display_name"),
        item.Bool("is_organizer"), item.Bool("is_participating"), item.String("wishlist"), item.String("avoidances"),
        item.Address("address"), item.String("created_at"), item.String("updated_at"),
        item.TryGetValue("assignment_viewed_draw_id", out var viewed) ? viewed.S : null,
        ReadClaims(item),
        item.TryGetValue("wish_claims_draw_id", out var claimsDraw) ? claimsDraw.S : null,
        Enum.TryParse<GiftStage>(item.String("gift_stage"), out var giftStage) ? giftStage : null,
        item.TryGetValue("gift_stage_at", out var stageAt) ? stageAt.S : null,
        item.TryGetValue("gift_received_at", out var receivedAt) ? receivedAt.S : null,
        item.TryGetValue("gift_progress_draw_id", out var giftDraw) ? giftDraw.S : null);

    private static IReadOnlyDictionary<string, WishClaimRecord>? ReadClaims(
        IReadOnlyDictionary<string, AttributeValue> item)
    {
        if (!item.TryGetValue("wish_claims", out var value) || value.M is not { Count: > 0 } map) return null;
        return map.ToDictionary(
            pair => pair.Key,
            pair => new WishClaimRecord(
                Enum.TryParse<WishClaimState>(pair.Value.M?.String("state"), out var state)
                    ? state
                    : WishClaimState.Planned,
                (int)(pair.Value.M?.Long("quantity") ?? 1),
                pair.Value.M?.String("updated_at") ?? ""),
            StringComparer.Ordinal);
    }

    internal static MembershipRecord NewRecord(
        string groupId,
        string userId,
        string displayName,
        bool organizer,
        bool participating = true)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        return new MembershipRecord(
            MemberId(groupId, userId),
            groupId,
            userId,
            displayName,
            organizer,
            participating,
            "",
            "",
            new(),
            now,
            now);
    }

    /// <summary>
    /// A membership's id: a hash of the group and the account, so it is the same value every time.
    /// </summary>
    /// <remarks>
    /// Internal rather than private because repeating an exchange (#136) needs it: exclusions are
    /// keyed by member id, and the ids in a NEW exchange do not exist until people join. Because the
    /// value is derived rather than random, the pairs can be translated up front and simply lie
    /// inert until both people are there.
    /// </remarks>
    internal static string MemberId(string groupId, string userId) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{groupId}:{userId}"))).ToLowerInvariant()[..32];
}
