<#
.SYNOPSIS
    Moabom 프로토타입을 Azure Container Apps 에 배포.

.DESCRIPTION
    1) 리소스 그룹 / Postgres / ACR / Log Analytics / Container Apps Env 배포 (Bicep)
    2) ACR 에서 서버사이드 이미지 빌드 (로컬 Docker 불필요)
    3) Container App 생성 또는 업데이트 (.env 의 API 키들을 secret 으로 주입)

.EXAMPLE
    .\infra\deploy.ps1

.NOTES
    사전 요구사항:
      - Azure CLI 설치 & `az login` 완료
      - 활성 subscription 선택: `az account set --subscription <id>`
      - 프로젝트 루트에 .env 가 채워져 있어야 함
#>

$ErrorActionPreference = 'Stop'

# ============================================================
# 설정 (필요시 수정)
# ============================================================
$RG_NAME      = 'rg-moabom'
$LOCATION     = 'koreacentral'
$NAME_PREFIX  = 'moabom'
$APP_NAME     = 'ca-moabom'
$IMAGE_NAME   = 'moabom-app'
$IMAGE_TAG    = Get-Date -Format 'yyyyMMddHHmmss'

# ============================================================
# 0. 환경 점검
# ============================================================
Write-Host "`n=== 0. 환경 점검 ===" -ForegroundColor Cyan

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI 가 설치되지 않았습니다. https://aka.ms/installazurecliwindows"
}

$account = az account show --output json 2>$null | ConvertFrom-Json
if (-not $account) {
    throw "az login 이 필요합니다. 터미널에서 'az login' 실행 후 다시 시도하세요."
}
Write-Host "  Subscription: $($account.name) ($($account.id))" -ForegroundColor Gray

$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile  = Join-Path $repoRoot '.env'
if (-not (Test-Path $envFile)) {
    throw ".env 파일을 찾을 수 없습니다: $envFile"
}

# .env 파싱
$envVars = @{}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $k, $v = $line -split '=', 2
        $envVars[$k.Trim()] = $v.Trim()
    }
}

$required = @('YOUTUBE_API_KEY', 'GROQ_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_DEPLOYMENT')
foreach ($key in $required) {
    if (-not $envVars.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($envVars[$key])) {
        throw ".env 에 $key 값이 비어있습니다."
    }
}

# Postgres 비밀번호 (처음엔 입력, 이후엔 기존 서버를 사용)
$pgPassword = Read-Host "Postgres 관리자 비밀번호 입력 (최소 8자, 대/소/숫자 포함)" -AsSecureString
$pgPasswordPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgPassword)
)

# ============================================================
# 1. 리소스 그룹
# ============================================================
Write-Host "`n=== 1. 리소스 그룹 ($RG_NAME) ===" -ForegroundColor Cyan
az group create --name $RG_NAME --location $LOCATION --output none
Write-Host "  OK" -ForegroundColor Green

# ============================================================
# 2. 인프라 배포 (Bicep)
# ============================================================
Write-Host "`n=== 2. 인프라 배포 (Bicep) — 5~10분 소요 ===" -ForegroundColor Cyan
$bicepFile = Join-Path $PSScriptRoot 'main.bicep'

$deployResult = az deployment group create `
    --resource-group $RG_NAME `
    --template-file $bicepFile `
    --parameters namePrefix=$NAME_PREFIX `
                 location=$LOCATION `
                 pgAdminPassword=$pgPasswordPlain `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) { throw "Bicep 배포 실패" }

$outputs         = $deployResult.properties.outputs
$ACR_NAME        = $outputs.acrName.value
$ACR_LOGIN       = $outputs.acrLoginServer.value
$CAE_NAME        = $outputs.containerAppsEnvName.value
$PG_HOST         = $outputs.postgresHost.value
$PG_USER         = $outputs.postgresUser.value
$PG_DB           = $outputs.postgresDatabase.value

Write-Host "  ACR:      $ACR_LOGIN" -ForegroundColor Gray
Write-Host "  Postgres: $PG_HOST" -ForegroundColor Gray

