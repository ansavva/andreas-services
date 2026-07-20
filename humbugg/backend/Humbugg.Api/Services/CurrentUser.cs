using Humbugg.Api.Models;
using System.Security.Claims;

namespace Humbugg.Api.Services;

internal interface ICurrentUser
{
    string UserId { get; }

    // The caller's email address when the validated token carries it. Cognito access tokens do not
    // include the email claim by default (it lives on the id token), so this is best-effort and may be
    // null; callers must treat a missing value as "not available from the token", never as an error.
    // Defaulted so the many existing test doubles that only need UserId keep compiling.
    string? Email => null;
}

internal sealed class CurrentUser(IHttpContextAccessor accessor) : ICurrentUser
{
    public string UserId => accessor.HttpContext?.User.FindFirst("sub")?.Value
        ?? accessor.HttpContext?.User.FindFirst(ClaimTypes.NameIdentifier)?.Value
        ?? throw ApiException.Forbidden("A valid Cognito access token is required.");

    public string? Email
    {
        get
        {
            var email = accessor.HttpContext?.User.FindFirst("email")?.Value
                ?? accessor.HttpContext?.User.FindFirst(ClaimTypes.Email)?.Value;
            return string.IsNullOrWhiteSpace(email) ? null : email;
        }
    }
}
