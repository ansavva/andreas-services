# Humbugg

Humbugg is a holiday gift-exchange platform that helps organizers create groups, enroll participants, capture wish lists, and run secure recipient matching. The solution now consists of the API plus a lightweight React client that authenticates against AWS Cognito (IdentityServer has been removed in favor of a managed IdP).

## Projects

- **`backend/`** – Flask + PyMongo API that exposes group, member, and profile endpoints. It persists data to MongoDB, validates AWS Cognito JWTs, and implements the original GroupEngine/GroupMemberEngine logic plus matching.
- **`frontend/`** – Vite + React standalone SPA that talks directly to the API. It authenticates against AWS Cognito (resource owner password grant or pasted bearer tokens) and renders group/member dashboards without the legacy ASP.NET MVC wrapper.
- **`Wiki/`** – Docs site built with Docsify that captures operational runbooks (AWS, Docker, etc.).
- **`Deploy.ps1`** – PowerShell helpers for bundling and pushing artifacts.

## Prerequisites

Install the core tooling before building the solution (Homebrew commands for macOS):

- **.NET SDK 6+** – `brew install dotnet-sdk`
- **Node.js 18+** – `brew install node` (used by the React frontend under `frontend/`)

## Local development

Each project runs independently (API + React). Typical workflow:

1. Install the required .NET SDK (check the `.csproj` files for the target framework; currently `netcoreapp3.1`/`net5.0` style) plus Node.js 18+ (`brew install node`).
2. Start MongoDB (or point at a connection string via `MONGO_URI` in the backend config).
3. Configure an AWS Cognito User Pool + App Client. Note the user pool ID, region, hosted domain, client ID, and client secret. Set the backend environment variables (`COGNITO_*`) or `.env` accordingly.
4. Start the API:

```bash
cd backend
pip install -r requirements.txt
python src/app.py
```

5. Run the React client:

```bash
cd frontend
npm install
npm run dev
```

6. Sign in through the UI using your Cognito credentials or paste a bearer token from AWS Cognito. The SPA requests a password-grant token via the Cognito `/oauth2/token` endpoint and then talks to the API directly.

## Deployment

The API still ships with AWS Lambda entry points (`LambdaEntryPoint.cs`) and `serverless.template` definitions, so it can be published as a Lambda-backed API. The React client is static and can be deployed to S3/CloudFront (or any SPA host). Configure AWS Cognito user pool domains + app clients per environment and update the runtime environment variables accordingly.


# Savva Solutions - Documentation

## Helpful links 

- AWS Console
    - https://console.aws.amazon.com/
- A simple introduction to AWS CloudFormation Part 1: EC2 Instance 
    - https://blog.boltops.com/2017/03/06/a-simple-introduction-to-aws-cloudformation-part-1-ec2-instance
- AWS Cloud Formation Templates 
    - https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/sample-templates-services-us-west-2.html#w1ab2c21c45c15c15


## Windows Commands

- How to SSH into a EC2 instance
    - Verify you have SSH installed by typing in ssh into PS. 
    - Instructions for modify pem permissions for a pem file in windows: https://superuser.com/questions/1296024/windows-ssh-permissions-for-private-key-are-too-open
    - `ssh -i /path/my-key-pair.pem ec2-user@ec2-198-51-100-1.compute-1.amazonaws.com`
