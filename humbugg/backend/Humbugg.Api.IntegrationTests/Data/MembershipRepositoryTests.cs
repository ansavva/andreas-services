using Humbugg.Api.Data;
using Humbugg.Api.Models;

using Xunit;

namespace Humbugg.Api.IntegrationTests.Data;

public sealed class MembershipRepositoryTests(DevStackFixture stack) : DevStackTest(stack)
{
    private MembershipRepository Repository => new(Db, Settings);

    private async Task<MembershipRecord> CreateTracked(string groupId, string userId, bool organizer = false)
    {
        var record = await Repository.CreateAsync(groupId, userId, "Member " + userId[^4..], organizer);
        CleanupItem(Settings.GroupMembersTable, "member_id", record.MemberId);
        return record;
    }

    [IntegrationFact]
    public async Task Create_derives_the_member_id_from_group_and_user()
    {
        var groupId = Uid("group");
        var userId = Uid("user");
        var record = await CreateTracked(groupId, userId, organizer: true);

        // The id is a pure function of (group, user): the same pair resolves to the same row.
        var byPair = await Repository.GetByUserAndGroupAsync(userId, groupId);
        Assert.NotNull(byPair);
        Assert.Equal(record.MemberId, byPair.MemberId);
        Assert.True(byPair.IsOrganizer);
        Assert.True(byPair.IsParticipating);

        // And creating the same membership again is refused by the key condition.
        await Assert.ThrowsAsync<Amazon.DynamoDBv2.Model.ConditionalCheckFailedException>(
            () => Repository.CreateAsync(groupId, userId, "Again", organizer: false));
    }

    [IntegrationFact]
    public async Task Both_GSIs_answer_for_a_new_membership()
    {
        var groupId = Uid("group");
        var userId = Uid("user");
        var record = await CreateTracked(groupId, userId);

        // GSIs are eventually consistent — poll rather than read-after-write.
        await Eventually(async () =>
        {
            var byUser = await Repository.GetByUserAsync(userId);
            var found = Assert.Single(byUser);
            Assert.Equal(record.MemberId, found.MemberId);
        });
        await Eventually(async () =>
        {
            var byGroup = await Repository.GetByGroupAsync(groupId);
            var found = Assert.Single(byGroup);
            Assert.Equal(record.MemberId, found.MemberId);
        });
    }

    [IntegrationFact]
    public async Task Private_fields_round_trip_including_the_address_map()
    {
        var record = await CreateTracked(Uid("group"), Uid("user"));
        var address = new Address("1 Main St", "Apt 2", "Springfield", "IL", "62701", "US");

        var updated = await Repository.UpdatePrivateAsync(record.MemberId, "socks", "no wool", address);

        Assert.Equal("socks", updated.Wishlist);
        Assert.Equal("no wool", updated.Avoidances);
        Assert.Equal(address, updated.Address);

        var fetched = await Repository.GetAsync(record.MemberId);
        Assert.Equal(address, fetched!.Address);
    }

    [IntegrationFact]
    public async Task Anonymize_strips_the_person_and_keeps_the_row()
    {
        var groupId = Uid("group");
        var record = await CreateTracked(groupId, Uid("user"), organizer: true);
        await Repository.UpdatePrivateAsync(record.MemberId, "secrets", "more secrets",
            new Address("1 Main St", null, "Springfield", null, "62701", "US"));

        await Repository.AnonymizeAsync(record.MemberId, "anon-123", "Former member");

        var anonymized = await Repository.GetAsync(record.MemberId);
        Assert.NotNull(anonymized);
        Assert.Equal("anon-123", anonymized.UserId);
        Assert.Equal("Former member", anonymized.DisplayName);
        Assert.False(anonymized.IsOrganizer);
        Assert.Equal("", anonymized.Wishlist);
        Assert.Equal("", anonymized.Avoidances);
        // The wire form of "no address" is six empty strings, not six nulls: AddressValue
        // writes `?? ""` and the reader never resurrects null fields.
        Assert.Equal(new Address("", "", "", "", "", ""), anonymized.Address);
        Assert.Equal(groupId, anonymized.GroupId); // the draw's reference stays valid
    }

    [IntegrationFact]
    public async Task DeleteByGroup_removes_every_member_of_that_group_only()
    {
        var groupId = Uid("group");
        var memberA = await CreateTracked(groupId, Uid("user"));
        var memberB = await CreateTracked(groupId, Uid("user"));
        var bystander = await CreateTracked(Uid("group"), Uid("user"));

        // The sweep reads through the group GSI, so wait until it sees both rows.
        await Eventually(async () => Assert.Equal(2, (await Repository.GetByGroupAsync(groupId)).Count));
        await Repository.DeleteByGroupAsync(groupId);

        Assert.Null(await Repository.GetAsync(memberA.MemberId));
        Assert.Null(await Repository.GetAsync(memberB.MemberId));
        Assert.NotNull(await Repository.GetAsync(bystander.MemberId));
    }
}
