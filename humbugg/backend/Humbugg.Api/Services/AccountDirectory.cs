using Amazon.CognitoIdentityProvider;
using Amazon.CognitoIdentityProvider.Model;

namespace Humbugg.Api.Services;

/// <summary>
/// Where a member's email address comes from (#137).
/// </summary>
/// <remarks>
/// <para>
/// Humbugg does not store one. Until now the only address it could reach was on an accepted
/// **managed invitation**, which is a Plus capability — so a Free exchange could not be notified at
/// all, and "keep account holders informed on every plan" was unbuildable. Cognito already holds a
/// verified address for every account; this reads it back.
/// </para>
/// <para>
/// **Only a verified one, ever.** Cognito's <c>email_verified</c> is the difference between an
/// address the person proved they control and a string they typed. Sending to the latter would turn
/// Humbugg into a way to mail arbitrary strangers on someone else's say-so, which is a spam relay
/// with extra steps. An unverified address reads as no address, and the caller sends nothing.
/// </para>
/// <para>
/// Not cached. A draw notifies at most fifty people once, and a cached address is a stale address
/// the day somebody changes theirs — which is exactly when a "your assignment is ready" going to the
/// old one matters most.
/// </para>
/// </remarks>
public interface IAccountDirectory
{
    /// <summary>The account's verified email address, or null when there is not one to send to.</summary>
    Task<string?> VerifiedEmailAsync(string userId, CancellationToken cancellationToken = default);
}

internal sealed class CognitoAccountDirectory(
    IAmazonCognitoIdentityProvider cognito,
    HumbuggSettings settings,
    ILogger<CognitoAccountDirectory> logger) : IAccountDirectory
{
    /// <summary>
    /// The rule, separated from the call so it can be tested without standing up Cognito.
    /// </summary>
    /// <remarks>
    /// Fails closed in every direction: an absent flag, a flag that is not exactly "true", and a
    /// verified flag with no address all read as no address. The default answer to "should Humbugg
    /// email this string?" is no.
    /// </remarks>
    internal static string? VerifiedEmailFrom(IEnumerable<AttributeType> attributes)
    {
        var list = attributes.ToList();
        var verified = list.FirstOrDefault(attribute => attribute.Name == "email_verified")?.Value;
        if (!string.Equals(verified, "true", StringComparison.OrdinalIgnoreCase)) return null;
        var email = list.FirstOrDefault(attribute => attribute.Name == "email")?.Value;
        return string.IsNullOrWhiteSpace(email) ? null : email.Trim();
    }

    public async Task<string?> VerifiedEmailAsync(string userId, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(userId)) return null;
        // An anonymized membership points at a pseudonym rather than a Cognito subject (#189). Asking
        // Cognito about one is a guaranteed miss, and a noisy one — skip it.
        if (userId.StartsWith("anon:", StringComparison.Ordinal)) return null;

        try
        {
            // The pool's username is the subject for this pool's sign-in configuration, and
            // AdminGetUser accepts it directly.
            var response = await cognito.AdminGetUserAsync(new AdminGetUserRequest
            {
                UserPoolId = settings.CognitoUserPoolId,
                Username = userId,
            }, cancellationToken);

            return VerifiedEmailFrom(response.UserAttributes ?? []);
        }
        catch (UserNotFoundException)
        {
            // A deleted account whose membership row survives because a draw references it. There is
            // nobody to write to, which is the correct outcome rather than an error.
            return null;
        }
        catch (Exception exception)
        {
            // Never fatal. A notification is a courtesy on top of an action that already succeeded,
            // and a Cognito outage must not fail a draw.
            logger.LogWarning(exception, "Could not read a verified address for a member.");
            return null;
        }
    }
}
