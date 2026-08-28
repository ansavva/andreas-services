using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Tests;

/// <summary>
/// An in-memory <see cref="IInvitationRepository"/> for the services that read invitations without
/// being about them — the readiness dashboard, mostly. Delivery feedback is a dictionary keyed by
/// message id, the same key the real table uses, so a bounced invitation can be staged honestly.
/// </summary>
internal sealed class FakeInvitations(params InvitationRecord[] seed) : IInvitationRepository
{
    public List<InvitationRecord> Items { get; } = [.. seed];
    public Dictionary<string, string> DeliveryStatuses { get; } = new(StringComparer.Ordinal);

    public Task CreateAsync(InvitationRecord value, CancellationToken cancellationToken = default)
    {
        Items.Add(value);
        return Task.CompletedTask;
    }

    public Task<InvitationRecord?> GetAsync(string invitationId, CancellationToken cancellationToken = default) =>
        Task.FromResult(Items.FirstOrDefault(item => item.InvitationId == invitationId));

    public Task<IReadOnlyList<InvitationRecord>> GetByGroupAsync(string groupId, CancellationToken cancellationToken = default) =>
        Task.FromResult<IReadOnlyList<InvitationRecord>>(Items.Where(item => item.GroupId == groupId).ToList());

    public Task UpdateAsync(string invitationId, string status, string? tokenHash, string? expiresAt, string? messageId, CancellationToken cancellationToken = default)
    {
        var index = Items.FindIndex(item => item.InvitationId == invitationId);
        if (index >= 0)
            Items[index] = Items[index] with
            {
                Status = status,
                TokenHash = tokenHash ?? Items[index].TokenHash,
                ExpiresAt = expiresAt ?? Items[index].ExpiresAt,
                MessageId = messageId ?? Items[index].MessageId
            };
        return Task.CompletedTask;
    }

    public Task AcceptAndCreateMembershipAsync(string invitationId, string userId, MembershipRecord membership, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("This fake does not accept invitations.");

    public Task<string?> GetDeliveryStatusAsync(string? messageId, CancellationToken cancellationToken = default) =>
        Task.FromResult(messageId is not null && DeliveryStatuses.TryGetValue(messageId, out var status) ? status : null);

    /// <summary>A sent, unaccepted invitation that expires two weeks out.</summary>
    public static InvitationRecord Pending(string invitationId, string groupId, string email, string? messageId = null) => new(
        invitationId, groupId, email, "hash", "sent",
        DateTimeOffset.UtcNow.AddDays(14).ToString("O"), "now", "now", MessageId: messageId);
}
