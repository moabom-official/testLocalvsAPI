from regression.contracts import validate_report1
from regression.tests._helpers import codes, load_text


def test_valid_fixture_is_ok():
    result = validate_report1(load_text("report1", "valid"))
    assert result.is_ok
    assert result.status == "ok"
    assert result.errors == []


def test_broken_fixture_detected():
    result = validate_report1(load_text("report1", "broken"))
    assert not result.is_ok
    assert result.status == "violated"
    assert "R1.MISSING_SECTION" in codes(result)


def test_error_string_is_generation_failed():
    result = validate_report1("[ERROR] Transcript report generation failed: boom")
    assert result.status == "generation_failed"
    assert result.is_ok  # 양식 위반 아님 — 게이트 하드 실패 대상 아님


def test_no_transcript_is_generation_failed():
    result = validate_report1("No transcript content available.")
    assert result.status == "generation_failed"


def test_missing_main_heading_flagged():
    text = load_text("report1", "valid").replace(
        "## 📦 제품 핵심 인사이트 보고서", "## 다른 제목"
    )
    result = validate_report1(text)
    assert "R1.MISSING_MAIN_HEADING" in codes(result)
