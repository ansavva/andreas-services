using Humbugg.Api.Models;
using System.Security.Claims;

namespace Humbugg.Api.Services;

internal interface ICurrentUser { string UserId { get; } }

internal sealed class CurrentUser(IHttpContextAccessor accessor) : ICurrentUser
{
    public string UserId => accessor.HttpContext?.User.FindFirst("sub")?.Value
        ?? accessor.HttpContext?.User.FindFirst(ClaimTypes.NameIdentifier)?.Value
        ?? throw ApiException.Forbidden("A valid Cognito access token is required.");
}
