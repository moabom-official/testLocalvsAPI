"""로딩 화면 TIP 문구 풀 + 동적 인기 제품 조회 (5분 캐시).

읽을거리 제공으로 사용자 체감 대기 시간 단축. 정적 문장은 코드에 박고,
동적 한 줄은 usage_events 합산 (최근 7일, 5분 메모리 캐시).

★ 의존성 얇게 유지 — scripts.database.queries.query_all 만 사용.
★ TIP 은 보조 기능 — 어떤 실패도 호출자(/loading-tips 라우트)를 죽이지 않는다.
"""
from __future__ import annotations

from time import time
from typing import List, Optional

# ── 정적 문장 풀 (★ 23개 — 카테고리·문장 모두 다양화. 임의 추가/삭제 금지) ──
STATIC_TIPS: List[str] = [
    # 어원·정체성
    "MOABOM은 '모아서 봄' — 흩어진 리뷰를 한 곳에 모아 보여드려요.",
    "수많은 리뷰어의 의견을 *모아* 한 번에 *봄* — MOABOM의 이름이 담은 뜻이에요.",
    "유튜브 리뷰 정보를 *모아*서 *보는* 서비스, MOABOM입니다.",
    "리뷰 영상의 핵심을 한눈에 — 그것이 MOABOM의 모토예요.",
    # 차별점·가치
    "MOABOM은 한 번에 수십 개 리뷰 영상을 분석합니다.",
    "리뷰어 자막과 시청자 댓글을 함께 비교해 진짜 평가를 보여드려요.",
    "한 명의 리뷰어보다 여러 리뷰어의 합의가 더 신뢰할 수 있어요.",
    "MOABOM은 리뷰어와 시청자, 양쪽 시선을 모두 담아 비교해드립니다.",
    "광고와 진짜 후기를 구분하는 AI 분석이 MOABOM의 핵심이에요.",
    "여러 영상을 종합하면 한 채널의 편향에서 자유로워질 수 있어요.",
    # 사용 팁
    "분석할 영상이 많을수록 보고서의 신뢰성이 높아져요.",
    "댓글에서 반복되는 표현은 실제 사용자 인식의 핵심일 가능성이 높아요.",
    "장점·단점은 빈도수까지 함께 보면 더 정확한 판단이 가능해요.",
    "리뷰어 의견과 댓글의 합의가 일치하면 그 정보는 더 신뢰할 수 있어요.",
    "유사 제품 비교하기로 다른 제품과 한 번에 비교해보세요.",
    "종합 인사이트는 영상 2개 이상에서 신뢰성이 높아져요.",
    # 친근한 메시지
    "잠시만 기다려주세요. 곧 결과를 보여드릴게요.",
    "수십 개의 리뷰를 꼼꼼히 모으는 중이에요.",
    "리뷰어들의 진짜 평가를 분석하는 중입니다.",
    "유튜브의 수많은 의견을 정리하는 중이에요. 거의 다 됐어요.",
    # 재미·인사이트
    "리뷰 영상 1개의 자막은 평균 1만 자 정도예요. MOABOM이 한 번에 처리합니다.",
    "테크 리뷰는 짧게는 5분, 길게는 30분. MOABOM이 핵심만 뽑아드려요.",
    "댓글은 시청자의 직접적인 목소리예요. MOABOM은 그것도 빠뜨리지 않아요.",
]

# ── 동적 인기 제품 한 줄 (5분 메모리 캐시) ──────────────────────
_POPULAR_CACHE: dict = {"value": None, "ts": 0.0}
_POPULAR_TTL_SEC = 300  # 5분


def get_popular_products_tip() -> Optional[str]:
    """최근 7일 usage_events 합산 → 상위 3개 제품명을 한 줄로 묶음.

    조회 실패·결과 없음 → None (호출부가 정적 문장만 반환).
    절대 raise 안 함 — 로딩 TIP 은 보조 기능, 호출자를 죽이지 않음.
    """
    now = time()
    cached = _POPULAR_CACHE["value"]
    if cached is not None and (now - _POPULAR_CACHE["ts"]) < _POPULAR_TTL_SEC:
        return cached

    tip: Optional[str] = None
    try:
        from scripts.database.queries import query_all

        rows = query_all(
            """
            SELECT tp.name, COUNT(*) AS hits
              FROM usage_events ue
              JOIN tech_products tp ON tp.product_id = ue.product_id
             WHERE ue.event_type IN ('page_view', 'product_create')
               AND ue.product_id IS NOT NULL
               AND ue.ts >= NOW() - INTERVAL '7 days'
             GROUP BY tp.name
             ORDER BY hits DESC
             LIMIT 3
            """
        )
        names = [r["name"] for r in (rows or []) if r.get("name")]
        if names:
            joined = ", ".join(names)
            tip = f"최근 MOABOM에서 많이 찾아본 제품: {joined}"
    except Exception as e:  # noqa: BLE001 — TIP 은 보조 기능, raise 금지
        print(f"[WARN] loading-tips popular query failed: "
              f"{type(e).__name__}: {e}")
        tip = None

    _POPULAR_CACHE["value"] = tip
    _POPULAR_CACHE["ts"] = now
    return tip
