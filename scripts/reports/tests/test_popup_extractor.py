"""scripts/popup/extractor.py 단위 테스트 (순수·오프라인 — LLM·DB·네트워크 0).

④ 출력 양식(prompt_manager 가 강제) 기준 픽스처로 §4 매핑 검증.
"""
from scripts.popup.extractor import (
    DATA_INSUFFICIENT,
    TIER_LABELS,
    derive_tier,
    extract_popup_data,
)


_FULL_MD = """## ① 한줄 구매 판정 + 종합 점수
- 카메라 화질과 화면 품질을 중시하면 긍정적으로 고려할 만한 제품이다
- 종합 평가: 8.2 / 10  (분석 영상 5개 기반)
- 리뷰어 합의도: 높음

## ② 핵심 요약
- [디자인] 깔끔하다
- [성능] 발열 우려
- [가성비] 평균

## ③ 6차원 종합 평가
| 차원 | 점수 | 커버리지 | 리뷰어 합의 | 핵심 코멘트 |
| --- | --- | --- | --- | --- |
| 배터리 | 7.0 | 3/5 | 중간 | 양호 |

## ④ 장점 / 단점 (합의 기반)
### 장점
- 선명한 디스플레이 (5/5)
- 안정적인 카메라 화질 (4/5)
- 깔끔한 소프트웨어 (4/5)
- 가벼움 (2/5)
### 단점
- 느린 충전 속도 (4/5)
- 부족한 기본 저장공간 (3/5)
- 다소 높은 가격 (3/5)
### 개별 리뷰어 의견
- 무음 진동 거슬림 (영상 2)
- 케이스 호환성 (영상 4)

## ⑤ 소비자 여론 (댓글 기반)
- 분석 댓글 수: 134건

## ⑥ 전작 대비 달라진 점 (표)
| 항목 | 전작 | 현재 | 변화 평가 | 언급 영상 수 |
| --- | --- | --- | --- | --- |
| 배터리 | 4000 | 5000 | 개선 | 3 |
| 발열 | — | — | 갈림 | 2 |
| 무게 | 200g | 195g | 데이터 부족 | 1 |

## ⑦ 이런 사람에게 추천 / 비추
### 추천
- 사진·영상 촬영 중시 (근거: 영상 1)
"""


# ── 기본 추출 (정상 케이스) ────────────────────────────────────


def test_full_extraction_happy_path():
    d = extract_popup_data(_FULL_MD)
    v = d["verdict"]
    assert v["score"] == "8.2"
    assert v["consensus"] == "높음"
    assert "카메라 화질" in v["one_liner"]
    # 점수 8.2 + 합의 높음 → 등급 high → 라벨 "추천" 녹색
    assert v["tier"] == "high" and v["label"] == "추천" and v["color"] == "green"
    # 영상 수
    assert d["videos_n"] == 5
    assert d["comments_n"] == 134  # §4-F ⑤ "분석 댓글 수: 134건"
    # 합의 장점 — 상위 3 (N 내림차순), 개별 의견 제외
    assert [p["label"] for p in d["pros"]] == [
        "선명한 디스플레이", "안정적인 카메라 화질", "깔끔한 소프트웨어"]
    assert d["pros"][0]["n"] == 5 and d["pros"][0]["total"] == 5
    # 합의 단점 — 정확히 3개
    assert len(d["cons"]) == 3
    assert d["cons"][0]["label"] == "느린 충전 속도"
    # 주의 노트 (⑥ "갈림"/"데이터 부족" 항목)
    assert d["caveat"]
    assert "발열" in d["caveat"] or "무게" in d["caveat"]
    # 결측 없음
    assert "verdict.score" not in d["missing"]
    assert "verdict.tier" not in d["missing"]


# ── 한 줄 결론은 첫 불릿이되 점수/합의도 라인 제외 ────────────


def test_one_liner_skips_score_and_consensus_lines():
    md = """## ① 한줄 구매 판정 + 종합 점수
- 종합 평가: 7.0 / 10  (분석 영상 3개 기반)
- 리뷰어 합의도: 중간
- 진짜 한 줄 결론이 여기 있다
"""
    d = extract_popup_data(md)
    assert d["verdict"]["one_liner"] == "진짜 한 줄 결론이 여기 있다"


# ── §4-D 등급 도출 — 모든 분기 ─────────────────────────────────


def test_derive_tier_high():
    assert derive_tier("8.0", "높음") == "high"


def test_derive_tier_mid_by_score():
    # 7.5 미만 → mid (합의 높음이어도)
    assert derive_tier("6.5", "높음") == "mid"


def test_derive_tier_mid_by_consensus():
    # 합의 중간 → mid (점수 충분해도)
    assert derive_tier("9.0", "중간") == "mid"


def test_derive_tier_low_by_consensus():
    # 합의 낮음이면 점수 무관 low
    assert derive_tier("9.5", "낮음") == "low"


def test_derive_tier_low_by_score():
    assert derive_tier("3.0", "높음") == "low"


