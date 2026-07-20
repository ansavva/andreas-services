using Humbugg.Api.Data;
using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Services;

/// <summary>
/// Resolves a recipient's non-essential email opt-out from their Humbugg profile. Essential categories
/// always send; non-essential categories send only when the recipient's account has the preference
/// enabled. Recipients without a resolvable account (for example an invitation to someone who has not
/// signed up) fail open so essential onboarding mail is never dropped — and those categories are
/// essential anyway. This adapter lives outside <c>Email/Core</c> because it depends on persistence.
/// </summary>
internal sealed class AccountEmailPreferenceGate(
    IProfileRepository profiles,
    ILogger<AccountEmailPreferenceGate> logger) : IEmailPreferenceGate
{
    /// <inheritdoc />
    public async Task<bool> IsAllowedAsync(TransactionalEmail email, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(email);

        if (EmailClassification.IsEssential(email.Category))
            return true;

        // Non-essential mail addressed to someone we cannot tie to an account cannot be scoped to a
        // preference; allow it rather than silently dropping messages.
        if (string.IsNullOrEmpty(email.RecipientUserId))
            return true;

        var profile = await profiles.GetAsync(email.RecipientUserId, cancellationToken);
        if (profile is null)
        {
            logger.LogDebug(
                "No profile for recipient {RecipientUserId}; allowing non-essential {Category}",
                email.RecipientUserId,
                email.Category);
            return true;
        }

        return profile.NonEssentialEmailsEnabled;
    }
}
