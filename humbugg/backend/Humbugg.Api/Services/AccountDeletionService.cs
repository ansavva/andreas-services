using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Services;

/// <summary>
/// Executes a user's own request to delete their Humbugg account. The request is honored on the
/// caller's own identity: there is no organizer, Work-administrator, or organization approval gate,
/// so an authorized Work administrator can never block an individual's valid deletion request.
/// <para>
/// The operation is idempotent — safe to retry — and defines exactly how each class of data is
/// handled (see <c>humbugg/docs/data-retention-deletion.md</c>):
/// <list type="bullet">
/// <item>Product-profile data (profile row, wishlist, avoidances, mailing address, display name) is erased.</item>
/// <item>Groups the user organizes are deleted in full (memberships + draw + group).</item>
/// <item>Memberships in groups the user only participates in are removed when the group is still open,
/// and anonymized in place when a draw has completed — this keeps the completed draw's giver→recipient
/// mapping valid while removing the personal data behind it.</item>
/// <item>Audit records are never deleted; the actor reference is anonymized to an irreversible
/// pseudonym so the trail (what happened, to what, when) stays intact.</item>
/// <item>Required financial records live outside the product-profile store and are retained under their
/// own legal retention rule; deletion only anonymizes their link to the person, never erases them.</item>
/// </list>
/// </para>
/// </summary>
public interface IAccountDeletionService
{
    Task DeleteAsync(CancellationToken cancellationToken = default);
}

internal sealed class AccountDeletionService(
    ICurrentUser user,
    IProfileRepository profiles,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IAuditTrail audit,
    IAuditActorAnonymizer auditAnonymizer) : IAccountDeletionService
{
    // Scope used for the single account-level terminal audit event. Group-scoped effects
    // (group deletions, participant removals) are audited under their own group id.
    private const string AccountAuditScope = "account";
    private const string AnonymizedDisplayName = "Former participant";

    public async Task DeleteAsync(CancellationToken cancellationToken = default)
    {
        var userId = user.UserId;
        var pseudonym = Pseudonym(userId);

        var memberOf = await memberships.GetByUserAsync(userId, cancellationToken);
        foreach (var membership in memberOf)
        {
            var group = await groups.GetAsync(membership.GroupId, cancellationToken);
            if (group is null)
            {
                // Orphaned membership row (its group is already gone): just remove it.
                await memberships.DeleteAsync(membership.MemberId, cancellationToken);
                continue;
            }
            if (membership.IsOrganizer)
                await DeleteOrganizedGroupAsync(group, userId, cancellationToken);
            else
                await RemoveParticipantAsync(group, membership, pseudonym, userId, cancellationToken);
        }

        var profile = await profiles.GetAsync(userId, cancellationToken);
        await profiles.DeleteAsync(userId, cancellationToken);

        var didWork = profile is not null || memberOf.Count > 0;
        if (didWork)
            await audit.RecordAsync(AuditAction.AccountDeleted, AccountAuditScope, AuditTarget.Account(pseudonym),
                new Dictionary<string, string>
                {
                    ["groups_affected"] = memberOf.Count.ToString(System.Globalization.CultureInfo.InvariantCulture)
                }, cancellationToken: cancellationToken);

        // Anonymize the actor across the whole trail last, so the terminal event above is swept too.
        // Idempotent: a retry finds no records still pointing at the real subject.
        await auditAnonymizer.AnonymizeActorAsync(userId, pseudonym, cancellationToken);
    }

    private async Task DeleteOrganizedGroupAsync(GroupRecord group, string userId, CancellationToken cancellationToken)
    {
        await memberships.DeleteByGroupAsync(group.GroupId, cancellationToken);
        await groups.DeleteAsync(group.GroupId, cancellationToken);
        await audit.RecordAsync(AuditAction.GroupDeleted, group.GroupId, AuditTarget.Group(group.GroupId),
            new Dictionary<string, string> { ["reason"] = "account_deletion" }, cancellationToken: cancellationToken);
    }

    private async Task RemoveParticipantAsync(GroupRecord group, MembershipRecord membership, string pseudonym, string userId, CancellationToken cancellationToken)
    {
        if (group.Status == GroupStatus.Drawn)
        {
            // A draw references member_id, so the row must survive; strip the personal data instead.
            await memberships.AnonymizeAsync(membership.MemberId, pseudonym, AnonymizedDisplayName, cancellationToken);
            await audit.RecordAsync(AuditAction.MembershipAnonymized, group.GroupId, AuditTarget.Member(membership.MemberId),
                new Dictionary<string, string> { ["reason"] = "account_deletion" }, cancellationToken: cancellationToken);
            return;
        }

        await memberships.DeleteAsync(membership.MemberId, cancellationToken);
        await audit.RecordAsync(AuditAction.ParticipantRemoved, group.GroupId, AuditTarget.Member(membership.MemberId),
            new Dictionary<string, string> { ["reason"] = "account_deletion" }, cancellationToken: cancellationToken);

        var remaining = group.Exclusions.Where(pair => !pair.Contains(membership.MemberId, StringComparer.Ordinal)).ToList();
        if (remaining.Count == group.Exclusions.Count) return;
        try
        {
            await groups.UpdateAsync(group.GroupId,
                new Dictionary<string, AttributeValue> { ["exclusions"] = DynamoValues.ExclusionsValue(remaining) },
                GroupStatus.Open, cancellationToken);
        }
        catch (ConditionalCheckFailedException)
        {
            // The group was drawn or removed concurrently; the exclusion cleanup no longer applies.
        }
    }

    /// <summary>
    /// Derives a stable, irreversible pseudonym from the Cognito subject. Deterministic so every
    /// record for the same user maps to one anonymized identity and retries stay idempotent; a
    /// one-way hash so the pseudonym cannot be resolved back to the original subject.
    /// </summary>
    internal static string Pseudonym(string userId) =>
        "deleted-user-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(userId))).ToLowerInvariant()[..24];
}
