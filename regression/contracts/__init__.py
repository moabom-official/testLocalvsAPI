"""포맷 계약 검증기 모음.

각 검증기는 예외를 던지지 않고 항상 ContractResult 를 반환한다.
"""
from regression.contracts.result import ContractResult, Violation
from regression.contracts.report1_contract import validate_report1
from regression.contracts.report2_contract import validate_report2
from regression.contracts.report3_contract import validate_report3
from regression.contracts.report4_contract import validate_report4

__all__ = [
    "ContractResult",
    "Violation",
    "validate_report1",
    "validate_report2",
    "validate_report3",
    "validate_report4",
]
