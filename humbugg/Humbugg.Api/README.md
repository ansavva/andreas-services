# Humbugg API

## Setup Instructions
- Create New Web Api Application.
    - Run `dotnet new webapi` to createa  new web api application.

- Configuration Web Api application work with IdentityServer4.
    - Add JWET Bearer Token Authentication Nuget Package to web api `dotnet add package Microsoft.AspNetCore.Authentication.JwtBearer`.
    - Configure Startup application to enable JWT Bearer Authentication.
    - Add MongoDB as a nuget package `dotnet add package MongoDB.Driver`.
    - Add appsettings for MongoDB and Authentication IdentityServer4. 
    - Add Database repository to retrieve logged in user profile.
    - Create ProfileService to access Profile Repository
    - Create IUser service to provide access to JWT Claims and User Profile. 

- Add Health Check Endpoint
    - https://docs.microsoft.com/en-us/aspnet/core/host-and-deploy/health-checks?view=aspnetcore-3.1

- Add serverless.template and LambdaEntryPoint class to configure IdentityServer to run inside of AWS Lambda.
    - Install nuget package for AWS Lambda Dotnet Core 3.1 `dotnet add package Amazon.Lambda.AspNetCoreServer --version 5.1.6`

- Setup Serilog
    - Add Serilog as nuget package `dotnet add package Serilog.AspNetCore`.
    - Configure appsettings.json to log to MongoDB logs database.

- Add AWS SSM as Data Protection Provider 
    - https://aws.amazon.com/blogs/developer/aws-ssm-asp-net-core-data-protection-provider/
    - By default ASP.Net Core creates data protect keys in memory. This nuget package allows us to share data protection keys between servers (Lambda Functions) in a "load balanced" environment. `dotnet add pacakge Amazon.AspNetCore.DataProtection.SSM`

## Application Startup 
- Run `dotnet run` and navigate to localhost:5050.

## Application Deployment
- Run `dotnet lambda deploy-serverless` to depoyment code into AWS Lambda
    - You may need to run this to install the AWS tools for dotnet CLI. `dotnet tool install -g Amazon.Lambda.Tools`