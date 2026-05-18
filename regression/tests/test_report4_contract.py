from regression.contracts import validate_report4
from regression.tests._helpers import codes, load_text


def test_valid_fixture_is_ok():
    result = validate_report4(load_text("report4", "valid"))
    assert result.is_ok
    assert result.status == "ok"
    assert result.errors == []


def test_broken_fixture_table3_columns_changed():
    result = validate_report4(load_text("report4", "broken"))
    assert not result.is_ok
    assert result.status == "violated"
    assert "R4.MISSING_TABLE3" in codes(result)


def test_fallback_fixture_classified_fallback():
    result = validate_report4(load_text("report4", "fallback"))
    assert result.status == "fallback"
    assert result.is_ok  # 폴백 — 게이트 하드 실패 대상 아님


def test_error_string_is_generation_failed():
    result = validate_report4("[ERROR] 입력 보고서가 없습니다.")
    assert result.status == "generation_failed"
    assert result.is_ok


def test_missing_section_flagged():
    text = load_text("report4", "valid").replace(
        "## ⑦ 이런 사람에게 추천 / 비추", "## 추천/비추"
    )
    result = validate_report4(text)
    assert "R4.MISSING_SECTION" in codes(result)


def test_consumer_empty_skips_h3_check():
    text = load_text("report4", "valid")
    head, _, _tail = text.partition("## ⑤ 소비자 여론 (댓글 기반)")
    rebuilt = (
        head
        + "## ⑤ 소비자 여론 (댓글 기반)\n- 데이터 부족 (분석 가능한 댓글 없음)\n\n"
        + "## ⑥ 전작 대비 달라진 점 (표)"
        + text.split("## ⑥ 전작 대비 달라진 점 (표)", 1)[1]
    )
    result = validate_report4(rebuilt)
    # ⑤ H3 누락이어도 데이터 부족 패턴이면 검사 생략 → 그 항목 위반 없음
    assert not any(
        v.code == "R4.MISSING_SUBHEADING" and "⑤" in v.message
        for v in result.violations
    )
