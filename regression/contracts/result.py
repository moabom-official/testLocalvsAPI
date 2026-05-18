"""계약 검증 공통 타입 — Violation / ContractResult.

검증기는 절대 예외를 던지지 않고 항상 ContractResult 를 반환한다.
status 분류:
  - "ok"                : 양식 위반 없음 (error severity 위반 0)
  - "violated"          : error severity 위반이 1개 이상 — 게이트 하드 실패 대상
  - "generation_failed" : 보고서 생성 자체가 실패한 산출물 ([ERROR]/None 등). 양식
                          위반이 아니므로 게이트를 하드 실패시키지 않는다.
  - "fallback"          : 휴리스틱 폴백 산출물 (보고서 ④ LLM 미사용 모드). 정식
                          7섹션 계약 대상이 아니므로 게이트 하드 실패 대상이 아니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

VALID_STATUSES = ("ok", "violated", "generation_failed", "fallback")
VALID_SEVERITIES = ("error", "warning")


@dataclass
class Violation:
    """단일 양식 위반 1건.

    code     : 기계 판별용 위반 코드 (예: "R4.MISSING_SECTION").
    message  : 사람이 읽을 한국어 설명.
    severity : "error" (양식 깨짐, 게이트 실패) | "warning" (참고 — 게이트 통과).
    """

    code: str
    message: str
    severity: str = "error"

    def __post_init__(self) -> None:
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"severity 는 {VALID_SEVERITIES} 중 하나여야 합니다: {self.severity!r}")

    def __str__(self) -> str:
        mark = "✗" if self.severity == "error" else "△"
        return f"{mark} [{self.code}] {self.message}"


@dataclass
class ContractResult:
    """한 보고서 산출물에 대한 계약 검증 결과.

    status 는 명시적으로 지정하거나(generation_failed / fallback), 지정하지 않으면
    violations 의 severity 로부터 자동 결정한다(error 있으면 violated, 없으면 ok).
    """

    report_kind: str
    status: str = "ok"
    violations: List[Violation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status 는 {VALID_STATUSES} 중 하나여야 합니다: {self.status!r}")

    def add(self, code: str, message: str, severity: str = "error") -> "ContractResult":
        """위반 1건을 추가하고 self 를 반환(체이닝용)."""
        self.violations.append(Violation(code=code, message=message, severity=severity))
        return self

    def finalize(self) -> "ContractResult":
        """status 가 ok/violated 인 경우에 한해 error 위반 유무로 재판정한다.

        generation_failed / fallback 은 검증기가 이미 명시적으로 정한 분류이므로
        건드리지 않는다.
        """
        if self.status in ("generation_failed", "fallback"):
            return self
        self.status = "violated" if self.has_errors else "ok"
        return self

    @property
    def has_errors(self) -> bool:
        return any(v.severity == "error" for v in self.violations)

    @property
    def warnings(self) -> List[Violation]:
        return [v for v in self.violations if v.severity == "warning"]

    @property
    def errors(self) -> List[Violation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def is_ok(self) -> bool:
        """게이트 통과 여부.

        ok / generation_failed / fallback 은 통과(게이트 하드 실패 아님).
        violated 만 실패. (generation_failed·fallback 은 정보로만 표기한다.)
        """
        return self.status != "violated"

    def summary(self) -> str:
        """사람이 읽을 한 줄 요약."""
        n_err = len(self.errors)
        n_warn = len(self.warnings)
        return (
            f"[{self.report_kind}] status={self.status} "
            f"errors={n_err} warnings={n_warn}"
        )

    def detail(self) -> str:
        """위반 목록까지 포함한 여러 줄 출력."""
        lines = [self.summary()]
        for v in self.violations:
            lines.append(f"  {v}")
        return "\n".join(lines)