# ============================================================
# 3. ACR 서버사이드 빌드 & 푸시
# ============================================================
Write-Host "`n=== 3. Docker 이미지 빌드 (Azure 내부에서 수행) ===" -ForegroundColor Cyan
Push-Location $repoRoot
try {
    az acr build `
        --registry $ACR_NAME `
        --image "$($IMAGE_NAME):$IMAGE_TAG" `
        --image "$($IMAGE_NAME):latest" `
        --file Dockerfile `
        .
    if ($LASTEXITCODE -ne 0) { throw "az acr build 실패" }
} finally {
    Pop-Location
}

$fullImage = "$ACR_LOGIN/$($IMAGE_NAME):$IMAGE_TAG"
Write-Host "  이미지: $fullImage" -ForegroundColor Gray

# ============================================================
# 4. Container App 생성 또는 업데이트
# ============================================================
Write-Host "`n=== 4. Container App 배포 ===" -ForegroundColor Cyan

$databaseUrl = "postgresql://$($PG_USER):$($pgPasswordPlain)@$($PG_HOST):5432/$($PG_DB)?sslmode=require"

$acrCreds = az acr credential show --name $ACR_NAME --output json | ConvertFrom-Json
$acrUser  = $acrCreds.username
$acrPass  = $acrCreds.passwords[0].value

$existingApp = az containerapp show --name $APP_NAME --resource-group $RG_NAME --output json 2>$null

# secrets 문자열 구성 (공백/특수문자 대응을 위해 배열로)
$secrets = @(
    "database-url=$databaseUrl"
    "youtube-api-key=$($envVars['YOUTUBE_API_KEY'])"
    "groq-api-key=$($envVars['GROQ_API_KEY'])"
    "azure-openai-api-key=$($envVars['AZURE_OPENAI_API_KEY'])"
    "acr-password=$acrPass"
)

$envMappings = @(
    'DATABASE_URL=secretref:database-url'
    'YOUTUBE_API_KEY=secretref:youtube-api-key'
    'GROQ_API_KEY=secretref:groq-api-key'
    "GROQ_MODEL=$($envVars['GROQ_MODEL'])"
    "AZURE_OPENAI_ENDPOINT=$($envVars['AZURE_OPENAI_ENDPOINT'])"
    'AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key'
    "AZURE_OPENAI_DEPLOYMENT=$($envVars['AZURE_OPENAI_DEPLOYMENT'])"
    "AZURE_OPENAI_API_VERSION=$($envVars['AZURE_OPENAI_API_VERSION'])"
    'PORT=8000'
)

if (-not $existingApp) {
    Write-Host "  최초 생성 중..." -ForegroundColor Gray
    az containerapp create `
        --name $APP_NAME `
        --resource-group $RG_NAME `
        --environment $CAE_NAME `
        --image $fullImage `
        --registry-server $ACR_LOGIN `
        --registry-username $acrUser `
        --registry-password $acrPass `
        --target-port 8000 `
        --ingress external `
        --min-replicas 0 `
        --max-replicas 2 `
        --cpu 0.5 --memory 1.0Gi `
        --secrets $secrets `
        --env-vars $envMappings `
        --output none
} else {
    Write-Host "  기존 앱 업데이트..." -ForegroundColor Gray
    az containerapp secret set `
        --name $APP_NAME --resource-group $RG_NAME `
        --secrets $secrets --output none
    az containerapp update `
        --name $APP_NAME --resource-group $RG_NAME `
        --image $fullImage `
        --set-env-vars $envMappings `
        --output none
}
if ($LASTEXITCODE -ne 0) { throw "Container App 배포 실패" }

$fqdn = az containerapp show --name $APP_NAME --resource-group $RG_NAME `
    --query properties.configuration.ingress.fqdn --output tsv

Write-Host "`n=== 완료 ===" -ForegroundColor Green
Write-Host "  URL: https://$fqdn" -ForegroundColor Yellow
Write-Host "  로그 보기: az containerapp logs show -n $APP_NAME -g $RG_NAME --follow" -ForegroundColor Gray
