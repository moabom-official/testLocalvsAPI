"""메타데이터 1차 필터 (Phase 3 단계 2-ⓐ) — 순수, API 호출 없음.

목적: 비전 검증에 넘길 후보 추리기. "명백한" 노이즈만 싸게 제거하고
너무 깐깐하게 거르지 않는다(애매하면 통과시켜 비전이 판단). 후보가
부족해 이미지가 비는 것을 막는 게 우선(§4 검증 철학).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# 명백한 비제품 출처/형식만(과하지 않게). 밈·짤 도메인 위주.
_BAD_DOMAIN_HINTS = ("pinterest.", "lookaside.", "fbcdn.", "memecdn",
                     "tenor.com", "giphy.com")
_BAD_EXT = (".svg", ".gif")


def metadata_prefilter(
    candidates: List[Dict[str, Any]],
    *,
    min_px: int,
    max_keep: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """반환: (kept, rejected). rejected 원소에 'reject_reason' 부착."""
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for c in candidates:
        w, h = int(c.get("width") or 0), int(c.get("height") or 0)
        url = (c.get("image_url") or "").lower()
        dom = (c.get("domain") or "").lower()

        # 1) 명백히 작은 이미지(썸네일/아이콘)만 — 크기 정보 있을 때만 판단
        if w and h and (w < min_px or h < min_px):
            rejected.append({**c, "reject_reason": f"크기 미달({w}x{h})"})
            continue
        # 2) 명백히 부적합 확장자(벡터/움짤)
        if url.endswith(_BAD_EXT):
            rejected.append({**c, "reject_reason": "형식 부적합(svg/gif)"})
            continue
        # 3) 명백한 밈/핀터레스트류 도메인
        if any(b in dom or b in url for b in _BAD_DOMAIN_HINTS):
            rejected.append({**c, "reject_reason": f"노이즈 도메인({dom})"})
            continue
        kept.append(c)

    # 비전 비용 통제: 상위 max_keep 만 넘김(검색 순위=position 보존).
    overflow = kept[max_keep:]
    for o in overflow:
        rejected.append({**o, "reject_reason": "비전 후보 상한 초과(검색 하위)"})
    return kept[:max_keep], rejected
