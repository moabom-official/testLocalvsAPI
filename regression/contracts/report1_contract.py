"""보고서 ① (영상별 자막 기반, 마크다운) 양식 검증기.

원본 양식 출처: scripts/reports/transcript_report.py 의 _SYSTEM_PROMPT / _FINAL_PROMPT
(few-shot 예시). build_transcript_report 는 자막 없음 시
"No transcript content available.", LLM 실패 시 "[ERROR] ..." 문자열을 반환한다.
"""
from __future__ import annotations

from regression.contracts._markdown import (
    has_heading,
    section_body,
    table_header_columns,
)
from regression.contracts.result import ContractResult

REPORT_KIND = "report1"

H2_MAIN = "## 📦 제품 핵심 인사이트 보고서"
PRODUCT_LABEL = "**제품명:**"

REQUIRED_H3 = (
    "### 장점 / 단점",
    "### 전작 대비 달라진 것",
    "### 이런 사람한테 맞습니다",
    "### 이런 사람한테는 비추",
    "### 차별성 & 구매 합리성",
    "### 리뷰어가 강조한 핵심 포인트",
    "### 🛒 한 줄 구매 판정",
)

STRENGTH_SYMBOLS = ("◎", "○", "△", "✕")


def validate_report1(text) -> ContractResult:
    """보고서 ① 마크다운 문자열의 구조 계약을 검증한다."""
    result = ContractResult(report_kind=REPORT_KIND)

    if not isinstance(text, str) or not text.strip():
        result.status = "generation_failed"
        result.add(
            "R1.EMPTY",
            "보고서 ① 입력이 비어 있거나 문자열이 아닙니다.",
            severity="warning",
        )
        return result

    stripped = text.strip()
    if stripped.startswith("[ERROR]") or stripped == "No transcript content available.":
        result.status = "generation_failed"
        result.add(
            "R1.GENERATION_FAILED",
            "보고서 생성 실패 산출물(에러/자막 없음)입니다. 양식 위반이 아닙니다.",
            severity="warning",
        )
        return result

    # 메인 H2
    if not has_heading(text, H2_MAIN, level=2):
        result.add("R1.MISSING_MAIN_HEADING", f"필수 H2 '{H2_MAIN}' 누락")

    # 제품명 라벨
    if PRODUCT_LABEL not in text:
        result.add("R1.MISSING_PRODUCT_LABEL", f"제품명 라벨 '{PRODUCT_LABEL}' 누락")

    # 필수 H3 (표기 그대로, 존재 여부)
    for h3 in REQUIRED_H3:
        if not has_heading(text, h3, level=3):
            result.add("R1.MISSING_SECTION", f"필수 H3 '{h3}' 누락")

    # 장점/단점 라벨
    pros_cons = section_body(text, "### 장점 / 단점", level=3)
    if pros_cons:
        if "**장점**" not in pros_cons:
            result.add("R1.MISSING_PROS_LABEL", "'### 장점 / 단점' 섹션에 '**장점**' 라벨 누락")
        if "**단점**" not in pros_cons:
            result.add("R1.MISSING_CONS_LABEL", "'### 장점 / 단점' 섹션에 '**단점**' 라벨 누락")

    # 강도 기호 (전체 본문 기준 최소 1개)
    if not any(sym in text for sym in STRENGTH_SYMBOLS):
        result.add(
            "R1.MISSING_STRENGTH_SYMBOL",
            f"강도 기호 {' '.join(STRENGTH_SYMBOLS)} 중 최소 1개가 없습니다.",
        )

    # 차별성 & 구매 합리성 — 차별점/감안할 점 라벨 불릿
    diff_body = section_body(text, "### 차별성 & 구매 합리성", level=3)
    if diff_body:
        if "- 차별점:" not in diff_body:
            result.add(
                "R1.MISSING_DIFF_BULLET",
                "'### 차별성 & 구매 합리성' 섹션에 '- 차별점:' 라벨 불릿 누락",
            )
        if "- 감안할 점:" not in diff_body:
            result.add(
                "R1.MISSING_CONSIDER_BULLET",
                "'### 차별성 & 구매 합리성' 섹션에 '- 감안할 점:' 라벨 불릿 누락",
            )

    # 전작 대비 달라진 것 — 마크다운 표 헤더 존재
    prev_body = section_body(text, "### 전작 대비 달라진 것", level=3)
    if prev_body and not _has_any_pipe_table(prev_body):
        result.add(
            "R1.MISSING_PREV_TABLE",
            "'### 전작 대비 달라진 것' 섹션에 마크다운 표(파이프 헤더 행) 누락",
        )

    return result.finalize()


def _has_any_pipe_table(block: str) -> bool:
    """컬럼명 무관하게 파이프 표 헤더 행이 하나라도 있는지."""
    return len(table_header_columns(block)) > 0
