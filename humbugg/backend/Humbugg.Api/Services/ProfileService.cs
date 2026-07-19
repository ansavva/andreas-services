using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services;

public interface IProfileService
{
    Task<Profile> GetAsync(CancellationToken cancellationToken = default);
    Task<Profile> SaveAsync(SaveProfileRequest request, CancellationToken cancellationToken = default);
    Task<Profile> UploadAvatarAsync(UploadAvatarRequest request, CancellationToken cancellationToken = default);
    Task<Profile> RemoveAvatarAsync(CancellationToken cancellationToken = default);
}

internal sealed class ProfileService(
    ICurrentUser user,
    IProfileRepository profiles,
    IAvatarStore avatars,
    HumbuggSettings settings) : IProfileService
{
    public async Task<Profile> GetAsync(CancellationToken cancellationToken = default)
    {
        var profile = await profiles.GetAsync(user.UserId, cancellationToken)
            ?? throw ApiException.NotFound("Complete your profile to continue.");
        return ToModel(profile);
    }

    public async Task<Profile> SaveAsync(SaveProfileRequest request, CancellationToken cancellationToken = default)
    {
        var displayName = Validation.Required(request.DisplayName, "display_name", 100);
        return ToModel(await profiles.UpsertAsync(
            user.UserId, displayName, request.NonEssentialEmailsEnabled, cancellationToken));
    }

    public async Task<Profile> UploadAvatarAsync(UploadAvatarRequest request, CancellationToken cancellationToken = default)
    {
        // Validation + safe re-encoding happen before any storage or DB write. A profile must already
        // exist (SetAvatarKeyAsync enforces this) so avatars can't create nameless rows.
        var normalized = AvatarImage.Normalize(request.Image);
        var existing = await profiles.GetAsync(user.UserId, cancellationToken)
            ?? throw ApiException.NotFound("Complete your profile before adding a photo.");

        var key = await avatars.SaveAsync(user.UserId,
            new NormalizedAvatarBytes(normalized.Bytes, normalized.ContentType, normalized.Extension), cancellationToken);
        var updated = await profiles.SetAvatarKeyAsync(user.UserId, key, cancellationToken);

        // Best-effort cleanup of the previous object so replacing a photo doesn't leak orphans. The
        // new key is already persisted, so a cleanup failure never blocks the user.
        await TryDeleteAsync(existing.AvatarKey, key, cancellationToken);
        return ToModel(updated);
    }

    public async Task<Profile> RemoveAvatarAsync(CancellationToken cancellationToken = default)
    {
        var existing = await profiles.GetAsync(user.UserId, cancellationToken)
            ?? throw ApiException.NotFound("Complete your profile to continue.");
        var updated = await profiles.SetAvatarKeyAsync(user.UserId, null, cancellationToken);
        await TryDeleteAsync(existing.AvatarKey, null, cancellationToken);
        return ToModel(updated);
    }

    private async Task TryDeleteAsync(string? oldKey, string? newKey, CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(oldKey) || oldKey == newKey) return;
        try { await avatars.DeleteAsync(oldKey, cancellationToken); }
        catch { /* orphaned object cleanup is best-effort; the profile is already consistent. */ }
    }

    private Profile ToModel(ProfileRecord record) => new(
        record.UserId, record.DisplayName, record.CreatedAt, record.UpdatedAt, AvatarUrl(record.AvatarKey),
        record.NonEssentialEmailsEnabled);

    private string? AvatarUrl(string? avatarKey) =>
        string.IsNullOrEmpty(avatarKey) ? null : $"{settings.AvatarBaseUrl}/{avatarKey}";
}

internal static class Validation
{
    public static string Required(string? value, string field, int maxLength)
    {
        var result = value?.Trim() ?? "";
        if (result.Length is 0 || result.Length > maxLength)
            throw ApiException.BadRequest($"{field} is required and must be {maxLength} characters or fewer.");
        return result;
    }

    public static string Optional(string? value, int maxLength)
    {
        var result = value?.Trim() ?? "";
        if (result.Length > maxLength) throw ApiException.BadRequest($"Text must be {maxLength} characters or fewer.");
        return result;
    }

    public static string? Date(string? value, string field)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        if (!DateOnly.TryParseExact(value, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.None, out var date))
            throw ApiException.BadRequest($"{field} must use YYYY-MM-DD format.");
        return date.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
    }

    public static (string? EventDate, string? SignupDeadline) GroupDates(
        string? eventDateValue,
        string? signupDeadlineValue,
        DateOnly? today = null)
    {
        var eventDate = Date(eventDateValue, "event_date");
        var signupDeadline = Date(signupDeadlineValue, "signup_deadline");
        var minimum = today ?? DateOnly.FromDateTime(DateTime.UtcNow);
        var parsedEventDate = ParseDate(eventDate);
        var parsedSignupDeadline = ParseDate(signupDeadline);

        if (parsedEventDate is not null && parsedEventDate < minimum)
            throw ApiException.BadRequest("event_date cannot be in the past.");
        if (parsedSignupDeadline is not null && parsedSignupDeadline < minimum)
            throw ApiException.BadRequest("signup_deadline cannot be in the past.");
        if (parsedEventDate is not null && parsedSignupDeadline is not null && parsedSignupDeadline > parsedEventDate)
            throw ApiException.BadRequest("signup_deadline must be on or before event_date.");

        return (eventDate, signupDeadline);
    }

    public static long? SpendingLimit(decimal? value)
    {
        if (value is null) return null;
        if (value <= 0 || value > 100_000) throw ApiException.BadRequest("spending_limit must be between 0.01 and 100,000 USD.");
        if (decimal.Round(value.Value, 2) != value.Value)
            throw ApiException.BadRequest("spending_limit must use no more than two decimal places.");
        return checked((long)decimal.Round(value.Value * 100, 0, MidpointRounding.AwayFromZero));
    }

    public static Address Address(Address? value)
    {
        if (value is null) return new();
        var result = new Address(
            Optional(value.Line1, 150), Optional(value.Line2, 150), Optional(value.City, 100),
            Optional(value.Region, 100), Optional(value.PostalCode, 32), Optional(value.Country, 100));
        var fields = new[] { result.Line1, result.Line2, result.City, result.Region, result.PostalCode, result.Country };
        if (fields.All(string.IsNullOrEmpty)) return result;
        if (string.IsNullOrEmpty(result.Line1) || string.IsNullOrEmpty(result.City) ||
            string.IsNullOrEmpty(result.PostalCode) || string.IsNullOrEmpty(result.Country))
            throw ApiException.BadRequest("A mailing address requires line1, city, postal_code, and country.");
        return result;
    }

    public static string? InviteToken(string? value)
    {
        var result = value?.Trim();
        if (result is null || result.Length != 43 || result.Any(character =>
                !(char.IsAsciiLetterOrDigit(character) || character is '-' or '_')))
            return null;
        return result;
    }

    private static DateOnly? ParseDate(string? value) => value is null
        ? null
        : DateOnly.ParseExact(value, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
}
