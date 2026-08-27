using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

public interface IWishService
{
    Task<IReadOnlyList<Wish>> ListAsync(string groupId, CancellationToken cancellationToken = default);
    Task<Wish> CreateAsync(string groupId, CreateWishRequest request, CancellationToken cancellationToken = default);
    Task<Wish> UpdateAsync(string groupId, string wishId, UpdateWishRequest request, CancellationToken cancellationToken = default);
    Task DeleteAsync(string groupId, string wishId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<Wish>> ReorderAsync(string groupId, ReorderWishesRequest request, CancellationToken cancellationToken = default);
}

/// <summary>
/// A participant's own wishes. Every method resolves the caller's membership in the named group
/// first and operates on that member id, so a caller can only ever reach their own list — the group
/// id in the route selects a list, it does not authorize one.
/// </summary>
internal sealed class WishService(
    ICurrentUser user,
    IGroupRepository groups,
    IMembershipRepository memberships,
    IWishRepository wishes,
    IAuditTrail audit) : IWishService
{
    public async Task<IReadOnlyList<Wish>> ListAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var (_, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        return (await wishes.GetByMemberAsync(membership.MemberId, cancellationToken)).Select(Public).ToList();
    }

    public async Task<Wish> CreateAsync(
        string groupId,
        CreateWishRequest request,
        CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        var existing = await wishes.GetByMemberAsync(membership.MemberId, cancellationToken);
        if (existing.Count >= WishValidation.MaxWishesPerMember)
            throw ApiException.Conflict(
                $"A wishlist holds up to {WishValidation.MaxWishesPerMember} items. Remove one before adding another.");

        var now = DateTimeOffset.UtcNow.ToString("O");
        var record = new WishRecord(
            membership.MemberId,
            Guid.NewGuid().ToString("N"),
            group.GroupId,
            user.UserId,
            WishValidation.Kind(request.Kind),
            WishValidation.Title(request.Title),
            WishValidation.Url(request.Url, "url"),
            WishValidation.Url(request.ImageUrl, "image_url"),
            WishValidation.PriceCents(request.PriceCents),
            WishValidation.Currency(request.Currency, group.Currency),
            WishValidation.Quantity(request.Quantity),
            WishValidation.Priority(request.Priority),
            WishValidation.Details(request.Details),
            // Appended, not inserted. A new wish going to the bottom is predictable; a new wish
            // landing in the middle of a list the owner just arranged is not.
            existing.Count == 0 ? 0 : existing.Max(item => item.Position) + 1,
            now,
            now);

        await wishes.CreateAsync(record, cancellationToken);
        await audit.RecordAsync(
            AuditAction.WishCreated,
            group.GroupId,
            AuditTarget.Member(membership.MemberId),
            cancellationToken: cancellationToken);
        return Public(record);
    }

    public async Task<Wish> UpdateAsync(
        string groupId,
        string wishId,
        UpdateWishRequest request,
        CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        var fields = new Dictionary<string, AttributeValue>(StringComparer.Ordinal);

        // Absent means "leave alone" throughout. Only fields the caller actually named are written,
        // so a client sending a two-field patch cannot blank the rest of the wish.
        if (request.Kind is not null) fields["kind"] = DynamoValues.S(WishValidation.Kind(request.Kind).ToString());
        if (request.Title is not null) fields["title"] = DynamoValues.S(WishValidation.Title(request.Title));
        if (request.Url is not null) fields["url"] = DynamoValues.S(WishValidation.Url(request.Url, "url"));
        if (request.ImageUrl is not null) fields["image_url"] = DynamoValues.S(WishValidation.Url(request.ImageUrl, "image_url"));
        if (request.Currency is not null) fields["currency"] = DynamoValues.S(WishValidation.Currency(request.Currency, group.Currency));
        if (request.Quantity is not null) fields["quantity"] = DynamoValues.N(WishValidation.Quantity(request.Quantity));
        if (request.Priority is not null) fields["priority"] = DynamoValues.S(WishValidation.Priority(request.Priority).ToString());
        if (request.Details is not null) fields["details"] = DynamoValues.S(WishValidation.Details(request.Details));
        if (request.PriceCents is not null) fields["price_cents"] = DynamoValues.N(WishValidation.PriceCents(request.PriceCents)!.Value);

        if (fields.Count == 0) throw ApiException.BadRequest("Provide at least one field to update.");
        fields["updated_at"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O"));

        WishRecord updated;
        try { updated = await wishes.UpdateAsync(membership.MemberId, wishId, fields, cancellationToken); }
        catch (ConditionalCheckFailedException) { throw ApiException.NotFound("That wish is not on your list."); }

        await audit.RecordAsync(
            AuditAction.WishUpdated,
            group.GroupId,
            AuditTarget.Member(membership.MemberId),
            cancellationToken: cancellationToken);
        return Public(updated);
    }

    public async Task DeleteAsync(string groupId, string wishId, CancellationToken cancellationToken = default)
    {
        var (group, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        try { await wishes.DeleteAsync(membership.MemberId, wishId, cancellationToken); }
        catch (ConditionalCheckFailedException) { throw ApiException.NotFound("That wish is not on your list."); }
        await audit.RecordAsync(
            AuditAction.WishDeleted,
            group.GroupId,
            AuditTarget.Member(membership.MemberId),
            cancellationToken: cancellationToken);
    }

    public async Task<IReadOnlyList<Wish>> ReorderAsync(
        string groupId,
        ReorderWishesRequest request,
        CancellationToken cancellationToken = default)
    {
        var (_, membership) = await RequireMembershipAsync(groupId, cancellationToken);
        var current = await wishes.GetByMemberAsync(membership.MemberId, cancellationToken);
        var requested = request.WishIds ?? [];

        // The request must be a permutation of the list as it stands. A partial order would leave the
        // unnamed wishes at stale positions, and an order naming an unknown id is a client working
        // from a list that has since changed — both are better refused than half-applied.
        var currentIds = current.Select(item => item.WishId).ToHashSet(StringComparer.Ordinal);
        if (requested.Count != currentIds.Count ||
            requested.Distinct(StringComparer.Ordinal).Count() != requested.Count ||
            !requested.All(currentIds.Contains))
            throw ApiException.BadRequest(
                "wish_ids must list every wish on your list exactly once. Reload the list and try again.");

        await wishes.SetPositionsAsync(membership.MemberId, requested, cancellationToken);
        return (await wishes.GetByMemberAsync(membership.MemberId, cancellationToken)).Select(Public).ToList();
    }

    private async Task<(GroupRecord Group, MembershipRecord Membership)> RequireMembershipAsync(
        string groupId,
        CancellationToken cancellationToken)
    {
        var group = await groups.GetAsync(groupId, cancellationToken)
            ?? throw ApiException.NotFound("Group not found.");
        var membership = (await memberships.GetByUserAsync(user.UserId, cancellationToken))
            .FirstOrDefault(item => item.GroupId == groupId)
            ?? throw ApiException.NotFound("Group not found.");
        return (group, membership);
    }

    private static Wish Public(WishRecord record) => new(
        record.WishId,
        record.Kind,
        record.Title,
        NullIfEmpty(record.Url),
        NullIfEmpty(record.ImageUrl),
        record.PriceCents,
        record.PriceCents is null ? null : NullIfEmpty(record.Currency),
        record.Quantity,
        record.Priority,
        NullIfEmpty(record.Details),
        record.Position,
        record.CreatedAt,
        record.UpdatedAt);

    private static string? NullIfEmpty(string value) => string.IsNullOrWhiteSpace(value) ? null : value;
}
