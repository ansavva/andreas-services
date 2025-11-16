# Humbugg Web

## Application Startup 
- Run `dotnet run` and navigate to localhost:4200.

## Application Deployment
- Run `dotnet lambda deploy-serverless` to deploy code into AWS Lambda
    - You may need to run this to install the AWS tools for dotnet CLI. `dotnet tool install -g Amazon.Lambda.Tools`

## Other Helpful Commands

Add a component
```
    cd ClientApp
    ng generate component components/{component_name} --module=app
```

Add service
```
    cd ClientApp
    ng generate service services/{service_name}
```

Run and watch C# code
```
    dotnet watch run --environment "Development"
```

Install Amazon.Lambda.Tools Global Tools if not already installed.
```
    dotnet tool install -g Amazon.Lambda.Tools
```

If already installed check if new version is available.
```
    dotnet tool update -g Amazon.Lambda.Tools
```

Run Mongo Local
```
     mongod.exe --dbpath="c:\mongodb\data\db"
```

## Project Files
- serverless.template - an AWS CloudFormation Serverless Application Model template file for declaring your Serverless functions and other AWS resources
- aws-lambda-tools-defaults.json - default argument settings for use with Visual Studio and command line deployment tools for AWS
- LambdaEntryPoint.cs - class that derives from **Amazon.Lambda.AspNetCoreServer.APIGatewayProxyFunction**. The code in 
this file bootstraps the ASP.NET Core hosting framework. The Lambda function is defined in the base class.
Change the base class to **Amazon.Lambda.AspNetCoreServer.ApplicationLoadBalancerFunction** when using an 
Application Load Balancer.
- LocalEntryPoint.cs - for local development this contains the executable Main function which bootstraps the ASP.NET Core hosting framework with Kestrel, as for typical ASP.NET Core applications.
- Startup.cs - usual ASP.NET Core Startup class used to configure the services ASP.NET Core will use.
