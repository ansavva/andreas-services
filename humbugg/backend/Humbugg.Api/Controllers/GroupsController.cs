using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/groups")]
public sealed class GroupsController(IGroupService groups) : ControllerBase
{
    [HttpGet]
    public Task<IReadOnlyList<GroupSummary>> List(CancellationToken cancellationToken) => groups.ListAsync(cancellationToken);

    [HttpPost]
    public async Task<ActionResult<GroupDetail>> Create([FromBody] CreateGroupRequest request, CancellationToken cancellationToken) =>
        StatusCode(StatusCodes.Status201Created, await groups.CreateAsync(request, cancellationToken));

    [HttpGet("{groupId}")]
    public Task<GroupDetail> Get(string groupId, CancellationToken cancellationToken) => groups.GetAsync(groupId, cancellationToken);

    [HttpPatch("{groupId}")]
    public Task<GroupDetail> Update(string groupId, [FromBody] UpdateGroupRequest request, CancellationToken cancellationToken) =>
        groups.UpdateAsync(groupId, request, cancellationToken);

    [HttpDelete("{groupId}")]
    public async Task<IActionResult> Delete(string groupId, CancellationToken cancellationToken)
    {
        await groups.DeleteAsync(groupId, cancellationToken);
        return NoContent();
    }

    [HttpPost("{groupId}/invite")]
    public Task<InviteResponse> RotateInvite(string groupId, CancellationToken cancellationToken) => groups.RotateInviteAsync(groupId, cancellationToken);

    [HttpPost("{groupId}/join")]
    public Task<GroupDetail> Join(string groupId, [FromBody] JoinGroupRequest request, CancellationToken cancellationToken) =>
        groups.JoinAsync(groupId, request, cancellationToken);

    [HttpGet("{groupId}/members/me")]
    public Task<Membership> GetMembership(string groupId, CancellationToken cancellationToken) => groups.GetMyMembershipAsync(groupId, cancellationToken);

    [HttpPatch("{groupId}/members/me")]
    public Task<Membership> UpdateMembership(string groupId, [FromBody] UpdateMembershipRequest request, CancellationToken cancellationToken) =>
        groups.UpdateMyMembershipAsync(groupId, request, cancellationToken);

    [HttpDelete("{groupId}/members/me")]
    public async Task<IActionResult> Leave(string groupId, CancellationToken cancellationToken)
    {
        await groups.LeaveAsync(groupId, cancellationToken);
        return NoContent();
    }

    [HttpDelete("{groupId}/members/me/private-data")]
    public Task<Membership> ClearPrivateData(string groupId, CancellationToken cancellationToken) =>
        groups.ClearMyPrivateDataAsync(groupId, cancellationToken);

    [HttpPatch("{groupId}/members/{memberId}/participation")]
    public Task<Membership> Participation(string groupId, string memberId, [FromBody] ParticipationRequest request, CancellationToken cancellationToken) =>
        groups.UpdateParticipationAsync(groupId, memberId, request, cancellationToken);

    [HttpPatch("{groupId}/members/{memberId}/organizer-role")]
    public Task<Membership> OrganizerRole(
        string groupId,
        string memberId,
        [FromBody] OrganizerRoleRequest request,
        CancellationToken cancellationToken) =>
        groups.UpdateOrganizerRoleAsync(groupId, memberId, request, cancellationToken);

    [HttpPut("{groupId}/exclusions")]
    public Task<GroupDetail> Exclusions(string groupId, [FromBody] ExclusionsRequest request, CancellationToken cancellationToken) =>
        groups.SetExclusionsAsync(groupId, request, cancellationToken);

    [HttpPost("{groupId}/draw")]
    public Task<RecipientAssignment> Draw(string groupId, CancellationToken cancellationToken) => groups.DrawAsync(groupId, cancellationToken);

    [HttpPost("{groupId}/reset")]
    public Task<GroupDetail> Reset(string groupId, CancellationToken cancellationToken) => groups.ResetAsync(groupId, cancellationToken);

    [HttpGet("{groupId}/assignment")]
    public Task<RecipientAssignment> Assignment(string groupId, CancellationToken cancellationToken) => groups.GetAssignmentAsync(groupId, cancellationToken);

    [HttpPost("{groupId}/assignment/reveal")]
    public Task<RevealResponse> Reveal(string groupId, [FromBody] RevealRequest request, CancellationToken cancellationToken) =>
        groups.RevealAsync(groupId, request, cancellationToken);
}
