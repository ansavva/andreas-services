namespace Humbugg.Api.Services.Email.Core;

/// <summary>
/// Decides whether a rendered message may be delivered to its recipient. This is the single choke
/// point where the recipient's non-essential email opt-out is honored: essential categories are always
/// allowed, while non-essential ones are suppressed when the recipient has opted out. Implementations
/// resolve the recipient's preference from their account (<see cref="TransactionalEmail.RecipientUserId"/>).
/// </summary>
public interface IEmailPreferenceGate
{
    /// <summary>
    /// Returns true when the message may be sent. Never throws for an unknown recipient — it fails open
    /// (allow) so a missing profile can never silently drop mail; only an explicit opt-out suppresses.
    /// </summary>
    Task<bool> IsAllowedAsync(TransactionalEmail email, CancellationToken cancellationToken = default);
}

/// <summary>
/// A gate that permits every message. Used where preferences do not apply (local capture transport,
/// unit tests) and as a safe default. Because it never consults account state it lives in Core.
/// </summary>
public sealed class AllowAllEmailPreferenceGate : IEmailPreferenceGate
{
    /// <inheritdoc />
    public Task<bool> IsAllowedAsync(TransactionalEmail email, CancellationToken cancellationToken = default) =>
        Task.FromResult(true);
}
