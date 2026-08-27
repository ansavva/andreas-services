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
public sealed class WishesController(IWishService wishes) : ControllerBase
{
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
