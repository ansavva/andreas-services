using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.SpaServices.AngularCli;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.AspNetCore.Authentication.Cookies;
using System;
using Humbugg.Web.Services;
using Serilog;
using System.IdentityModel.Tokens.Jwt;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;

namespace Humbugg.Web
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
        public void ConfigureServices(IServiceCollection services)
        {
            services.ConfigureNonBreakingSameSiteCookies();

            if (!CurrentEnvironment.IsDevelopment())
            {
                services.AddDataProtection()
                    .PersistKeysToAWSSystemsManager("/HumbuggWeb/DataProtection");
            }

            JwtSecurityTokenHandler.DefaultInboundClaimTypeMap.Clear();
            
            services.AddAuthentication(options =>
            {
                options.DefaultScheme = CookieAuthenticationDefaults.AuthenticationScheme;
                options.DefaultChallengeScheme = OpenIdConnectDefaults.AuthenticationScheme;
            })
            .AddCookie()
            .AddOpenIdConnect(options =>
            {
                options.SignInScheme = CookieAuthenticationDefaults.AuthenticationScheme;
                options.Authority = Configuration["AuthenticationSettings:Authority"];
                options.RequireHttpsMetadata = Convert.ToBoolean(Configuration["AuthenticationSettings:RequireHttpsMetadata"]);
                options.ClientId = "humbugg_web";
                options.ClientSecret = "e65e808b-5a02-496a-9e5f-9d6418a21488";
                options.ResponseType = "code";
                options.SaveTokens = true;
                options.Scope.Add("humbugg_api.read");
                options.Scope.Add("humbugg_api.write");
            });

            services.AddTransient<IHttpClientService, HttpClientService>(_ => new HttpClientService(Configuration["ApiUrl"]));

            services.AddHealthChecks()
                .AddCheck<HumbuggHealthCheck>("humbugg");

            services.AddControllersWithViews();

            // In production, the Angular files will be served from this directory
            services.AddSpaStaticFiles(configuration =>
            {
                configuration.RootPath = "ClientApp/dist";
            });
        }

        // This method gets called by the runtime. Use this method to configure the HTTP request pipeline.
        public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
        {
            if (env.IsDevelopment()) app.UseDeveloperExceptionPage();
            else
            {
                app.UseExceptionHandler("/Error");
                app.UseHsts();
            }
            app.ConfigureExceptionHandler(app.ApplicationServices.GetService<ILogger>());
            app.UseCookiePolicy();
            if (!env.IsDevelopment())  app.UseHttpsRedirection();
            app.UseStaticFiles();
            if (!env.IsDevelopment()) app.UseSpaStaticFiles();
            // app.UseSerilogRequestLogging();
            app.UseRouting();
            app.UseAuthentication();
            app.UseAuthorization();
            app.UseEndpoints(endpoints => 
            {
                endpoints.MapDefaultControllerRoute();
                endpoints.MapHealthChecks("/health");
            });
            app.UseSpa(spa =>
            {
                spa.Options.SourcePath = "ClientApp";
                if (env.IsDevelopment())
                {
                    spa.UseAngularCliServer(npmScript: "start");
                    // Switch to using an externally started angular application instead of starting one up
                    // and restarting it on every code change. This is useful when making frequent C# changes. 
                    //spa.UseProxyToSpaDevelopmentServer("http://localhost:4200");
                }
            });
        }
    }
}
