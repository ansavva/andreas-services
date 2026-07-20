using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/groups/{groupId}/invitations")]
public sealed class InvitationsController(IInvitationService service) : ControllerBase
{
    [HttpGet] public Task<IReadOnlyList<ManagedInvitation>> List(string groupId, CancellationToken ct) => service.ListAsync(groupId, ct);
    [HttpPost] public Task<CreateInvitationsResponse> Create(string groupId, CreateInvitationsRequest request, CancellationToken ct) => service.CreateAsync(groupId, request, ct);
    [HttpPost("{invitationId}/resend")] public Task<ManagedInvitation> Resend(string groupId, string invitationId, CancellationToken ct) => service.ResendAsync(groupId, invitationId, ct);
    [HttpPost("{invitationId}/revoke")] public async Task<IActionResult> Revoke(string groupId, string invitationId, CancellationToken ct) { await service.RevokeAsync(groupId, invitationId, ct); return NoContent(); }
    [HttpPost("{invitationId}/accept")] public Task<AcceptInvitationResponse> Accept(string groupId, string invitationId, AcceptInvitationRequest request, CancellationToken ct) => service.AcceptAsync(groupId, invitationId, request, ct);
    [AllowAnonymous, HttpGet("{invitationId}/preview")] public Task<InvitationPreview> Preview(string groupId, string invitationId, [FromQuery] string? token, CancellationToken ct) => service.PreviewAsync(groupId, invitationId, token, ct);
}
