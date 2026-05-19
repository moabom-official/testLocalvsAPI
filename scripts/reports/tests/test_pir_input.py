"""scripts/reports/_pir_input.py 단위 테스트 (순수 단계 — DB·LLM 없음).

Phase 2-a: ④ 입력 ①②③ 종합 파이프라인. 노드 친화(수집/직렬화/절삭/조립
분리) 검증.
"""
from scripts.reports._pir_input import (
    R1_MAX_CHARS,
    assemble_input_blocks,
    serialize_bundles,
    serialize_report2,
    serialize_report3,
    truncate_bundles,
)

CR = {
    "sentiment_summary": {"positive_pct": 60.0, "neutral_pct": 25.0,
                          "negative_pct": 15.0, "one_line_mood": "대체로 호평"},
    "positive_points": [{"aspect_name": "디스플레이", "summary_line": "밝다",
                         "comment_count": 12}],
    "negative_points": [{"aspect_name": "발열", "summary_line": "뜨겁다",
                         "comment_count": 5}],
    "top_issues": [{"keyword": "발열", "count": 5}],
}
IR = {
    "verdict": {"trust_score": 78, "summary": "대체로 일치"},
    "agreement_points": [{"topic": "화면", "reviewer_quote": "밝다"}],
    "disagreement_points": [{"topic": "가격", "gap_type": "opposite",
                             "reviewer_quote": "비싸다"}],
    "spec_changes": [{"spec_name": "배터리", "before": "4000", "after": "5000",
                      "delta": "+1000"}],
    "reviewer_only": ["방수"], "consumer_only": ["케이스"],
}


def test_serialize_report2_faithful():
    s = serialize_report2(CR)
    assert "긍정 60.0%" in s and "디스플레이" in s and "발열" in s
    assert serialize_report2(None) == ""
    assert serialize_report2({}) == ""


def test_serialize_report3_faithful():
    s = serialize_report3(IR)
    assert "신뢰도 78" in s and "화면" in s and "배터리" in s
    assert "방수" in s and "케이스" in s
    assert serialize_report3(None) == ""


def test_serialize_bundles_adds_text_keys_preserves_dicts():
    bundles = [{"video_id": "v1", "title": "T", "transcript_report": "① 본문",
                "comment_report": CR, "integrated_report": IR}]
    out = serialize_bundles(bundles)
    assert out[0]["comment_text"] and out[0]["integrated_text"]
    assert out[0]["comment_report"] == CR  # 원본 dict 보존
    assert out[0]["transcript_report"] == "① 본문"


def test_truncate_caps_and_no_zeroing():
    big = "가" * 9000
    bundles = [{"video_id": "v1", "title": "T", "transcript_report": big,
                "comment_text": big, "integrated_text": big}]
    out, m = truncate_bundles(bundles)
    b = out[0]
    assert 0 < len(b["transcript_report"]) <= R1_MAX_CHARS + 20
    # 어떤 보고서도 통째로 0 이 되면 안 된다
    assert len(b["comment_text"]) > 0 and len(b["integrated_text"]) > 0
    assert m["cut_chars"]["r1"] > 0


def test_truncate_proportional_shrink_on_total_overflow():
    big = "가" * 5000
    bundles = [{"video_id": f"v{i}", "title": "T", "transcript_report": big,
                "comment_text": big, "integrated_text": big} for i in range(30)]
    out, m = truncate_bundles(bundles)
    assert m["proportional_shrink"] is True
    assert m["total_chars_after"] <= m["total_cap"]
    for b in out:  # 0 방지
        assert len(b["transcript_report"]) > 0


def test_assemble_preserves_video_boundary_and_ids():
    bundles = [
        {"video_id": "vidA", "title": "리뷰A", "transcript_report": "①A",
         "comment_text": "②A", "integrated_text": "③A"},
        {"video_id": "vidB", "title": "리뷰B", "transcript_report": "①B",
         "comment_text": "", "integrated_text": ""},
    ]
    txt = assemble_input_blocks(bundles)
    assert "video_id=vidA" in txt and "video_id=vidB" in txt
    assert "리뷰A" in txt and "리뷰B" in txt
    assert "① 자막 기반 보고서" in txt and "② 댓글 기반 분석" in txt
    assert "③ 자막+댓글 통합 분석" in txt
    assert "[영상 1 " in txt and "[영상 2 " in txt
    # ②③ 비어도 (없음) 으로 진행 (안전 퇴화)
    assert "(없음)" in txt
