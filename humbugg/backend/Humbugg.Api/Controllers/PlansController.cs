using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/plans")]
public sealed class PlansController(IPlanCatalog plans) : ControllerBase
{
    [HttpGet]
    public IReadOnlyList<PlanDefinition> List() => plans.All;
}
