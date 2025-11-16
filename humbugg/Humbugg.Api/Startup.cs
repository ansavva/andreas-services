using System;
using Humbugg.Api.Data;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;
using Serilog;

namespace Humbugg.Api
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

            if (!CurrentEnvironment.IsDevelopment())
            {
                services.AddDataProtection()
                    .PersistKeysToAWSSystemsManager("/HumbuggApi/DataProtection");
            }

            services.AddAuthentication(options => {
                options.DefaultAuthenticateScheme = JwtBearerDefaults.AuthenticationScheme;
                options.DefaultChallengeScheme = JwtBearerDefaults.AuthenticationScheme;
            })
            .AddJwtBearer(options =>
            {
                options.Authority = Configuration["AuthenticationSettings:Authority"];
                options.RequireHttpsMetadata = Convert.ToBoolean(Configuration["AuthenticationSettings:RequireHttpsMetadata"]);
                options.Audience = "humbugg_api";
            });

            // Database services
            services.Configure<DatabaseSettings>(Configuration.GetSection(nameof(DatabaseSettings)));
            services.AddSingleton<IDatabaseSettings>(sp => sp.GetRequiredService<IOptions<DatabaseSettings>>().Value);
            services.AddTransient<IProfileRepository, ProfileRepository>();
            services.AddTransient<IGroupRepository, GroupRepository>();
            services.AddTransient<IGroupMemberRepository, GroupMemberRepository>();

            // Services/Engines
            services.AddSingleton<IHttpContextAccessor, HttpContextAccessor>();
            services.AddTransient<IUser, User>();
            services.AddTransient<IProfileService, ProfileService>();
            services.AddTransient<IGroupEngine, GroupEngine>();
            services.AddTransient<IGroupMemberEngine, GroupMemberEngine>();
            services.AddTransient<ILoggerEnigne, LoggerEngine>();

            services.AddHealthChecks()
                .AddCheck<HumbuggHealthCheck>("humbugg");

            services.AddControllers();
        }

        // This method gets called by the runtime. Use this method to configure the HTTP request pipeline.
        public void Configure(IApplicationBuilder app, IWebHostEnvironment env)
        {
            if (env.IsDevelopment()) app.UseDeveloperExceptionPage();
            else app.UseHttpsRedirection();
            app.ConfigureExceptionHandler(app.ApplicationServices.GetService<ILogger>());
            app.UseCors(builder => builder.WithOrigins(Configuration["ClientUrls:HumbuggWeb"]).AllowAnyHeader().AllowAnyMethod().AllowCredentials());
            // app.UseSerilogRequestLogging();
            app.UseRouting();
            app.UseAuthentication();
            app.UseAuthorization();
            app.UseEndpoints(endpoints =>
            {
                endpoints.MapControllers();
                endpoints.MapHealthChecks("/health");
            });
        }
    }
}