using Humbugg.Api.Services.Realtime;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

/// <summary>
/// The door to the realtime channel (#691): an authorized call mints the one-time ticket the socket
/// connects with. The socket itself is API Gateway's in production and Kestrel's in a dev container;
/// the app learns which from <c>EXPO_PUBLIC_REALTIME_URL</c>, not from here.
/// </summary>
[ApiController, Authorize, Route("api/realtime")]
public sealed class RealtimeController(IRealtimeTicketService tickets) : ControllerBase
{
    [HttpPost("tickets")]
    public async Task<ActionResult<RealtimeTicket>> Issue(CancellationToken cancellationToken) =>
        Ok(await tickets.IssueAsync(cancellationToken));
}
