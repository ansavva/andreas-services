using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/me")]
public sealed class MeController(IProfileService profiles, IAccountDeletionService accountDeletion) : ControllerBase
{
    [HttpGet]
    public Task<Profile> Get(CancellationToken cancellationToken) => profiles.GetAsync(cancellationToken);

    [HttpPut]
    public Task<Profile> Put([FromBody] SaveProfileRequest request, CancellationToken cancellationToken) =>
        profiles.SaveAsync(request, cancellationToken);

    // Avatar upload accepts a base64/data-URL image in JSON so it rides the same API Gateway/Lambda
    // path as every other call. The service validates content type, size, and dimensions and re-encodes
    // to a safe, metadata-free image before storing it.
    [HttpPut("avatar")]
    public Task<Profile> UploadAvatar([FromBody] UploadAvatarRequest request, CancellationToken cancellationToken) =>
        profiles.UploadAvatarAsync(request, cancellationToken);

    [HttpDelete("avatar")]
    public Task<Profile> RemoveAvatar(CancellationToken cancellationToken) =>
        profiles.RemoveAvatarAsync(cancellationToken);

    // User-initiated account deletion. Runs on the caller's own identity with no administrator or
    // organization approval gate, and is idempotent, so it is safe to retry.
    [HttpDelete]
    public async Task<IActionResult> Delete(CancellationToken cancellationToken)
    {
        await accountDeletion.DeleteAsync(cancellationToken);
        return NoContent();
    }
}
