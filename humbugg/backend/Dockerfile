FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Humbugg.Api/Humbugg.Api.csproj Humbugg.Api/
RUN dotnet restore Humbugg.Api/Humbugg.Api.csproj
COPY Humbugg.Api/ Humbugg.Api/
RUN dotnet publish Humbugg.Api/Humbugg.Api.csproj --configuration Release --output /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS development
WORKDIR /src
COPY Humbugg.Api/Humbugg.Api.csproj Humbugg.Api/
RUN dotnet restore Humbugg.Api/Humbugg.Api.csproj
COPY Humbugg.Api/ Humbugg.Api/
ENTRYPOINT ["dotnet", "watch", "--no-hot-reload", "--project", "Humbugg.Api/Humbugg.Api.csproj", "run", "--no-launch-profile"]

FROM public.ecr.aws/lambda/dotnet:10 AS final
WORKDIR ${LAMBDA_TASK_ROOT}
COPY --from=build /app/publish .
CMD ["Humbugg.Api"]
