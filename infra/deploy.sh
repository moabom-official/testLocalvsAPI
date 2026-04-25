#!/usr/bin/env bash
# ============================================================
# Moabom 프로토타입 → Azure Container Apps 배포 (bash 버전)
#
# 사전 요구사항:
#   - Azure CLI 설치 (`az --version`)
#   - `az login` 완료
#   - 프로젝트 루트의 .env 가 채워져 있어야 함
#
# 사용법:
#   ./infra/deploy.sh
# ============================================================

set -euo pipefail

# --- 설정 (필요시 수정) ---
RG_NAME='rg-moabom'
LOCATION='koreacentral'
NAME_PREFIX='moabom'
APP_NAME='ca-moabom'
IMAGE_NAME='moabom-app'
IMAGE_TAG="$(date +%Y%m%d%H%M%S)"
DEPLOY_NAME='moabom-infra'

cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
gray()  { printf "\033[90m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*" >&2; }

die() { red "ERROR: $*"; exit 1; }

# URL 인코딩 (순수 bash, 외부 의존성 없음)
urlencode() {
    local s="$1" out="" c i
    for (( i=0; i<${#s}; i++ )); do
        c="${s:$i:1}"
        case "$c" in
            [a-zA-Z0-9.~_-]) out+="$c" ;;
            *) printf -v h '%%%02X' "'$c"; out+="$h" ;;
        esac
    done
    printf '%s' "$out"
}

# WSL + Windows az.exe 조합일 때 경로를 Windows 형식으로 변환
towin_path() {
    if [ -n "${WSL_DISTRO_NAME:-}" ] && command -v wslpath >/dev/null 2>&1; then
        wslpath -w "$1"
    else
        printf '%s' "$1"
    fi
}

# ============================================================
# 0. 환경 점검
# ============================================================
cyan ""
cyan "=== 0. 환경 점검 ==="

command -v az >/dev/null 2>&1 || die "Azure CLI 가 없습니다. winget install -e --id Microsoft.AzureCLI 로 설치 후 셸 재시작."

ACCOUNT_NAME="$(az account show --query name -o tsv 2>/dev/null | tr -d '\r\n' || true)"
[ -n "$ACCOUNT_NAME" ] || die "az login 필요."
ACCOUNT_ID="$(az account show --query id -o tsv | tr -d '\r\n')"
gray "  Subscription: $ACCOUNT_NAME ($ACCOUNT_ID)"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( dirname "$SCRIPT_DIR" )"
ENV_FILE="$REPO_ROOT/.env"
[ -f "$ENV_FILE" ] || die ".env 파일 없음: $ENV_FILE"

# .env 파싱
declare -A envVars
while IFS= read -r line || [ -n "$line" ]; do
    # trim leading whitespace
    line="${line#"${line%%[![:space:]]*}"}"
    [ -z "$line" ] && continue
    [[ "$line" == \#* ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    # trim trailing whitespace from key
    key="${key%"${key##*[![:space:]]}"}"
    # strip trailing CR (Windows line endings)
    value="${value%$'\r'}"
    envVars["$key"]="$value"
done < "$ENV_FILE"

for k in YOUTUBE_API_KEY GROQ_API_KEY AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY AZURE_OPENAI_DEPLOYMENT; do
    [ -n "${envVars[$k]:-}" ] || die ".env 의 $k 값이 비어있음."
done

# Postgres 비밀번호 입력 (8자+, 대/소/숫자 포함 권장, 특수문자 가능)
printf "Postgres 관리자 비밀번호 입력 (최소 8자, 대/소/숫자 포함): "
read -rs PG_PASSWORD
printf "\n"
[ ${#PG_PASSWORD} -ge 8 ] || die "비밀번호는 최소 8자."

# URL 용 인코딩 (특수문자 대비)
PG_PASSWORD_ENCODED="$(urlencode "$PG_PASSWORD")"

# ============================================================
# 1. 리소스 그룹
# ============================================================
cyan ""
cyan "=== 1. 리소스 그룹 ($RG_NAME) ==="
az group create --name "$RG_NAME" --location "$LOCATION" --output none
green "  OK"

# ============================================================
# 2. 인프라 배포 (Bicep)
# ============================================================
cyan ""
cyan "=== 2. 인프라 배포 (Bicep) — 5~10분 소요 ==="
BICEP_FILE="$(towin_path "$SCRIPT_DIR/main.bicep")"

az deployment group create \
    --resource-group "$RG_NAME" \
    --name "$DEPLOY_NAME" \
    --template-file "$BICEP_FILE" \
    --parameters \
        namePrefix="$NAME_PREFIX" \
        location="$LOCATION" \
        pgAdminPassword="$PG_PASSWORD" \
    --output none

OUT() { az deployment group show -g "$RG_NAME" -n "$DEPLOY_NAME" --query "properties.outputs.$1.value" -o tsv | tr -d '\r\n'; }
ACR_NAME="$(OUT acrName)"
ACR_LOGIN="$(OUT acrLoginServer)"
CAE_NAME="$(OUT containerAppsEnvName)"
PG_HOST="$(OUT postgresHost)"
PG_USER="$(OUT postgresUser)"
PG_DB="$(OUT postgresDatabase)"

gray "  ACR:      $ACR_LOGIN"
gray "  Postgres: $PG_HOST"

# ============================================================
# 3. Docker 이미지 서버사이드 빌드 (ACR)
# ============================================================
cyan ""
cyan "=== 3. 이미지 빌드 (az acr build) ==="
(
    cd "$REPO_ROOT"
    az acr build \
        --registry "$ACR_NAME" \
        --image "$IMAGE_NAME:$IMAGE_TAG" \
        --image "$IMAGE_NAME:latest" \
        --file Dockerfile \
        .
)
FULL_IMAGE="$ACR_LOGIN/$IMAGE_NAME:$IMAGE_TAG"
gray "  이미지: $FULL_IMAGE"

# ============================================================
# 4. Container App 생성 / 업데이트
# ============================================================
cyan ""
cyan "=== 4. Container App 배포 ==="

DATABASE_URL="postgresql://${PG_USER}:${PG_PASSWORD_ENCODED}@${PG_HOST}:5432/${PG_DB}?sslmode=require"

ACR_USER="$(az acr credential show --name "$ACR_NAME" --query username -o tsv | tr -d '\r\n')"
ACR_PASS="$(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' -o tsv | tr -d '\r\n')"

SECRETS=(
    "database-url=$DATABASE_URL"
    "youtube-api-key=${envVars[YOUTUBE_API_KEY]}"
    "groq-api-key=${envVars[GROQ_API_KEY]}"
    "azure-openai-api-key=${envVars[AZURE_OPENAI_API_KEY]}"
)

ENV_VARS=(
    "DATABASE_URL=secretref:database-url"
    "YOUTUBE_API_KEY=secretref:youtube-api-key"
    "GROQ_API_KEY=secretref:groq-api-key"
    "GROQ_MODEL=${envVars[GROQ_MODEL]:-llama-3.3-70b-versatile}"
    "AZURE_OPENAI_ENDPOINT=${envVars[AZURE_OPENAI_ENDPOINT]}"
    "AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key"
    "AZURE_OPENAI_DEPLOYMENT=${envVars[AZURE_OPENAI_DEPLOYMENT]}"
    "AZURE_OPENAI_API_VERSION=${envVars[AZURE_OPENAI_API_VERSION]:-2025-01-01-preview}"
    "PORT=8000"
)

if az containerapp show -n "$APP_NAME" -g "$RG_NAME" >/dev/null 2>&1; then
    gray "  기존 앱 업데이트..."
    az containerapp secret set \
        -n "$APP_NAME" -g "$RG_NAME" \
        --secrets "${SECRETS[@]}" \
        --output none
    az containerapp update \
        -n "$APP_NAME" -g "$RG_NAME" \
        --image "$FULL_IMAGE" \
        --set-env-vars "${ENV_VARS[@]}" \
        --output none
else
    gray "  최초 생성..."
    az containerapp create \
        -n "$APP_NAME" -g "$RG_NAME" \
        --environment "$CAE_NAME" \
        --image "$FULL_IMAGE" \
        --registry-server "$ACR_LOGIN" \
        --registry-username "$ACR_USER" \
        --registry-password "$ACR_PASS" \
        --target-port 8000 \
        --ingress external \
        --min-replicas 0 \
        --max-replicas 2 \
        --cpu 0.5 --memory 1.0Gi \
        --secrets "${SECRETS[@]}" \
        --env-vars "${ENV_VARS[@]}" \
        --output none
fi

FQDN="$(az containerapp show -n "$APP_NAME" -g "$RG_NAME" --query properties.configuration.ingress.fqdn -o tsv | tr -d '\r\n')"

green ""
green "=== 완료 ==="
printf "  URL: \033[33mhttps://%s\033[0m\n" "$FQDN"
gray "  로그: az containerapp logs show -n $APP_NAME -g $RG_NAME --follow"
