using Humbugg.Api;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Formats.Png;
using SixLabors.ImageSharp.PixelFormats;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class ProfileServiceAvatarTests
{
    private const string BaseUrl = "https://humbugg.com";

    [Fact]
    public async Task UploadingAvatarStoresObjectAndReturnsDerivedUrl()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");

        var profile = await world.Service.UploadAvatarAsync(
            new UploadAvatarRequest(PngDataUrl()), TestContext.Current.CancellationToken);

        Assert.NotNull(world.Profiles.Items["user"].AvatarKey);
        var key = world.Profiles.Items["user"].AvatarKey!;
        Assert.StartsWith("avatars/user/", key);
        Assert.Equal($"{BaseUrl}/{key}", profile.AvatarUrl);
        Assert.True(world.Store.Objects.ContainsKey(key));
    }

    [Fact]
    public async Task UploadingAvatarWithoutAProfileIsRejected()
    {
        var world = new World();
        var error = await Assert.ThrowsAsync<ApiException>(() =>
            world.Service.UploadAvatarAsync(new UploadAvatarRequest(PngDataUrl()), TestContext.Current.CancellationToken));
        Assert.Equal(404, error.StatusCode);
        Assert.Empty(world.Store.Objects);
    }

    [Fact]
    public async Task ReplacingAvatarDeletesThePreviousObject()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");

        await world.Service.UploadAvatarAsync(new UploadAvatarRequest(PngDataUrl()), TestContext.Current.CancellationToken);
        var firstKey = world.Profiles.Items["user"].AvatarKey!;
        await world.Service.UploadAvatarAsync(new UploadAvatarRequest(PngDataUrl()), TestContext.Current.CancellationToken);
        var secondKey = world.Profiles.Items["user"].AvatarKey!;

        Assert.NotEqual(firstKey, secondKey);
        Assert.False(world.Store.Objects.ContainsKey(firstKey));
        Assert.True(world.Store.Objects.ContainsKey(secondKey));
    }

    [Fact]
    public async Task RemovingAvatarClearsTheKeyDeletesObjectAndReturnsNullUrl()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");
        await world.Service.UploadAvatarAsync(new UploadAvatarRequest(PngDataUrl()), TestContext.Current.CancellationToken);
        var key = world.Profiles.Items["user"].AvatarKey!;

        var profile = await world.Service.RemoveAvatarAsync(TestContext.Current.CancellationToken);

        Assert.Null(world.Profiles.Items["user"].AvatarKey);
        Assert.Null(profile.AvatarUrl);
        Assert.False(world.Store.Objects.ContainsKey(key));
    }

    [Fact]
    public async Task InvalidUploadNeverTouchesStorage()
    {
        var world = new World();
        world.Profiles.Items["user"] = new ProfileRecord("user", "Alex", "now", "now");

        await Assert.ThrowsAsync<ApiException>(() =>
            world.Service.UploadAvatarAsync(new UploadAvatarRequest("data:image/png;base64,not-base64"), TestContext.Current.CancellationToken));

        Assert.Empty(world.Store.Objects);
        Assert.Null(world.Profiles.Items["user"].AvatarKey);
    }

    private static string PngDataUrl()
    {
        using var image = new Image<Rgba32>(256, 256, new Rgba32(30, 90, 60, 255));
        using var stream = new MemoryStream();
        image.Save(stream, new PngEncoder());
        return $"data:image/png;base64,{Convert.ToBase64String(stream.ToArray())}";
    }

    private sealed class World
    {
        public FakeUser User { get; } = new();
        public InMemoryProfiles Profiles { get; } = new();
        public InMemoryAvatarStore Store { get; } = new();
        public ProfileService Service { get; }

        public World()
        {
            var settings = new HumbuggSettings("us-east-1", "us-east-1", "pool", "client",
                "http://localhost:5173", BaseUrl, null, "profiles", "groups", "members", "draws", "audit", "analytics",
                AvatarBaseUrl: BaseUrl);
            Service = new ProfileService(User, Profiles, Store, settings);
        }
    }

    private sealed class FakeUser : ICurrentUser { public string UserId => "user"; }

    private sealed class InMemoryProfiles : IProfileRepository
    {
        public Dictionary<string, ProfileRecord> Items { get; } = new(StringComparer.Ordinal);
        public Task<ProfileRecord?> GetAsync(string userId, CancellationToken cancellationToken = default) =>
            Task.FromResult(Items.TryGetValue(userId, out var record) ? record : null);
        public Task<ProfileRecord> UpsertAsync(string userId, string displayName, CancellationToken cancellationToken = default)
        {
            var record = new ProfileRecord(userId, displayName, "now", "now");
            Items[userId] = record;
            return Task.FromResult(record);
        }
        public Task<ProfileRecord> SetAvatarKeyAsync(string userId, string? avatarKey, CancellationToken cancellationToken = default)
        {
            if (!Items.TryGetValue(userId, out var record))
                throw ApiException.NotFound("Complete your profile before adding a photo.");
            Items[userId] = record with { AvatarKey = avatarKey };
            return Task.FromResult(Items[userId]);
        }
        public Task DeleteAsync(string userId, CancellationToken cancellationToken = default) { Items.Remove(userId); return Task.CompletedTask; }
    }
}
