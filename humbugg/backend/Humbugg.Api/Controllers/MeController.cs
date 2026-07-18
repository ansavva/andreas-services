using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/me")]
public sealed class MeController(IProfileService profiles) : ControllerBase
{
    [HttpGet]
    public Task<Profile> Get(CancellationToken cancellationToken) => profiles.GetAsync(cancellationToken);

    [HttpPut]
    public Task<Profile> Put([FromBody] SaveProfileRequest request, CancellationToken cancellationToken) =>
        profiles.SaveAsync(request, cancellationToken);
}
