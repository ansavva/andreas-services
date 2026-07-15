using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal static class DynamoValues
{
    public static AttributeValue S(string value) => new(value);
    public static AttributeValue N(long value) => new() { N = value.ToString(System.Globalization.CultureInfo.InvariantCulture) };
    public static AttributeValue B(bool value) => new() { BOOL = value };
    public static string String(this IReadOnlyDictionary<string, AttributeValue> item, string key, string fallback = "") =>
        item.TryGetValue(key, out var value) ? value.S ?? fallback : fallback;
    public static bool Bool(this IReadOnlyDictionary<string, AttributeValue> item, string key) =>
        item.TryGetValue(key, out var value) && value.BOOL == true;
    public static long? Long(this IReadOnlyDictionary<string, AttributeValue> item, string key) =>
        item.TryGetValue(key, out var value) && long.TryParse(value.N, out var number) ? number : null;

    public static AttributeValue AddressValue(Address address) => new()
    {
        M = new Dictionary<string, AttributeValue>(StringComparer.Ordinal)
        {
            ["line1"] = S(address.Line1 ?? ""),
            ["line2"] = S(address.Line2 ?? ""),
            ["city"] = S(address.City ?? ""),
            ["region"] = S(address.Region ?? ""),
            ["postal_code"] = S(address.PostalCode ?? ""),
            ["country"] = S(address.Country ?? "")
        }
    };

    public static Address Address(this IReadOnlyDictionary<string, AttributeValue> item, string key)
    {
        if (!item.TryGetValue(key, out var value) || value.M is null) return new Address();
        return new Address(value.M.String("line1"), value.M.String("line2"), value.M.String("city"),
            value.M.String("region"), value.M.String("postal_code"), value.M.String("country"));
    }

    public static AttributeValue ExclusionsValue(IReadOnlyList<string[]> exclusions) => new()
    {
        L = exclusions.Select(pair => new AttributeValue { L = pair.Select(S).ToList() }).ToList()
    };

    public static IReadOnlyList<string[]> Exclusions(this IReadOnlyDictionary<string, AttributeValue> item)
    {
        if (!item.TryGetValue("exclusions", out var value) || value.L is null) return [];
        return value.L.Select(pair => pair.L?.Select(entry => entry.S ?? "").ToArray() ?? []).ToList();
    }
}
