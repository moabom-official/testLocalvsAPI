"""보고서 양식 회귀 게이트 단일 진입점 (오프라인 — DB·LLM·네트워크 없음).

  python -m regression.run_gate
  python -m regression.run_gate --report 4

판정 규칙:
  - label="valid" 픽스처가 하나라도 status="violated" 면 게이트 실패(종료 코드 1).
  - broken / generation_failed / fallback / raw 분류는 정보로만 표기하고 게이트를
    실패시키지 않는다.

Phase 1~4 작업자는 보고서 생성 코드를 바꾼 뒤 이 게이트가 초록(종료 코드 0)인지
확인하고 그 결과를 PR 에 첨부한다.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import List, Optional

from regression._fixtures import Fixture, discover_fixtures, report_kind_for


@dataclass
class GateRow:
    report_kind: str
    label: str
    status: str
    is_valid_label: bool
    n_errors: int
    n_warnings: int
    error_codes: List[str]


@dataclass
class GateReport:
    rows: List[GateRow]

    @property
    def failing(self) -> List[GateRow]:
        """게이트를 실패시키는 행 = valid 라벨인데 violated."""
        return [r for r in self.rows if r.is_valid_label and r.status == "violated"]

    @property
    def passed(self) -> bool:
        return len(self.failing) == 0

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


def collect_gate_report(only_report: Optional[str] = None) -> GateReport:
    """핵심 집계 함수 — 테스트는 이 함수를 직접 호출한다(서브프로세스 불필요)."""
    rows: List[GateRow] = []
    fixtures: List[Fixture] = discover_fixtures(only_report=only_report)
    for fx in fixtures:
        try:
            result = fx.check()
            status = result.status
            n_err = len(result.errors)
            n_warn = len(result.warnings)
            codes = [v.code for v in result.errors]
        except Exception as e:  # noqa: BLE001 — 게이트 표시용
            status = f"load_error:{type(e).__name__}"
            n_err, n_warn, codes = 1, 0, ["GATE.LOAD_ERROR"]
        rows.append(
            GateRow(
                report_kind=fx.report_kind,
                label=fx.label,
                status=status,
                is_valid_label=fx.is_valid_label,
                n_errors=n_err,
                n_warnings=n_warn,
                error_codes=codes,
            )
        )
    return GateReport(rows=rows)


def render(report: GateReport) -> str:
    lines = []
    lines.append(f"{'report':<9} {'label':<14} {'status':<18} {'E/W':<7} codes")
    lines.append("-" * 78)
    for r in report.rows:
        ew = f"{r.n_errors}/{r.n_warnings}"
        codes = ", ".join(sorted(set(r.error_codes))) if r.error_codes else "-"
        flag = "  <== 게이트 실패" if (r.is_valid_label and r.status == "violated") else ""
        lines.append(
            f"{r.report_kind:<9} {r.label:<14} {r.status:<18} {ew:<7} {codes}{flag}"
        )
    lines.append("-" * 78)
    if report.passed:
        lines.append("게이트 결과: ✅ PASS (valid 픽스처 모두 양식 보존)")
    else:
        lines.append(
            f"게이트 결과: ❌ FAIL — valid 픽스처 {len(report.failing)}건 양식 위반"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m regression.run_gate")
    p.add_argument(
        "--report", type=int, choices=(1, 2, 3, 4), default=None,
        help="특정 보고서만 검사 (미지정 시 4종 전체)",
    )
    args = p.parse_args(argv)
    only = report_kind_for(args.report) if args.report else None
    report = collect_gate_report(only_report=only)
    print(render(report))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
