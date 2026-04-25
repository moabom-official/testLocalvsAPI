<#
.SYNOPSIS
    Moabom Azure 리소스 전체 삭제 (과금 중지용).

.DESCRIPTION
    deploy.ps1 이 생성한 리소스 그룹을 통째로 삭제합니다.
    주의: Postgres 의 데이터도 함께 삭제됩니다.
#>

$ErrorActionPreference = 'Stop'

$RG_NAME = 'rg-moabom'

$confirm = Read-Host "리소스 그룹 '$RG_NAME' 을(를) 완전히 삭제합니다. 진행? (yes/NO)"
if ($confirm -ne 'yes') {
    Write-Host "취소됨." -ForegroundColor Yellow
    exit 0
}

Write-Host "삭제 중... (5~10분 소요, 백그라운드로 진행)" -ForegroundColor Cyan
az group delete --name $RG_NAME --yes --no-wait
Write-Host "삭제 요청 전송 완료. 'az group show -n $RG_NAME' 로 상태 확인 가능." -ForegroundColor Green
