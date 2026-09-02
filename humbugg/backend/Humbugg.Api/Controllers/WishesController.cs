using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

/// <summary>
/// A participant's own wishes, under <c>members/me</c> because that is what the route addresses.
/// There is no route to another member's list: a giver reads their recipient's wishes through
/// <c>GET /groups/{groupId}/assignment</c>, which is the one place the draw is consulted.
/// </summary>
[ApiController, Authorize, Route("api/groups/{groupId}/members/me/wishes")]
public sealed class WishesController(IWishService wishes, IWishPreviewService previews) : ControllerBase
{
    // Reading a pasted product link (#129). A POST because it has a side effect — Humbugg's servers
    // make a request somebody else chose the destination of — and because a URL in a request body is
    // not written to an access log the way a query string is.
    //
    // Authenticated and membership-checked: this is the one endpoint that makes an outbound request
    // on a caller's say-so, so it is not available to the internet at large. What it can reach is
    // bounded by WishUrlSafety, and what it returns is four short fields, never the page.
    [HttpPost("preview")]
    public Task<WishPreview> Preview(string groupId, [FromBody] WishPreviewRequest request, CancellationToken cancellationToken) =>
        previews.PreviewAsync(groupId, request, cancellationToken);

    [HttpGet]
    public Task<IReadOnlyList<Wish>> List(string groupId, CancellationToken cancellationToken) =>
        wishes.ListAsync(groupId, cancellationToken);

    [HttpPost]
    public async Task<ActionResult<Wish>> Create(
        string groupId,
        [FromBody] CreateWishRequest request,
        CancellationToken cancellationToken) =>
        StatusCode(StatusCodes.Status201Created, await wishes.CreateAsync(groupId, request, cancellationToken));

    [HttpPatch("{wishId}")]
    public Task<Wish> Update(
        string groupId,
        string wishId,
        [FromBody] UpdateWishRequest request,
        CancellationToken cancellationToken) =>
        wishes.UpdateAsync(groupId, wishId, request, cancellationToken);

    [HttpDelete("{wishId}")]
    public async Task<IActionResult> Delete(string groupId, string wishId, CancellationToken cancellationToken)
    {
        await wishes.DeleteAsync(groupId, wishId, cancellationToken);
        return NoContent();
    }

    // PUT, not PATCH: the body is the complete new order, and applying a partial one would leave the
    // unnamed wishes at stale positions.
    [HttpPut("order")]
    public Task<IReadOnlyList<Wish>> Reorder(
        string groupId,
        [FromBody] ReorderWishesRequest request,
        CancellationToken cancellationToken) =>
        wishes.ReorderAsync(groupId, request, cancellationToken);
}
