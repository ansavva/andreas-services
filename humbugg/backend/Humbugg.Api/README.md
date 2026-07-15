# Humbugg API

ASP.NET Core 10 API for Humbugg. Cognito owns registration and authentication;
the API accepts only Cognito access tokens for the configured secretless client.
Profiles, groups, memberships, private draws, and reveal audit events are stored
in DynamoDB.

Run from `humbugg/backend`:

```sh
dotnet test Humbugg.slnx
docker compose up --build
```

The containerized local API is available at `http://localhost:5001` and creates
the required tables in DynamoDB Local. It never connects to production tables.
