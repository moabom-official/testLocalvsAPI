"""보고서 ④ (제품 단위 종합 인사이트, 마크다운 7섹션) 양식 검증기.

원본 양식 출처: scripts/utils/prompt_manager.py 의 build_product_integrated_insight_prompt
"출력 형식" 블록. 휴리스틱 폴백 출처: scripts/reports/product_integrated_insight.py
의 _heuristic_fallback_report.

⚠️ 양식 스펙 보정 메모(작업 로그):
  지시서 §4.5 는 "폴백 산출물로 판단되면(7섹션 동그라미 H2 가 통째로 부재 등)"
  이라 적었으나, 실제 _heuristic_fallback_report 는 7개 동그라미 H2 를 모두
  출력한다. 따라서 폴백의 신뢰 가능한 식별자는 H1 제목줄의
  "(LLM 미사용 모드)" 마커다. 원본 코드를 스펙보다 우선해, 폴백 판별을 이
  명시 마커(보조: "## 입력 영상별 보고서 (참고)") + 7섹션 동그라미 H2 전부
  부재 의 OR 조건으로 한다.
"""
from __future__ import annotations

import re

from regression.contracts._markdown import (
    has_table_header,
    iter_headings,
    section_body,
)
from regression.contracts.result import ContractResult

REPORT_KIND = "report4"

CIRCLED = ("①", "②", "③", "④", "⑤", "⑥", "⑦")

# 각 동그라미 섹션 제목의 핵심 키워드(2차 확인용)
SECTION_KEYWORDS = {
    "①": "구매 판정",
    "②": "핵심 요약",
    "③": "6차원",
    "④": "장점",
    "⑤": "소비자 여론",
    "⑥": "전작",
    "⑦": "추천",
}

SCORE_RE = re.compile(r"\d\.\d\s*/\s*10")
FALLBACK_MARKER = "(LLM 미사용 모드)"
FALLBACK_APPENDIX = "## 입력 영상별 보고서 (참고)"
CONSUMER_EMPTY_LINE = "데이터 부족 (분석 가능한 댓글 없음)"

TABLE3_COLS = ("차원", "점수", "커버리지", "리뷰어 합의", "핵심 코멘트")
TABLE6_COLS = ("항목", "전작", "현재", "변화 평가", "언급 영상 수")


def _h2_for(md: str, circled: str):
    """주어진 동그라미 숫자가 들어간 H2 헤딩의 (정규화 텍스트) 또는 None."""
    for level, text, _ln in iter_headings(md):
        if level == 2 and circled in text:
            return text
    return None


def _looks_like_fallback(md: str) -> bool:
    if FALLBACK_MARKER in md or FALLBACK_APPENDIX in md:
        return True
    # 7개 동그라미 H2 가 통째로 부재 (스펙이 명시한 보조 조건)
    if all(_h2_for(md, c) is None for c in CIRCLED):
        return True
    return False


