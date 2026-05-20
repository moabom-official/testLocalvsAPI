"""백그라운드 자동 분석 태스크 (외부 카드 [예] 클릭 시 발동).

★ 두 Agent 코드 무변경 — 기존 라우트 `POST /select-videos` ·
  `POST /integrated-insight` 를 *HTTP 로 호출만* 한다.
★ MVP 한계: 메모리 dict 상태. 서버 재시작 시 진행 정보 손실 — 폴링이 404
  를 받으면 프론트는 진행 표시 자연 숨김.
★ 동시 진행 1개 — 새 시작 전 _ACTIVE_COUNT 검사. 진행 중이면 호출부가 409
  HTTP 응답으로 거절.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 메모리 상태 ───────────────────────────────────────────────────
_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = asyncio.Lock()
_DEFAULT_LOCAL_BASE = f"http://127.0.0.1:{os.getenv('PORT', '8000')}"


def _new_task_state(task_id: str, product_id: int, name: str) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "product_id": product_id,
        "name": name,
        "stage": "queued",        # queued | selecting_videos | generating_insight
        "status": "running",       # running | completed | failed | cancelled
        "error": None,
        "cancel": False,
    }


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    t = _TASKS.get(task_id)
    if not t:
        return None
    # 외부 노출 dict — cancel 플래그는 내부용
    return {
        "task_id": t["task_id"],
        "product_id": t["product_id"],
        "name": t.get("name"),
        "stage": t.get("stage"),
        "status": t.get("status"),
        "error": t.get("error"),
    }


def request_cancel(task_id: str) -> bool:
    """취소 플래그 set. 다음 단계 진입 직전에 BG 함수가 확인."""
    t = _TASKS.get(task_id)
    if not t:
        return False
    if t.get("status") not in ("running",):
        return False
    t["cancel"] = True
    return True


def is_any_running() -> bool:
    return any(t.get("status") == "running" for t in _TASKS.values())


async def _post_select_videos(product_id: int, base_url: str) -> None:
    """기존 POST /products/{id}/select-videos — auto 모드, 합리적 기본값."""
    import httpx

    payload = {
        "mode": "auto",
        "k": 5,
        "candidate_pool_size": 30,
        "process_comments": True,
    }
    # 영상 선정 + 댓글 분석 — 5분 이상 걸릴 수 있음. timeout 넉넉히.
    async with httpx.AsyncClient(timeout=600.0) as client:
        r = await client.post(
            f"{base_url}/products/{product_id}/select-videos",
            json=payload,
        )
        r.raise_for_status()


async def _post_integrated_insight(product_id: int, base_url: str) -> None:
    """기존 POST /products/{id}/integrated-insight — 영상 선정 결과 활용.

    엔드포인트가 video_ids 를 명시 요구하므로, 직전에 선정된 영상을 DB에서
    꺼내 그대로 전달.
    """
    import httpx

    from scripts.database.queries import query_all

    video_rows = query_all(
        "SELECT video_id FROM videos WHERE product_id = %s ORDER BY view_count DESC",
        (product_id,),
    ) or []
    video_ids = [r["video_id"] for r in video_rows]
    if not video_ids:
        raise RuntimeError("선정된 영상이 없어 인사이트 생성을 진행할 수 없습니다.")

    payload = {"video_ids": video_ids}
    async with httpx.AsyncClient(timeout=600.0) as client:
        r = await client.post(
            f"{base_url}/products/{product_id}/integrated-insight",
            json=payload,
        )
        r.raise_for_status()


async def _run_pipeline(task_id: str, base_url: str) -> None:
    t = _TASKS[task_id]
    product_id = t["product_id"]
    try:
        if t["cancel"]:
            t["status"] = "cancelled"
            return
        t["stage"] = "selecting_videos"
        await _post_select_videos(product_id, base_url)

        if t["cancel"]:
            t["status"] = "cancelled"
            return
        t["stage"] = "generating_insight"
        await _post_integrated_insight(product_id, base_url)

        t["status"] = "completed"
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 상태 기록 후 종료
        logger.warning("[bg_task] %s failed: %s", task_id, e)
        t["status"] = "failed"
        t["error"] = str(e)


async def start_task(
    product_id: int,
    name: str,
    *,
    base_url: Optional[str] = None,
) -> Optional[str]:
    """동시성 검사 + 신규 태스크 큐 적재. 진행 중이면 None 반환(409 신호).

    base_url: 기본은 PORT 환경변수 기반 localhost. 단위 테스트에서 주입 가능.
    """
    async with _LOCK:
        if is_any_running():
            return None
        task_id = uuid.uuid4().hex
        _TASKS[task_id] = _new_task_state(task_id, product_id, name)
    # 비동기 백그라운드 실행 — await 하지 않음
    asyncio.create_task(
        _run_pipeline(task_id, base_url or _DEFAULT_LOCAL_BASE)
    )
    return task_id
