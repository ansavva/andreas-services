using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/templates")]
public sealed class TemplatesController(IExchangeTemplateService templates) : ControllerBase
{
    [HttpGet] public Task<IReadOnlyList<ExchangeTemplate>> List(CancellationToken ct) => templates.ListAsync(ct);
    [HttpPost]
    public async Task<ActionResult<ExchangeTemplate>> Save(SaveTemplateRequest request, CancellationToken ct) =>
        StatusCode(201, await templates.SaveAsync(request, ct));
    [HttpPut("{id}")] public Task<ExchangeTemplate> Update(string id, UpdateTemplateRequest request, CancellationToken ct) => templates.UpdateAsync(id, request, ct);
    [HttpPost("{id}/duplicate")] public Task<ExchangeTemplate> Duplicate(string id, CancellationToken ct) => templates.DuplicateAsync(id, ct);
    [HttpPost("{id}/apply")] public Task<GroupDetail> Apply(string id, ApplyTemplateRequest request, CancellationToken ct) => templates.ApplyAsync(id, request, ct);
    [HttpDelete("{id}")] public async Task<IActionResult> Delete(string id, CancellationToken ct) { await templates.DeleteAsync(id, ct); return NoContent(); }
}
