using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

/// <summary>
/// The giver's side of an anonymous question thread (#131).
/// </summary>
/// <remarks>
/// Routed under <c>assignment</c> because the assignment is the authorization: the only person you
/// may ask is the one the draw gave you. No route here or below carries a member id — a URL is one
/// of the surfaces the issue names, and the way to keep an identity out of it is to have no id to
/// put there.
/// </remarks>
[ApiController, Authorize, Route("api/groups/{groupId}/assignment/questions")]
public sealed class GiverQuestionsController(IQuestionService questions) : ControllerBase
{
    [HttpGet]
    public Task<QuestionThread> Get(string groupId, CancellationToken cancellationToken) =>
        questions.GetForGiverAsync(groupId, cancellationToken);

    [HttpPost]
    public Task<QuestionThread> Ask(
        string groupId,
        [FromBody] SendQuestionRequest request,
        CancellationToken cancellationToken) =>
        questions.AskAsync(groupId, request, cancellationToken);
}

/// <summary>
/// The recipient's side: the conversation about their own list, and the switch that ends it.
/// </summary>
/// <remarks>
/// Under <c>members/me</c> for the same reason the wishlist routes are — the group id selects a
/// conversation, it does not authorize one, and "me" is the only member a caller can address.
///
/// There is deliberately no organizer route anywhere in this file. An organizer running an exchange
/// has no management tool that reads these, and the emergency reveal returns assignments, not
/// conversations.
/// </remarks>
[ApiController, Authorize, Route("api/groups/{groupId}/members/me/questions")]
public sealed class RecipientQuestionsController(IQuestionService questions) : ControllerBase
{
    [HttpGet]
    public Task<QuestionThread> Get(string groupId, CancellationToken cancellationToken) =>
        questions.GetForRecipientAsync(groupId, cancellationToken);

    [HttpPost]
    public Task<QuestionThread> Reply(
        string groupId,
        [FromBody] SendQuestionRequest request,
        CancellationToken cancellationToken) =>
        questions.ReplyAsync(groupId, request, cancellationToken);

    [HttpPut("blocked")]
    public Task<QuestionThread> SetBlocked(
        string groupId,
        [FromBody] BlockQuestionsRequest request,
        CancellationToken cancellationToken) =>
        questions.SetBlockedAsync(groupId, request, cancellationToken);
}
