using System.Net;
using System.Text.Json;
using Xunit;

namespace Humbugg.Api.IntegrationTests.Http;

// One full product flow through the real stack: controllers → services → repositories →
// dev-stack DynamoDB, over HTTP with real auth. This is the in-process equivalent of the
// prod smoke's curl checks, but it can exercise authenticated, state-changing paths.
public sealed class GroupFlowTests(ApiFixture api) : HttpTest(api)
{
    private const string Consent =
        "\"consent\": {\"version\": \"2026-01\", \"accepted_at\": \"2026-08-27T00:00:00Z\"}";

    [IntegrationFact]
    public async Task Create_join_wish_draw_and_reveal()
    {
        var alice = Uid("user");
        var bob = Uid("user");
        CleanupItem(Api.Settings.ProfilesTable, "user_id", alice);
        CleanupItem(Api.Settings.ProfilesTable, "user_id", bob);
        using var asAlice = Api.ClientFor(alice);
        using var asBob = Api.ClientFor(bob);

        // Profiles first — the consent record is required on first save.
        var profile = await asAlice.PutAsync("/api/me", Json($$"""{"display_name": "Alice", {{Consent}}}"""));
        Assert.Equal(HttpStatusCode.OK, profile.StatusCode);
        Assert.Equal("Alice", (await ReadJson(profile)).GetProperty("display_name").GetString());
        Assert.Equal(HttpStatusCode.OK,
            (await asBob.PutAsync("/api/me", Json($$"""{"display_name": "Bob", {{Consent}}}"""))).StatusCode);

        // Alice creates the exchange; the response carries the invite URL with its secret.
        var created = await asAlice.PostAsync("/api/groups", Json("""{"name": "Flow Exchange"}"""));
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var group = await ReadJson(created);
        var groupId = group.GetProperty("group_id").GetString()!;
        Cleanup(() => asAlice.DeleteAsync($"/api/groups/{groupId}"));
        Assert.True(group.GetProperty("is_owner").GetBoolean());
        var inviteUrl = group.GetProperty("invite_url").GetString()!;
        var secret = inviteUrl[(inviteUrl.IndexOf("#invite=", StringComparison.Ordinal) + "#invite=".Length)..];

        // Bob joins with the invite secret and fills in his wishlist.
        var joined = await asBob.PostAsync($"/api/groups/{groupId}/join", Json($$"""{"invite_token": "{{secret}}"}"""));
        Assert.Equal(HttpStatusCode.OK, joined.StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await asBob.PatchAsync($"/api/groups/{groupId}/members/me",
            Json("""{"wishlist": "wool socks"}"""))).StatusCode);
        var wish = await asBob.PostAsync($"/api/groups/{groupId}/members/me/wishes",
            Json("""{"kind": "product", "title": "Wool socks", "price_cents": 1999}"""));
        Assert.True(wish.IsSuccessStatusCode);
        var wishBody = await ReadJson(wish);
        // The wire shape is snake_case throughout — a naming-policy regression breaks every client.
        Assert.Equal(1999, wishBody.GetProperty("price_cents").GetInt64());

        // Alice draws; both members can read their own assignment and reveal.
        var draw = await asAlice.PostAsync($"/api/groups/{groupId}/draw", Json("{}"));
        Assert.Equal(HttpStatusCode.OK, draw.StatusCode);
        // The draw returns the caller's own RecipientAssignment — a flat projection.
        var assignment = await ReadJson(draw);
        Assert.False(string.IsNullOrEmpty(assignment.GetProperty("display_name").GetString()));

        var bobAssignment = await asBob.GetAsync($"/api/groups/{groupId}/assignment");
        Assert.Equal(HttpStatusCode.OK, bobAssignment.StatusCode);
        // With two participants the draw is a swap: Bob must have been assigned Alice.
        Assert.Equal("Alice", (await ReadJson(bobAssignment)).GetProperty("display_name").GetString());

        // Deleting the exchange is part of the flow — and the cleanup.
        Assert.Equal(HttpStatusCode.NoContent, (await asAlice.DeleteAsync($"/api/groups/{groupId}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await asAlice.GetAsync($"/api/groups/{groupId}")).StatusCode);
    }

    [IntegrationFact]
    public async Task A_wrong_invite_token_cannot_join()
    {
        var owner = Uid("user");
        var intruder = Uid("user");
        CleanupItem(Api.Settings.ProfilesTable, "user_id", owner);
        CleanupItem(Api.Settings.ProfilesTable, "user_id", intruder);
        using var asOwner = Api.ClientFor(owner);
        using var asIntruder = Api.ClientFor(intruder);

        await asOwner.PutAsync("/api/me", Json($$"""{"display_name": "Owner", {{Consent}}}"""));
        await asIntruder.PutAsync("/api/me", Json($$"""{"display_name": "Intruder", {{Consent}}}"""));
        var created = await asOwner.PostAsync("/api/groups", Json("""{"name": "Locked Exchange"}"""));
        var groupId = (await ReadJson(created)).GetProperty("group_id").GetString()!;
        Cleanup(() => asOwner.DeleteAsync($"/api/groups/{groupId}"));

        var joined = await asIntruder.PostAsync($"/api/groups/{groupId}/join",
            Json("""{"invite_token": "not-the-secret"}"""));
        Assert.False(joined.IsSuccessStatusCode);
        var error = (await ReadJson(joined)).GetProperty("error");
        Assert.Equal(JsonValueKind.String, error.GetProperty("code").ValueKind);
    }
}
