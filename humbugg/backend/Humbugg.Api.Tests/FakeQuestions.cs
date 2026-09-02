using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Tests;

/// <summary>
/// An in-memory question store (#131).
/// </summary>
/// <remarks>
/// Real behaviour rather than a counter, because the tests that matter most here are about what is
/// NOT stored: <see cref="All"/> is asserted against directly to show no row carries a giver.
/// </remarks>
internal sealed class FakeQuestions : IQuestionRepository
{
    private readonly List<QuestionMessageRecord> messages = [];
    private readonly Dictionary<string, QuestionThreadRecord> threads = new(StringComparer.Ordinal);

    public IReadOnlyList<QuestionMessageRecord> All => messages;
    public int DeleteByGroupCalls { get; private set; }
    public List<string> DeletedForMembers { get; } = [];

    public Task<(QuestionThreadRecord? Thread, IReadOnlyList<QuestionMessageRecord> Messages)> GetThreadAsync(
        string threadId,
        CancellationToken cancellationToken = default) =>
        Task.FromResult<(QuestionThreadRecord?, IReadOnlyList<QuestionMessageRecord>)>((
            threads.TryGetValue(threadId, out var thread) ? thread : null,
            messages
                .Where(item => item.ThreadId == threadId)
                .OrderBy(item => item.MessageId, StringComparer.Ordinal)
                .ToList()));

    public Task AppendAsync(QuestionMessageRecord message, CancellationToken cancellationToken = default)
    {
        messages.Add(message);
        return Task.CompletedTask;
    }

    public Task SetBlockedAsync(QuestionThreadRecord thread, CancellationToken cancellationToken = default)
    {
        threads[thread.ThreadId] = thread;
        return Task.CompletedTask;
    }

    public Task DeleteByGroupAsync(string groupId, CancellationToken cancellationToken = default)
    {
        DeleteByGroupCalls++;
        messages.RemoveAll(item => item.GroupId == groupId);
        foreach (var key in threads.Where(pair => pair.Value.GroupId == groupId).Select(pair => pair.Key).ToList())
            threads.Remove(key);
        return Task.CompletedTask;
    }

    public Task DeleteForMemberAsync(
        string groupId,
        string recipientMemberId,
        IReadOnlyCollection<string> alsoThreadIds,
        CancellationToken cancellationToken = default)
    {
        DeletedForMembers.Add(recipientMemberId);
        var wanted = new HashSet<string>(alsoThreadIds, StringComparer.Ordinal);
        bool Matches(string group, string recipient, string thread) =>
            group == groupId && (recipient == recipientMemberId || wanted.Contains(thread));
        messages.RemoveAll(item => Matches(item.GroupId, item.RecipientMemberId, item.ThreadId));
        foreach (var key in threads
            .Where(pair => Matches(pair.Value.GroupId, pair.Value.RecipientMemberId, pair.Key))
            .Select(pair => pair.Key)
            .ToList())
            threads.Remove(key);
        return Task.CompletedTask;
    }
}
