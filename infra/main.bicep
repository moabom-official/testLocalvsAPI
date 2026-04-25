// ============================================================================
// Moabom - Azure 인프라 (ACR + Postgres + Log Analytics + Container Apps Env)
// ----------------------------------------------------------------------------
// 이 템플릿은 "인프라"만 배포합니다. Container App 자체는 이미지가 푸시된 이후
// deploy.ps1 에서 CLI 로 생성/업데이트합니다.
// ============================================================================

@description('리소스 공통 접두사 (소문자, 영숫자, 5~11자). 예: moabom')
@minLength(5)
@maxLength(11)
param namePrefix string = 'moabom'

@description('모든 리소스 배포 지역')
param location string = resourceGroup().location

@description('Postgres 관리자 계정명')
param pgAdminUser string = 'moabomadmin'

@secure()
@description('Postgres 관리자 비밀번호 (배포 시 주입)')
param pgAdminPassword string

@description('Postgres 초기 DB 이름')
param pgDatabaseName string = 'techdb'

// ---------- Azure Container Registry ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: '${namePrefix}acr${uniqueString(resourceGroup().id)}'
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// ---------- Log Analytics ----------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${namePrefix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ---------- Container Apps Environment ----------
resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${namePrefix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ---------- Postgres Flexible Server (Burstable B1ms — 가장 싼 티어) ----------
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: 'psql-${namePrefix}-${uniqueString(resourceGroup().id)}'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '15'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    storage: {
      storageSizeGB: 32
      autoGrow: 'Disabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

// Azure 내부 서비스(= Container Apps) 가 Postgres 에 접속 가능하도록 허용
resource pgFirewallAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: pgDatabaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// ---------- Outputs (deploy.ps1 에서 사용) ----------
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output containerAppsEnvId string = containerAppsEnv.id
output containerAppsEnvName string = containerAppsEnv.name
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output postgresUser string = pgAdminUser
output postgresDatabase string = pgDatabaseName
