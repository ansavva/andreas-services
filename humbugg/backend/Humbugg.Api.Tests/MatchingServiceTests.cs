using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class MatchingServiceTests
{
    private readonly MatchingService _subject = new();

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void RequiresAtLeastTwoMembers(int count)
    {
        var error = Assert.Throws<ApiException>(() => _subject.CreateAssignments(
            Enumerable.Range(0, count).Select(index => index.ToString()), []));
        Assert.Equal(409, error.StatusCode);
    }

    [Fact]
    public void TwoMembersDrawEachOther()
    {
        var result = _subject.CreateAssignments(["a", "b"], []);
        Assert.Equal("b", result["a"]);
        Assert.Equal("a", result["b"]);
    }

    [Fact]
    public void ProducesACompleteUniqueDerangement()
    {
        var members = Enumerable.Range(0, 50).Select(index => $"member-{index}").ToArray();
        var result = _subject.CreateAssignments(members, []);
        Assert.Equal(members.Length, result.Count);
        Assert.Equal(members.Order(), result.Keys.Order());
        Assert.Equal(members.Order(), result.Values.Order());
        Assert.All(result, assignment => Assert.NotEqual(assignment.Key, assignment.Value));
    }

    [Fact]
    public void RespectsSymmetricPairExclusions()
    {
        var result = _subject.CreateAssignments(["a", "b", "c", "d"], [["a", "b"]]);
        Assert.NotEqual("b", result["a"]);
        Assert.NotEqual("a", result["b"]);
    }

    [Fact]
    public void RejectsImpossibleGraphWithoutLooping()
    {
        var error = Assert.Throws<ApiException>(() => _subject.CreateAssignments(
            ["a", "b", "c"], [["a", "b"], ["a", "c"]]));
        Assert.Equal("conflict", error.Code);
    }

    [Fact]
    public void NeverAssignsInactiveMembersWhenCallerFiltersRoster()
    {
        var active = new[] { "a", "b", "c" };
        var result = _subject.CreateAssignments(active, []);
        Assert.DoesNotContain("inactive", result.Keys);
        Assert.DoesNotContain("inactive", result.Values);
    }

    [Fact]
    public void RepeatedDrawsAlwaysTerminateAndRemainValid()
    {
        var members = Enumerable.Range(0, 12).Select(index => index.ToString()).ToArray();
        for (var iteration = 0; iteration < 250; iteration++)
        {
            var result = _subject.CreateAssignments(members, [["0", "1"], ["2", "3"]]);
            Assert.Equal(members.Length, result.Count);
            Assert.All(result, pair => Assert.NotEqual(pair.Key, pair.Value));
        }
    }
}
