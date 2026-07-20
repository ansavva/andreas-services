using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/groups/{groupId}/reminders")]
public sealed class RemindersController(IReminderService reminders) : ControllerBase
{
    [HttpGet]
    public Task<ReminderOverview> Get(string groupId, CancellationToken cancellationToken) =>
        reminders.GetAsync(groupId, cancellationToken);

    [HttpPut]
    public Task<ReminderOverview> Update(
        string groupId,
        UpdateReminderSettingsRequest request,
        CancellationToken cancellationToken) =>
        reminders.UpdateAsync(groupId, request, cancellationToken);

    [HttpPost("send")]
    public Task<ReminderHistoryItem> Send(
        string groupId,
        ManualReminderRequest request,
        CancellationToken cancellationToken) =>
        reminders.SendManualAsync(groupId, request, cancellationToken);
}
