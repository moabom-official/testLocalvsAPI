"""scripts/reports/_verification.py 단위 테스트.

LLM 호출은 주입 가능(llm_call) — 실제 네트워크·DB·LLM 없이 전 시나리오 검증.
"""
import json

import pytest

from scripts.reports._verification import (
    LLMResult,
    VerificationConfig,
    code_gate_report4_consumer,
    numeric_token_gate,
    verify_json_report,
    verify_markdown_report,
)

ON = VerificationConfig(enabled=True, critique_rounds=1, recritique=False)
OFF = VerificationConfig(enabled=False)


class FakeLLM:
    """system 프롬프트로 비평/수정을 구분하는 스크립트형 가짜 LLM."""

    def __init__(self, critique_issues=None, revised=None,
                 critique_raises=False, revise_raises=False):
        self.critique_issues = critique_issues or []
        self.revised = revised
        self.critique_raises = critique_raises
        self.revise_raises = revise_raises
        self.calls = {"critique": 0, "revise": 0}

    def __call__(self, messages, *, temperature, max_tokens, json_mode=False):
        sys_prompt = messages[0]["content"]
        if "사실검증관" in sys_prompt:
            self.calls["critique"] += 1
            if self.critique_raises:
                raise RuntimeError("critique boom")
            return LLMResult(
                content=json.dumps({"issues": self.critique_issues}),
                prompt_tokens=11, completion_tokens=7,
            )
        if "교정자" in sys_prompt:
            self.calls["revise"] += 1
            if self.revise_raises:
                raise RuntimeError("revise boom")
            return LLMResult(content=self.revised, prompt_tokens=13, completion_tokens=9)
        raise AssertionError("예상치 못한 프롬프트")


def always_ok(_x):
    return True


def always_bad(_x):
    return False


# ── §4-1: 설정 off → Phase 1 이전과 동일 ───────────────────────


def test_disabled_returns_draft_no_llm():
    llm = FakeLLM(critique_issues=[{"claim": "x", "reason": "y"}])
    vr = verify_markdown_report(
        "report1", "DRAFT", "GROUND",
        llm_call=llm, config=OFF, format_validator=always_ok,
    )
    assert vr.output == "DRAFT"
    assert vr.perf.skipped is True
    assert vr.perf.enabled is False
    assert llm.calls == {"critique": 0, "revise": 0}


def test_global_env_off(monkeypatch):
    monkeypatch.setenv("REPORT_VERIFICATION_ENABLED", "0")
    llm = FakeLLM(critique_issues=[{"claim": "x", "reason": "y"}])
    vr = verify_markdown_report(
        "report1", "DRAFT", "GROUND",
        llm_call=llm, config=ON, format_validator=always_ok,
    )
    assert vr.output == "DRAFT"
    assert vr.perf.skipped is True
    assert llm.calls["critique"] == 0


# ── §4-4: 비평 0건 → 수정 호출 생략 ────────────────────────────


def test_clean_critique_skips_revise():
    llm = FakeLLM(critique_issues=[])
    vr = verify_markdown_report(
        "report1", "DRAFT", "GROUND",
        llm_call=llm, config=ON, format_validator=always_ok,
    )
    assert vr.output == "DRAFT"
    assert vr.applied is False
    assert llm.calls["critique"] == 1
    assert llm.calls["revise"] == 0


# ── 비평 issue 있음 → 수정 채택 ────────────────────────────────


def test_issues_lead_to_accepted_revision():
    llm = FakeLLM(
        critique_issues=[{"claim": "169만원", "reason": "입력에 없음"}],
        revised="REVISED-OK",
    )
    vr = verify_markdown_report(
        "report1", "DRAFT", "GROUND",
        llm_call=llm, config=ON, format_validator=always_ok,
    )
    assert vr.output == "REVISED-OK"
    assert vr.applied is True
    assert vr.perf.revise_applied is True
    assert llm.calls["revise"] == 1
    assert vr.perf.prompt_tokens > 0  # §4-2 토큰 측정


# ── 수정본 양식 위반 → 초안 채택(퇴화) ─────────────────────────


def test_revision_format_violation_degrades_to_draft():
    llm = FakeLLM(
        critique_issues=[{"claim": "a", "reason": "b"}], revised="BROKEN",
    )
    vr = verify_markdown_report(
        "report1", "DRAFT", "GROUND",
        llm_call=llm, config=ON, format_validator=always_bad,
    )
    assert vr.output == "DRAFT"
    assert vr.perf.revise_rejected is True
    assert vr.applied is False


# ── 비평/수정 LLM 예외 → 초안 채택(퇴화) ───────────────────────


def test_critique_exception_degrades():
    llm = FakeLLM(critique_raises=True)
    vr = verify_markdown_report(
        "report1", "DRAFT", "GROUND",
        llm_call=llm, config=ON, format_validator=always_ok,
    )
    assert vr.output == "DRAFT"
    assert vr.perf.critique_failed is True
    assert llm.calls["revise"] == 0


