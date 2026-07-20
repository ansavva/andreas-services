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

    [Fact]
    public void FreeAllowsSixTotalIncludingOrganizer()
    {
        new PlanCatalog(new()).EnsureParticipantCapacity(PlanCode.Free, null, 5);
    }

    [Fact]
    public void ParticipantSevenRequiresActivePlusEntitlement()
    {
        var plans = new PlanCatalog(new());
        var free = Assert.Throws<ApiException>(() =>
            plans.EnsureParticipantCapacity(PlanCode.Free, null, 6));
        var unverifiedPlus = Assert.Throws<ApiException>(() =>
            plans.EnsureParticipantCapacity(PlanCode.Plus, null, 6));

        Assert.Equal((402, "plus_required"), (free.StatusCode, free.Code));
        Assert.Equal(402, unverifiedPlus.StatusCode);
        plans.EnsureParticipantCapacity(PlanCode.Plus, "plus:group-1", 6);
    }

    [Fact]
    public void PlusAllowsFiftyAndRejectsFiftyOneWithWorkExplanation()
    {
        var plans = new PlanCatalog(new());
        plans.EnsureParticipantCapacity(PlanCode.Plus, "plus:group-1", 49);

        var error = Assert.Throws<ApiException>(() =>
            plans.EnsureParticipantCapacity(PlanCode.Plus, "plus:group-1", 50));

        Assert.Equal(409, error.StatusCode);
        Assert.Contains("Work", error.Message);
        Assert.Contains("51", error.Message);
    }

    [Fact]
    public void WorkUsesItsConfiguredBoundary()
    {
        var plans = new PlanCatalog(new());
        plans.EnsureParticipantCapacity(PlanCode.Work, null, 9_999);
        Assert.Equal(409, Assert.Throws<ApiException>(() =>
            plans.EnsureParticipantCapacity(PlanCode.Work, null, 10_000)).StatusCode);
    }

    [Theory]
    [InlineData(PlanCapability.ManagedInvitations)]
    [InlineData(PlanCapability.AutomaticReminders)]
    [InlineData(PlanCapability.CoOrganizers)]
    [InlineData(PlanCapability.ExchangeCustomization)]
    [InlineData(PlanCapability.ExchangeTemplates)]
    [InlineData(PlanCapability.LateParticipants)]
    public void EveryPlusCapabilityRequiresDurableEntitlement(PlanCapability capability)
    {
        var plans = new PlanCatalog(new());
        Assert.Equal(402, Assert.Throws<ApiException>(() =>
            plans.EnsureCapability(PlanCode.Free, null, capability)).StatusCode);
        Assert.Equal(402, Assert.Throws<ApiException>(() =>
            plans.EnsureCapability(PlanCode.Plus, null, capability)).StatusCode);
        plans.EnsureCapability(PlanCode.Plus, "plus:group-1", capability);
        plans.EnsureCapability(PlanCode.Work, null, capability);
    }

    [Fact]
    public void ExistingGroupsWithoutAStoredPlanDefaultToFree()
    {
        Assert.Equal(PlanCode.Free, GroupRepository.ReadPlan(""));
    }

    private static (int Limit, long Price, string? Product, string? PriceId) PlanValues(PlanDefinition plan) =>
        (plan.ParticipantLimit, plan.PriceCents, plan.ProductId, plan.PriceId);
}
