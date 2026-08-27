using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class InvitationRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private InvitationRepository Repository => new(Db, Settings);

    private async Task<InvitationRecord> CreateTracked(string groupId, string status = "sent", string? expiresAt = null)
    {
        var record = new InvitationRecord(
            Uid("invitation"), groupId, "invitee@example.test", TokenHash: "tokenhash",
            Status: status, ExpiresAt: expiresAt ?? DateTimeOffset.UtcNow.AddDays(7).ToString("O"),
            CreatedAt: Now(), UpdatedAt: Now());
        await Repository.CreateAsync(record);
        CleanupItem(Settings.InvitationsTable, "invitation_id", record.InvitationId);
        return record;
    }

    [IntegrationFact]
    public async Task Create_and_get_round_trip_with_optional_fields_absent()
    {
        var record = await CreateTracked(Uid("group"));
        var fetched = await Repository.GetAsync(record.InvitationId);

        Assert.Equal(record, fetched);
        Assert.Null(fetched!.AcceptedAt);
        Assert.Null(fetched.MessageId);
    }

    [IntegrationFact]
    public async Task GetByGroup_answers_through_the_GSI()
    {
        var groupId = Uid("group");
        var record = await CreateTracked(groupId);
        await CreateTracked(Uid("group")); // another group's invitation must not appear

        await Eventually(async () =>
        {
            var invitations = await Repository.GetByGroupAsync(groupId);
            var found = Assert.Single(invitations);
            Assert.Equal(record.InvitationId, found.InvitationId);
        });
    }

    [IntegrationFact]
    public async Task Update_refuses_terminal_states()
    {
        var record = await CreateTracked(Uid("group"));

        await Repository.UpdateAsync(record.InvitationId, "sent", tokenHash: "rotated", expiresAt: null,
            messageId: "msg-1");
        var updated = await Repository.GetAsync(record.InvitationId);
        Assert.Equal("rotated", updated!.TokenHash);
        Assert.Equal("msg-1", updated.MessageId);
        Assert.NotNull(updated.LastSentAt);

        var revoked = await CreateTracked(Uid("group"), status: "revoked");
        await Assert.ThrowsAsync<ConditionalCheckFailedException>(
            () => Repository.UpdateAsync(revoked.InvitationId, "sent", null, null, null));
    }

    [IntegrationFact]
    public async Task Accepting_creates_the_membership_in_the_same_transaction()
    {
        var groupId = Uid("group");
        var record = await CreateTracked(groupId);
        var userId = Uid("user");
        var membership = MembershipRepository.NewRecord(groupId, userId, "Joiner", organizer: false);
        CleanupItem(Settings.GroupMembersTable, "member_id", membership.MemberId);

        await Repository.AcceptAndCreateMembershipAsync(record.InvitationId, userId, membership);

        var accepted = await Repository.GetAsync(record.InvitationId);
        Assert.Equal("accepted", accepted!.Status);
        Assert.Equal(userId, accepted.AcceptedUserId);
        Assert.NotNull(await new MembershipRepository(Db, Settings).GetAsync(membership.MemberId));

        // A second accept must fail atomically: the invitation is no longer "sent".
        await Assert.ThrowsAsync<TransactionCanceledException>(
            () => Repository.AcceptAndCreateMembershipAsync(record.InvitationId, userId, membership));
    }

    [IntegrationFact]
    public async Task An_expired_invitation_cannot_be_accepted()
    {
        var groupId = Uid("group");
        var expired = await CreateTracked(groupId, expiresAt: DateTimeOffset.UtcNow.AddMinutes(-1).ToString("O"));
        var membership = MembershipRepository.NewRecord(groupId, Uid("user"), "Too Late", organizer: false);
        CleanupItem(Settings.GroupMembersTable, "member_id", membership.MemberId);

        await Assert.ThrowsAsync<TransactionCanceledException>(
            () => Repository.AcceptAndCreateMembershipAsync(expired.InvitationId, membership.UserId, membership));
        Assert.Equal("sent", (await Repository.GetAsync(expired.InvitationId))!.Status);
    }

    [IntegrationFact]
    public async Task Delivery_status_reads_from_the_email_messages_table()
    {
        Assert.Null(await Repository.GetDeliveryStatusAsync(null));
        Assert.Null(await Repository.GetDeliveryStatusAsync("itest-msg-absent"));

        var messageId = Uid("msg");
        CleanupItem(Settings.EmailMessagesTable, "message_id", messageId);
        await Db.PutItemAsync(new PutItemRequest
        {
            TableName = Settings.EmailMessagesTable,
            Item = new() { ["message_id"] = new(messageId), ["status"] = new("delivered") }
        });

        Assert.Equal("delivered", await Repository.GetDeliveryStatusAsync(messageId));
    }
}
