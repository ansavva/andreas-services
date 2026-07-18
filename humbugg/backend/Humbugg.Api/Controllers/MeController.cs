using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/me")]
public sealed class MeController(IProfileService profiles) : ControllerBase
{
    [HttpGet]
    public Task<Profile> Get(CancellationToken cancellationToken) => profiles.GetAsync(cancellationToken);

    // First-write of a profile is how a freshly signed-up Cognito user becomes usable in Humbugg,
    // so it carries the account-creation limiter. True identity creation is rate-limited upstream at
    // Cognito / WAF; see humbugg/docs/threat-model.md.
    [HttpPut, EnableRateLimiting(RateLimitSettings.AccountCreationPolicy)]
    public Task<Profile> Put([FromBody] SaveProfileRequest request, CancellationToken cancellationToken) =>
        profiles.SaveAsync(request, cancellationToken);
}
