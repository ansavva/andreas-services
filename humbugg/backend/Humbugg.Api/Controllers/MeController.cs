using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/me")]
public sealed class MeController(
    IProfileService profiles,
    IAccountDeletionService accountDeletion,
    IDataExportService dataExport) : ControllerBase
{
    [HttpGet]
    public Task<Profile> Get(CancellationToken cancellationToken) => profiles.GetAsync(cancellationToken);

    [HttpPut]
    public Task<Profile> Put([FromBody] SaveProfileRequest request, CancellationToken cancellationToken) =>
        profiles.SaveAsync(request, cancellationToken);

    // Self-service data export — the GDPR right of access / portability (Art. 15 & 20), the read-only
    // counterpart to DELETE below. Returns only the caller's own personal data as portable JSON, runs
    // on the caller's own identity with no admin gate, and is safe to call repeatedly. A Content-
    // Disposition header hints browsers to save it as a file when hit directly.
    [HttpGet("export")]
    public async Task<DataExport> Export(CancellationToken cancellationToken)
    {
        var export = await dataExport.ExportAsync(cancellationToken);
        var stamp = DateTimeOffset.UtcNow.ToString("yyyyMMdd'T'HHmmss'Z'");
        Response.Headers.ContentDisposition = $"attachment; filename=\"humbugg-data-export-{stamp}.json\"";
        return export;
    }

    // User-initiated account deletion. Runs on the caller's own identity with no administrator or
    // organization approval gate, and is idempotent, so it is safe to retry.
    [HttpDelete]
    public async Task<IActionResult> Delete(CancellationToken cancellationToken)
    {
        await accountDeletion.DeleteAsync(cancellationToken);
        return NoContent();
    }
}
