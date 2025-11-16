Set-Location Humbugg.Api
dotnet lambda deploy-serverless

Set-Location ../Humbugg.Web
dotnet lambda deploy-serverless

Set-Location ../Humbugg.IdentityServer
dotnet lambda deploy-serverless

Set-Location ..