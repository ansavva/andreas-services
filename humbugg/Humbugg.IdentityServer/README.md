# Humbugg Identity Server

## Setup Instructions

- Followed instructions from here https://www.scottbrady91.com/Identity-Server/Getting-Started-with-IdentityServer-4 for setting up a basic IdentityServer 4 setup
    - Run `dotnet new web` to create an empty IdentityServer web project
    - Run `dotnet add package IdentityServer4` to install IdentityServer as a nuget package. 
    - Add in memory configurations inside Config.cs for in memory Clients, IdentityResources, ApiResources, ApiScopes, and TestUsers. 
    - Startup IdentityServer 4 using `dotnet run` and verify you can get an access token using OAuth client. 
    - Add UI using https://github.com/IdentityServer/IdentityServer4.Quickstart.UI command `iex ((New-Object System.Net.WebClient).DownloadString('https://raw.githubusercontent.com/IdentityServer/IdentityServer4.Quickstart.UI/main/getmain.ps1'))`.
    - Configure dotnet application to startup MVC.

- Setup MongoDB (online insturctions lost)
    - Add MongoDB as a nuget package `dotnet add package MongoDB.Driver`.
    - Create `Profile` and `BaseModel` model classes in Models directory for MongoDB Profile retrieval. 
    - Create `BaseRepository`, `DatabaseSettings` and `ProfileRepository` for MongoDB database retrieval. 
    - Create `DatabaseSettings` configuration in appsettings.json file.
    - Register services in dotnet DI for `ProfileRepository`. 

- Setup Serilog
    - Add Serilog as nuget package `dotnet add package Serilog.AspNetCore`.
    - Configure appsettings.json to log to MongoDB logs database.

- Configure IdentityServer4 quickstart to work with MongoDB 
    - Create `ProfileService` in services directory for retrieving user Profiles from MongoDB using `IProfileRepository`.
    - Create `ClaimsService` in services directory for building user claims based on Profile data stored in MongoDB. 
    - Create `Extensions` class in services directory to handle hashing a user's stored password.
    - Create `LoginService` in services directory to handle validating a user credentials, finding a user by username, and creating a new profile in the MongoDB database with a salt and password. 
    - Create `ResourceOwnerPasswordValidator` class in services directory to handle validating a user based grant type `/conect/token` utilizing MongoDB data. 
    - Register `IProfileService` and `IResourceOwnerPasswordValidator` and `ILoginService` in dotnet DI.
    - Add `ProfileService` to be used by IdentityServer. 
    - Add `ResourceOwnerPasswordValidator` to be used by IdentityServer.
    - Configure Quickstart `AccountController` and `ExternalController` to utilize `IUserService` to retrieve `Profile` in place of hard coded `TestUser` data. 

- Add work around for Chrome SameSite Cookie restriction
    - https://www.thinktecture.com/en/identity/samesite/prepare-your-identityserver/
    - https://community.abp.io/articles/patch-for-chrome-login-issue-identityserver4-samesite-cookie-problem-weypwp3n

- Configure resources for Humbugg Web implicit flow
    - Configure Clients to allow for implicit flow with redirect URLs for oidc-client URLs in Humbugg Web
    - Add app configurations in JSON for handling Humbugg Web client URLs in different environments
    - Enable Cors for local environment since we have different domains

- Configure resources for Humbugg Api
    - Add Humbugg Api Read and Write scopes to control read and write access to the api for client application.

- Configure IdentityServer4 to allow Google and Facebook login
    - Add Facebook external login https://docs.microsoft.com/en-us/aspnet/core/security/authentication/social/facebook-logins?view=aspnetcore-3.1 
    - Add Facebook Authentication nuget package `dotnet add package Microsoft.AspNetCore.Authentication.Facebook`
    - Add Facebook Api ID and App Secret for develop and production
    - Add Google external login https://docs.microsoft.com/en-us/aspnet/core/security/authentication/social/google-logins?view=aspnetcore-3.1
    - ADd Google Authentication nuget package `dotnet add package Microsoft.AspNetCore.Authentication.Google`
    - Add Google Api ID and App Secret for develop and production
    - Add Logic to handle external provider Profile creation and conflict handling

- Add serverless.template and LambdaEntryPoint class to configure IdentityServer to run inside of AWS Lambda.
    - Install nuget package for AWS Lambda Dotnet Core 3.1 `dotnet add package Amazon.Lambda.AspNetCoreServer --version 5.1.6`

- Generate and install signing-certificate for Identity Server
    - http://amilspage.com/signing-certificates-idsv4/

- Add AWS SSM as Data Protection Provider 
    - https://aws.amazon.com/blogs/developer/aws-ssm-asp-net-core-data-protection-provider/
    - By default ASP.Net Core creates data protect keys in memory. This nuget package allows us to share data protection keys between servers (Lambda Functions) in a "load balanced" environment. `dotnet add pacakge Amazon.AspNetCore.DataProtection.SSM`

- Add Health Check Endpoint
    - https://docs.microsoft.com/en-us/aspnet/core/host-and-deploy/health-checks?view=aspnetcore-3.1

## Application Startup 
- Run `dotnet run` and navigate to localhost:5000. 
    - You can see the OpenID confgiruation for IdentityServer 4 here: `http://localhost:5000/.well-known/openid-configuration`. 

## Application Deployment
- Run `dotnet lambda deploy-serverless` to depoyment code into AWS Lambda
    - You may need to run this to install the AWS tools for dotnet CLI. `dotnet tool install -g Amazon.Lambda.Tools`