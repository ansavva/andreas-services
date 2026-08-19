using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/groups/{groupId}/late-participants")]
public sealed class LateParticipantsController(ILateParticipantService lateParticipants) : ControllerBase
{
    [HttpPost("{memberId}/preview")]
    public Task<LateParticipantPreview> Preview(
        string groupId,
        string memberId,
        CancellationToken cancellationToken) =>
        lateParticipants.PreviewAsync(groupId, memberId, cancellationToken);

    [HttpPost("confirm")]
    public Task<LateParticipantResult> Confirm(
        string groupId,
        ConfirmLateParticipantRequest request,
        CancellationToken cancellationToken) =>
        lateParticipants.ConfirmAsync(groupId, request, cancellationToken);
}
