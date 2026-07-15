using Humbugg.Api.Services;
using Microsoft.AspNetCore.Http;
using System.Security.Claims;
using Xunit;

namespace Humbugg.Api.Tests;

public sealed class CurrentUserTests
{
    [Fact]
    public void ReadsRawCognitoSubjectClaim()
    {
        var subject = CreateSubject(new Claim("sub", "cognito-user-id"));

        Assert.Equal("cognito-user-id", subject.UserId);
    }

    [Fact]
    public void AcceptsFrameworkMappedSubjectClaim()
    {
        var subject = CreateSubject(new Claim(ClaimTypes.NameIdentifier, "mapped-user-id"));

        Assert.Equal("mapped-user-id", subject.UserId);
    }

    private static CurrentUser CreateSubject(Claim claim)
    {
        var context = new DefaultHttpContext
        {
            User = new ClaimsPrincipal(new ClaimsIdentity([claim], "test"))
        };
        return new CurrentUser(new HttpContextAccessor { HttpContext = context });
    }
}
