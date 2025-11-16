using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography.X509Certificates;
using System.Threading.Tasks;
using IdentityServer4.Stores;
using Microsoft.Extensions.DependencyInjection;

namespace Humbugg.IdentityServer
{
    public static class Extensions
    {
        /// <summary>
        /// Determines whether the client is configured to use PKCE.
        /// </summary>
        /// <param name="store">The store.</param>
        /// <param name="client_id">The client identifier.</param>
        /// <returns></returns>
        public static async Task<bool> IsPkceClientAsync(this IClientStore store, string client_id)
        {
            if (!string.IsNullOrWhiteSpace(client_id))
            {
                var client = await store.FindEnabledClientByIdAsync(client_id);
                return client?.RequirePkce == true;
            }

            return false;
        }

        public static IIdentityServerBuilder AddCertificateFromFile(this IIdentityServerBuilder builder)
        {
            var path = Path.Combine(Directory.GetCurrentDirectory(), "IdentityServer4Auth.pfx");
            Console.WriteLine(path);
            var fileData = File.ReadAllBytes(path);
            builder.AddSigningCredential(new X509Certificate2(fileData));
            return builder;
        }
    }
}
