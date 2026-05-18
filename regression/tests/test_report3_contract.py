from regression.contracts import validate_report3
from regression.tests._helpers import codes, load_json


def test_valid_final_fixture_ok_no_errors():
    result = validate_report3(load_json("report3", "valid"))
    assert result.is_ok
    assert result.status == "ok"
    assert result.errors == []
    assert result.warnings == []


def test_broken_fixture_missing_top_key():
    result = validate_report3(load_json("report3", "broken"))
    assert not result.is_ok
    assert "R3.MISSING_TOP_KEY" in codes(result)


def test_raw_fixture_is_ok_with_warnings():
    result = validate_report3(load_json("report3", "raw"))
    assert result.is_ok
    assert result.errors == []
    assert len(result.warnings) > 0
    w = codes(result)
    assert "R3.MISSING_META" in w
    assert "R3.MISSING_CONSUMER_COMMENTS" in w


def test_none_is_generation_failed():
    result = validate_report3(None)
    assert result.status == "generation_failed"
    assert result.is_ok
