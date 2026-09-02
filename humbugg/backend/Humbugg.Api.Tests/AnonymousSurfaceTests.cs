using System.Reflection;
using Humbugg.Api.Controllers;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// Every endpoint reachable without a token, enumerated (#158).
/// </summary>
/// <remarks>
/// <para>
/// The API is `[Authorize]` by default and each exception is a deliberate widening of the public
/// attack surface — but an exception is one attribute on one line, which is invisible in a diff
/// that also moves a hundred lines of a controller. Nothing asserted this before, so nothing would
/// have noticed an `[AllowAnonymous]` added by habit, by a merge, or by somebody working around a
/// 401 in development.
/// </para>
/// <para>
/// This is the list. Adding to it is fine — it just has to be done here too, on purpose, with the
/// reason written down.
/// </para>
/// </remarks>
public sealed class AnonymousSurfaceTests
{
    /// <summary>
    /// The public endpoints, and why each one is public.
    /// </summary>
    /// <remarks>
    /// <list type="bullet">
    /// <item><c>StripeWebhookController.Webhook</c> — Stripe calls it and holds no Humbugg token.
    /// It is not unauthenticated: the request is verified by its signature against the webhook
    /// secret, which is a different credential rather than no credential.</item>
    /// <item><c>InvitationsController.Preview</c> and <c>GroupsController.Invitation</c> — read by
    /// somebody who has been invited and does not have an account yet, which is the entire point.
    /// Both demand the invitation secret, and both return only an exchange's name and its
    /// customization: no roster, no wishlist, no member id.</item>
    /// <item><c>PlansController.List</c> — a price list, read by the public pricing pages. It is
    /// marketing copy and carries no customer, exchange or account data.</item>
    /// </list>
    /// </remarks>
    private static readonly string[] Expected =
    [
        "GroupsController.Invitation",
        "InvitationsController.Preview",
        "PlansController.List",
        "StripeWebhookController.Webhook",
    ];

    [Fact]
    public void OnlyTheseEndpointsAreReachableWithoutTheAuthorizer()
    {
        var found = new List<string>();

        foreach (var controller in typeof(PlansController).Assembly.GetTypes()
                     .Where(type => typeof(ControllerBase).IsAssignableFrom(type) && !type.IsAbstract))
        {
            // A controller-level `[AllowAnonymous]` makes every one of its actions anonymous, which
            // is how the Stripe webhook is declared — so the check cannot look only at methods.
            var wholeController = controller.GetCustomAttribute<AllowAnonymousAttribute>() is not null;

            foreach (var action in controller.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
            {
                if (action.IsSpecialName) continue;
                if (action.GetCustomAttributes<HttpMethodAttribute>().Any() is false) continue;
                if (wholeController || action.GetCustomAttribute<AllowAnonymousAttribute>() is not null)
                    found.Add($"{controller.Name}.{action.Name}");
            }
        }

        Assert.Equal(Expected, found.Order(StringComparer.Ordinal).ToArray());
    }
}
