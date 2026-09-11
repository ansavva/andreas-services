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
        Assert.Throws<ApiException>(() => CustomizationValidation.Validate(new(greeting, instructions)));

    // Words only since #677. The colours and the banner are gone from the record, so there is no
    // longer a styling input to reject; what is pinned here is that the record stays two strings —
    // a colour or an image creeping back in is a decision, not a field.
    [Fact]
    public void CustomizationIsGreetingAndInstructionsOnly()
    {
        var saved = CustomizationValidation.Validate(new(" Welcome ", " Bring it wrapped. "));
        Assert.Equal(new ExchangeCustomization("Welcome", "Bring it wrapped."), saved);
        Assert.Equal(2, typeof(ExchangeCustomization).GetProperties().Length);
    }

    [Fact]
    public void IncompleteCustomizationKeepsReadableHumbuggDisclosure()
    {
        var email = new TransactionalEmailTemplates().Invitation(new(
            "event", "person@example.com", "Pat", "Alex", "Exchange",
            new Uri("https://humbugg.com/join"), new ExchangeCustomization()));
        Assert.Contains("<h1 ", email.HtmlBody);
        Assert.Contains("— Humbugg", email.TextBody);
        Assert.DoesNotContain("<script", email.HtmlBody, StringComparison.OrdinalIgnoreCase);
    }
}
