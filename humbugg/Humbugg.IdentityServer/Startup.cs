using System.Linq;
using Humbugg.IdentityServer.Data;
using Humbugg.IdentityServer.Services;
using IdentityServer4;
using IdentityServer4.Models;
using IdentityServer4.Services;
using IdentityServer4.Validation;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;
using MongoDB.Bson.Serialization.Conventions;
using Serilog;

namespace Humbugg.IdentityServer
{
    public class Startup
    {
        public Startup(IConfiguration configuration, IWebHostEnvironment currentEnvironment)
        {
            Configuration = configuration;
            CurrentEnvironment = currentEnvironment;
        }

        private IConfiguration Configuration { get; }
        private IWebHostEnvironment CurrentEnvironment{ get; } 
        
        // This method gets called by the runtime. Use this method to add services to the container.
        // For more information on how to configure your application, visit https://go.microsoft.com/fwlink/?LinkID=398940
        public void ConfigureServices(IServiceCollection services)
        {
            services.ConfigureNonBreakingSameSiteCookies();

            if (!CurrentEnvironment.IsDevelopment())
            {
                services.AddDataProtection()
                    .PersistKeysToAWSSystemsManager("/HumbuggIdentity/DataProtection");
            }

            var identityServer = services.AddIdentityServer()
                .AddMongoRepository(
                    Configuration["DatabaseSettings:ConnectionString"],
                    Configuration["DatabaseSettings:DatabaseName"])
                .AddClients()
                .AddIdentityApiResources()
                .AddPersistedGrants()
                .AddProfileService<ProfileService>()      
                .AddResourceOwnerValidator<ResourceOwnerPasswordValidator>();

            if (!CurrentEnvironment.IsDevelopment())
            {
                identityServer.AddCertificateFromFile();
            }
            else 
            {
                identityServer.AddDeveloperSigningCredential();
            }

            services.AddAuthentication()
                .AddFacebook(options => 
                {
                    options.SignInScheme = IdentityServerConstants.ExternalCookieAuthenticationScheme;
                    options.AppId = Configuration["Authentication:Facebook:AppId"];
                    options.AppSecret = Configuration["Authentication:Facebook:AppSecret"];
                })
                .AddGoogle(options =>
                {
                    options.SignInScheme = IdentityServerConstants.ExternalCookieAuthenticationScheme;
                    options.ClientId = Configuration["Authentication:Google:ClientId"];
                    options.ClientSecret = Configuration["Authentication:Google:ClientSecret"];
                });

            services.Configure<DatabaseSettings>(Configuration.GetSection(nameof(DatabaseSettings)));

            services.AddSingleton<IDatabaseSettings>(sp => sp.GetRequiredService<IOptions<DatabaseSettings>>().Value);
            services.AddTransient<IProfileRepository, ProfileRepository>();
            services.AddTransient<IResourceOwnerPasswordValidator, ResourceOwnerPasswordValidator>();
            services.AddTransient<IProfileService, ProfileService>();
            services.AddTransient<ILoginService, LoginService>();

            services.AddSingleton<ICorsPolicyService, RepositoryCorsPolicyService>();

            // Ignore extra elements in MongoDB Classes
            var pack = new ConventionPack();
            pack.Add(new IgnoreExtraElementsConvention(true));
            ConventionRegistry.Register("Humbugg Identity Server Conventions", pack, t => true);

            // SeedDatabase(services);

            services.AddHealthChecks()
                .AddCheck<HumbuggHealthCheck>("humbugg");

            services.AddMvc();
        }

        // This method gets called by the runtime. Use this method to configure the HTTP request pipeline.
        public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
        {
            if (env.IsDevelopment()) app.UseDeveloperExceptionPage();
            else app.UseExceptionHandler("/Home/Error");
            app.ConfigureExceptionHandler(app.ApplicationServices.GetService<ILogger>());
            app.UseCookiePolicy();
            if (!env.IsDevelopment()) app.UseHttpsRedirection();
            app.UseStaticFiles();
            app.UseCors(builder => builder.WithOrigins(Configuration["ClientUrls:HumbuggWeb"]).AllowAnyHeader().AllowAnyMethod().AllowCredentials());
            // app.UseSerilogRequestLogging();
            app.UseRouting();
            app.UseIdentityServer();
            app.UseAuthorization();
            app.UseEndpoints(endpoints => 
            {
                endpoints.MapDefaultControllerRoute();
                endpoints.MapHealthChecks("/health");
            });
        }

        // private void SeedDatabase(IServiceCollection services)
        // {
        //     ConfigureMongoDriverIgnoreExtraElements();

        //     var config = new Config(Configuration);
        //     var sp = services.BuildServiceProvider();
        //     var repository = sp.GetService<IRepository>();

        //     if (!repository.All<Client>().Any())
        //         repository.Add<Client>(config.Clients);

        //     if (!repository.All<IdentityResource>().Any())
        //         repository.Add<IdentityResource>(config.IdentityResources);

        //     if (!repository.All<ApiResource>().Any())
        //         repository.Add<ApiResource>(config.ApiResources);

        //     if (!repository.All<ApiScope>().Any())
        //         repository.Add<ApiScope>(config.ApiScopes);
        // }

        private void ConfigureMongoDriverIgnoreExtraElements()
        {
            var pack = new ConventionPack();
            pack.Add(new IgnoreExtraElementsConvention(true));
            ConventionRegistry.Register("IdentityServer Mongo Conventions", pack, t => true);
        }
    }
}