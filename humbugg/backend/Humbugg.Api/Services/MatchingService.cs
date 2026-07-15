using Humbugg.Api.Models;
using System.Security.Cryptography;

namespace Humbugg.Api.Services;

public interface IMatchingService
{
    IReadOnlyDictionary<string, string> CreateAssignments(IEnumerable<string> memberIds, IEnumerable<string[]> exclusions);
}

public sealed class MatchingService : IMatchingService
{
    public IReadOnlyDictionary<string, string> CreateAssignments(IEnumerable<string> memberIds, IEnumerable<string[]> exclusions)
    {
        var members = memberIds.Distinct(StringComparer.Ordinal).ToList();
        if (members.Count < 2) throw ApiException.Conflict("At least two active participants are required.");
        var excluded = exclusions.Where(pair => pair.Length == 2)
            .Select(pair => PairKey(pair[0], pair[1])).ToHashSet(StringComparer.Ordinal);
        var candidates = members.ToDictionary(giver => giver, giver =>
        {
            var allowed = members.Where(recipient => recipient != giver && !excluded.Contains(PairKey(giver, recipient))).ToList();
            Shuffle(allowed);
            return allowed;
        }, StringComparer.Ordinal);

        var recipientToGiver = new Dictionary<string, string>(StringComparer.Ordinal);
        var order = members.ToList();
        Shuffle(order);
        foreach (var giver in order)
            if (!Assign(giver, new HashSet<string>(StringComparer.Ordinal), candidates, recipientToGiver))
                throw ApiException.Conflict("These exclusions do not allow a complete draw.");
        return recipientToGiver.ToDictionary(pair => pair.Value, pair => pair.Key, StringComparer.Ordinal);
    }

    private static bool Assign(string giver, HashSet<string> seen, IReadOnlyDictionary<string, List<string>> candidates, IDictionary<string, string> recipientToGiver)
    {
        foreach (var recipient in candidates[giver])
        {
            if (!seen.Add(recipient)) continue;
            if (!recipientToGiver.TryGetValue(recipient, out var previous) || Assign(previous, seen, candidates, recipientToGiver))
            {
                recipientToGiver[recipient] = giver;
                return true;
            }
        }
        return false;
    }

    private static string PairKey(string left, string right) => string.CompareOrdinal(left, right) < 0 ? $"{left}\0{right}" : $"{right}\0{left}";
    private static void Shuffle<T>(IList<T> values)
    {
        for (var index = values.Count - 1; index > 0; index--)
        {
            var other = RandomNumberGenerator.GetInt32(index + 1);
            (values[index], values[other]) = (values[other], values[index]);
        }
    }
}