def validate_report4(text) -> ContractResult:
    """보고서 ④ 마크다운 문자열의 7섹션 구조 계약을 검증한다."""
    result = ContractResult(report_kind=REPORT_KIND)

    if not isinstance(text, str) or not text.strip():
        result.status = "generation_failed"
        result.add(
            "R4.EMPTY",
            "보고서 ④ 입력이 비어 있거나 문자열이 아닙니다.",
            severity="warning",
        )
        return result

    if text.strip().startswith("[ERROR]"):
        result.status = "generation_failed"
        result.add(
            "R4.GENERATION_FAILED",
            "보고서 생성 실패 산출물([ERROR])입니다. 양식 위반이 아닙니다.",
            severity="warning",
        )
        return result

    if _looks_like_fallback(text):
        result.status = "fallback"
        result.add(
            "R4.FALLBACK",
            "휴리스틱 폴백(LLM 미사용 모드) 산출물입니다. 정식 7섹션 계약 비적용 — "
            "게이트 하드 실패 대상 아님.",
            severity="warning",
        )
        return result

    # ── 정상(LLM) 산출물 검사 ──
    # 1차: 7개 동그라미 H2 존재 / 2차: 제목 키워드
    for c in CIRCLED:
        h2 = _h2_for(text, c)
        if h2 is None:
            result.add("R4.MISSING_SECTION", f"동그라미 '{c}' 가 붙은 H2 섹션 누락")
            continue
        kw = SECTION_KEYWORDS[c]
        if kw not in h2:
            result.add(
                "R4.SECTION_KEYWORD",
                f"'{c}' 섹션 제목에 핵심 키워드 '{kw}' 누락 (실제: '{h2}')",
            )

    # ① 종합 점수 표기
    sec1 = _section_by_circled(text, "①")
    if sec1 is not None:
        if not SCORE_RE.search(sec1) and "데이터 부족 / 10" not in sec1:
            result.add(
                "R4.MISSING_SCORE",
                "① 섹션에 종합 점수('X.X / 10' 또는 '데이터 부족 / 10') 누락",
            )

    # ③ 6차원 표 헤더 (5컬럼)
    sec3 = _section_by_circled(text, "③")
    if sec3 is not None and not has_table_header(sec3, TABLE3_COLS):
        result.add(
            "R4.MISSING_TABLE3",
            f"③ 섹션에 표 헤더 | {' | '.join(TABLE3_COLS)} | (5컬럼) 누락",
        )

    # ④ 장점 / 단점 H3 (### 개별 리뷰어 의견 은 선택)
    sec4 = _section_by_circled(text, "④")
    if sec4 is not None:
        for h3 in ("### 장점", "### 단점"):
            if not _has_h3(sec4, h3):
                result.add("R4.MISSING_SUBHEADING", f"④ 섹션에 '{h3}' H3 누락")

    # ⑤ 소비자 여론 H3 (데이터 부족 한 줄이면 H3 검사 생략)
    sec5 = _section_by_circled(text, "⑤")
    if sec5 is not None and CONSUMER_EMPTY_LINE not in sec5:
        for h3 in ("### 소비자가 꼽은 강점", "### 소비자가 꼽은 불만", "### 대표 댓글"):
            if not _has_h3(sec5, h3):
                result.add("R4.MISSING_SUBHEADING", f"⑤ 섹션에 '{h3}' H3 누락")

    # ⑥ 전작 대비 표 헤더 (5컬럼, 본문 행 0개 허용 — 헤더만 검사)
    sec6 = _section_by_circled(text, "⑥")
    if sec6 is not None and not has_table_header(sec6, TABLE6_COLS):
        result.add(
            "R4.MISSING_TABLE6",
            f"⑥ 섹션에 표 헤더 | {' | '.join(TABLE6_COLS)} | (5컬럼) 누락",
        )

    # ⑦ 추천 / 비추 H3
    sec7 = _section_by_circled(text, "⑦")
    if sec7 is not None:
        for h3 in ("### 추천", "### 비추"):
            if not _has_h3(sec7, h3):
                result.add("R4.MISSING_SUBHEADING", f"⑦ 섹션에 '{h3}' H3 누락")

    # 메타 박스
    if "📊 분석 기반" not in text:
        result.add("R4.MISSING_META_BOX", "메타 박스 표시 '📊 분석 기반' 누락")

    return result.finalize()


def _section_by_circled(md: str, circled: str):
    """동그라미 번호로 H2 를 찾아 그 섹션 본문(헤딩 포함)을 반환."""
    h2 = _h2_for(md, circled)
    if h2 is None:
        return None
    body = section_body(md, h2, level=2)
    # 하위 H3 검사를 위해 헤딩 라인 자체는 빼고 본문만 충분 (section_body 가 본문 반환)
    return body


def _has_h3(section_text: str, h3: str) -> bool:
    """섹션 본문 안에 정확 표기의 H3 가 있는지 (정규화 비교)."""
    from regression.contracts._markdown import normalize_heading

    want = normalize_heading(h3)
    for level, txt, _ln in iter_headings(section_text):
        if level == 3 and txt == want:
            return True
    return False
