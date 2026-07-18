using Amazon.DynamoDBv2.Model;
using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using System.Net;
using System.Security.Claims;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// Security tests for the controls named in the Humbugg threat model (humbugg/docs/threat-model.md):
/// invite-secret handling that never leaks through referrers or logs, enumeration resistance on
/// join, the emergency-reveal audit, and the (configurable, plan-independent) rate-limit wiring.
/// </summary>
public sealed class SecurityControlsTests
{
    // ─── Invite secrets are delivered in the URL fragment, never the path/query ──────────────
    // A fragment (#invite=...) is not sent to the server, is not written to access logs, and is
    // stripped from the Referer header — so the invite secret cannot leak the way a query string can.

    [Fact]
    public async Task RotatedInviteDeliversSecretOnlyInUrlFragment()
    {
        var fixture = new Fixture(Fixture.Organizer());

        var response = await fixture.Subject.RotateInviteAsync("group", TestContext.Current.CancellationToken);

        var url = response.InviteUrl;
        var hashIndex = url.IndexOf('#');
        Assert.True(hashIndex > 0, "The invite URL must carry the secret in a fragment.");
        var beforeFragment = url[..hashIndex];
        var fragment = url[(hashIndex + 1)..];

        Assert.StartsWith("invite=", fragment);
        var secret = fragment["invite=".Length..];

        // The referrer-/log-exposed portion of the URL (everything before '#') must not contain the secret.
        Assert.DoesNotContain(secret, beforeFragment, StringComparison.Ordinal);
        Assert.DoesNotContain("invite=", beforeFragment, StringComparison.Ordinal);
        Assert.DoesNotContain("?", beforeFragment, StringComparison.Ordinal);
        Assert.Equal("https://humbugg.example/join/group", beforeFragment);
        // 32 random bytes, base64url-encoded, is 43 characters — the shape JoinAsync accepts.
        Assert.Equal(43, secret.Length);
    }

    // ─── Enumeration resistance: a wrong token and a malformed token are indistinguishable ────

    [Fact]
    public async Task JoinRejectsMalformedAndWrongTokensWithTheIdenticalForbiddenResponse()
    {
        var malformed = await Assert.ThrowsAsync<ApiException>(() =>
            new Fixture(member: null).Subject.JoinAsync("group", new JoinGroupRequest("not-a-real-token"), TestContext.Current.CancellationToken));

        // Correctly shaped (43-char base64url) token, but the wrong secret for this group.
        var wellFormedButWrong = new string('a', 43);
        var wrong = await Assert.ThrowsAsync<ApiException>(() =>
            new Fixture(member: null).Subject.JoinAsync("group", new JoinGroupRequest(wellFormedButWrong), TestContext.Current.CancellationToken));

        Assert.Equal(403, malformed.StatusCode);
        Assert.Equal(403, wrong.StatusCode);
        Assert.Equal(malformed.Message, wrong.Message);
        Assert.Equal(malformed.Code, wrong.Code);
    }

    // ─── Emergency-reveal audit: organizer-only, always recorded with actor + reason ──────────

    [Fact]
    public async Task OrganizerRevealRecordsExactlyOneAuditEventWithTheReason()
    {
        var fixture = new Fixture(Fixture.Organizer(), drawn: true);

        await fixture.Subject.RevealAsync("group", new RevealRequest("investigating a delivery complaint"), TestContext.Current.CancellationToken);

        var record = Assert.Single(fixture.Audit.Events);
        Assert.Equal(AuditAction.AssignmentRevealed, record.Action);
        Assert.Equal("investigating a delivery complaint", record.Metadata?["reason"]);
    }

    [Fact]
    public async Task NonOrganizerCannotRevealAndNothingIsAudited()
    {
        var fixture = new Fixture(Fixture.Member("actor", organizer: false), drawn: true);

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            fixture.Subject.RevealAsync("group", new RevealRequest("curiosity"), TestContext.Current.CancellationToken));

