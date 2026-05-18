"""마크다운 보고서(①④) 구조 파싱 공통 헬퍼.

순수 함수만 — DB·LLM·네트워크 없음. report1/report4 계약기와 fingerprint 가
중복 없이 공유한다. 헤딩 텍스트 비교는 좌우 공백/구분선(`---`) 변형에 강하도록
정규화한 뒤 수행한다.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


def normalize_heading(text: str) -> str:
    """헤딩 본문 정규화 — 선행 `#`, 좌우 공백, 연속 공백을 접는다."""
    t = text.strip()
    t = re.sub(r"^#{1,6}\s*", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def iter_headings(md: str) -> List[Tuple[int, str, int]]:
    """(level, normalized_text, line_index) 리스트. ATX(`#`) 헤딩만 인식."""
    out: List[Tuple[int, str, int]] = []
    for idx, raw in enumerate(md.splitlines()):
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", raw)
        if m:
            out.append((len(m.group(1)), normalize_heading(m.group(2)), idx))
    return out


def heading_texts(md: str, level: Optional[int] = None) -> List[str]:
    """정규화된 헤딩 텍스트 목록 (level 지정 시 해당 레벨만)."""
    return [h[1] for h in iter_headings(md) if level is None or h[0] == level]


def has_heading(md: str, expected: str, level: Optional[int] = None) -> bool:
    """정규화 기준으로 expected 헤딩이 존재하는지."""
    target = normalize_heading(expected)
    return target in heading_texts(md, level=level)


def section_body(md: str, heading: str, level: Optional[int] = None) -> str:
    """지정 헤딩 바로 다음부터, 같거나 더 상위(작은 레벨) 헤딩 직전까지의 본문.

    찾지 못하면 빈 문자열. 같은 레벨 또는 더 상위 헤딩에서 절단한다(하위 헤딩은
    섹션 본문에 포함).
    """
    target = normalize_heading(heading)
    lines = md.splitlines()
    headings = iter_headings(md)

    start_line = None
    start_level = level
    for lv, txt, ln in headings:
        if txt == target and (level is None or lv == level):
            start_line = ln
            start_level = lv
            break
    if start_line is None:
        return ""

    end_line = len(lines)
    for lv, _txt, ln in headings:
        if ln > start_line and lv <= start_level:
            end_line = ln
            break
    return "\n".join(lines[start_line + 1 : end_line]).strip()


def table_header_columns(block: str) -> List[Tuple[str, ...]]:
    """블록 안 모든 마크다운 표의 헤더 컬럼 시그니처 목록.

    파이프 표의 '헤더 행' 만 추출한다(바로 다음 줄이 `---|---` 구분 행인 행).
    각 헤더는 trim 된 컬럼명 튜플로 반환.
    """
    sigs: List[Tuple[str, ...]] = []
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if not re.match(r"^\|?\s*:?-{2,}.*", nxt):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        sigs.append(tuple(c for c in cols))
    return sigs


def has_table_header(block: str, expected_columns: Tuple[str, ...]) -> bool:
    """지정 컬럼 시그니처(순서·개수 일치)의 표 헤더가 블록에 있는지."""
    want = tuple(c.strip() for c in expected_columns)
    return any(sig == want for sig in table_header_columns(block))


def marker_map(md: str, markers: Dict[str, str]) -> Dict[str, bool]:
    """{이름: 부분문자열} → {이름: 존재여부}. fingerprint 의 필수 마커 맵용."""
    return {name: (needle in md) for name, needle in markers.items()}
