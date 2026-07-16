using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

public interface IPlanCatalog
{
    IReadOnlyList<PlanDefinition> All { get; }
    PlanDefinition Get(PlanCode code);
    void EnsureParticipantCapacity(PlanCode code, int activeParticipantCount);
}

public sealed record PlanCatalogOptions(
    int FreeParticipantLimit = 6,
    int PlusParticipantLimit = 50,
    int WorkParticipantLimit = 10_000,
    long PlusPriceCents = 1_200,
    long WorkPriceCents = 9_900,
    string? PlusProductId = null,
    string? PlusPriceId = null,
    string? WorkProductId = null,
    string? WorkPriceId = null);

public sealed class PlanCatalog : IPlanCatalog
{
    private readonly IReadOnlyDictionary<PlanCode, PlanDefinition> plans;

    public PlanCatalog(PlanCatalogOptions options)
    {
        Validate(options);
        plans = new Dictionary<PlanCode, PlanDefinition>
        {
            [PlanCode.Free] = new(PlanCode.Free, "Free", options.FreeParticipantLimit, false, 0, "USD", BillingCadence.Free),
            [PlanCode.Plus] = new(PlanCode.Plus, "Plus", options.PlusParticipantLimit, false, options.PlusPriceCents, "USD",
                BillingCadence.OneTime, Clean(options.PlusProductId), Clean(options.PlusPriceId)),
            [PlanCode.Work] = new(PlanCode.Work, "Work", options.WorkParticipantLimit, true, options.WorkPriceCents, "USD",
                BillingCadence.Annual, Clean(options.WorkProductId), Clean(options.WorkPriceId))
        };
        All = [plans[PlanCode.Free], plans[PlanCode.Plus], plans[PlanCode.Work]];
    }

    public IReadOnlyList<PlanDefinition> All { get; }

    public PlanDefinition Get(PlanCode code) => plans.TryGetValue(code, out var plan)
        ? plan
        : throw new InvalidOperationException($"Unsupported Humbugg plan '{code}'.");

    public void EnsureParticipantCapacity(PlanCode code, int activeParticipantCount)
    {
        var plan = Get(code);
        if (activeParticipantCount >= plan.ParticipantLimit)
            throw ApiException.Conflict($"The {plan.Name} plan supports up to {plan.ParticipantLimit:N0} participants.");
    }

    public static PlanCatalog FromEnvironment() => new(new PlanCatalogOptions(
        PositiveInt("HUMBUGG_FREE_PARTICIPANT_LIMIT", 6),
        PositiveInt("HUMBUGG_PLUS_PARTICIPANT_LIMIT", 50),
        PositiveInt("HUMBUGG_WORK_PARTICIPANT_LIMIT", 10_000),
        NonNegativeLong("HUMBUGG_PLUS_PRICE_CENTS", 1_200),
        NonNegativeLong("HUMBUGG_WORK_PRICE_CENTS", 9_900),
        Environment.GetEnvironmentVariable("HUMBUGG_PLUS_PRODUCT_ID"),
        Environment.GetEnvironmentVariable("HUMBUGG_PLUS_PRICE_ID"),
        Environment.GetEnvironmentVariable("HUMBUGG_WORK_PRODUCT_ID"),
        Environment.GetEnvironmentVariable("HUMBUGG_WORK_PRICE_ID")));

    private static int PositiveInt(string name, int fallback)
    {
        var value = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(value)) return fallback;
        if (int.TryParse(value, out var parsed) && parsed > 0) return parsed;
        throw new InvalidOperationException($"{name} must be a positive integer.");
    }

    private static long NonNegativeLong(string name, long fallback)
    {
        var value = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(value)) return fallback;
        if (long.TryParse(value, out var parsed) && parsed >= 0) return parsed;
        throw new InvalidOperationException($"{name} must be a non-negative integer number of cents.");
    }

    private static void Validate(PlanCatalogOptions options)
    {
        if (options.FreeParticipantLimit <= 0 || options.PlusParticipantLimit <= 0 || options.WorkParticipantLimit <= 0)
            throw new ArgumentOutOfRangeException(nameof(options), "Participant limits must be positive.");
        if (options.PlusPriceCents < 0 || options.WorkPriceCents < 0)
            throw new ArgumentOutOfRangeException(nameof(options), "Prices cannot be negative.");
    }

    private static string? Clean(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
