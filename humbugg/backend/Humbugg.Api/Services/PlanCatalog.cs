using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

public interface IPlanCatalog
{
    IReadOnlyList<PlanDefinition> All { get; }
    PlanDefinition Get(PlanCode code);
    bool HasCapability(PlanCode code, string? entitlementId, PlanCapability capability);
    void EnsureCapability(PlanCode code, string? entitlementId, PlanCapability capability);
    void EnsureParticipantCapacity(PlanCode code, string? entitlementId, int activeParticipantCount);
}

public enum PlanCapability
{
    ManagedInvitations,
    AutomaticReminders,
    CoOrganizers,
    ExchangeCustomization,
    ExchangeTemplates,
    LateParticipants,
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

    public bool HasCapability(PlanCode code, string? entitlementId, PlanCapability capability)
    {
        _ = capability;
        return code == PlanCode.Work ||
            code == PlanCode.Plus &&
            entitlementId?.StartsWith("plus:", StringComparison.Ordinal) == true;
    }

    public void EnsureCapability(PlanCode code, string? entitlementId, PlanCapability capability)
    {
        if (!HasCapability(code, entitlementId, capability))
            throw ApiException.PaymentRequired(
                $"Plus is required to use {CapabilityName(capability)} for this exchange.");
    }

    public void EnsureParticipantCapacity(
        PlanCode code,
        string? entitlementId,
        int activeParticipantCount)
    {
        if (activeParticipantCount < 0)
            throw new ArgumentOutOfRangeException(nameof(activeParticipantCount));

        if (code == PlanCode.Work)
        {
            var work = Get(PlanCode.Work);
            if (activeParticipantCount >= work.ParticipantLimit)
                throw ApiException.Conflict(
                    $"The Work plan supports up to {work.ParticipantLimit:N0} participants.");
            return;
        }

        var free = Get(PlanCode.Free);
        if (activeParticipantCount < free.ParticipantLimit) return;

        if (!HasCapability(code, entitlementId, PlanCapability.ManagedInvitations))
            throw ApiException.PaymentRequired(
                $"Plus is required for participant {activeParticipantCount + 1:N0}. " +
                $"The Free plan includes the organizer and up to {free.ParticipantLimit - 1:N0} other participants.");

        var plus = Get(PlanCode.Plus);
        if (activeParticipantCount >= plus.ParticipantLimit)
            throw ApiException.Conflict(
                $"Plus supports up to {plus.ParticipantLimit:N0} total participants, including the organizer. " +
                "Upgrade to Work to add participant 51 or run a larger exchange.");
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

    private static string CapabilityName(PlanCapability capability) => capability switch
    {
        PlanCapability.ManagedInvitations => "managed email invitations",
        PlanCapability.AutomaticReminders => "automatic reminders",
        PlanCapability.CoOrganizers => "co-organizers",
        PlanCapability.ExchangeCustomization => "exchange customization",
        PlanCapability.ExchangeTemplates => "exchange templates",
        PlanCapability.LateParticipants => "late-participant reassignment",
        _ => throw new ArgumentOutOfRangeException(nameof(capability)),
    };
}
