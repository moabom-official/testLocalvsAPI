"""보고서 ② (영상별 댓글 기반, JSON dict) 양식 검증기.

⚠️ 보고서 ② 는 이미 검증 자산이 존재한다. 상수·검증 로직을 새로 손으로 짜지 않고
scripts.reports._comment_aggregator 의 validate_report2_json 과 REQUIRED_REPORT2_*
를 재사용한다(단일 진실 공급원, 복붙 없음). 단 _comment_aggregator 가 import
시점에 DB 드라이버를 끌어오므로, 오프라인 안전을 위해 regression._aggregator_adapter
경유로 import 한다. 본 모듈은 그 위에 "어느 키가 어디서 빠졌는지" 위치를 채워
ContractResult 로 확장 반환할 뿐이다.

검증 대상은 raw LLM 응답이 아니라 DB 저장 "최종 dict" (후처리로 _meta 와 댓글
원문이 첨부된 형태) 다. 1차(raw 필수 스키마)는 error, 2차(후처리 첨부 형태)는
warning 으로 처리한다(raw 형태일 수도 있으므로 hard fail 아님).
"""
from __future__ import annotations

from regression._aggregator_adapter import (
    REQUIRED_REPORT2_POINT_KEYS,
    REQUIRED_REPORT2_SENT_KEYS,
    REQUIRED_REPORT2_TOP_KEYS,
    validate_report2_json,
)

from regression.contracts.result import ContractResult

REPORT_KIND = "report2"

_META_KEYS = (
    "video_id",
    "product_name",
    "total_analyzed_comments",
    "model_used",
    "schema_version",
)
_REP_COMMENT_KEYS = ("comment_id", "text_raw", "like_count", "author_name")


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_report2(data) -> ContractResult:
    """보고서 ② 최종 dict 의 구조 계약을 검증한다."""
    result = ContractResult(report_kind=REPORT_KIND)

    if data is None:
        result.status = "generation_failed"
        result.add(
            "R2.GENERATION_FAILED",
            "보고서 ② 가 None (분석 댓글 0건 또는 LLM 3회 실패) — 양식 위반 아님.",
            severity="warning",
        )
        return result

    # ── 1차: raw 필수 스키마 (error) — 위치 상세 채움 ──
    if not isinstance(data, dict):
        result.add("R2.NOT_DICT", "최상위가 dict 가 아닙니다.")
        return result.finalize()

    for k in REQUIRED_REPORT2_TOP_KEYS:
        if k not in data:
            result.add("R2.MISSING_TOP_KEY", f"최상위 필수 키 '{k}' 누락")

    sent = data.get("sentiment_summary")
    if not isinstance(sent, dict):
        result.add("R2.SENTIMENT_NOT_DICT", "'sentiment_summary' 가 dict 가 아닙니다.")
    else:
        for k in REQUIRED_REPORT2_SENT_KEYS:
            if k not in sent:
                result.add("R2.MISSING_SENT_KEY", f"sentiment_summary 필수 키 '{k}' 누락")

    for grp in ("positive_points", "negative_points"):
        seq = data.get(grp)
        if not isinstance(seq, list):
            result.add("R2.POINTS_NOT_LIST", f"'{grp}' 가 list 가 아닙니다.")
            continue
        for i, item in enumerate(seq):
            if not isinstance(item, dict):
                result.add("R2.POINT_NOT_DICT", f"{grp}[{i}] 가 dict 가 아닙니다.")
                continue
            for k in REQUIRED_REPORT2_POINT_KEYS:
                if k not in item:
                    result.add("R2.MISSING_POINT_KEY", f"{grp}[{i}] 필수 키 '{k}' 누락")
            if "representative_comment_ids" in item and not isinstance(
                item["representative_comment_ids"], list
            ):
                result.add(
                    "R2.REP_IDS_NOT_LIST",
                    f"{grp}[{i}].representative_comment_ids 가 list 가 아닙니다.",
                )

    if not isinstance(data.get("top_issues"), list):
        result.add("R2.TOP_ISSUES_NOT_LIST", "'top_issues' 가 list 가 아닙니다.")

    # 권위 있는 1차 게이트: 기존 bool 검증기와 교차 확인
    authoritative_ok = validate_report2_json(data)
    if not authoritative_ok and not result.has_errors:
        result.add(
            "R2.SCHEMA_INVALID",
            "validate_report2_json 가 False 를 반환했으나 세부 위치를 특정하지 못했습니다.",
        )

    # ── 2차: 최종 산출물(후처리 첨부) 형태 (warning) ──
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        result.add(
            "R2.MISSING_META",
            "최종 산출물 표식 '_meta' dict 누락 (raw LLM 응답 형태일 수 있음).",
            severity="warning",
        )
    else:
        for k in _META_KEYS:
            if k not in meta:
                result.add("R2.MISSING_META_KEY", f"_meta 키 '{k}' 누락", severity="warning")

    for grp in ("positive_points", "negative_points"):
        seq = data.get(grp)
        if not isinstance(seq, list):
            continue
        for i, item in enumerate(seq):
            if not isinstance(item, dict):
                continue
            reps = item.get("representative_comments")
            if reps is None:
                result.add(
                    "R2.MISSING_REP_COMMENTS",
                    f"{grp}[{i}] 후처리 첨부 키 'representative_comments' 누락",
                    severity="warning",
                )
                continue
            if not isinstance(reps, list):
                result.add(
                    "R2.REP_COMMENTS_NOT_LIST",
                    f"{grp}[{i}].representative_comments 가 list 가 아닙니다.",
                    severity="warning",
                )
                continue
            # 빈 리스트 허용. 원소가 있으면 키 검사.
            for j, c in enumerate(reps):
                if not isinstance(c, dict):
                    result.add(
                        "R2.REP_COMMENT_NOT_DICT",
                        f"{grp}[{i}].representative_comments[{j}] 가 dict 가 아닙니다.",
                        severity="warning",
                    )
                    continue
                for k in _REP_COMMENT_KEYS:
                    if k not in c:
                        result.add(
                            "R2.MISSING_REP_COMMENT_KEY",
                            f"{grp}[{i}].representative_comments[{j}] 키 '{k}' 누락",
                            severity="warning",
                        )

    top_issues = data.get("top_issues")
    if isinstance(top_issues, list):
        for i, t in enumerate(top_issues):
            if not isinstance(t, dict):
                result.add(
                    "R2.TOP_ISSUE_NOT_DICT",
                    f"top_issues[{i}] 가 dict 가 아닙니다.",
                    severity="warning",
                )
                continue
            if "keyword" not in t or not isinstance(t["keyword"], str):
                result.add(
                    "R2.TOP_ISSUE_KEYWORD",
                    f"top_issues[{i}].keyword (str) 누락/형식 오류",
                    severity="warning",
                )
            if "count" not in t or not _is_number(t["count"]):
                result.add(
                    "R2.TOP_ISSUE_COUNT",
                    f"top_issues[{i}].count (숫자) 누락/형식 오류",
                    severity="warning",
                )

    return result.finalize()
