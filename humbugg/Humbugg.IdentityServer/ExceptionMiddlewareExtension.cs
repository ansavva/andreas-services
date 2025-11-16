using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Http;
using System.Net;
using Humbugg.IdentityServer.Models;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using Serilog;

namespace Humbugg.IdentityServer
{
    public static class ExceptionMiddlewareExtensions
    {
        public static void ConfigureExceptionHandler(this IApplicationBuilder app, ILogger logger)
        {
            app.UseWhen(context => context.Request.Path.StartsWithSegments("/api"), subApp =>
            {
                subApp.UseExceptionHandler(appError =>
                {
                    appError.Run(async context =>
                    {
                        var errorMessage = "Oops! Something went wrong with Humbugg.";
                        var contextFeature = context.Features.Get<IExceptionHandlerFeature>();
                        if(contextFeature != null)
                        {
                            logger.Error(contextFeature.Error, "Internal Server Error");
                            if (contextFeature.Error is HumbuggException) errorMessage = contextFeature.Error.Message;
                        }
                        context.Response.StatusCode = (int)HttpStatusCode.InternalServerError;
                        context.Response.ContentType = "application/json";
                        await context.Response.WriteAsync(
                                JsonConvert.SerializeObject(
                                    new ErrorResponse()
                                    {
                                        StatusCode = context.Response.StatusCode,
                                        Message = errorMessage
                                    }, 
                                    new JsonSerializerSettings { ContractResolver = new CamelCasePropertyNamesContractResolver() }
                                ));
                    });
                });
            });
        }
    }
}