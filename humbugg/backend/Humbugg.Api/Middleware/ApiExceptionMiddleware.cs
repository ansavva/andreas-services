using Humbugg.Api.Models;

namespace Humbugg.Api.Middleware;

internal sealed class ApiExceptionMiddleware(RequestDelegate next, ILogger<ApiExceptionMiddleware> logger)
{
    public async Task InvokeAsync(HttpContext context)
    {
        try { await next(context); }
        catch (ApiException exception) { await WriteAsync(context, exception.StatusCode, exception.Code, exception.Message); }
        catch (Exception exception)
        {
            logger.LogError(exception, "Unhandled Humbugg API exception");
            await WriteAsync(context, 500, "internal_error", "Humbugg could not complete this request.");
        }
    }

    private static async Task WriteAsync(HttpContext context, int status, string code, string message)
    {
        context.Response.StatusCode = status;
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsJsonAsync(new { error = new { code, message } });
    }
}
