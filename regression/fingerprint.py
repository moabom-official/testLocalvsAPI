"""보고서 → 결정론적·내용 무관 구조 지문(fingerprint).

LLM 출력은 비결정적이므로 원문 diff 는 쓰지 않는다. 같은 양식이면 같은 지문이
나오고, 섹션 추가/삭제/개명 또는 표 컬럼 변경 시 지문이 달라진다. 지문은 JSON
직렬화 가능하다.

마크다운(①④): 헤딩(레벨+텍스트) 집합 / 표 컬럼 시그니처 / 필수 마커 존재 맵.
JSON(②③): 키 경로 집합 / 리스트 원소 키 집합 / _meta 존재 플래그.
"""
from __future__ import annotations

from typing import Any, Dict, List

from regression.contracts._markdown import iter_headings, table_header_columns

# 마크다운 보고서별 필수 마커 (내용 무관 — 양식 표식만)
_MARKERS = {
    "report1": {
        "main_heading": "📦 제품 핵심 인사이트 보고서",
        "product_label": "**제품명:**",
        "verdict_heading": "🛒 한 줄 구매 판정",
    },
    "report4": {
        "meta_box": "📊 분석 기반",
        "score_slash_10": "/ 10",
    },
}


def _markdown_fingerprint(report_kind: str, text: str) -> Dict[str, Any]:
    headings = iter_headings(text or "")
    heading_sig = sorted({f"{lv}:{txt}" for lv, txt, _ln in headings})
    tables = sorted({" | ".join(sig) for sig in table_header_columns(text or "")})
    markers = {
        name: (needle in (text or ""))
        for name, needle in _MARKERS.get(report_kind, {}).items()
    }
    return {
        "report_kind": report_kind,
        "form": "markdown",
        "headings": heading_sig,
        "tables": tables,
        "markers": markers,
    }


def _json_key_paths(obj: Any, prefix: str = "") -> List[str]:
    """dict 키 경로 집합. 리스트는 [] 로 인덱스를 추상화(원소 키는 별도 수집)."""
    paths: List[str] = []
    if isinstance(obj, dict):
        for k in obj.keys():
            p = f"{prefix}.{k}" if prefix else str(k)
            paths.append(p)
            paths.extend(_json_key_paths(obj[k], p))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                paths.extend(_json_key_paths(item, f"{prefix}[]"))
    return paths


def _list_elem_keys(obj: Any, prefix: str = "") -> Dict[str, List[str]]:
    """각 리스트 경로별 원소 dict 키 합집합. {경로[]: [정렬된 키...]}"""
    acc: Dict[str, set] = {}

    def walk(o: Any, pre: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{pre}.{k}" if pre else str(k))
        elif isinstance(o, list):
            key = f"{pre}[]"
            for item in o:
                if isinstance(item, dict):
                    acc.setdefault(key, set()).update(item.keys())
                walk(item, key)

    walk(obj, prefix)
    return {k: sorted(v) for k, v in sorted(acc.items())}


def _json_fingerprint(report_kind: str, data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {
            "report_kind": report_kind,
            "form": "json",
            "valid_dict": False,
            "key_paths": [],
            "list_elem_keys": {},
            "has_meta": False,
        }
    return {
        "report_kind": report_kind,
        "form": "json",
        "valid_dict": True,
        "key_paths": sorted(set(_json_key_paths(data))),
        "list_elem_keys": _list_elem_keys(data),
        "has_meta": isinstance(data.get("_meta"), dict),
    }


def fingerprint(report_kind: str, report: Any) -> Dict[str, Any]:
    """보고서 종류에 맞는 구조 지문 dict 를 반환한다.

    report_kind: "report1" | "report2" | "report3" | "report4"
    report     : 마크다운 문자열(①④) 또는 dict(②③).
    """
    if report_kind in ("report1", "report4"):
        return _markdown_fingerprint(report_kind, report if isinstance(report, str) else "")
    if report_kind in ("report2", "report3"):
        return _json_fingerprint(report_kind, report)
    raise ValueError(f"알 수 없는 report_kind: {report_kind!r}")


def diff_fingerprints(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    """두 지문을 비교해 사람이 읽을 차이 목록을 만든다. 차이 없으면 빈 리스트."""
    diffs: List[str] = []

    if old.get("report_kind") != new.get("report_kind"):
        diffs.append(
            f"report_kind 변경: {old.get('report_kind')} → {new.get('report_kind')}"
        )
    if old.get("form") != new.get("form"):
        diffs.append(f"form 변경: {old.get('form')} → {new.get('form')}")

    # 마크다운: headings / tables / markers
    if old.get("form") == "markdown" and new.get("form") == "markdown":
        diffs += _diff_set("헤딩", old.get("headings", []), new.get("headings", []))
        diffs += _diff_set("표 컬럼 시그니처", old.get("tables", []), new.get("tables", []))
        om, nm = old.get("markers", {}), new.get("markers", {})
        for name in sorted(set(om) | set(nm)):
            if om.get(name) != nm.get(name):
                diffs.append(
                    f"마커 '{name}' 존재여부 변경: {om.get(name)} → {nm.get(name)}"
                )

    # JSON: key_paths / list_elem_keys / has_meta
    if old.get("form") == "json" and new.get("form") == "json":
        diffs += _diff_set("키 경로", old.get("key_paths", []), new.get("key_paths", []))
        ole, nle = old.get("list_elem_keys", {}), new.get("list_elem_keys", {})
        for path in sorted(set(ole) | set(nle)):
            if ole.get(path) != nle.get(path):
                diffs.append(
                    f"리스트 '{path}' 원소 키 변경: {ole.get(path)} → {nle.get(path)}"
                )
        if old.get("has_meta") != new.get("has_meta"):
            diffs.append(
                f"_meta 존재여부 변경: {old.get('has_meta')} → {new.get('has_meta')}"
            )

    return diffs


def _diff_set(label: str, old_list, new_list) -> List[str]:
    o, n = set(old_list), set(new_list)
    out: List[str] = []
    for removed in sorted(o - n):
        out.append(f"{label} 제거됨: {removed}")
    for added in sorted(n - o):
        out.append(f"{label} 추가됨: {added}")
    return out
