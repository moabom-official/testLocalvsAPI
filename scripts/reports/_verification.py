"""보고서 4종 공용 다중 LLM 검증 모듈 (Phase 1).

목적: 보고서 내용의 환각(입력 자막·댓글에 근거 없는 사실·수치·비교) 최소화.
양식(섹션·헤딩·표·JSON 키)은 절대 바꾸지 않는다 — 바뀌는 것은 "내용 정확도"뿐.

표준 패턴 (§3):  생성 → 코드 게이트 → 비평 → 수정
  [1] 생성     : 호출부가 기존 방식대로 초안을 만든다 (이 모듈 밖).
  [2] 코드 게이트: LLM 없이 결정론적으로 잡히는 위반을 먼저 거른다 (싸다).
  [3] 비평     : 별도 LLM 호출. 초안 ↔ 입력 대조로 근거 없는 주장을 찾는다.
  [4] 수정     : 코드 게이트·비평이 0건이면 초안 그대로 (수정 LLM 호출 없음).
                 0건이 아니면 1회 수정 — 지적된 부분만 덜어내고 양식은 불변.

비용·지연 통제 4원칙 (§4):
  4-1 보고서별 검증 설정 분리 (REPORT_VERIFICATION_CONFIG / 전역 off 스위치)
  4-2 검증 perf 측정 (VerificationPerf — 전역 없이 반환값으로 전달)
  4-3 LLM 비평 앞 코드 게이트 (④ ⑤섹션 수치 대조 필수 + 범용 수치 토큰 게이트)
  4-4 비평 0건 시 수정 LLM 호출 생략

설계 제약 (§7 — Phase 4 LangGraph 노드 흡수 대비):
  - 각 단계(코드게이트/비평/수정)가 독립 호출 가능한 순수 함수.
  - 전역 상태 의존·변경 없음. LLM 호출은 주입 가능(llm_call 인자).
  - 부수효과(DB/파일 IO) 없음 — LLM 호출만.
  - 단계 간 상태는 인자·반환값으로 명시 전달 (숨은 통로 없음).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── 4-1. 보고서별 검증 설정 ──────────────────────────────────────


@dataclass
class VerificationConfig:
    """보고서 1종의 검증 강도. 한 곳(REPORT_VERIFICATION_CONFIG)에서만 본다."""

    enabled: bool = True
    # 비평→수정 라운드 수 (recritique=False 면 사실상 1).
    critique_rounds: int = 1
    # 수정 후 다시 비평할지. 기본 off (지연·비용 통제).
    recritique: bool = False
    critique_temperature: float = 0.0
    revise_temperature: float = 0.2


# 권장 기본값 — 근거는 모듈 docstring/PR 참조.
#  ④: 사용자가 직접 대기 → 가장 보수적(비평1+수정1, 재비평 없음).
#  ①: 백그라운드, 검증 신설 → 비평1+수정1.
#  ②③: 백그라운드, 기존 attempt 루프 안에서 비평1+수정1.
REPORT_VERIFICATION_CONFIG: Dict[str, VerificationConfig] = {
    "report1": VerificationConfig(enabled=True, critique_rounds=1, recritique=False),
    "report2": VerificationConfig(enabled=True, critique_rounds=1, recritique=False),
    "report3": VerificationConfig(enabled=True, critique_rounds=1, recritique=False),
    "report4": VerificationConfig(enabled=True, critique_rounds=1, recritique=False),
}


def _global_enabled() -> bool:
    """전역 긴급 off 스위치. REPORT_VERIFICATION_ENABLED=0/false 면 검증 통째 비활성."""
    v = os.getenv("REPORT_VERIFICATION_ENABLED", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def get_config(kind: str, override: Optional[VerificationConfig] = None) -> VerificationConfig:
    """보고서 종류의 검증 설정. 전역 off 면 enabled=False 로 덮어 반환."""
    cfg = override or REPORT_VERIFICATION_CONFIG.get(kind, VerificationConfig())
    if not _global_enabled():
        return VerificationConfig(
            enabled=False,
            critique_rounds=cfg.critique_rounds,
            recritique=cfg.recritique,
            critique_temperature=cfg.critique_temperature,
            revise_temperature=cfg.revise_temperature,
        )
    return cfg


# ── LLM 호출 추상화 (주입 가능 — 테스트는 가짜를 넣는다) ──────────


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


# llm_call(messages, *, temperature, max_tokens, json_mode=False) -> LLMResult
LLMCall = Callable[..., LLMResult]


def default_llm_call(
    messages: List[Dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    json_mode: bool = False,
) -> LLMResult:
    """기존 보고서 클라이언트(get_report_llm_client / RunYourAI)를 그대로 사용.

    새 클라이언트·langchain 금지 (오리엔테이션 Q1 결정).
    """
    from scripts.reports.transcript_report import (  # 지연 import — 순환 방지
        REPORT_LLM_DEPLOYMENT,
        get_report_llm_client,
    )

    client = get_report_llm_client()
    kwargs: Dict[str, Any] = {
        "model": REPORT_LLM_DEPLOYMENT,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    content = (resp.choices[0].message.content if resp.choices else "") or ""
    usage = getattr(resp, "usage", None)
    return LLMResult(
        content=content.strip(),
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )


# ── 4-2. 검증 perf 측정 (전역 없이 반환값으로) ───────────────────


@dataclass
class VerificationPerf:
    enabled: bool = True
    skipped: bool = False  # 설정 off / 검증 미수행
    code_gate_issues: int = 0
    critique_calls: int = 0
    critique_issues: int = 0
    revise_calls: int = 0
    revise_applied: bool = False
    revise_rejected: bool = False  # 수정본이 양식 가드 실패 → 초안 채택
    critique_failed: bool = False  # 비평 LLM 예외/파싱실패 → 초안 채택
    revise_failed: bool = False  # 수정 LLM 예외 → 초안 채택
    total_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # ── Phase 1-b 측정 강화 (기존 키 불변 — 새 키만 추가) ──
    # 비평이 지목한 이슈 본문 샘플(과탐/진짜환각 사람 판정용. 길면 앞부분만).
    critique_issue_samples: List[str] = field(default_factory=list)
    # 수정본이 양식 가드에서 탈락한 경우 위반 계약 코드(예: R4.MISSING_TABLE3).
    revise_reject_codes: List[str] = field(default_factory=list)
    # 최종 채택 출처: "draft"(초안) | "revision"(수정본).
    final_source: str = "draft"
    draft_len: int = 0  # 초안 길이(문자) — 거친 변화량 지표
    final_len: int = 0  # 최종 산출물 길이(문자)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerifyResult:
    """오케스트레이터 반환 — 상태를 명시적으로 담는다(§7-4)."""

    output: Any  # 최종 산출물 (str=①④ / dict=②③)
    perf: VerificationPerf
    applied: bool = False  # 수정이 실제 적용됐는지


# ── 4-3. 코드 게이트 (LLM 없이 결정론적) ─────────────────────────

_R4_COUNT_RE = re.compile(r"분석\s*댓글\s*수\s*[:：]\s*([\d,]+)\s*건")
_R4_RATIO_RE = re.compile(
    r"가중\s*비율\s*[:：]\s*긍정\s*([\d.]+)\s*%\s*/\s*중립\s*([\d.]+)\s*%\s*/\s*부정\s*([\d.]+)\s*%"
)
_R4_EMPTY_RE = re.compile(r"데이터\s*부족\s*\(분석\s*가능한\s*댓글\s*없음\)")


def _num_close(a: float, b: float, tol: float = 0.05) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def code_gate_report4_consumer(
    draft: str, consumer_aggregate: Optional[Dict[str, Any]]
) -> List[str]:
    """④ ⑤ 소비자 여론 섹션의 수치가 집계 입력과 글자 그대로 일치하는지 검사.

    프롬프트가 "⑤ 비율·건수는 집계값 그대로, 재계산 금지"를 절대 규칙으로 걸고
    있으므로 위반은 LLM 없이 잡힌다. 집계가 비었으면(⑤=데이터 부족) 검사 생략.
    """
    issues: List[str] = []
    total = 0
    if consumer_aggregate:
        total = int(consumer_aggregate.get("total_analyzed_comments", 0) or 0)
    if not consumer_aggregate or total <= 0:
        return issues  # ⑤ 가 "데이터 부족" 이어야 정상 — 검사 대상 아님

    if _R4_EMPTY_RE.search(draft):
        issues.append(
            "⑤ 소비자 여론: 집계 댓글이 존재(total=%d)하는데 '데이터 부족(분석 "
            "가능한 댓글 없음)'으로 표기됨 — 집계 수치를 반영해야 함." % total
        )
        return issues

    m_cnt = _R4_COUNT_RE.search(draft)
    if m_cnt:
        reported = int(m_cnt.group(1).replace(",", ""))
        if reported != total:
            issues.append(
                "⑤ 분석 댓글 수 불일치: 보고서=%d, 집계 입력=%d (집계값 그대로 써야 함)."
                % (reported, total)
            )
    else:
        issues.append("⑤ '분석 댓글 수: N건' 라인을 찾을 수 없음 (집계 존재 시 필수).")

    wr = consumer_aggregate.get("weighted_ratio") or {}
    m_ratio = _R4_RATIO_RE.search(draft)
    if m_ratio and wr:
        rp, rn, rg = (float(x) for x in m_ratio.groups())
        exp = (
            float(wr.get("positive_pct", 0.0)),
            float(wr.get("neutral_pct", 0.0)),
            float(wr.get("negative_pct", 0.0)),
        )
        if not (
            _num_close(rp, exp[0]) and _num_close(rn, exp[1]) and _num_close(rg, exp[2])
        ):
            issues.append(
                "⑤ 가중 비율 불일치: 보고서=긍정%s/중립%s/부정%s, 집계=긍정%s/중립%s/부정%s "
                "(집계값 그대로, 재계산 금지)." % (rp, rn, rg, exp[0], exp[1], exp[2])
            )
    return issues


_NUM_UNIT_RE = re.compile(
    r"(\d[\d,]*\.?\d*)\s?"
    r"(시간|분|초|만원|원|nit|니트|밀리|mAh|Wh|Hz|㎐|인치|％|%|배|개월|일|주|"
    r"g|kg|그램|GB|TB|MP|화소|만화소|fps|W|V|mm|cm)"
)


def numeric_token_gate(draft: str, grounding: str) -> List[str]:
    """보고서가 인용한 정량 수치가 입력 텍스트에 문자열로 존재하는지 대조.

    휴리스틱 — 오탐 가능. 그래서 보고서를 직접 고치지 않고 "환각 후보" 힌트로만
    수정 LLM 에 넘긴다(§4-3). 입력 숫자 집합에 없는 숫자만 후보로.
    """
    if not grounding:
        return []
    g_nums = set(re.findall(r"\d[\d,]*\.?\d*", grounding))
    g_nums_norm = {n.replace(",", "") for n in g_nums}
    hints: List[str] = []
    seen = set()
    for num, unit in _NUM_UNIT_RE.findall(draft):
        norm = num.replace(",", "")
        token = f"{num}{unit}"
        if token in seen:
            continue
        seen.add(token)
        if norm and norm not in g_nums_norm and num not in g_nums:
            hints.append(f"입력 자막/댓글에 없는 수치 가능성(확인 요): '{token}'")
    return hints[:12]  # 힌트 폭주 방지


# ── 비평·수정 프롬프트 (prompt_manager.py 밖 — 양식 원천과 분리) ──

# 보고서별 "허용되는 종합·가공" 가드.
# 핵심: 각 보고서가 *하기로 되어 있는* 정상적 종합·요약·집계·매핑은 환각이 아니다.
# 진짜 환각만(입력 어디에도 없는 구체 사양·가격·출시일·비교 제품명·인물·정량
# 스펙 날조) 잡게 한다. ①②③ 가드는 짧되 보수적으로(진짜 환각을 놓치지 않게).
_CRITIQUE_GUARDS = {
    "report1": (
        "이 보고서(①)는 한 영상의 자막을 요약·재구성하고, 리뷰어의 정성 평가를 "
        "장단점·강도 기호로 정리하는 보고서다. 자막에 나온 리뷰어의 의견·평가를 "
        "요약·재서술한 문장은 환각이 아니다. 진짜 환각만 보고하라: 자막 어디에도 "
        "없는 구체 수치·스펙·가격·출시일·비교 제품명·인물을 새로 지어낸 경우. "
        "'(수치 미언급)'·'언급 없음' 같은 표기는 정상이므로 문제 삼지 마라."
    ),
    "report2": (
        "이 보고서(②)는 다수 댓글을 집계·분류해 감성 비율·aspect·대표 요약으로 "
        "만드는 보고서다. 댓글 데이터를 집계·요약·분류한 값(비율·건수·aspect 요약 "
        "문장)은 환각이 아니다. 대표 댓글 원문은 별도 화이트리스트로 이미 보호되니 "
        "초점이 아니다. 진짜 환각만 보고하라: 입력 댓글 집계 어디에도 근거가 없는 "
        "사실·수치·제품 정보를 지어낸 경우."
    ),
    "report3": (
        "이 보고서(③)는 리뷰어(자막) vs 소비자(댓글)를 비교·매칭하고 신뢰도 점수 "
        "등을 산출하는 보고서다. 입력(자막 보고서·댓글 보고서·aspect 요약)을 비교·"
        "분류·집계한 값(매칭 tier, 신뢰 점수, 일치/불일치 판정)은 환각이 아니다. "
        "진짜 환각만 보고하라: 입력 후보 어디에도 없는 스펙·인용·토픽을 새로 "
        "지어낸 경우."
    ),
    "report4": (
        "이 보고서(④)는 여러 영상의 자막 기반 보고서를 *종합*하는 메타 보고서다. "
        "다음은 ④가 하기로 되어 있는 정상 작업이므로 절대 환각으로 보고하지 마라:\n"
        "  - 입력 어딘가에 근거가 있는 내용을 여러 영상에 걸쳐 종합·요약·재구성한 문장.\n"
        "  - 종합 평가 점수(예: '8.2 / 10'), ③의 6차원 점수 — 이는 정성 평가"
        "('우수'·'아쉬움' 등)를 점수로 매핑하고 가중평균한 산출값이다. 입력 자막에 "
        "그 숫자가 글자 그대로 없다는 이유로 환각이라 하지 마라.\n"
        "  - 장단점 합의 빈도(예: '5개 영상 중 3개', '(3/5)'), 리뷰어 합의도"
        "(높음/중간/낮음), 추천/비추 페르소나의 '(근거: 영상 N)' 표기 — 모두 "
        "여러 영상 종합/집계 산출값이다.\n"
        "  - ⑤ 소비자 여론 섹션의 수치(분석 댓글 수·가중 비율)는 코드 게이트가 "
        "이미 결정론적으로 검사한다. 비평은 ⑤ 수치를 중복 판단하지 마라.\n"
        "진짜 환각은 따로다 — 입력 보고서 어디에도 없는 구체 제품 사양·가격·"
        "출시일·비교 대상 제품명·리뷰어 이름·정량 스펙을 지어낸 경우. 이런 것만 잡아라."
    ),
}
_DEFAULT_GUARD = (
    "입력 근거를 정상적으로 요약·종합·집계한 문장은 환각이 아니다. 입력 어디에도 "
    "없는 구체 사실·수치·스펙·가격·출시일·비교 제품·인물을 지어낸 경우만 보고하라."
)

_CRITIQUE_SYSTEM = (
    "당신은 보고서 사실검증관입니다. 주어진 '입력 근거'에 비추어 '보고서 초안'이 "
    "근거 없이 지어낸 사실·수치·사양·가격·비교 제품·출시일·인물을 찾아냅니다. "
    "양식·문체·완성도는 절대 평가하지 않습니다. 오직 '입력 근거로 뒷받침되는가'만 "
    "봅니다. 중요: 각 보고서가 *하기로 되어 있는* 정상적 종합·요약·집계·점수 "
    "매핑은 환각이 아닙니다 — 사용자 메시지의 '이 보고서의 허용 작업' 가드를 "
    "반드시 따르고, 그 범위의 산출물은 문제로 보고하지 마십시오. 추측·일반상식으로 "
    "메우라고 요구하지 마십시오 — 검증의 방향은 '덜어내고 바로잡기'입니다. "
    "의심스러우면 보고하지 마십시오(과탐보다 미탐이 안전합니다 — 진짜 환각만)."
)

_CRITIQUE_USER_TMPL = """다음 보고서 초안에서, 아래 입력 근거에 **나타나지 않는**
사실/수치/스펙/가격/비교 제품/출시일/인물을 새로 **지어낸** 것만 골라 JSON 으로
보고하세요. 정상적 종합·요약·집계·점수 매핑은 보고하지 마세요. 양식·표현은 평가
대상이 아닙니다.

