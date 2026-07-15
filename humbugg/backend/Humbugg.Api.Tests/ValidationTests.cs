using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class ValidationTests
{
    private static readonly DateOnly Today = new(2030, 1, 1);

    [Fact]
    public void RequiredRejectsWhitespaceAndOverlongValues()
    {
        Assert.Throws<ApiException>(() => Validation.Required("   ", "name", 10));
        Assert.Throws<ApiException>(() => Validation.Required("12345678901", "name", 10));
        Assert.Equal("Name", Validation.Required("  Name  ", "name", 10));
    }

    [Fact]
    public void DateRequiresIsoCalendarFormat()
    {
        Assert.Throws<ApiException>(() => Validation.Date("12/25/2030", "event_date"));
        Assert.Throws<ApiException>(() => Validation.Date("2030-02-30", "event_date"));
    }

    [Fact]
    public void GroupDatesRejectPastEventDate()
    {
        var error = Assert.Throws<ApiException>(() => Validation.GroupDates("2029-12-31", null, Today));
        Assert.Equal(400, error.StatusCode);
        Assert.Contains("event_date", error.Message);
    }

    [Fact]
    public void GroupDatesRejectPastSignupDeadline()
    {
        var error = Assert.Throws<ApiException>(() => Validation.GroupDates("2030-12-25", "2029-12-31", Today));
        Assert.Equal(400, error.StatusCode);
        Assert.Contains("signup_deadline", error.Message);
    }

    [Fact]
    public void GroupDatesRequireDeadlineOnOrBeforeEvent()
    {
        var error = Assert.Throws<ApiException>(() => Validation.GroupDates("2030-12-24", "2030-12-25", Today));
        Assert.Equal(400, error.StatusCode);
        Assert.Contains("on or before", error.Message);
    }

    [Fact]
    public void GroupDatesAcceptTodayAndFutureDates()
    {
        var result = Validation.GroupDates("2030-12-25", "2030-01-01", Today);
        Assert.Equal("2030-12-25", result.EventDate);
        Assert.Equal("2030-01-01", result.SignupDeadline);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(100000.01)]
    [InlineData(1.001)]
    public void SpendingLimitRejectsInvalidValues(decimal value)
    {
        Assert.Throws<ApiException>(() => Validation.SpendingLimit(value));
    }

    [Theory]
    [InlineData(0.01, 1)]
    [InlineData(50, 5000)]
    [InlineData(100000, 10000000)]
    public void SpendingLimitAcceptsValidValues(decimal value, long expectedCents)
    {
        Assert.Equal(expectedCents, Validation.SpendingLimit(value));
    }

    [Fact]
    public void AddressAllowsEmptyOrCompleteValues()
    {
        var empty = Validation.Address(new Address());
        Assert.All(new[] { empty.Line1, empty.Line2, empty.City, empty.Region, empty.PostalCode, empty.Country },
            value => Assert.Equal("", value));
        var address = Validation.Address(new Address("1 Main St", null, "Boston", "MA", "02110", "US"));
        Assert.Equal("1 Main St", address.Line1);
    }

    [Fact]
    public void AddressRejectsPartialValues()
    {
        var error = Assert.Throws<ApiException>(() => Validation.Address(new Address(City: "Boston")));
        Assert.Contains("requires", error.Message);
    }

    [Fact]
    public void InviteTokenRequiresExpectedBase64UrlShape()
    {
        Assert.Null(Validation.InviteToken("short"));
        Assert.Null(Validation.InviteToken(new string('!', 43)));
        Assert.Equal(new string('a', 43), Validation.InviteToken(new string('a', 43)));
    }
}
