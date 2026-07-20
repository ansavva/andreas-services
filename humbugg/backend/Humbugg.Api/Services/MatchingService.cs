using Humbugg.Api.Models;
using System.Security.Cryptography;

namespace Humbugg.Api.Services;

public interface IMatchingService
{
    IReadOnlyDictionary<string, string> CreateAssignments(IEnumerable<string> memberIds, IEnumerable<string[]> exclusions);
    MinimalAssignmentResult CreateMinimalChangeAssignments(
        IReadOnlyDictionary<string, string> currentAssignments,
        string newMemberId,
        IEnumerable<string[]> exclusions);
}

public sealed class MatchingService : IMatchingService
{
    private const long ChangedAssignmentCost = 100_000;
    private const long ForbiddenCost = 1_000_000_000;

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

    public MinimalAssignmentResult CreateMinimalChangeAssignments(
        IReadOnlyDictionary<string, string> currentAssignments,
        string newMemberId,
        IEnumerable<string[]> exclusions)
    {
        if (string.IsNullOrWhiteSpace(newMemberId) || currentAssignments.ContainsKey(newMemberId))
            throw ApiException.Conflict("The late participant is already part of this draw.");
        var existing = currentAssignments.Keys.Order(StringComparer.Ordinal).ToArray();
        if (existing.Length < 2 ||
            currentAssignments.Count != currentAssignments.Values.Distinct(StringComparer.Ordinal).Count() ||
            existing.Any(member => !currentAssignments.Values.Contains(member, StringComparer.Ordinal)))
            throw ApiException.Conflict("The current draw is not a complete assignment.");

        var members = existing.Append(newMemberId).Order(StringComparer.Ordinal).ToArray();
        var excluded = exclusions
            .Where(pair => pair.Length == 2)
            .Select(pair => PairKey(pair[0], pair[1]))
            .ToHashSet(StringComparer.Ordinal);
        var costs = new long[members.Length, members.Length];
        for (var giverIndex = 0; giverIndex < members.Length; giverIndex++)
        {
            var giver = members[giverIndex];
            for (var recipientIndex = 0; recipientIndex < members.Length; recipientIndex++)
            {
                var recipient = members[recipientIndex];
                if (giver == recipient || excluded.Contains(PairKey(giver, recipient)))
                {
                    costs[giverIndex, recipientIndex] = ForbiddenCost;
                    continue;
                }
                var changed = giver != newMemberId &&
                    (!currentAssignments.TryGetValue(giver, out var oldRecipient) || oldRecipient != recipient);
                costs[giverIndex, recipientIndex] =
                    (changed ? ChangedAssignmentCost : 0) + recipientIndex;
            }
        }

        var assignmentIndexes = MinimumCostAssignment(costs);
        var assignments = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var giverIndex = 0; giverIndex < members.Length; giverIndex++)
        {
            var recipientIndex = assignmentIndexes[giverIndex];
            if (recipientIndex < 0 || costs[giverIndex, recipientIndex] >= ForbiddenCost)
                throw ApiException.Conflict("No valid minimal reassignment exists for this late participant.");
            assignments[members[giverIndex]] = members[recipientIndex];
        }
        var affected = members
            .Where(giver => giver == newMemberId ||
                !currentAssignments.TryGetValue(giver, out var oldRecipient) ||
                assignments[giver] != oldRecipient)
            .Order(StringComparer.Ordinal)
            .ToArray();
        return new(assignments, affected);
    }

    private static int[] MinimumCostAssignment(long[,] costs)
    {
        var count = costs.GetLength(0);
        var rowPotential = new long[count + 1];
        var columnPotential = new long[count + 1];
        var matchedRow = new int[count + 1];
        var path = new int[count + 1];
        for (var row = 1; row <= count; row++)
        {
            matchedRow[0] = row;
            var minimum = Enumerable.Repeat(long.MaxValue, count + 1).ToArray();
            var used = new bool[count + 1];
            var column = 0;
            do
            {
                used[column] = true;
                var currentRow = matchedRow[column];
                var delta = long.MaxValue;
                var nextColumn = 0;
                for (var candidate = 1; candidate <= count; candidate++)
                {
                    if (used[candidate]) continue;
                    var reduced = costs[currentRow - 1, candidate - 1] -
                        rowPotential[currentRow] -
                        columnPotential[candidate];
                    if (reduced < minimum[candidate])
                    {
                        minimum[candidate] = reduced;
                        path[candidate] = column;
                    }
                    if (minimum[candidate] < delta)
                    {
                        delta = minimum[candidate];
                        nextColumn = candidate;
                    }
                }
                for (var candidate = 0; candidate <= count; candidate++)
                {
                    if (used[candidate])
                    {
                        rowPotential[matchedRow[candidate]] += delta;
                        columnPotential[candidate] -= delta;
                    }
                    else
                    {
                        minimum[candidate] -= delta;
                    }
                }
                column = nextColumn;
            } while (matchedRow[column] != 0);

            do
            {
                var previous = path[column];
                matchedRow[column] = matchedRow[previous];
                column = previous;
            } while (column != 0);
        }

        var result = Enumerable.Repeat(-1, count).ToArray();
        for (var column = 1; column <= count; column++)
            if (matchedRow[column] > 0)
                result[matchedRow[column] - 1] = column - 1;
        return result;
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
