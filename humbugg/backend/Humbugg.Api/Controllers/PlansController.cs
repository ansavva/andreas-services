using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers;

[ApiController, Authorize, Route("api/plans")]
public sealed class PlansController(IPlanCatalog plans) : ControllerBase
{
    /// <summary>
    /// The plan catalogue: what each plan costs, what it allows, and how it is billed.
    /// </summary>
    /// <remarks>
    /// Anonymous, deliberately (#158). This is a price list — it is marketing copy, it was already
    /// readable by any signed-in account, and the public pricing pages have to show the same
    /// numbers Stripe charges against rather than a second copy that drifts. Making the marketing
    /// site authenticate to read a price would be the only alternative, and the numbers duplicated
    /// into the site instead is the failure the issue names.
    ///
    /// It carries `product_id` and `price_id`, which are Stripe's own public identifiers — a price
    /// id appears in every Checkout URL — and no customer, exchange or account data of any kind.
    /// </remarks>
    [AllowAnonymous, HttpGet]
    public IReadOnlyList<PlanDefinition> List() => plans.All;
}