================ 이 보고서의 허용 작업 (가드 — 반드시 준수) ================
{report_guard}

[코드 사전검사가 표시한 의심 항목 — 참고용, 오탐일 수 있음]
{gate_hints}

================ 입력 근거 ================
{grounding}

================ 보고서 초안 ================
{draft}

================ 응답 형식 (JSON only, 코드펜스 금지) ================
{{"issues": [{{"claim": "<초안의 근거 없는 표현 인용>",
  "reason": "<왜 입력 근거에 없는지 — 가드의 허용 작업이 아님을 명시>",
  "fix_hint": "<제거 또는 '(수치 미언급)'/'데이터 부족' 등으로 완화 제안>"}}]}}
근거 없는 항목이 하나도 없으면 {{"issues": []}} 만 출력.
"""

# 보고서별 수정 시 "절대 보존" 구조 라인 규칙. 마크다운(①④)은 구조가 텍스트라
# 더 구체적으로 박는다. JSON(②③)은 키 구조 보존.
_REVISE_STRUCTURE_RULES = {
    "report1": (
        "이 보고서는 마크다운이다. 다음 구조 라인은 글자 한 자도 바꾸지 말고 "
        "삭제·병합·요약하지 마라: '## 📦' 로 시작하는 제목, 모든 '### ' 하위 헤딩, "
        "표의 헤더 행('| ... | ... |')과 구분 행, 강도 기호(◎ ○ △ ✕) 체계, "
        "'**제품명:**' 등 굵은 라벨."
    ),
    "report4": (
        "이 보고서는 마크다운이며 구조가 엄격하다. 다음 구조 라인은 글자 한 자도 "
        "바꾸지 말고, 줄을 삭제·병합·요약·재배치하지 마라: '## ①'~'## ⑦' 7개 "
        "섹션 헤딩 줄, 모든 '### ' 하위 헤딩, 표의 헤더 행('| 차원 | 점수 | ...' / "
        "'| 항목 | 전작 | ...')과 '| --- |' 구분 행, '📊 분석 기반' 메타 박스 줄. "
        "표의 행 개수·열 개수도 그대로 둔다. 수정은 오직 지적된 근거 없는 표현이 "
        "들어있는 *문장 안에서만* 일어난다."
    ),
    "report2": "이 보고서는 JSON 이다. 모든 키·중첩 구조·배열 길이를 그대로 두고, 값 문자열 안의 지적된 표현만 완화한다.",
    "report3": "이 보고서는 JSON 이다. 모든 키·중첩 구조·배열 길이를 그대로 두고, 값 문자열 안의 지적된 표현만 완화한다.",
}
_DEFAULT_STRUCTURE_RULE = "원본의 구조(헤딩·표·키·기호)를 글자 그대로 보존하고, 지적된 문장 내부만 최소 수정한다."

_REVISE_SYSTEM = (
    "당신은 보고서 교정자입니다. 지적된 '근거 없는 표현'만 최소 침습으로 "
    "제거하거나 '(수치 미언급)'·'언급 없음'·'데이터 부족' 으로 완화합니다. "
    "그 외 문장은 한 글자도 바꾸지 마십시오. 새로운 내용·수치·비교를 추가하지 "
    "마십시오. 절대 규칙: 섹션 구조·헤딩 표기·표의 헤더/구분/행 수·열 수·기호 "
    "체계·JSON 키·배열 길이 등 양식은 일절 변경·삭제·병합·재배치 금지. 지적된 "
    "문장 외의 모든 줄과 모든 구조 라인은 원본을 그대로 복사하십시오. "
    "의심스러우면 덜 고치십시오 — 고치는 것보다 구조 보존이 절대 우선입니다. "
    "출력은 보고서 본문 그 자체만(설명·인사말·코드펜스 금지)."
)

_REVISE_USER_TMPL = """아래 '지적 사항'에 해당하는 표현만 그 문장 안에서 제거·완화
하세요. 지적되지 않은 모든 줄과 모든 구조 라인은 원본을 글자 그대로 복사하세요.

