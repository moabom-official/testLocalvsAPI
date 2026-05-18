"""저장소 루트를 sys.path 에 추가 — scripts/regression import 가능하게.

검증 모듈 테스트는 DB·네트워크·실제 LLM 없이 통과해야 한다.
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
