using Humbugg.Api.Services;

namespace Humbugg.Api.Tests;

/// <summary>
/// The verified-address lookup (#137), in memory.
/// </summary>
/// <remarks>
/// Empty by default, which is the honest default for a test that is not about notifications: an
/// account with no verified address is sent nothing, so a service under test does not silently
/// depend on mail it never asserted. Seed <see cref="Emails"/> to make one reachable.
/// </remarks>
internal sealed class FakeAccountDirectory : IAccountDirectory
{
    public Dictionary<string, string> Emails { get; } = new(StringComparer.Ordinal);

    public Task<string?> VerifiedEmailAsync(string userId, CancellationToken cancellationToken = default) =>
        Task.FromResult(Emails.GetValueOrDefault(userId));
}
