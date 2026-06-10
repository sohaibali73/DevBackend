# Azure Deployment Guide

Provisions and deploys the full stack into the existing resource group
**`PFM-RG-AI_Apps-Dev`** (subscription `PFM-AI-Apps-Dev`, region `eastus`).

## Prerequisites (one-time, needs an admin)

Resource-provider registration is a **subscription-level** action — ask whoever
has Owner/subscription-Contributor to run:

```bash
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.DBforPostgreSQL
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.OperationalInsights
```

You (resource-group Contributor) can do everything below once those are registered.

## 1. Build & push images (no Azure permissions needed)

```bash
# backend (from DevBackend/)
docker build -t ghcr.io/sohaibali73/potomac-backend:latest .
docker push ghcr.io/sohaibali73/potomac-backend:latest

# frontend (from AnalystDevelopmentFrontEnd/)
docker build --build-arg NEXT_PUBLIC_API_URL=https://PLACEHOLDER -t ghcr.io/sohaibali73/analyst-frontend:latest .
docker push ghcr.io/sohaibali73/analyst-frontend:latest
```

(If the ghcr packages are private, set `registryUsername` + `registryPassword`
— a GitHub PAT with `read:packages` — in the parameters file.)

## 2. Fill in secrets

Edit `infra/main.parameters.json` and set: `pgAdminPassword`, `secretKey`
(`python -c "import secrets;print(secrets.token_urlsafe(48))"`), `encryptionKey`,
and the LLM API keys.

## 3. Deploy infrastructure

```bash
az deployment group create \
  -g PFM-RG-AI_Apps-Dev \
  -f infra/main.bicep \
  -p @infra/main.parameters.json
```

Outputs include `backendUrl`, `frontendUrl`, `postgresFqdn`, `storageAccount`.

## 4. Apply database migrations

```bash
# DATABASE_URL = the postgres connection string (see deployment output / portal)
export DATABASE_URL='postgresql://pfmadmin:<pw>@<postgresFqdn>:5432/potomac?sslmode=require'
python scripts/apply_migrations.py
```

This runs `000_azure_bootstrap.sql` (Supabase-compat shim) first, then the
historical migrations, then `035_azure_selfhosted_auth.sql`.

## 5. Point the frontend at the backend

The Bicep already injects `NEXT_PUBLIC_API_URL` into the frontend app from the
backend FQDN. If you rebuilt the frontend image with a placeholder, redeploy the
frontend container app (the env var is read at runtime by server components; for
fully-static public usage rebuild with the real `--build-arg`).

## Notes
- **Redis** is intentionally omitted — the app falls back to an in-process cache.
- **Secrets** live as Container App secrets (no Key Vault required).
- **Backend runs as a single replica** (min=max=1) because the scheduler +
  in-memory task manager must not double-fire. Scale the frontend freely.
- Blob access uses the user-assigned **Managed Identity** (no storage keys in
  app config).