def test_derive_tier_score_missing_consensus_only():
    assert derive_tier(DATA_INSUFFICIENT, "높음") == "high"
    assert derive_tier(DATA_INSUFFICIENT, "중간") == "mid"
    assert derive_tier(DATA_INSUFFICIENT, "낮음") == "low"


def test_derive_tier_both_missing_returns_none():
    assert derive_tier(None, None) is None
    assert derive_tier(DATA_INSUFFICIENT, None) is None


def test_tier_labels_match_user_spec():
    # 사용자 결정 — 라벨 텍스트 변경 금지
    assert TIER_LABELS["high"][0] == "추천"
    assert TIER_LABELS["mid"][0] == "조건부 추천"
    assert TIER_LABELS["low"][0] == "신중하게 고려하세요"


# ── §4-A: "데이터 부족 / 10" 케이스 ─────────────────────────────


def test_score_data_insufficient():
    md = """## ① 한줄 구매 판정 + 종합 점수
- 한 줄 결론
- 종합 평가: 데이터 부족 / 10  (분석 영상 2개 기반)
- 리뷰어 합의도: 중간
"""
    d = extract_popup_data(md)
    assert d["verdict"]["score"] == "데이터 부족"
    # 점수 결측 + 합의 중간 → mid
    assert d["verdict"]["tier"] == "mid"


# ── §4-E: "- 데이터 부족" 한 줄만 / 헤딩 누락 ──────────────────


def test_section4_data_insufficient_group():
    md = """## ④ 장점 / 단점 (합의 기반)
### 장점
- 데이터 부족
### 단점
- 그저 그렇다 (4/5)
"""
    d = extract_popup_data(md)
    # 공개 계약: pros 빈 + missing 에 'pros' 표기 (데이터 부족 한 줄 그룹)
    assert d["pros"] == []
    assert "pros" in d["missing"]
    assert len(d["cons"]) == 1


def test_section4_missing_entire_section():
    md = "## ① 한줄 구매 판정 + 종합 점수\n- 결론\n- 종합 평가: 8.0 / 10\n- 리뷰어 합의도: 높음\n"
    d = extract_popup_data(md)
    assert d["pros"] == [] and d["cons"] == []
    assert "pros" in d["missing"] and "cons" in d["missing"]


# ── §4-E: 합의 항목 3개 초과 시 N 내림차순 상위 3 ───────────────


def test_pros_top3_by_n_desc_stable():
    md = """## ④ 장점 / 단점 (합의 기반)
### 장점
- 첫번째 (2/5)
- 두번째 (5/5)
- 세번째 (3/5)
- 네번째 (5/5)
- 다섯번째 (4/5)
### 단점
- 하나 (2/5)
"""
    d = extract_popup_data(md)
    labels = [p["label"] for p in d["pros"]]
    # N 내림차순(5,5,4), 동률은 등장 순서 → 두번째 → 네번째 → 다섯번째
    assert labels == ["두번째", "네번째", "다섯번째"]


# ── §4-G: 주의 노트 — ⑥ 갈림/데이터 부족 ───────────────────────


def test_caveat_picks_ambiguous_from_section6():
    md = """## ⑥ 전작 대비 달라진 점 (표)
| 항목 | 전작 | 현재 | 변화 평가 | 언급 영상 수 |
| --- | --- | --- | --- | --- |
| 발열 | — | — | 갈림 | 2 |
| 무게 | 200g | 195g | 데이터 부족 | 1 |
"""
    d = extract_popup_data(md)
    assert d["caveat"] and ("발열" in d["caveat"] or "무게" in d["caveat"])


def test_caveat_empty_when_no_ambiguous():
    md = """## ⑥ 전작 대비 달라진 점 (표)
| 항목 | 전작 | 현재 | 변화 평가 | 언급 영상 수 |
| --- | --- | --- | --- | --- |
| 배터리 | 4000 | 5000 | 개선 | 3 |
"""
    d = extract_popup_data(md)
    assert d["caveat"] == ""


# ── 전체 실패 안전 (빈 입력) ───────────────────────────────────


# ── 보강 3: '한 문장 결론:' 등 접두어 결정론적 제거 ─────────────


def test_oneliner_prefix_stripped_korean_variants():
    for prefix in (
        "한 문장 결론: ",
        "한문장결론:",
        "한 줄 결론 : ",
        "한줄 결론: ",
        "결론: ",
        "판정: ",
        "한 문장 결론：",  # 전각 콜론
    ):
        md = (
            "## ① 한줄 구매 판정 + 종합 점수\n"
            f"- {prefix}진짜 결론 텍스트\n"
            "- 종합 평가: 7.0 / 10  (분석 영상 3개 기반)\n"
            "- 리뷰어 합의도: 중간\n"
        )
        d = extract_popup_data(md)
        assert d["verdict"]["one_liner"] == "진짜 결론 텍스트", f"prefix={prefix!r}"


def test_oneliner_no_prefix_passes_through():
    md = """## ① 한줄 구매 판정 + 종합 점수
- 접두어 없이 그냥 결론 문장이다
- 종합 평가: 8.0 / 10
- 리뷰어 합의도: 높음
"""
    d = extract_popup_data(md)
    assert d["verdict"]["one_liner"] == "접두어 없이 그냥 결론 문장이다"


