using Humbugg.Api.Services.Realtime;

namespace Humbugg.Api.Tests;

/// <summary>Records every nudge, so a test can say who was told and exactly what.</summary>
internal sealed class RecordingRealtime : IRealtimeNotifier
{
    public List<(string UserId, RealtimeNudge Nudge)> Sent { get; } = [];

    public Task NudgeAsync(string userId, RealtimeNudge nudge, CancellationToken cancellationToken = default)
    {
        Sent.Add((userId, nudge));
        return Task.CompletedTask;
    }
}
