using Microsoft.AspNetCore.WebUtilities;
using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Services;

/// <summary>
/// The managed-invitation secret, its stored hash, and the link that carries it — in one place,
/// because two services mint them.
/// </summary>
/// <remarks>
/// <see cref="InvitationService"/> creates and resends invitations; <see cref="ReminderService"/>
/// nudges the people who have not answered one. Until #675 the reminder linked to
/// <c>/groups/{id}</c>, where an invitee — not a member — could not go, because the secret is stored
/// only as a hash and the reminder had no way to make a link. It now does what "Send again" does:
/// mints a fresh secret, stores its hash, and links to it. The rules live here so the two cannot
/// drift on what a valid invitation link looks like.
/// </remarks>
internal static class InvitationLinks
{
    /// <summary>A fresh 256-bit secret, URL-safe.</summary>
    public static string Secret() => WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32));

    /// <summary>What is stored: the secret's SHA-256, lower-case hex. The secret itself is never stored.</summary>
    public static string Hash(string secret) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(secret)));

    /// <summary>The product app's join route with the invitation id and secret in the fragment, so no server log sees them.</summary>
    public static string Link(string appBaseUrl, string groupId, string invitationId, string secret) =>
        $"{appBaseUrl}/join/{groupId}#managed={invitationId}.{secret}";

    /// <summary>How long a freshly minted link stays valid.</summary>
    public static readonly TimeSpan Lifetime = TimeSpan.FromDays(14);
}
