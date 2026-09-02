using Amazon.CognitoIdentityProvider.Model;
using Humbugg.Api.Services;
using Xunit;

namespace Humbugg.Api.Tests;

/// <summary>
/// Where a member's email address comes from (#137).
/// </summary>
/// <remarks>
/// One rule, and it is a safety rule rather than a data-shape one: Humbugg sends only to an address
/// Cognito says the person has proved they control. Sending to an unverified one would let anybody
/// who can sign up direct Humbugg's mail at a stranger, which is a spam relay with extra steps.
/// </remarks>
public sealed class AccountDirectoryTests
{
    private static AttributeType Attribute(string name, string value) => new() { Name = name, Value = value };

    [Fact]
    public void AVerifiedAddressIsReturned()
    {
        var email = CognitoAccountDirectory.VerifiedEmailFrom(
            [Attribute("email", " person@example.test "), Attribute("email_verified", "true")]);

        Assert.Equal("person@example.test", email);
    }

    /// <summary>Everything that is not an explicit, verified address reads as no address.</summary>
    [Theory]
    // Signed up and never confirmed: the commonest case, and the one that matters.
    [InlineData("false")]
    // Cognito writes "true"/"false", but a pool configured differently, or a value that arrives
    // through an import, must not be read as consent by accident.
    [InlineData("yes")]
    [InlineData("1")]
    [InlineData("")]
    public void AnUnverifiedAddressIsNotAnAddress(string verified)
    {
        Assert.Null(CognitoAccountDirectory.VerifiedEmailFrom(
            [Attribute("email", "person@example.test"), Attribute("email_verified", verified)]));
    }

    [Fact]
    public void AMissingFlagOrMissingAddressIsNotAnAddress()
    {
        Assert.Null(CognitoAccountDirectory.VerifiedEmailFrom([Attribute("email", "person@example.test")]));
        Assert.Null(CognitoAccountDirectory.VerifiedEmailFrom([Attribute("email_verified", "true")]));
        Assert.Null(CognitoAccountDirectory.VerifiedEmailFrom(
            [Attribute("email", "   "), Attribute("email_verified", "true")]));
        Assert.Null(CognitoAccountDirectory.VerifiedEmailFrom([]));
    }

    /// <summary>Cognito's own casing is "true"; a pool that ever writes "True" still counts.</summary>
    [Fact]
    public void TheFlagIsReadCaseInsensitively()
    {
        Assert.Equal("person@example.test", CognitoAccountDirectory.VerifiedEmailFrom(
            [Attribute("email", "person@example.test"), Attribute("email_verified", "True")]));
    }
}
