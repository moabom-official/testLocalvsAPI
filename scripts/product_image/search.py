"""Serper Google Images 검색 (Phase 3 단계 1).

Serper 는 단순 HTTP/JSON API — API 키를 X-API-KEY 헤더에 넣고 쿼리를 POST.
무거운 SDK 없이 기존 requests 로 호출. 구글 Custom Search/CSE/CX 미사용.
요청/응답 필드는 Serper 공식 문서(google.serper.dev/images) 기준.
"""
from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, List, Tuple


def build_query(name: str, brand: str = "", suffix: str = None) -> str:
    """제품 단독 사진을 유도하는 검색 쿼리 (순수 — suffix 주입 시 config 불필요)."""
    if suffix is None:
        from scripts.config import PRODUCT_IMAGE_QUERY_SUFFIX
        suffix = PRODUCT_IMAGE_QUERY_SUFFIX

    base = (name or "").strip()
    b = (brand or "").strip()
    # brand 가 name 에 이미 포함돼 있으면 중복 회피
    if b and b.lower() not in base.lower():
        base = f"{b} {base}"
    return f"{base} {suffix}".strip()


def serper_image_search(query: str, num: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Serper Google Images 호출 → 정규화된 후보 리스트.

    반환: (candidates, perf). candidate = {image_url, title, source,
    domain, link, width, height, thumbnail, position}.
    예외(타임아웃·rate limit·네트워크)는 호출부(collector)가 안전 퇴화로
    처리하도록 그대로 raise — 단, 키 부재는 빈 결과로 안전 처리.
    """
    import requests  # 지연 import (오프라인/순수 경로 보호)

    from scripts.config import SERPER_API_KEY, SERPER_IMAGES_ENDPOINT

    perf: Dict[str, Any] = {"query": query, "num_requested": num,
                            "received": 0, "ms": 0.0}
    if not SERPER_API_KEY:
        perf["error"] = "no_serper_key"
        return [], perf

    t0 = perf_counter()
    resp = requests.post(
        SERPER_IMAGES_ENDPOINT,
        headers={"X-API-KEY": SERPER_API_KEY,
                 "Content-Type": "application/json"},
        json={"q": query, "num": num, "gl": "kr", "hl": "ko"},
        timeout=15,
    )
    perf["ms"] = round((perf_counter() - t0) * 1000, 1)
    perf["status_code"] = resp.status_code
    resp.raise_for_status()
    data = resp.json() or {}

    out: List[Dict[str, Any]] = []
    for it in (data.get("images") or []):
        url = it.get("imageUrl") or it.get("link")
        if not url:
            continue
        out.append({
            "image_url": url,
            "title": it.get("title") or "",
            "source": it.get("source") or "",
            "domain": it.get("domain") or "",
            "link": it.get("link") or "",
            "width": int(it.get("imageWidth") or 0),
            "height": int(it.get("imageHeight") or 0),
            "thumbnail": it.get("thumbnailUrl") or "",
            "position": it.get("position"),
        })
    perf["received"] = len(out)
    return out, perf
