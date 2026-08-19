using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services.Email.Core;
using Microsoft.AspNetCore.WebUtilities;
using System.Net.Mail;
using System.Security.Cryptography;
using System.Text;

namespace Humbugg.Api.Services;

public interface IInvitationService
{
    Task<IReadOnlyList<ManagedInvitation>> ListAsync(string groupId, CancellationToken cancellationToken = default);
    Task<CreateInvitationsResponse> CreateAsync(string groupId, CreateInvitationsRequest request, CancellationToken cancellationToken = default);
    Task<ManagedInvitation> ResendAsync(string groupId, string invitationId, CancellationToken cancellationToken = default);
    Task RevokeAsync(string groupId, string invitationId, CancellationToken cancellationToken = default);
    Task<AcceptInvitationResponse> AcceptAsync(string groupId, string invitationId, AcceptInvitationRequest request, CancellationToken cancellationToken = default);
    Task<InvitationPreview> PreviewAsync(string groupId, string invitationId, string? token, CancellationToken cancellationToken = default);
}

internal sealed class InvitationService(ICurrentUser user, IProfileRepository profiles, IGroupRepository groups, IMembershipRepository members,
    IInvitationRepository invitations, IPlanCatalog plans, ITransactionalEmailTemplates templates, ITransactionalEmailService email,
    IAuditTrail audit, HumbuggSettings settings) : IInvitationService
{
    public async Task<IReadOnlyList<ManagedInvitation>> ListAsync(string groupId, CancellationToken ct = default) { await RequireOrganizer(groupId, ct); var result = new List<ManagedInvitation>(); foreach (var item in await invitations.GetByGroupAsync(groupId, ct)) result.Add(await Public(item, ct)); return result; }
    public async Task<CreateInvitationsResponse> CreateAsync(string groupId, CreateInvitationsRequest request, CancellationToken ct = default)
    {
        var group = await RequireOrganizer(groupId, ct); var addresses = (request.Emails ?? []).Select(Normalize).ToList();
        if (addresses.Count == 0) throw ApiException.BadRequest("At least one email address is required.");
        if (addresses.Count != addresses.Distinct(StringComparer.Ordinal).Count()) throw ApiException.Conflict("Duplicate email addresses are not allowed.");
        var existing = (await invitations.GetByGroupAsync(groupId, ct)).Select(x => x.Email).ToHashSet(StringComparer.Ordinal);
        if (addresses.Any(existing.Contains)) throw ApiException.Conflict("One or more recipients have already been invited.");
        var result = new List<ManagedInvitation>();
        foreach (var address in addresses) result.Add(await CreateOne(group, address, ct));
        return new(result);
    }
    public async Task<ManagedInvitation> ResendAsync(string groupId, string id, CancellationToken ct = default)
    {
        var group = await RequireOrganizer(groupId, ct); var item = await Get(groupId, id, ct);
        if (DateTimeOffset.TryParse(item.LastSentAt, out var sent) && DateTimeOffset.UtcNow - sent < TimeSpan.FromMinutes(15)) throw ApiException.Conflict("Wait 15 minutes before resending.");
        var secret = Secret(); var expires = DateTimeOffset.UtcNow.AddDays(14).ToString("O");
        var message = templates.Invitation(new($"{id}:{Guid.NewGuid():N}", item.Email, "there", "Your organizer", group.Name, new Uri(Link(groupId, id, secret)), group.Customization));
        await email.SendAsync(message, ct); await invitations.UpdateAsync(id, "sent", Hash(secret), expires, message.MessageId, ct);
        await audit.RecordAsync(AuditAction.InvitationResent, groupId, new("invitation", id), cancellationToken: ct);
        return await Public((await invitations.GetAsync(id, ct))!, ct);
    }
    public async Task RevokeAsync(string groupId, string id, CancellationToken ct = default) { await RequireOrganizer(groupId, ct); await Get(groupId, id, ct); await invitations.UpdateAsync(id, "revoked", null, null, null, ct); await audit.RecordAsync(AuditAction.InvitationRevoked, groupId, new("invitation", id), cancellationToken: ct); }
    public async Task<AcceptInvitationResponse> AcceptAsync(string groupId, string id, AcceptInvitationRequest request, CancellationToken ct = default)
    {
        var group = await groups.GetAsync(groupId, ct) ?? throw ApiException.NotFound("Exchange not found."); var item = await Get(groupId, id, ct);
        if (string.IsNullOrWhiteSpace(request.Token) || !CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(item.TokenHash), Encoding.UTF8.GetBytes(Hash(request.Token)))) throw ApiException.Forbidden("This invitation is invalid or expired.");
        if (!string.Equals(Normalize(user.Email ?? "missing@example.invalid"), item.Email, StringComparison.Ordinal) && !request.ConfirmAddressMismatch) throw ApiException.Conflict("The signed-in address differs from the invited address. Confirm to bind this invitation to this account.");
        var profile = await profiles.GetAsync(user.UserId, ct) ?? throw ApiException.Conflict("Complete your profile before joining.");
        var current = await members.GetByGroupAsync(groupId, ct); plans.EnsureParticipantCapacity(group.Plan, group.EntitlementId, current.Count(x => x.IsParticipating));
        var membership = MembershipRepository.NewRecord(groupId, user.UserId, profile.DisplayName, false);
        try { await invitations.AcceptAndCreateMembershipAsync(id, user.UserId, membership, ct); }
        catch (TransactionCanceledException) { throw ApiException.Conflict("This invitation has already been used, revoked, expired, or accepted by this account."); }
        await audit.RecordAsync(AuditAction.InvitationAccepted, groupId, new("invitation", id), cancellationToken: ct); return new(groupId, true);
    }
    public async Task<InvitationPreview> PreviewAsync(string groupId, string id, string? token, CancellationToken ct = default)
    {
        var group = await groups.GetAsync(groupId, ct) ?? throw ApiException.NotFound("Exchange not found.");
        var item = await Get(groupId, id, ct);
        if (string.IsNullOrWhiteSpace(token) || !CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(item.TokenHash), Encoding.UTF8.GetBytes(Hash(token))))
            throw ApiException.Forbidden("This invitation is invalid or expired.");
        return new(group.GroupId, group.Name, group.Customization ?? new());
    }
    private async Task<ManagedInvitation> CreateOne(GroupRecord g, string address, CancellationToken ct) { var id = Guid.NewGuid().ToString("N"); var secret = Secret(); var now = DateTimeOffset.UtcNow.ToString("O"); var expires = DateTimeOffset.UtcNow.AddDays(14).ToString("O"); var message = templates.Invitation(new(id, address, "there", "Your organizer", g.Name, new Uri(Link(g.GroupId, id, secret)), g.Customization)); var row = new InvitationRecord(id, g.GroupId, address, Hash(secret), "sent", expires, now, now, LastSentAt: now, MessageId: message.MessageId); await invitations.CreateAsync(row, ct); await email.SendAsync(message, ct); await audit.RecordAsync(AuditAction.InvitationCreated, g.GroupId, new("invitation", id), cancellationToken: ct); return await Public(row, ct); }
    private async Task<GroupRecord> RequireOrganizer(string id, CancellationToken ct) { var g = await groups.GetAsync(id, ct) ?? throw ApiException.NotFound("Exchange not found."); if (g.OwnerUserId != user.UserId) throw ApiException.Forbidden("Only the organizer can manage invitations."); plans.EnsureCapability(g.Plan, g.EntitlementId, PlanCapability.ManagedInvitations); return g; }
    private async Task<InvitationRecord> Get(string gid, string id, CancellationToken ct) { var x = await invitations.GetAsync(id, ct); return x is null || x.GroupId != gid ? throw ApiException.NotFound("Invitation not found.") : x; }
    private async Task<ManagedInvitation> Public(InvitationRecord x, CancellationToken ct) { var delivery = await invitations.GetDeliveryStatusAsync(x.MessageId, ct); var status = x.Status == "revoked" ? InvitationStatus.Revoked : x.Status == "accepted" ? InvitationStatus.Accepted : DateTimeOffset.Parse(x.ExpiresAt) <= DateTimeOffset.UtcNow ? InvitationStatus.Expired : delivery == "delivery" ? InvitationStatus.Delivered : delivery is "bounce" or "reject" or "complaint" or "suppressed" ? InvitationStatus.Bounced : InvitationStatus.Sent; return new(x.InvitationId, x.Email, status, x.ExpiresAt, x.AcceptedAt, x.LastSentAt); }
    private static string Normalize(string raw) { try { var a = new MailAddress(raw.Trim()); if (a.Address != raw.Trim()) throw new Exception(); return a.Address.ToLowerInvariant(); } catch { throw ApiException.BadRequest($"'{raw}' is not a valid single email address."); } }
    private static string Secret() => WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32)); private static string Hash(string x) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(x)));
    private string Link(string gid, string id, string secret) => $"{settings.AppBaseUrl}/join/{gid}#managed={id}.{secret}";
}
