from regression.contracts import validate_report2
from regression.tests._helpers import codes, load_json


def test_valid_final_fixture_ok_no_errors():
    result = validate_report2(load_json("report2", "valid"))
    assert result.is_ok
    assert result.status == "ok"
    assert result.errors == []
    assert result.warnings == []  # 최종 형태 — 2차 warning 도 없음


def test_broken_fixture_missing_top_key():
    result = validate_report2(load_json("report2", "broken"))
    assert not result.is_ok
    assert "R2.MISSING_TOP_KEY" in codes(result)


def test_raw_fixture_is_ok_with_warnings():
    result = validate_report2(load_json("report2", "raw"))
    assert result.is_ok  # raw 도 게이트 통과 (error 0)
    assert result.errors == []
    assert len(result.warnings) > 0
    w = codes(result)
    assert "R2.MISSING_META" in w
    assert "R2.MISSING_REP_COMMENTS" in w


def test_none_is_generation_failed():
    result = validate_report2(None)
    assert result.status == "generation_failed"
    assert result.is_ok
