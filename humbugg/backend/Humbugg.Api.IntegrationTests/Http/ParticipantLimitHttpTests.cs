using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Microsoft.AspNetCore.WebUtilities;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

// PlanCatalogTests covers EnsureParticipantCapacity as pure logic (no HTTP, no DynamoDB). These
// are the same two boundaries — Free's 6 and Plus's 50 — exercised through the real join route
// (POST /api/groups/{id}/join), so the 402 an organizer actually sees is the one under test,
// not just the exception type it is built from.
public sealed class ParticipantLimitHttpTests(ApiFixture api) : HttpTest(api)
{
    private const string Consent =
        "\"consent\": {\"version\": \"2026-01\", \"accepted_at\": \"2026-08-27T00:00:00Z\"}";

    [IntegrationFact]
    public async Task Free_seats_six_and_refuses_a_seventh_with_402_naming_Plus()
    {
        var owner = Uid("user");
        CleanupItem(Api.Settings.ProfilesTable, "user_id", owner);
        using var asOwner = Api.ClientFor(owner);
        await asOwner.PutAsync("/api/me", Json($$"""{"display_name": "Owner", {{Consent}}}"""));
        var created = await asOwner.PostAsync("/api/groups", Json("""{"name": "Free Cap Exchange"}"""));
        var group = await ReadJson(created);
        var groupId = group.GetProperty("group_id").GetString()!;
        var secret = InviteSecret(group);
        Cleanup(() => asOwner.DeleteAsync($"/api/groups/{groupId}"));

        // The owner is already participant #1. Five more joins fill the Free plan's six seats.
        for (var i = 0; i < 5; i++)
        {
            var joiner = Uid("user");
            CleanupItem(Api.Settings.ProfilesTable, "user_id", joiner);
            using var asJoiner = Api.ClientFor(joiner);
            await asJoiner.PutAsync("/api/me", Json($$"""{"display_name": "Joiner", {{Consent}}}"""));
            var response = await asJoiner.PostAsync($"/api/groups/{groupId}/join",
                Json($$"""{"invite_token": "{{secret}}"}"""));
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        }

        // The seventh person — the group is already at its six-participant Free cap.
        var refused = Uid("user");
        CleanupItem(Api.Settings.ProfilesTable, "user_id", refused);
        using var asRefused = Api.ClientFor(refused);
        await asRefused.PutAsync("/api/me", Json($$"""{"display_name": "Refused", {{Consent}}}"""));
        var rejection = await asRefused.PostAsync($"/api/groups/{groupId}/join",
            Json($$"""{"invite_token": "{{secret}}"}"""));

        Assert.Equal(HttpStatusCode.PaymentRequired, rejection.StatusCode);
        var error = (await ReadJson(rejection)).GetProperty("error");
        Assert.Equal("plus_required", error.GetProperty("code").GetString());
        Assert.Contains("Plus", error.GetProperty("message").GetString());
    }

    [IntegrationFact]
    public async Task Plus_seats_fifty_and_refuses_a_fifty_first_pointing_to_Work()
    {
        var groupId = Uid("group");
        var ownerId = Uid("user");
        CleanupItem(Api.Settings.GroupsTable, "group_id", groupId);
        CleanupItem(Api.Settings.ProfilesTable, "user_id", ownerId);

        // A Plus group with 49 seats already filled, built directly against the repositories —
        // reaching 49 real members through 49 real HTTP joins would just re-run the Free test
        // forty-nine times. This test is about the boundary itself, not how a roster grows.
        var groups = new GroupRepository(Api.Db, Api.Settings);
        var members = new MembershipRepository(Api.Db, Api.Settings);
        // Same shape GroupService.NewSecret() generates — Validation.InviteToken requires
        // exactly 43 characters, so an itest-prefixed id would fail format validation, not
        // the hash comparison this test is actually about.
        var secret = WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(secret))).ToLowerInvariant();
        var now = DateTimeOffset.UtcNow.ToString("O");
        await groups.CreateAsync(new GroupRecord(groupId, ownerId, "Plus Cap Exchange", "", null, null, null,
            "USD", PlanCode.Plus, $"plus:{groupId}", GroupStatus.Open, hash, [], now, now));
        for (var i = 0; i < 49; i++)
        {
            var record = await members.CreateAsync(groupId, Uid("user"), $"Member {i}", organizer: false);
            CleanupItem(Api.Settings.GroupMembersTable, "member_id", record.MemberId);
        }

        var joiner = Uid("user");
        CleanupItem(Api.Settings.ProfilesTable, "user_id", joiner);
        using var asJoiner = Api.ClientFor(joiner);
        await asJoiner.PutAsync("/api/me", Json($$"""{"display_name": "Fiftieth", {{Consent}}}"""));
        var accepted = await asJoiner.PostAsync($"/api/groups/{groupId}/join",
            Json($$"""{"invite_token": "{{secret}}"}"""));
        Assert.Equal(HttpStatusCode.OK, accepted.StatusCode);

        var refused = Uid("user");
        CleanupItem(Api.Settings.ProfilesTable, "user_id", refused);
        using var asRefused = Api.ClientFor(refused);
        await asRefused.PutAsync("/api/me", Json($$"""{"display_name": "FiftyFirst", {{Consent}}}"""));
        var rejection = await asRefused.PostAsync($"/api/groups/{groupId}/join",
            Json($$"""{"invite_token": "{{secret}}"}"""));

        Assert.Equal(HttpStatusCode.Conflict, rejection.StatusCode);
        var error = (await ReadJson(rejection)).GetProperty("error");
        Assert.Contains("Work", error.GetProperty("message").GetString());
        Assert.Contains("51", error.GetProperty("message").GetString());
    }

    private static string InviteSecret(JsonElement group)
    {
        var inviteUrl = group.GetProperty("invite_url").GetString()!;
        return inviteUrl[(inviteUrl.IndexOf("#invite=", StringComparison.Ordinal) + "#invite=".Length)..];
    }
}