        Assert.Equal(403, error.StatusCode);
        Assert.Empty(fixture.Audit.Events);
    }

    [Fact]
    public async Task RevealWithoutAReasonIsRejectedAndNothingIsAudited()
    {
        var fixture = new Fixture(Fixture.Organizer(), drawn: true);

        var error = await Assert.ThrowsAsync<ApiException>(() =>
            fixture.Subject.RevealAsync("group", new RevealRequest("   "), TestContext.Current.CancellationToken));

        Assert.Equal(400, error.StatusCode);
        Assert.Empty(fixture.Audit.Events);
    }

    // ─── One uniform rate limit, configurable and on by default ───────────────────────────────

    [Fact]
    public void RateLimitSettingsUseSafeDefaultsWhenUnset()
    {
        var settings = WithEnvironment(new(), RateLimitSettings.FromEnvironment);

        Assert.True(settings.Enabled);
        Assert.Equal(300, settings.Global.PermitLimit);
        Assert.Equal(60, settings.Global.WindowSeconds);
    }

    [Fact]
    public void RateLimitSettingsAreOverridableFromTheEnvironment()
    {
        var settings = WithEnvironment(new()
        {
            ["HUMBUGG_RATELIMIT_ENABLED"] = "false",
            ["HUMBUGG_RATELIMIT_GLOBAL_LIMIT"] = "3",
            ["HUMBUGG_RATELIMIT_GLOBAL_WINDOW_SECONDS"] = "600",
        }, RateLimitSettings.FromEnvironment);

        Assert.False(settings.Enabled);
        Assert.Equal(3, settings.Global.PermitLimit);
        Assert.Equal(600, settings.Global.WindowSeconds);
    }

    [Fact]
    public void RateLimitSettingsRejectNonPositiveLimits()
    {
        var error = Assert.Throws<InvalidOperationException>(() =>
            WithEnvironment(new() { ["HUMBUGG_RATELIMIT_GLOBAL_LIMIT"] = "0" }, RateLimitSettings.FromEnvironment));

        Assert.Contains("HUMBUGG_RATELIMIT_GLOBAL_LIMIT", error.Message);
    }

    // ─── One global limiter covers every endpoint — no per-endpoint policies ──────────────────

    [Fact]
    public void GlobalLimiterCoversEveryEndpoint()
    {
        var services = new ServiceCollection();
        services.AddHumbuggRateLimiter(new RateLimitSettings(Enabled: true, Global: new RateLimitRule(300, 60)));

        var options = services.BuildServiceProvider()
            .GetRequiredService<IOptions<RateLimiterOptions>>().Value;

        Assert.NotNull(options.GlobalLimiter);
    }

    // ─── Partition key follows the account across IPs, then falls back to the TRUSTED client IP ─

    [Fact]
    public void PartitionKeyPrefersTheCognitoSubject()
    {
        var context = new DefaultHttpContext
        {
            User = new ClaimsPrincipal(new ClaimsIdentity([new Claim("sub", "cognito-123")], "test"))
        };
        context.Request.Headers["X-Forwarded-For"] = "203.0.113.9";

        Assert.Equal("user:cognito-123", RateLimiterConfiguration.PartitionKey(context));
    }

    [Fact]
    public void PartitionKeyUsesTheTrustedConnectionIpAndIgnoresSpoofableForwardedHeader()
    {
        var context = new DefaultHttpContext();
        context.Connection.RemoteIpAddress = IPAddress.Parse("198.51.100.7");
        // A caller-supplied X-Forwarded-For must NOT influence the partition — otherwise an attacker
        // could rotate the header to mint unlimited IP buckets and evade the per-IP limit.
        context.Request.Headers["X-Forwarded-For"] = "203.0.113.9, 10.0.0.1";

        Assert.Equal("ip:198.51.100.7", RateLimiterConfiguration.PartitionKey(context));
    }

    private static T WithEnvironment<T>(Dictionary<string, string> variables, Func<T> read)
    {
        var keys = new[]
        {
            "HUMBUGG_RATELIMIT_ENABLED",
            "HUMBUGG_RATELIMIT_GLOBAL_LIMIT",
            "HUMBUGG_RATELIMIT_GLOBAL_WINDOW_SECONDS",
        };
        var previous = keys.ToDictionary(key => key, Environment.GetEnvironmentVariable);
        try
        {
            foreach (var key in keys) Environment.SetEnvironmentVariable(key, null);
            foreach (var (key, value) in variables) Environment.SetEnvironmentVariable(key, value);
            return read();
        }
        finally
        {
            foreach (var (key, value) in previous) Environment.SetEnvironmentVariable(key, value);
        }
    }

    private sealed class Fixture
    {
        public FakeGroups Groups { get; }
        public FakeAuditTrail Audit { get; } = new();
        public GroupService Subject { get; }

        public Fixture(MembershipRecord? member, bool drawn = false)
        {
            var members = new List<MembershipRecord> { Member("other", organizer: false) };
            if (member is not null) members.Add(member);
            Groups = new FakeGroups(Group(drawn), drawn);
            Subject = new GroupService(
                new FakeUser(), new FakeProfiles(), Groups, new FakeMembers(members),
                new MatchingService(), new PlanCatalog(new()), Audit,
                new HumbuggSettings(
                    "us-east-1", "us-east-1", "pool", "client", "https://humbugg.example", "https://humbugg.example", null,
                    "profiles", "groups", "members", "draws", "audit"));
        }

        public static MembershipRecord Organizer() => Member("actor", organizer: true);

        public static MembershipRecord Member(string memberId, bool organizer) => new(
            memberId, "group", memberId == "actor" ? "user" : $"user-{memberId}", memberId,
            organizer, true, "wish", "avoid", new Address("address"), "now", "now");

        private static GroupRecord Group(bool drawn) => new(
            "group", "owner", "Exchange", "", null, null, null, "USD", PlanCode.Free, null,
            drawn ? GroupStatus.Drawn : GroupStatus.Open, "hash", [], "now", "now");
    }

    private sealed class FakeGroups(GroupRecord group, bool drawn) : IGroupRepository
    {
        public Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<GroupRecord?>(group);
        public Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default) => Task.FromResult(group);
        public Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<DrawRecord?>(
            drawn ? new DrawRecord("group", "draw", new Dictionary<string, string> { ["actor"] = "other", ["other"] = "actor" }, "now", "user") : null);
        public Task<GroupRecord> CreateAsync(GroupRecord value, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeUser : ICurrentUser { public string UserId => "user"; }

    private sealed class FakeAuditTrail : IAuditTrail
    {
        public List<(AuditAction Action, string GroupId, IReadOnlyDictionary<string, string>? Metadata)> Events { get; } = [];

        public Task RecordAsync(AuditAction action, string groupId, AuditTarget target,
            IReadOnlyDictionary<string, string>? metadata = null, string? organizationId = null, CancellationToken cancellationToken = default)
        {
            Events.Add((action, groupId, metadata));
            return Task.CompletedTask;
        }
    }

    private sealed class FakeProfiles : IProfileRepository
    {
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) => Task.FromResult<ProfileRecord?>(new(userId, "User", "now", "now"));
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class FakeMembers(IEnumerable<MembershipRecord> items) : IMembershipRepository
    {
        private readonly List<MembershipRecord> items = items.ToList();
        public Task<MembershipRecord?> GetByUserAndGroupAsync(string userId, string groupId, CancellationToken cancellationToken = default) => Task.FromResult(items.FirstOrDefault(item => item.UserId == userId && item.GroupId == groupId));
        public Task<IReadOnlyList<MembershipRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(items.Where(item => item.GroupId == groupId).ToList());
        public Task<IReadOnlyList<MembershipRecord>> GetByUserAsync(string userId, CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<MembershipRecord>>(items.Where(item => item.UserId == userId).ToList());
        public Task<MembershipRecord?> GetAsync(string memberId, CancellationToken cancellationToken = default) => Task.FromResult(items.FirstOrDefault(item => item.MemberId == memberId));
        public Task<MembershipRecord> CreateAsync(string groupId, string userId, string displayName, bool organizer, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdatePrivateAsync(string memberId, string wishlist, string avoidances, Address address, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task<MembershipRecord> UpdateParticipationAsync(string memberId, bool participating, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteAsync(string memberId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
        public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }
}
