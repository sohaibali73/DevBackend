// ============================================================================
// Azure infrastructure for the Potomac stack (backend + frontend).
// Deploys into an EXISTING resource group (PFM-RG-AI_Apps-Dev):
//   az deployment group create -g PFM-RG-AI_Apps-Dev -f infra/main.bicep -p @infra/main.parameters.json
//
// Provisions: Log Analytics, Container Apps Environment, PostgreSQL Flexible
// Server (+ pgvector), Storage (Blob containers + File share), a user-assigned
// Managed Identity (Blob Data Contributor), and the backend + frontend
// Container Apps.
// ============================================================================

@description('Azure region for most resources')
param location string = resourceGroup().location

@description('Region for PostgreSQL (some subscriptions are offer-restricted in the primary region; override if needed)')
param pgLocation string = location

@description('PostgreSQL server name (override to avoid name/location collisions from a prior failed deploy)')
param pgServerName string = '${namePrefix}-pg'

@description('Prefix for resource names (lowercase, <= 11 chars)')
param namePrefix string = 'pfmai'

@description('Container image for the backend, e.g. ghcr.io/sohaibali73/potomac-backend:latest')
param backendImage string

@description('Container image for the frontend, e.g. ghcr.io/sohaibali73/analyst-frontend:latest')
param frontendImage string

@description('Container registry server (e.g. ghcr.io)')
param registryServer string = 'ghcr.io'
param registryUsername string = ''
@secure()
param registryPassword string = ''

@description('PostgreSQL admin login + password')
param pgAdminUser string = 'pfmadmin'
@secure()
param pgAdminPassword string

@description('JWT signing secret (python -c "import secrets;print(secrets.token_urlsafe(48))")')
@secure()
param secretKey string

@description('AES key for encrypting user API keys at rest')
@secure()
param encryptionKey string

@description('Map of sensitive ENV_NAME -> value (API keys, etc). Each becomes a Container App secret + env var.')
@secure()
param appSecrets object = {}

@description('Map of non-sensitive ENV_NAME -> value (flags, pool sizes, etc).')
param appEnv object = {}

param adminEmails string = ''

@description('uvicorn worker count')
param webConcurrency string = '2'

var pgDbName = 'potomac'
var storageAccountName = toLower('${namePrefix}stg${uniqueString(resourceGroup().id)}')
var blobContainers = [ 'user-uploads', 'presentations', 'brain-docs', 'skills-bundles' ]

// Turn the appSecrets map into Container App secrets + env entries.
// Secret names must be lowercase alphanumeric/'-'; derive from the env name.
var appSecretItems = items(appSecrets)
var appSecretDefs = [for s in appSecretItems: {
  name: toLower(replace(s.key, '_', '-'))
  value: s.value
}]
var appSecretEnv = [for s in appSecretItems: {
  name: s.key
  secretRef: toLower(replace(s.key, '_', '-'))
}]
var appPlainEnv = [for e in items(appEnv): {
  name: e.key
  value: e.value
}]

// ── Observability ────────────────────────────────────────────────────────────
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: { retentionInDays: 30, sku: { name: 'PerGB2018' } }
}

// ── Storage: account + blob containers + file share ───────────────────────────
resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: { allowBlobPublicAccess: false, minimumTlsVersion: 'TLS1_2' }
}

resource blobSvc 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = [for c in blobContainers: {
  parent: blobSvc
  name: c
}]

resource fileSvc 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

resource dataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileSvc
  name: 'potomac-data'
  properties: { shareQuota: 100 }
}

// Storage connection string (used by the backend to reach Blob). Using a key
// here instead of Managed Identity avoids needing role-assignment rights, so the
// whole deployment works with plain resource-group Contributor.
var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

// ── PostgreSQL Flexible Server ─────────────────────────────────────────────────
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: pgServerName
  location: pgLocation
  sku: { name: 'Standard_B2ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7 }
    highAvailability: { mode: 'Disabled' }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: pg
  name: pgDbName
}

// Allow other Azure services (Container Apps) to reach Postgres.
resource pgFwAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: pg
  name: 'AllowAllAzure'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// Allow-list the pgvector + citext + pgcrypto extensions so migration 000 can CREATE them.
resource pgExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-06-01-preview' = {
  parent: pg
  name: 'azure.extensions'
  properties: { value: 'VECTOR,CITEXT,PGCRYPTO,UUID-OSSP,PG_TRGM', source: 'user-override' }
}

// ── Container Apps Environment ─────────────────────────────────────────────────
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// Mount the Azure Files share into the environment for the disk tier (STORAGE_ROOT).
resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'potomac-data'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: dataShare.name
      accessMode: 'ReadWrite'
    }
  }
}

var dbUrl = 'postgresql://${pgAdminUser}:${pgAdminPassword}@${pg.properties.fullyQualifiedDomainName}:5432/${pgDbName}?sslmode=require'

var registrySecrets = empty(registryPassword) ? [] : [
  { name: 'registry-password', value: registryPassword }
]
var registryConfig = empty(registryPassword) ? [] : [
  { server: registryServer, username: registryUsername, passwordSecretRef: 'registry-password' }
]

// ── Backend Container App ──────────────────────────────────────────────────────
resource backend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-backend'
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      registries: registryConfig
      secrets: concat(registrySecrets, [
        { name: 'database-url', value: dbUrl }
        { name: 'secret-key', value: secretKey }
        { name: 'encryption-key', value: encryptionKey }
        { name: 'storage-connection-string', value: storageConnectionString }
      ], appSecretDefs)
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: { cpu: json('2.0'), memory: '4Gi' }
          // Apply DB migrations on startup (idempotent; single replica) then serve.
          command: [ '/bin/sh' ]
          args: [ '-c', 'python scripts/apply_migrations.py || true; exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${webConcurrency}' ]
          env: concat([
            { name: 'ENVIRONMENT', value: 'production' }
            { name: 'PORT', value: '8000' }
            { name: 'STORAGE_ROOT', value: '/data' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'SECRET_KEY', secretRef: 'secret-key' }
            { name: 'ENCRYPTION_KEY', secretRef: 'encryption-key' }
            { name: 'ADMIN_EMAILS', value: adminEmails }
            { name: 'AZURE_STORAGE_CONNECTION_STRING', secretRef: 'storage-connection-string' }
            { name: 'AZURE_STORAGE_USE_MANAGED_IDENTITY', value: 'false' }
          ], appPlainEnv, appSecretEnv)
          volumeMounts: [ { volumeName: 'data', mountPath: '/data' } ]
        }
      ]
      // min=max=1: the in-memory task manager + yang_autopilot scheduler must
      // run as a single warm instance (avoids double-firing scheduled jobs).
      scale: { minReplicas: 1, maxReplicas: 1 }
      volumes: [ { name: 'data', storageType: 'AzureFile', storageName: envStorage.name } ]
    }
  }
}

// ── Frontend Container App ─────────────────────────────────────────────────────
resource frontend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-frontend'
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 3000, transport: 'auto', allowInsecure: false }
      registries: registryConfig
      secrets: registrySecrets
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'NODE_ENV', value: 'production' }
            { name: 'PORT', value: '3000' }
            { name: 'NEXT_PUBLIC_API_URL', value: 'https://${backend.properties.configuration.ingress.fqdn}' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

output backendUrl string = 'https://${backend.properties.configuration.ingress.fqdn}'
output frontendUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'
output postgresFqdn string = pg.properties.fullyQualifiedDomainName
output storageAccount string = storage.name
