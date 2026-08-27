using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

/// <summary>
/// Builds a portable, machine-readable snapshot of the caller's own personal data to serve the GDPR
/// right of access / data portability (Art. 15 &amp; 20). It is the read-only counterpart to the
/// erasure capability in <see cref="IAccountDeletionService"/>.
/// <para>
/// Runs purely on the caller's own Cognito identity — there is no administrator or organizer gate —
/// and only reads, so it is naturally idempotent and safe to call repeatedly. It returns exclusively
/// data the requester authored or that identifies them:
/// <list type="bullet">
/// <item>Their profile (display name, email from the token when present, timestamps).</item>
/// <item>Each of their group memberships, with the wishlist, avoidances, and mailing address
/// <b>they themselves</b> entered for that exchange, plus the group's name and status.</item>
/// </list>
/// It deliberately never includes another member's personal data, the group's other members, the
/// exclusion matrix, or any draw assignment — in particular it never reveals whom the caller was
/// assigned to give to, because that recipient's wishlist/address is the recipient's personal data,
/// not the caller's.
/// </para>
/// </summary>
public interface IDataExportService
{
    Task<DataExport> ExportAsync(CancellationToken cancellationToken = default);
}

internal sealed class DataExportService(
    ICurrentUser user,
    IProfileRepository profiles,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IWishRepository wishes) : IDataExportService
{
    private const string FormatVersion = "1.0";

    public async Task<DataExport> ExportAsync(CancellationToken cancellationToken = default)
    {
        var userId = user.UserId;

        var profile = await profiles.GetAsync(userId, cancellationToken);

        // GetByUserAsync is scoped to the caller's own user_id, so these rows are only ever the
        // caller's memberships — never another person's.
        var memberOf = await memberships.GetByUserAsync(userId, cancellationToken);
        var exportedMemberships = new List<ExportedMembership>(memberOf.Count);
        foreach (var membership in memberOf)
        {
            var group = await groups.GetAsync(membership.GroupId, cancellationToken);
            if (group is null) continue; // Orphaned membership whose group is already gone: nothing to export.
            exportedMemberships.Add(new ExportedMembership(
                GroupId: membership.GroupId,
                GroupName: group.Name,
                GroupStatus: group.Status,
                MemberId: membership.MemberId,
                Role: membership.IsOrganizer ? "organizer" : "participant",
                IsParticipating: membership.IsParticipating,
                // Only the caller's own authored content for this exchange.
                Wishlist: NullIfEmpty(membership.Wishlist),
                Avoidances: NullIfEmpty(membership.Avoidances),
                Address: HasAddress(membership.Address) ? membership.Address : null,
                // Keyed by the caller's own member_id, so this reads their list and no one else's.
                Wishes: (await wishes.GetByMemberAsync(membership.MemberId, cancellationToken))
                    .Select(ExportedWish).ToList(),
                JoinedAt: membership.CreatedAt,
                UpdatedAt: membership.UpdatedAt));
        }

        exportedMemberships = exportedMemberships
            .OrderBy(item => item.JoinedAt, StringComparer.Ordinal)
            .ToList();

        var notes = new List<string>
        {
            "This export contains only your own personal data. It never includes other members' " +
            "wishlists, addresses, or the identity of anyone you were assigned to give to.",
        };
        if (user.Email is null)
            notes.Add("Your email address is managed by AWS Cognito and was not present on the access " +
                      "token used for this request, so it is omitted here.");
        if (profile is null)
            notes.Add("No profile record was found for your account; you may not have completed profile setup.");
        // These fields are added by in-flight work; export them here once they persist real values.
        notes.Add("avatar is reserved for the profile-photo feature (issue #186) and is not yet stored.");
        notes.Add("non_essential_emails_enabled is reserved for the email-preference feature (issue #187) " +
                  "and is not yet stored.");
        notes.Add("consent is reserved for the signup Terms/Privacy consent record (issue #188) and is " +
                  "not yet stored.");

        var exportedProfile = new ExportedProfile(
            UserId: userId,
            DisplayName: profile?.DisplayName,
            Email: user.Email,
            CreatedAt: profile?.CreatedAt,
            UpdatedAt: profile?.UpdatedAt,
            Avatar: null,                       // #186
            NonEssentialEmailsEnabled: null,    // #187
            Consent: null);                     // #188

        return new DataExport(
            new DataExportMetadata(
                GeneratedAt: DateTimeOffset.UtcNow.ToString("O"),
                FormatVersion: FormatVersion,
                SubjectUserId: userId,
                Notes: notes),
            exportedProfile,
            exportedMemberships);
    }

    private static string? NullIfEmpty(string? value) => string.IsNullOrWhiteSpace(value) ? null : value;

    private static Wish ExportedWish(WishRecord record) => new(
        record.WishId, record.Kind, record.Title,
        NullIfEmpty(record.Url), NullIfEmpty(record.ImageUrl), record.PriceCents,
        record.PriceCents is null ? null : NullIfEmpty(record.Currency),
        record.Quantity, record.Priority, NullIfEmpty(record.Details), record.Position,
        record.CreatedAt, record.UpdatedAt);

    private static bool HasAddress(Address? address) => address is not null && new[]
    {
        address.Line1, address.Line2, address.City, address.Region, address.PostalCode, address.Country,
    }.Any(field => !string.IsNullOrWhiteSpace(field));
}
