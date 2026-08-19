using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Humbugg.Api.Services.Email.Core;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class CustomizationTests
{
    [Theory]
    [InlineData("<script>alert(1)</script>", "")]
    [InlineData("Welcome", "https://evil.example")]
    public void RejectsMarkupAndLinks(string greeting, string instructions) =>
        Assert.Throws<ApiException>(() => CustomizationValidation.Validate(
            new(greeting, instructions, "#112233", "#AABBCC", null)));

    [Theory]
    [InlineData("red")]
    [InlineData("#12345G")]
    public void RejectsArbitraryStyling(string color) =>
        Assert.Throws<ApiException>(() => CustomizationValidation.Validate(new("", "", color, "#AABBCC", null)));

    [Fact]
    public void RejectsNonImagePayload() =>
        Assert.Throws<ApiException>(() => CustomizationValidation.Validate(
            new("", "", "#112233", "#AABBCC", Convert.ToBase64String("not an image"u8.ToArray()))));

    [Fact]
    public void IncompleteCustomizationKeepsReadableHumbuggDisclosure()
    {
        var email = new TransactionalEmailTemplates().Invitation(new(
            "event", "person@example.com", "Pat", "Alex", "Exchange",
            new Uri("https://humbugg.com/join"), new ExchangeCustomization()));
        Assert.Contains("<h1>", email.HtmlBody);
        Assert.Contains("— Humbugg", email.TextBody);
        Assert.DoesNotContain("<script", email.HtmlBody, StringComparison.OrdinalIgnoreCase);
    }
}
