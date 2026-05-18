"""검증 자산 import-격리 어댑터.

문제: scripts.reports._comment_aggregator 의
REQUIRED_REPORT{2,3}_* 상수와 validate_report{2,3}_json 함수는 DB 를 전혀
쓰지 않는 순수 코드지만, 같은 파일이 모듈 최상단에서
`from scripts.database.queries import ...` 를 하고 그 체인이
`import psycopg2` / `from dotenv import load_dotenv` 까지 끌고 온다.
→ 운영 DB 의존성이 없는 깨끗한 환경에서 import 만으로 ModuleNotFoundError.

해결: _comment_aggregator 를 import 하기 직전, **설치돼 있지 않은** 외부 모듈만
무해한 stub 으로 sys.modules 에 주입한다(psycopg2 / psycopg2.extras / dotenv).
이 stub 들은 검증 경로에서 절대 호출되지 않는다(검증 함수는 DB 미사용). 실제
모듈이 설치돼 있으면 stub 을 만들지 않으므로 운영 동작은 영향받지 않는다.

이 어댑터는 scripts/ 하위를 한 줄도 수정하지 않고, 검증 상수·로직을 여전히
_comment_aggregator 단일 진실 공급원에서 그대로 재사용한다(복붙 없음).
"""
from __future__ import annotations

import sys
import types


def _ensure_stub(name: str, builder) -> None:
    """name 모듈이 import 불가할 때만 stub 을 sys.modules 에 등록한다."""
    if name in sys.modules:
        return
    try:
        __import__(name)
        return  # 실제 모듈 존재 — 손대지 않는다
    except ImportError:
        builder()


def _stub_dotenv() -> None:
    m = types.ModuleType("dotenv")

    def load_dotenv(*_args, **_kwargs):  # noqa: D401 — no-op
        return False

    m.load_dotenv = load_dotenv
    sys.modules["dotenv"] = m


def _stub_psycopg2() -> None:
    base = types.ModuleType("psycopg2")
    extras = types.ModuleType("psycopg2.extras")

    class RealDictCursor:  # queries.py 가 import 만 함 — 검증 경로에서 미사용
        pass

    extras.RealDictCursor = RealDictCursor

    def _unavailable(*_args, **_kwargs):
        raise RuntimeError(
            "regression 안전망은 오프라인 전용입니다 — psycopg2 stub 은 "
            "DB 접속에 사용할 수 없습니다."
        )

    base.connect = _unavailable
    base.extras = extras
    sys.modules["psycopg2"] = base
    sys.modules["psycopg2.extras"] = extras


_ensure_stub("dotenv", _stub_dotenv)
_ensure_stub("psycopg2", _stub_psycopg2)

# stub 주입 후 — 검증 자산을 단일 진실 공급원에서 그대로 재사용.
from scripts.reports._comment_aggregator import (  # noqa: E402
    REQUIRED_REPORT2_POINT_KEYS,
    REQUIRED_REPORT2_SENT_KEYS,
    REQUIRED_REPORT2_TOP_KEYS,
    REQUIRED_REPORT3_AGREE_KEYS,
    REQUIRED_REPORT3_DISAGREE_KEYS,
    REQUIRED_REPORT3_FALLBACK_KEYS,
    REQUIRED_REPORT3_QUESTION_KEYS,
    REQUIRED_REPORT3_SPEC_KEYS,
    REQUIRED_REPORT3_TOP_KEYS,
    REQUIRED_REPORT3_VERDICT_KEYS,
    validate_report2_json,
    validate_report3_json,
)

__all__ = [
    "REQUIRED_REPORT2_TOP_KEYS",
    "REQUIRED_REPORT2_SENT_KEYS",
    "REQUIRED_REPORT2_POINT_KEYS",
    "REQUIRED_REPORT3_TOP_KEYS",
    "REQUIRED_REPORT3_AGREE_KEYS",
    "REQUIRED_REPORT3_DISAGREE_KEYS",
    "REQUIRED_REPORT3_VERDICT_KEYS",
    "REQUIRED_REPORT3_SPEC_KEYS",
    "REQUIRED_REPORT3_QUESTION_KEYS",
    "REQUIRED_REPORT3_FALLBACK_KEYS",
    "validate_report2_json",
    "validate_report3_json",
]
