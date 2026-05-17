"""
보고서 ④ (PIR) 전용 — 제품 단위 댓글 집계 헬퍼.

역할:
  - 선택된 video_ids 들에 대해 comments / comment_sentiments / aspect_extractions /
    agent_decisions 를 READ ONLY 로 조회.
  - 영상을 가로질러 합산한 가중 sentiment 비율 + aspect 상위 + 대표 댓글을 산출.

⚠️ 모든 SQL 은 SELECT only. INSERT/UPDATE/DELETE 금지.
⚠️ scripts/reports/_comment_aggregator.py 의 compute_weighted_ratio / fetch_comment_texts /
   _sweet_length_priority / _truncate 는 READ ONLY 로 import 만 한다. 해당 파일은 절대
   수정하지 않는다 — 보고서 ② / ③ 파이프라인의 책임 영역.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from scripts.database.queries import query_all
from scripts.reports._comment_aggregator import (
    compute_weighted_ratio,
    _sweet_length_priority,
    _truncate,
)


# ── 튜닝 상수 ──────────────────────────────────────────────────

TOP_ASPECTS_PER_SIDE = 6           # 강점·불만 aspect 각각 상위 N
REPRESENTATIVE_COMMENT_LIMIT = 3   # ⑤ 섹션에 인용할 대표 댓글 수
REP_COMMENT_TEXT_MAX = 140         # 대표 댓글 한 건 truncate 길이 (프롬프트 비용 보호)


def aggregate_pir_consumer_inputs(video_ids: List[str]) -> Optional[Dict[str, Any]]:
    """
    제품 단위 ⑤ 소비자 여론 섹션을 위한 집계 dict 를 만든다.

    필터: agent_decisions.final_action='ANALYZE' 한 댓글만.
    반환: {
        "video_count": int,
        "total_analyzed_comments": int,
        "weighted_ratio": {"positive_pct", "neutral_pct", "negative_pct"},
        "top_positive_aspects": [{"aspect_name": str, "comment_count": int}, ...],
        "top_negative_aspects": [...],
        "representative_comments": [
            {"text_raw": str, "like_count": int, "video_id": str}, ...
        ],
    }
    분석 댓글이 0건이면 None.
    """
    if not video_ids:
        return None

    placeholders = ",".join(["%s"] * len(video_ids))
    params = tuple(video_ids)

    # 1) 분석 대상 댓글의 sentiment 행 — 가중 비율과 total 계산용
    sentiment_rows = query_all(
        f"""
        SELECT cs.sentiment_label, cs.analysis_weight
        FROM comments c
        INNER JOIN agent_decisions    ad ON c.comment_id = ad.comment_id
        INNER JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
        WHERE c.video_id IN ({placeholders}) AND ad.final_action = 'ANALYZE'
        """,
        params,
    )
    if not sentiment_rows:
        return None

    total_analyzed = len(sentiment_rows)
    weighted = compute_weighted_ratio(sentiment_rows)

    # 2) 강점·불만 aspect 상위 — 댓글 중복 제거 (한 댓글이 여러 aspect 가질 수 있음)
    top_positive_aspects = _aggregate_top_aspects(video_ids, "POSITIVE", TOP_ASPECTS_PER_SIDE)
    top_negative_aspects = _aggregate_top_aspects(video_ids, "NEGATIVE", TOP_ASPECTS_PER_SIDE)

    # 3) 대표 댓글 — 영상 가로지름. like_count 상위 + sweet length 우선
    representative = _fetch_representative_comments(video_ids, REPRESENTATIVE_COMMENT_LIMIT)

    return {
        "video_count": len(video_ids),
        "total_analyzed_comments": total_analyzed,
        "weighted_ratio": weighted,
        "top_positive_aspects": top_positive_aspects,
        "top_negative_aspects": top_negative_aspects,
        "representative_comments": representative,
    }


def _aggregate_top_aspects(
    video_ids: List[str],
    aspect_sentiment: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    """한 sentiment 방향(POSITIVE / NEGATIVE) aspect_name 상위 빈도 목록."""
    placeholders = ",".join(["%s"] * len(video_ids))
    rows = query_all(
        f"""
        SELECT ae.aspect_name, COUNT(DISTINCT ae.comment_id) AS cnt
        FROM aspect_extractions ae
        INNER JOIN comments         c ON ae.comment_id =  c.comment_id
        INNER JOIN agent_decisions ad ON ae.comment_id = ad.comment_id
        WHERE c.video_id IN ({placeholders})
          AND ad.final_action = 'ANALYZE'
          AND ae.aspect_sentiment = %s
          AND ae.aspect_name IS NOT NULL
          AND ae.aspect_name <> ''
        GROUP BY ae.aspect_name
        ORDER BY cnt DESC
        LIMIT %s
        """,
        tuple(video_ids) + (aspect_sentiment, top_k),
    )
    return [
        {"aspect_name": r["aspect_name"], "comment_count": int(r["cnt"])}
        for r in rows
    ]


def _fetch_representative_comments(video_ids: List[str], limit: int) -> List[Dict[str, Any]]:
    """제품 전체에서 대표 댓글 N건. like_count 상위 + sweet length 우선."""
    placeholders = ",".join(["%s"] * len(video_ids))
    # 후보를 넉넉히 (limit * 5) 가져온 뒤 Python 에서 sweet length 우선 정렬
    cand_rows = query_all(
        f"""
        SELECT c.comment_id, c.text_raw, c.like_count, c.video_id
        FROM comments c
        INNER JOIN agent_decisions ad ON c.comment_id = ad.comment_id
        WHERE c.video_id IN ({placeholders})
          AND ad.final_action = 'ANALYZE'
          AND c.text_raw IS NOT NULL
          AND length(c.text_raw) > 0
        ORDER BY c.like_count DESC NULLS LAST
        LIMIT %s
        """,
        tuple(video_ids) + (limit * 5,),
    )
    if not cand_rows:
        return []
    sorted_rows = sorted(
        cand_rows,
        key=lambda r: (
            _sweet_length_priority(r.get("text_raw") or ""),
            -(int(r.get("like_count") or 0)),
        ),
    )[:limit]
    return [
        {
            "text_raw":  _truncate(r.get("text_raw") or "", REP_COMMENT_TEXT_MAX),
            "like_count": int(r.get("like_count") or 0),
            "video_id":  r.get("video_id") or "",
        }
        for r in sorted_rows
    ]
