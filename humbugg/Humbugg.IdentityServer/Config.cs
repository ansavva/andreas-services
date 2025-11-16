// using System.Collections.Generic;
// using IdentityServer4;
// using IdentityServer4.Models;
// using Microsoft.Extensions.Configuration;

// namespace Humbugg.IdentityServer
// {
//     internal class Config
//     {
//         private readonly IConfiguration _configuration;

//         public Config(IConfiguration configuration)
//         {
//             _configuration = configuration;
//         }
        
//         public IEnumerable<Client> Clients =>
//             new List<Client>
//             {
//                 new Client 
//                 {
//                     ClientId = "humbugg_web",
//                     ClientName = "Humbugg Web",
//                     ClientSecrets = { new Secret("e65e808b-5a02-496a-9e5f-9d6418a21488".Sha256()) },
//                     AllowedGrantTypes = GrantTypes.Code,
//                     RequireConsent = false,
//                     RedirectUris = {$"{_configuration["ClientUrls:HumbuggWeb"]}/signin-oidc"},
//                     PostLogoutRedirectUris = {$"{_configuration["ClientUrls:HumbuggWeb"]}/signout-callback-oidc"},
//                     AllowAccessTokensViaBrowser = true,
//                     AccessTokenLifetime = 3600,
//                     AllowedScopes = new List<string>
//                     {
//                         IdentityServerConstants.StandardScopes.OpenId,
//                         IdentityServerConstants.StandardScopes.Profile,
//                         IdentityServerConstants.StandardScopes.Email,
//                         "humbugg_api.read",
//                         "humbugg_api.write"
//                     },
//                     AllowOfflineAccess = true,
//                     AllowedCorsOrigins = {_configuration["ClientUrls:HumbuggWeb"]}
//                 }
//             };

//         public IEnumerable<IdentityResource> IdentityResources =>
//             new List<IdentityResource>
//             {
//                 new IdentityResources.OpenId(),
//                 new IdentityResources.Profile(),
//                 new IdentityResources.Email()
//             };

//         public IEnumerable<ApiResource> ApiResources =>
//             new List<ApiResource>
//             {
//                 new ApiResource
//                 {
//                     Name = "humbugg_api",
//                     DisplayName = "Humbugg Api",
//                     Description = "Allow the application to access Humbugg API on your behalf",
//                     Scopes = { "humbugg_api.read", "humbugg_api.write"},
//                     ApiSecrets = { new Secret("b8d66da7-88c8-4ed8-98c7-2abb9637dbf7".Sha256()) },
//                     UserClaims = new List<string> {}
//                 }
//             };
        
//         public IEnumerable<ApiScope> ApiScopes =>
//             new List<ApiScope>
//             {
//                 new ApiScope("humbugg_api.read", "Read Access to Humbugg Api"),
//                 new ApiScope("humbugg_api.write", "Write Access to Humbugg Api")
//             };
//     }
// }