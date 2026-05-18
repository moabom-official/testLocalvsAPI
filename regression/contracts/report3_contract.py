"""보고서 ③ (영상별 자막+댓글 통합, JSON dict) 양식 검증기.

⚠️ 보고서 ③ 도 이미 검증 자산이 존재한다. 상수·검증 로직을 새로 손으로 짜지 않고
scripts.reports._comment_aggregator 의 validate_report3_json 과 REQUIRED_REPORT3_*
상수를 재사용한다(단일 진실 공급원, 복붙 없음). 오프라인 안전을 위해 import 는
regression._aggregator_adapter 경유. 본 모듈은 위반 위치를 채워 확장 반환할 뿐이다.

검증 대상은 DB 저장 "최종 dict" (후처리로 _meta·consumer_comments·question_comment
가 첨부된 형태). 1차(raw 필수 스키마)는 error, 2차(후처리 첨부 형태)는 warning.
"""
from __future__ import annotations

from regression._aggregator_adapter import (
    REQUIRED_REPORT3_AGREE_KEYS,
    REQUIRED_REPORT3_DISAGREE_KEYS,
    REQUIRED_REPORT3_FALLBACK_KEYS,
    REQUIRED_REPORT3_QUESTION_KEYS,
    REQUIRED_REPORT3_SPEC_KEYS,
    REQUIRED_REPORT3_TOP_KEYS,
    REQUIRED_REPORT3_VERDICT_KEYS,
    validate_report3_json,
)

from regression.contracts.result import ContractResult

REPORT_KIND = "report3"

_META_KEYS = (
    "video_id",
    "product_name",
    "agreement_count",
    "disagreement_count",
    "spec_change_count",
    "consumer_question_count",
    "model_used",
    "schema_version",
)


def _check_list_of_dicts(result, data, key, required_keys, list_subkeys=()):
    seq = data.get(key)
    if not isinstance(seq, list):
        result.add("R3.NOT_LIST", f"'{key}' 가 list 가 아닙니다.")
        return
    for i, item in enumerate(seq):
        if not isinstance(item, dict):
            result.add("R3.ITEM_NOT_DICT", f"{key}[{i}] 가 dict 가 아닙니다.")
            continue
        for k in required_keys:
            if k not in item:
                result.add("R3.MISSING_ITEM_KEY", f"{key}[{i}] 필수 키 '{k}' 누락")
        for sk in list_subkeys:
            if sk in item and not isinstance(item[sk], list):
                result.add("R3.SUBKEY_NOT_LIST", f"{key}[{i}].{sk} 가 list 가 아닙니다.")


def validate_report3(data) -> ContractResult:
    """보고서 ③ 최종 dict 의 구조 계약을 검증한다."""
    result = ContractResult(report_kind=REPORT_KIND)

    if data is None:
        result.status = "generation_failed"
        result.add(
            "R3.GENERATION_FAILED",
            "보고서 ③ 가 None (생성 실패) — 양식 위반 아님.",
            severity="warning",
        )
        return result

    if not isinstance(data, dict):
        result.add("R3.NOT_DICT", "최상위가 dict 가 아닙니다.")
        return result.finalize()

    # ── 1차: raw 필수 스키마 (error) ──
    for k in REQUIRED_REPORT3_TOP_KEYS:
        if k not in data:
            result.add("R3.MISSING_TOP_KEY", f"최상위 필수 키 '{k}' 누락")

    _check_list_of_dicts(
        result, data, "agreement_points", REQUIRED_REPORT3_AGREE_KEYS,
        list_subkeys=("consumer_comment_ids",),
    )
    _check_list_of_dicts(
        result, data, "disagreement_points", REQUIRED_REPORT3_DISAGREE_KEYS,
        list_subkeys=("consumer_comment_ids",),
    )

    for grp in ("reviewer_only", "consumer_only"):
        if not isinstance(data.get(grp), list):
            result.add("R3.NOT_LIST", f"'{grp}' 가 list 가 아닙니다.")

    _check_list_of_dicts(result, data, "spec_changes", REQUIRED_REPORT3_SPEC_KEYS)
    _check_list_of_dicts(
        result, data, "consumer_questions", REQUIRED_REPORT3_QUESTION_KEYS
    )

    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        result.add("R3.VERDICT_NOT_DICT", "'verdict' 가 dict 가 아닙니다.")
    else:
        for k in REQUIRED_REPORT3_VERDICT_KEYS:
            if k not in verdict:
                result.add("R3.MISSING_VERDICT_KEY", f"verdict 필수 키 '{k}' 누락")

    fb = data.get("fallback_notes")
    if not isinstance(fb, dict):
        result.add("R3.FALLBACK_NOT_DICT", "'fallback_notes' 가 dict 가 아닙니다.")
    else:
        for k in REQUIRED_REPORT3_FALLBACK_KEYS:
            if k not in fb:
                result.add("R3.MISSING_FALLBACK_KEY", f"fallback_notes 필수 키 '{k}' 누락")

    authoritative_ok = validate_report3_json(data)
    if not authoritative_ok and not result.has_errors:
        result.add(
            "R3.SCHEMA_INVALID",
            "validate_report3_json 가 False 를 반환했으나 세부 위치를 특정하지 못했습니다.",
        )

    # ── 2차: 최종 산출물(후처리 첨부) 형태 (warning) ──
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        result.add(
            "R3.MISSING_META",
            "최종 산출물 표식 '_meta' dict 누락 (raw LLM 응답 형태일 수 있음).",
            severity="warning",
        )
    else:
        for k in _META_KEYS:
            if k not in meta:
                result.add("R3.MISSING_META_KEY", f"_meta 키 '{k}' 누락", severity="warning")

    for grp in ("agreement_points", "disagreement_points"):
        seq = data.get(grp)
        if not isinstance(seq, list):
            continue
        for i, item in enumerate(seq):
            if not isinstance(item, dict):
                continue
            cc = item.get("consumer_comments")
            if cc is None:
                result.add(
                    "R3.MISSING_CONSUMER_COMMENTS",
                    f"{grp}[{i}] 후처리 첨부 키 'consumer_comments' 누락",
                    severity="warning",
                )
            elif not isinstance(cc, list):
                result.add(
                    "R3.CONSUMER_COMMENTS_NOT_LIST",
                    f"{grp}[{i}].consumer_comments 가 list 가 아닙니다.",
                    severity="warning",
                )

    cq = data.get("consumer_questions")
    if isinstance(cq, list):
        for i, q in enumerate(cq):
            if not isinstance(q, dict):
                continue
            if "question_comment" not in q:
                result.add(
                    "R3.MISSING_QUESTION_COMMENT",
                    f"consumer_questions[{i}] 후처리 첨부 키 'question_comment' 누락",
                    severity="warning",
                )
            else:
                qc = q["question_comment"]
                if qc is not None and not isinstance(qc, dict):
                    result.add(
                        "R3.QUESTION_COMMENT_BAD_TYPE",
                        f"consumer_questions[{i}].question_comment 는 dict 또는 null 이어야 합니다.",
                        severity="warning",
                    )

    return result.finalize()