# ── 보강 4: ⑦ 페르소나 → 두 줄 템플릿 (LLM 0건) ──────────────────


_BASE_FOR_TIER = """## ① 한줄 구매 판정 + 종합 점수
- 한 줄 결론(폴백용)
- 종합 평가: 8.0 / 10  (분석 영상 5개 기반)
- 리뷰어 합의도: 높음
"""


def test_two_line_desc_both_personas_present():
    md = _BASE_FOR_TIER + """
## ⑦ 이런 사람에게 추천 / 비추
### 추천
- 카메라 화질과 화면 품질 (근거: 영상 1, 2, 3)
- 디자인 중시 (근거: 영상 2)
### 비추
- 게이밍 성능 (근거: 영상 4)
- 가성비 최우선 (근거: 영상 5)
"""
    d = extract_popup_data(md)
    v = d["verdict"]
    # 첫 페르소나만 채택
    assert v["recommend_persona"] == "카메라 화질과 화면 품질"
    assert v["not_recommend_persona"] == "게이밍 성능"
    # 받침 처리: '품질'(받침 ㄹ) → 을 / '성능'(받침 ㅇ) → 이
    assert v["one_liner_main"] == "카메라 화질과 화면 품질을 중시한다면 긍정적으로 고려하세요."
    assert v["one_liner_sub"] == "게이밍 성능이 최우선이라면 유사 제품과 비교를 권합니다."


def test_two_line_josa_no_jongseong():
    # 받침 없는 마지막 음절('시')·('야') → 를/가
    md = _BASE_FOR_TIER + """
## ⑦ 이런 사람에게 추천 / 비추
### 추천
- 사진 촬영 중시 (근거: 영상 1)
### 비추
- 야간 카메라 (근거: 영상 2)
"""
    d = extract_popup_data(md)
    v = d["verdict"]
    # '중시'의 '시'는 받침 X → 를
    assert v["one_liner_main"].startswith("사진 촬영 중시를 중시한다면")
    # '야간 카메라'의 '라'는 받침 X → 가
    assert v["one_liner_sub"].startswith("야간 카메라가 최우선이라면")


def test_two_line_only_recommend_then_sub_empty():
    md = _BASE_FOR_TIER + """
## ⑦ 이런 사람에게 추천 / 비추
### 추천
- 디자인 (근거: 영상 1)
### 비추
- 데이터 부족
"""
    d = extract_popup_data(md)
    v = d["verdict"]
    assert v["recommend_persona"] == "디자인"
    assert v["not_recommend_persona"] is None
    assert "디자인" in v["one_liner_main"]
    assert v["one_liner_sub"] == ""    # 억지 생성 금지


def test_two_line_only_not_recommend_main_falls_back_to_oneliner():
    md = _BASE_FOR_TIER + """
## ⑦ 이런 사람에게 추천 / 비추
### 추천
- 데이터 부족
### 비추
- 게이밍 성능 (근거: 영상 1)
"""
    d = extract_popup_data(md)
    v = d["verdict"]
    assert v["recommend_persona"] is None
    assert v["not_recommend_persona"] == "게이밍 성능"
    # 윗줄은 한 줄 결론 fallback
    assert v["one_liner_main"] == "한 줄 결론(폴백용)"
    assert "게이밍 성능이" in v["one_liner_sub"]


def test_two_line_both_missing_fallback_to_oneliner():
    md = _BASE_FOR_TIER + """
## ⑦ 이런 사람에게 추천 / 비추
### 추천
- 데이터 부족
### 비추
- 데이터 부족
"""
    d = extract_popup_data(md)
    v = d["verdict"]
    assert v["one_liner_main"] == "한 줄 결론(폴백용)"
    assert v["one_liner_sub"] == ""


def test_two_line_section7_absent_fallback():
    d = extract_popup_data(_BASE_FOR_TIER)
    v = d["verdict"]
    # ⑦ 자체가 없음 → 윗줄 = 한 줄 결론, 아랫줄 빈 값
    assert v["one_liner_main"] == "한 줄 결론(폴백용)"
    assert v["one_liner_sub"] == ""


def test_two_line_english_persona_conservative_josa():
    # 페르소나가 영문/숫자로 끝나면 보수적으로 받침 있음 처리 → 을/이
    md = _BASE_FOR_TIER + """
## ⑦ 이런 사람에게 추천 / 비추
### 추천
- iOS 18 신기능 (근거: 영상 1)
### 비추
- AAA 게임 60fps (근거: 영상 2)
"""
    d = extract_popup_data(md)
    v = d["verdict"]
    assert v["one_liner_main"].startswith("iOS 18 신기능을 중시한다면")
    assert v["one_liner_sub"].startswith("AAA 게임 60fps이 최우선이라면")


def test_empty_input_no_crash_all_missing():
    d = extract_popup_data("")
    assert d["verdict"]["score"] is None
    assert d["verdict"]["consensus"] is None
    assert d["verdict"]["tier"] is None
    assert d["pros"] == [] and d["cons"] == []
    assert "verdict.score" in d["missing"]
    assert "verdict.tier" in d["missing"]
