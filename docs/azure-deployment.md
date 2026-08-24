# Azure deployment

The production workflow publishes the pipeline image to Azure Container
Registry and updates an Azure Container Apps scheduled job after a commit is
merged into `main`.

The workflow is intentionally disabled until the Azure infrastructure and OIDC
trust are configured. Enable it only after a manual test execution succeeds.

## Runtime architecture

```text
GitHub main
    |
    v
GitHub Actions --OIDC--> Microsoft Entra ID
    |
    +--> Azure Container Registry
    |
    +--> Azure Container Apps Job --DATABASE_URL--> Azure Database for PostgreSQL
                  |
                  +--> Log Analytics
```

The Container Apps job must keep the image entry point and pass `ingest` as its
command argument. Store `DATABASE_URL` as a Container Apps secret; do not store
database credentials in GitHub.

## Required GitHub configuration

Create a GitHub environment named `production`. Define
`AZURE_DEPLOY_ENABLED` as a repository variable because GitHub evaluates the job
condition before loading environment-level variables. The remaining values may
be repository or `production` environment variables:

| Variable | Purpose |
| --- | --- |
| `AZURE_DEPLOY_ENABLED` | Set to `true` only after setup is complete |
| `AZURE_CLIENT_ID` | Client ID trusted through GitHub OIDC |
| `AZURE_TENANT_ID` | Microsoft Entra tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target Azure subscription |
| `AZURE_RESOURCE_GROUP` | Resource group containing the job |
| `AZURE_ACR_NAME` | Azure Container Registry resource name |
| `AZURE_ACR_LOGIN_SERVER` | Registry host, for example `registry.azurecr.io` |
| `AZURE_IMAGE_NAME` | Container image repository name |
| `AZURE_CONTAINER_APP_JOB` | Existing Container Apps job name |

Configure the federated credential for this GitHub subject:

```text
repo:danMants/property-data-pipeline:environment:production
```

Grant the identity only the permissions needed to push to the selected registry
and update/start the selected Container Apps job.

## Activation checklist

1. Create Azure Database for PostgreSQL, Container Registry, a Container Apps
   environment, and a scheduled Container Apps job.
2. Configure the job command as `ingest`, add its `DATABASE_URL` secret, and run
   the job manually.
3. Configure the GitHub OIDC federated identity and least-privilege Azure roles.
4. Add the variables listed above to GitHub.
5. Set `AZURE_DEPLOY_ENABLED=true` last.
6. Run the `Deploy to Azure` workflow manually once before relying on its
   automatic `main` trigger.