================ 구조 보존 절대 규칙 ================
{structure_rule}

================ 지적 사항 ================
{issues}

================ 원본 보고서 ================
{draft}

================ 출력 ================
교정된 보고서 {fmt} 만 출력. {fmt_rule} 구조 라인은 원본과 1:1 일치해야 한다.
"""


def _fmt_words(json_mode: bool) -> Tuple[str, str]:
    if json_mode:
        return ("JSON 객체", "JSON 객체 하나만, 원본과 동일한 키 구조 유지.")
    return ("마크다운", "원본과 동일한 마크다운 구조(헤딩·표·기호) 유지.")


# ── 단계 함수 (각각 독립 호출 가능 — Phase 4 노드 단위) ──────────


def _parse_critique_issues(content: str) -> Optional[List[str]]:
    """비평 LLM 응답 → 이슈 문자열 리스트. 파싱 실패 시 None."""
    txt = (content or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", txt).strip()
    try:
        obj = json.loads(txt)
    except (json.JSONDecodeError, ValueError):
        return None
    raw = obj.get("issues", []) if isinstance(obj, dict) else []
    if not isinstance(raw, list):
        return None
    out: List[str] = []
    for it in raw:
        if isinstance(it, dict):
            claim = str(it.get("claim", "")).strip()
            reason = str(it.get("reason", "")).strip()
            hint = str(it.get("fix_hint", "")).strip()
            if claim or reason:
                out.append(
                    f"- 주장: {claim} / 근거없음: {reason}"
                    + (f" / 조치: {hint}" if hint else "")
                )
        elif isinstance(it, str) and it.strip():
            out.append(f"- {it.strip()}")
    return out


def critique_step(
    kind: str,
    draft: str,
    grounding: str,
    llm_call: LLMCall,
    *,
    temperature: float = 0.0,
    gate_hints: Optional[List[str]] = None,
) -> Tuple[List[str], bool, LLMResult]:
    """[3] 비평. 반환: (이슈목록, 실패여부, LLMResult).

    실패(예외/파싱불가)면 이슈=[] 이고 failed=True → 호출부는 초안을 채택(퇴화).
    """
    hints_txt = "\n".join(gate_hints or []) or "(없음)"
    user = _CRITIQUE_USER_TMPL.format(
        report_guard=_CRITIQUE_GUARDS.get(kind, _DEFAULT_GUARD),
        gate_hints=hints_txt,
        grounding=grounding,
        draft=draft,
    )
    try:
        res = llm_call(
            [
                {"role": "system", "content": _CRITIQUE_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=1200,
            json_mode=True,
        )
    except Exception as e:  # noqa: BLE001 — 검증 실패는 안전 퇴화
        print(f"[WARN][verification] {kind} critique LLM failed: {type(e).__name__}: {e}")
        return ([], True, LLMResult(content=""))
    issues = _parse_critique_issues(res.content)
    if issues is None:
        print(f"[WARN][verification] {kind} critique parse failed → treat as clean")
        return ([], True, res)
    return (issues, False, res)


def revise_step(
    kind: str,
    draft: str,
    issues: List[str],
    llm_call: LLMCall,
    *,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> Tuple[Optional[str], bool, LLMResult]:
    """[4] 수정. 반환: (수정본 raw 문자열 or None, 실패여부, LLMResult)."""
    fmt, fmt_rule = _fmt_words(json_mode)
    user = _REVISE_USER_TMPL.format(
        structure_rule=_REVISE_STRUCTURE_RULES.get(kind, _DEFAULT_STRUCTURE_RULE),
        issues="\n".join(issues),
        draft=draft,
        fmt=fmt,
        fmt_rule=fmt_rule,
    )
    try:
        res = llm_call(
            [
                {"role": "system", "content": _REVISE_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=4096,
            json_mode=json_mode,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[WARN][verification] {kind} revise LLM failed: {type(e).__name__}: {e}")
        return (None, True, LLMResult(content=""))
    content = (res.content or "").strip()
    if not content:
        return (None, True, res)
    return (content, False, res)


# ── 양식 가드 (①④ — Phase 0 계약기 재사용, 방어적 import) ────────


def markdown_format_validator(kind: str) -> Callable[[str], bool]:
    """regression/contracts 의 계약기를 양식 가드로 재사용. import 실패 시 통과(퇴화)."""

    def _validator(text: str) -> bool:
        try:
            if kind == "report1":
                from regression.contracts import validate_report1 as vf
            elif kind == "report4":
                from regression.contracts import validate_report4 as vf
            else:
                return True
        except Exception as e:  # noqa: BLE001 — 가드 없으면 초안 채택 쪽으로 안전
            print(f"[WARN][verification] format guard import 실패 ({kind}): {e} → 가드 건너뜀")
            return True
        try:
            result = vf(text)
            # 생성실패/폴백 분류는 양식위반이 아니므로 가드 통과로 본다.
            return result.status != "violated"
        except Exception as e:  # noqa: BLE001
            print(f"[WARN][verification] format guard 실행 실패 ({kind}): {e} → 통과 처리")
            return True

    return _validator


def markdown_format_diagnose(kind: str) -> Callable[[str], List[str]]:
    """①④ 수정본이 양식 가드에서 탈락한 경우 위반 계약 코드 목록을 돌려준다.

    측정용(§4-2) — 수정 LLM 이 무엇을 깨는지 보이게 한다. import/실행 실패 시 [].
    """

    def _diagnose(text: str) -> List[str]:
        try:
            if kind == "report1":
                from regression.contracts import validate_report1 as vf
            elif kind == "report4":
                from regression.contracts import validate_report4 as vf
            else:
                return []
            result = vf(text)
            return [getattr(v, "code", "?") for v in getattr(result, "violations", [])]
        except Exception as e:  # noqa: BLE001 — 진단 실패가 흐름을 막지 않음
            print(f"[WARN][verification] format diagnose 실패 ({kind}): {e}")
            return []

    return _diagnose


# ── 오케스트레이터 ──────────────────────────────────────────────


def _run(
    kind: str,
    draft: Any,
    grounding: str,
    *,
    json_mode: bool,
    llm_call: LLMCall,
    config: VerificationConfig,
    format_validator: Callable[[Any], bool],
    precomputed_gate_issues: Optional[List[str]] = None,
    format_diagnose: Optional[Callable[[Any], List[str]]] = None,
) -> VerifyResult:
    perf = VerificationPerf(enabled=config.enabled)
    if not config.enabled:
        perf.skipped = True
        return VerifyResult(output=draft, perf=perf, applied=False)

    t0 = perf_counter()
    draft_text = (
        json.dumps(draft, ensure_ascii=False) if json_mode else str(draft)
    )
    perf.draft_len = len(draft_text)

    # [2] 코드 게이트 — 결정론적 (호출부 사전검사 + 범용 수치 토큰).
    # 범용 수치 토큰 게이트는 ①④(마크다운)에만 적용 — ②③ JSON 구조의 숫자
    # (건수·비율 등)는 오탐이 많아 제외(§4-3 권장 범위).
    gate_issues: List[str] = list(precomputed_gate_issues or [])
    if not json_mode:
        gate_issues += numeric_token_gate(draft_text, grounding)
    perf.code_gate_issues = len(gate_issues)

    current = draft
    current_text = draft_text

    rounds = max(1, config.critique_rounds)
    for rnd in range(rounds):
        # [3] 비평
        issues, crit_failed, crit_res = critique_step(
            kind,
            current_text,
            grounding,
            llm_call,
            temperature=config.critique_temperature,
            gate_hints=gate_issues if rnd == 0 else None,
        )
        perf.critique_calls += 1
        perf.prompt_tokens += crit_res.prompt_tokens
        perf.completion_tokens += crit_res.completion_tokens
        if crit_failed:
            perf.critique_failed = True
            break  # 안전 퇴화 — 초안 채택

        round_issues = (gate_issues if rnd == 0 else []) + issues
        perf.critique_issues += len(issues)

        # [측정 §4-1] 비평이 지목한 이슈 본문을 진단 로그로 — 사람이 과탐/진짜
        # 환각을 눈으로 판정할 수 있게. 길면 앞부분만, 개수도 캡.
        for it in issues[:15]:
            sample = it if len(it) <= 240 else it[:240] + "…"
            perf.critique_issue_samples.append(sample)
            print(f"[VERIFY][critique] {kind} round{rnd} issue: {sample}")

        # [4-4] 코드게이트 0 + 비평 0 → 수정 호출 생략
        if not round_issues:
            break

        # [4] 수정
        revised_raw, rev_failed, rev_res = revise_step(
            kind,
            current_text,
            round_issues,
            llm_call,
            temperature=config.revise_temperature,
            json_mode=json_mode,
        )
        perf.revise_calls += 1
        perf.prompt_tokens += rev_res.prompt_tokens
        perf.completion_tokens += rev_res.completion_tokens
        if rev_failed or revised_raw is None:
            perf.revise_failed = True
            break  # 초안 유지

        # 양식 가드
        if json_mode:
            try:
                cand = json.loads(
                    re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", revised_raw.strip())
                )
            except (json.JSONDecodeError, ValueError):
                perf.revise_rejected = True
                perf.revise_reject_codes = ["JSON_PARSE_FAIL"]
                print(f"[VERIFY][reject] {kind} codes=JSON_PARSE_FAIL → 초안 채택")
                break
        else:
            cand = revised_raw

        if not format_validator(cand):
            perf.revise_rejected = True
            # [측정 §4-2] 수정 LLM 이 무엇을 깨뜨렸는지 위반 계약 코드로 기록.
            if json_mode:
                perf.revise_reject_codes = ["SCHEMA_INVALID"]
            elif format_diagnose is not None:
                perf.revise_reject_codes = format_diagnose(cand)
            print(
                f"[VERIFY][reject] {kind} codes="
                f"{','.join(perf.revise_reject_codes) or '?'} → 초안 채택"
            )
            break  # 수정본 양식 위반 → 초안 채택 (퇴화)

        current = cand
        current_text = (
            json.dumps(cand, ensure_ascii=False) if json_mode else str(cand)
        )
        perf.revise_applied = True

        if not config.recritique:
            break
        gate_issues = []  # 코드게이트 힌트는 1라운드만

    perf.total_ms = round((perf_counter() - t0) * 1000, 1)
    perf.final_source = "revision" if perf.revise_applied else "draft"
    perf.final_len = len(current_text)
    # [측정 §4-3] 검증 적용 여부 한 줄 요약 — 검증이 실제로 보고서를 바꿨는지.
    print(
        f"[VERIFY][summary] {kind} source={perf.final_source} "
        f"draft_len={perf.draft_len} final_len={perf.final_len} "
        f"critique_issues={perf.critique_issues} applied={perf.revise_applied} "
        f"rejected={perf.revise_rejected} reject_codes="
        f"{','.join(perf.revise_reject_codes) or '-'} ms={perf.total_ms}"
    )
    return VerifyResult(output=current, perf=perf, applied=perf.revise_applied)


def verify_markdown_report(
    kind: str,
    draft: str,
    grounding: str,
    *,
    llm_call: LLMCall = default_llm_call,
    precomputed_gate_issues: Optional[List[str]] = None,
    config: Optional[VerificationConfig] = None,
    format_validator: Optional[Callable[[str], bool]] = None,
) -> VerifyResult:
    """①④ (마크다운) 검증. 양식 가드 = Phase 0 계약기 (기본)."""
    cfg = get_config(kind, config)
    fv = format_validator or markdown_format_validator(kind)
    return _run(
        kind,
        draft,
        grounding,
        json_mode=False,
        llm_call=llm_call,
        config=cfg,
        format_validator=fv,
        precomputed_gate_issues=precomputed_gate_issues,
        format_diagnose=markdown_format_diagnose(kind),
    )


def verify_json_report(
    kind: str,
    draft: Dict[str, Any],
    grounding: str,
    *,
    format_validator: Callable[[Any], bool],
    llm_call: LLMCall = default_llm_call,
    config: Optional[VerificationConfig] = None,
) -> VerifyResult:
    """②③ (JSON dict) 검증. 양식 가드 = 호출부의 validate_report{2,3}_json."""
    cfg = get_config(kind, config)
    return _run(
        kind,
        draft,
        grounding,
        json_mode=True,
        llm_call=llm_call,
        config=cfg,
        format_validator=format_validator,
        precomputed_gate_issues=None,
    )