def test_revise_exception_degrades():
    llm = FakeLLM(
        critique_issues=[{"claim": "a", "reason": "b"}], revise_raises=True,
    )
    vr = verify_markdown_report(
        "report1", "DRAFT", "GROUND",
        llm_call=llm, config=ON, format_validator=always_ok,
    )
    assert vr.output == "DRAFT"
    assert vr.perf.revise_failed is True


# ── JSON 보고서(②③): 수정본 스키마 검증 ───────────────────────


def test_json_revision_invalid_json_degrades():
    llm = FakeLLM(
        critique_issues=[{"claim": "a", "reason": "b"}],
        revised="NOT-JSON",
    )
    draft = {"sentiment_summary": {}}
    vr = verify_json_report(
        "report2", draft, grounding="G",
        format_validator=always_ok, llm_call=llm, config=ON,
    )
    assert vr.output == draft
    assert vr.perf.revise_rejected is True


def test_json_revision_accepted_when_valid():
    revised = {"sentiment_summary": {"ok": 1}}
    llm = FakeLLM(
        critique_issues=[{"claim": "a", "reason": "b"}],
        revised=json.dumps(revised),
    )
    vr = verify_json_report(
        "report2", {"sentiment_summary": {}}, grounding="G",
        format_validator=always_ok, llm_call=llm, config=ON,
    )
    assert vr.output == revised
    assert vr.applied is True


# ── §4-3: 코드 게이트 — ④ ⑤섹션 수치 대조 ─────────────────────


def test_code_gate_detects_count_mismatch():
    draft = (
        "## ⑤ 소비자 여론 (댓글 기반)\n"
        "- 분석 댓글 수: 99건\n"
        "- 가중 비율: 긍정 60.0% / 중립 20.0% / 부정 20.0%\n"
    )
    agg = {
        "total_analyzed_comments": 134,
        "weighted_ratio": {"positive_pct": 60.0, "neutral_pct": 20.0, "negative_pct": 20.0},
    }
    issues = code_gate_report4_consumer(draft, agg)
    assert any("분석 댓글 수 불일치" in i for i in issues)


def test_code_gate_detects_ratio_mismatch():
    draft = (
        "- 분석 댓글 수: 134건\n"
        "- 가중 비율: 긍정 10.0% / 중립 10.0% / 부정 80.0%\n"
    )
    agg = {
        "total_analyzed_comments": 134,
        "weighted_ratio": {"positive_pct": 60.0, "neutral_pct": 20.0, "negative_pct": 20.0},
    }
    issues = code_gate_report4_consumer(draft, agg)
    assert any("가중 비율 불일치" in i for i in issues)


def test_code_gate_clean_when_matching():
    draft = (
        "- 분석 댓글 수: 134건\n"
        "- 가중 비율: 긍정 60.0% / 중립 20.0% / 부정 20.0%\n"
    )
    agg = {
        "total_analyzed_comments": 134,
        "weighted_ratio": {"positive_pct": 60.0, "neutral_pct": 20.0, "negative_pct": 20.0},
    }
    assert code_gate_report4_consumer(draft, agg) == []


def test_code_gate_skips_when_no_aggregate():
    assert code_gate_report4_consumer("아무 텍스트", None) == []
    assert code_gate_report4_consumer("x", {"total_analyzed_comments": 0}) == []


def test_code_gate_flags_false_data_insufficient():
    draft = "## ⑤ 소비자 여론 (댓글 기반)\n- 데이터 부족 (분석 가능한 댓글 없음)\n"
    agg = {"total_analyzed_comments": 50, "weighted_ratio": {}}
    issues = code_gate_report4_consumer(draft, agg)
    assert issues and "데이터 부족" in issues[0]


# ── §4-3: 범용 수치 토큰 게이트 (힌트) ─────────────────────────


def test_numeric_token_gate_flags_absent_number():
    hints = numeric_token_gate("배터리 12시간 지속, 가격 169만원", "배터리가 12시간 간다")
    assert any("169" in h for h in hints)
    assert not any("12시간" in h for h in hints)  # 입력에 있음 → 후보 아님


def test_numeric_token_gate_empty_grounding():
    assert numeric_token_gate("169만원", "") == []


# ── §4-2: perf 측정 항목 채워짐 ────────────────────────────────


def test_perf_fields_populated_on_revision():
    llm = FakeLLM(
        critique_issues=[{"claim": "a", "reason": "b"}], revised="R",
    )
    vr = verify_markdown_report(
        "report4", "DRAFT", "GROUND",
        llm_call=llm, config=ON, format_validator=always_ok,
    )
    d = vr.perf.to_dict()
    for k in ("enabled", "critique_calls", "revise_calls", "total_ms",
              "prompt_tokens", "completion_tokens", "code_gate_issues"):
        assert k in d
    assert d["critique_calls"] == 1 and d["revise_calls"] == 1
    assert d["total_ms"] >= 0
