"""
보고서 ② — 댓글 기반 소비자 여론 보고서 (RunYourAI openai/gpt-4.1-2025-04-14).

⚠️ 저장 형식 변경:
  video_reports.comment_report 는 v1 까지 마크다운 TEXT 였으나,
  이번 디벨롭(v2) 부터는 JSON 문자열로 저장한다.
  - 응답 dict 스키마: build_comment_analysis_prompt docstring 참조
  - 환각 차단: LLM 은 representative_comment_ids 만 지목, 원문은 백엔드가 첨부

공개 함수:
  build_comment_sentiment_report(video_id, product_name, video_title) -> Optional[dict]
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from scripts.reports._comment_aggregator import (
    aggregate_comment_report_inputs,
    attach_comment_texts,
    validate_report2_json,
)
from scripts.reports.transcript_report import (
    REPORT_LLM_DEPLOYMENT,
    fix_encoding,
    get_report_llm_client,
)
from scripts.utils.prompt_manager import build_comment_analysis_prompt


SCHEMA_VERSION = "v2.comment_report.1"
MAX_LLM_ATTEMPTS = 3


def build_comment_sentiment_report(
    video_id: str,
    product_name: str = "제품",
    video_title: str = "",
) -> Optional[Dict[str, Any]]:
    """
    영상 1개에 대한 댓글 기반 소비자 여론 보고서를 dict 로 생성한다.

    반환:
      성공 → dict (스키마: build_comment_analysis_prompt docstring + _meta)
      ANALYZE 댓글 0건 → None
      LLM 실패 (3회 재시도 모두 실패) → None
    """
    aggregated = aggregate_comment_report_inputs(video_id, product_name, video_title)
    if not aggregated or aggregated["total_analyzed_comments"] == 0:
        print(f"[comment_report] no ANALYZE comments for video_id={video_id}")
        return None

    try:
        client = get_report_llm_client()
    except ValueError as e:
        print(f"[ERROR] comment_report: LLM client unavailable: {e}")
        return None

    prompt = build_comment_analysis_prompt(aggregated)

    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=REPORT_LLM_DEPLOYMENT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2200,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            print(
                f"[ERROR] comment_report: LLM call failed "
                f"(attempt {attempt}/{MAX_LLM_ATTEMPTS}): {type(e).__name__}: {e}"
            )
            continue

        raw = (response.choices[0].message.content if response.choices else "") or ""
        raw = fix_encoding(raw.strip())

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(
                f"[WARN] comment_report: JSON parse failed "
                f"(attempt {attempt}/{MAX_LLM_ATTEMPTS}): {e}"
            )
            continue

        if not validate_report2_json(data):
            print(
                f"[WARN] comment_report: JSON schema invalid "
                f"(attempt {attempt}/{MAX_LLM_ATTEMPTS})"
            )
            continue

        # 다중 환각 검증 (생성 → 코드게이트 → 비평 → 수정). 한 attempt 안의
        # 추가 단계 — attempt 의미(JSON/양식 실패 시 재생성)는 그대로.
        verification_perf = None
        try:
            from scripts.reports._verification import verify_json_report

            _vr = verify_json_report(
                "report2",
                data,
                grounding=json.dumps(aggregated, ensure_ascii=False),
                format_validator=validate_report2_json,
            )
            if isinstance(_vr.output, dict) and validate_report2_json(_vr.output):
                data = _vr.output
            verification_perf = _vr.perf.to_dict()
        except Exception as e:  # noqa: BLE001 — 검증 실패는 초안 채택으로 퇴화
            print(f"[WARN][verification] report2 검증 건너뜀: {type(e).__name__}: {e}")

        # 환각 차단: LLM 이 입력 외 ID 를 지목한 경우 화이트리스트로 필터
        data = _filter_ids_by_whitelist(data, aggregated)

        # 원문 첨부 (representative_comment_ids → representative_comments)
        data = attach_comment_texts(
            data,
            id_paths=[
                ("positive_points", "representative_comment_ids", "representative_comments"),
                ("negative_points", "representative_comment_ids", "representative_comments"),
            ],
        )

        data["_meta"] = {
            "video_id": video_id,
            "product_name": product_name,
            "total_analyzed_comments": aggregated["total_analyzed_comments"],
            "model_used": REPORT_LLM_DEPLOYMENT,
            "schema_version": SCHEMA_VERSION,
        }
        # 기존 _meta 키 불변. 검증 perf 는 새 키로만 추가 (Phase 0 계약 보존).
        if verification_perf is not None:
            data["_meta"]["verification"] = verification_perf
        return data

    print(f"[ERROR] comment_report: failed after {MAX_LLM_ATTEMPTS} attempts (video_id={video_id})")
    return None


def _filter_ids_by_whitelist(
    data: Dict[str, Any],
    aggregated: Dict[str, Any],
) -> Dict[str, Any]:
    """
    representative_comment_ids 중 입력 candidate_comments 에 없는 ID 를 제거.
    각 그룹 최대 2개 유지.
    """
    pos_white = {
        c["comment_id"]
        for grp in aggregated.get("positive_aspects", [])
        for c in grp.get("candidate_comments", [])
    }
    neg_white = {
        c["comment_id"]
        for grp in aggregated.get("negative_aspects", [])
        for c in grp.get("candidate_comments", [])
    }

    for item in data.get("positive_points", []):
        ids = item.get("representative_comment_ids") or []
        item["representative_comment_ids"] = [i for i in ids if i in pos_white][:2]
    for item in data.get("negative_points", []):
        ids = item.get("representative_comment_ids") or []
        item["representative_comment_ids"] = [i for i in ids if i in neg_white][:2]
    return data
