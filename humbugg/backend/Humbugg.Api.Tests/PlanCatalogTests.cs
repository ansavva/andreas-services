using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class PlanCatalogTests
{
    [Fact]
    public void DefaultsDefineTheHumbuggPlanContract()
    {
        var plans = new PlanCatalog(new());

        Assert.Equal(new PlanDefinition(PlanCode.Free, "Free", 6, false, 0, "USD", BillingCadence.Free), plans.Get(PlanCode.Free));
        Assert.Equal(new PlanDefinition(PlanCode.Plus, "Plus", 50, false, 1_200, "USD", BillingCadence.OneTime), plans.Get(PlanCode.Plus));
        Assert.Equal(new PlanDefinition(PlanCode.Work, "Work", 10_000, true, 9_900, "USD", BillingCadence.Annual), plans.Get(PlanCode.Work));
    }

    [Fact]
    public void BillingIdentifiersAndValuesComeFromConfiguration()
    {
        var plans = new PlanCatalog(new PlanCatalogOptions(
            FreeParticipantLimit: 7,
            PlusParticipantLimit: 51,
            WorkParticipantLimit: 9_999,
            PlusPriceCents: 1_500,
            WorkPriceCents: 12_000,
            PlusProductId: " prod_plus ",
            PlusPriceId: "price_plus",
            WorkProductId: "prod_work",
            WorkPriceId: "price_work"));

        Assert.Equal(7, plans.Get(PlanCode.Free).ParticipantLimit);
        Assert.Equal((51, 1_500L, "prod_plus", "price_plus"), PlanValues(plans.Get(PlanCode.Plus)));
        Assert.Equal((9_999, 12_000L, "prod_work", "price_work"), PlanValues(plans.Get(PlanCode.Work)));
    }

    [Theory]
    [InlineData(PlanCode.Free, 5)]
    [InlineData(PlanCode.Plus, 49)]
    [InlineData(PlanCode.Work, 9_999)]
    public void EveryPlanAllowsTheParticipantBeforeItsBoundary(PlanCode plan, int currentParticipants)
    {
        new PlanCatalog(new()).EnsureParticipantCapacity(plan, currentParticipants);
    }

    [Theory]
    [InlineData(PlanCode.Free, 6)]
    [InlineData(PlanCode.Plus, 50)]
    [InlineData(PlanCode.Work, 10_000)]
    public void EveryPlanRejectsTheParticipantAtItsBoundary(PlanCode plan, int currentParticipants)
    {
        var error = Assert.Throws<ApiException>(() => new PlanCatalog(new()).EnsureParticipantCapacity(plan, currentParticipants));
        Assert.Equal(409, error.StatusCode);
    }

    [Fact]
    public void ExistingGroupsWithoutAStoredPlanDefaultToFree()
    {
        Assert.Equal(PlanCode.Free, GroupRepository.ReadPlan(""));
    }

    private static (int Limit, long Price, string? Product, string? PriceId) PlanValues(PlanDefinition plan) =>
        (plan.ParticipantLimit, plan.PriceCents, plan.ProductId, plan.PriceId);
}
