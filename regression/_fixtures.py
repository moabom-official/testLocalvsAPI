"""골든 픽스처 로딩·검증 공통 유틸 (오프라인 — DB·LLM·네트워크 없음).

snapshot_cli 와 run_gate 가 공유한다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, List, Optional

from regression.contracts import (
    ContractResult,
    validate_report1,
    validate_report2,
    validate_report3,
    validate_report4,
)
from regression.fingerprint import fingerprint

GOLDEN_ROOT = os.path.join(os.path.dirname(__file__), "golden")

REPORT_KINDS = ("report1", "report2", "report3", "report4")
# 마크다운(텍스트) 보고서 vs JSON 보고서
MARKDOWN_KINDS = ("report1", "report4")
JSON_KINDS = ("report2", "report3")

_VALIDATORS = {
    "report1": validate_report1,
    "report2": validate_report2,
    "report3": validate_report3,
    "report4": validate_report4,
}


def report_kind_for(n: int) -> str:
    if n not in (1, 2, 3, 4):
        raise ValueError(f"report 번호는 1~4 여야 합니다: {n}")
    return f"report{n}"


def ext_for(report_kind: str) -> str:
    return "md" if report_kind in MARKDOWN_KINDS else "json"


def load_report(report_kind: str, path: str) -> Any:
    """파일을 보고서 종류에 맞는 형태(str 또는 dict)로 로드."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if report_kind in JSON_KINDS:
        return json.loads(text)
    return text


def validate(report_kind: str, report: Any) -> ContractResult:
    return _VALIDATORS[report_kind](report)


@dataclass
class Fixture:
    report_kind: str
    label: str
    path: str

    @property
    def is_valid_label(self) -> bool:
        return self.label == "valid"

    def load(self) -> Any:
        return load_report(self.report_kind, self.path)

    def check(self) -> ContractResult:
        return validate(self.report_kind, self.load())

    def fingerprint(self) -> dict:
        return fingerprint(self.report_kind, self.load())


def discover_fixtures(only_report: Optional[str] = None) -> List[Fixture]:
    """golden/ 의 모든 픽스처를 찾는다. *.meta.json 은 제외."""
    out: List[Fixture] = []
    for kind in REPORT_KINDS:
        if only_report and kind != only_report:
            continue
        d = os.path.join(GOLDEN_ROOT, kind)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".meta.json"):
                continue
            stem, ext = os.path.splitext(fn)
            if ext.lstrip(".") not in ("md", "json"):
                continue
            out.append(Fixture(report_kind=kind, label=stem, path=os.path.join(d, fn)))
    return out
