#!/usr/bin/env bash
# Moabom Azure 리소스 전체 삭제 (과금 중지용)
# 주의: Postgres 데이터도 함께 삭제됨.

set -euo pipefail

RG_NAME='rg-moabom'

printf "리소스 그룹 '%s' 을(를) 완전히 삭제합니다. 진행? (yes/NO): " "$RG_NAME"
read -r confirm
[ "$confirm" = "yes" ] || { echo "취소됨."; exit 0; }

echo "삭제 요청 전송 중 (백그라운드 진행, 5~10분 소요)..."
az group delete --name "$RG_NAME" --yes --no-wait
echo "완료. 상태 확인: az group show -n $RG_NAME"
