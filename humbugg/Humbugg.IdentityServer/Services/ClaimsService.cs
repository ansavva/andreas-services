using System.Security.Claims;
using Humbugg.IdentityServer.Models;
using IdentityModel;

namespace Humbugg.IdentityServer.Services
{
    public class ClaimsService
    {
        //build claims array from user data
        public static Claim[] GetUserClaims(Profile user)
        {
            return new Claim[]
            {
                new Claim("user_id", user.Id.ToString() ?? ""),
                new Claim(JwtClaimTypes.Name, (!string.IsNullOrEmpty(user.FirstName) && !string.IsNullOrEmpty(user.LastName)) ? (user.FirstName + " " + user.LastName) : ""),
                new Claim(JwtClaimTypes.GivenName, user.FirstName  ?? ""),
                new Claim(JwtClaimTypes.FamilyName, user.LastName  ?? ""),
                new Claim(JwtClaimTypes.Email, user.Email  ?? ""),

                //roles
                new Claim(JwtClaimTypes.Role, user.Role)
            };
        }
    }
}