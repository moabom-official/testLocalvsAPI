"""비전 LLM 검증 (Phase 3 단계 2-ⓑ).

1차 필터 통과 후보만(전체 검색결과 X — 비용 통제), 한 번의 비전 호출로
일괄 평가. "첫 적합 채택"이 아니라 "명백한 노이즈만 탈락 + 남은 것 중
최선 채택"(§4 검증 철학). 비전 LLM 은 검증에만 — 이미지 생성 절대 금지.
인물이 크게 나온 사진은 명백한 노이즈로 탈락(§15 인물 금지).
"""
from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple

_SYSTEM = (
    "당신은 제품 사진 검증관입니다. 주어진 이미지들이 특정 제품의 '깔끔한 "
    "실제 제품 사진'으로 적절한지 평가합니다. 이미지를 만들지 않습니다."
)


def _build_user(product_name: str, candidates: List[Dict[str, Any]]) -> list:
    content: List[Dict[str, Any]] = [{
        "type": "text",
        "text": (
            f'대상 제품: "{product_name}"\n'
            f"아래 {len(candidates)}개 이미지를 각각 평가하세요. 각 이미지에 대해:\n"
            "- product_visible_score: 이 제품이 얼마나 명확히 보이는가 0~10\n"
            "- is_noise: 다음이면 true — 밈/짤, 비교 이미지, 액세서리만, "
            "다른 제품, 사람이 크게 나옴, 제품이 거의 안 보임, 워터마크 과다\n"
            "- reason: 한 줄 사유\n"
            'JSON 만 출력: {"results":[{"idx":0,'
            '"product_visible_score":0,"is_noise":false,"reason":""}, ...]}'
        ),
    }]
    for i, c in enumerate(candidates):
        content.append({"type": "text", "text": f"[이미지 {i}]"})
        content.append({
            "type": "image_url",
            "image_url": {"url": c["image_url"]},
        })
    return content


def _parse(txt: str) -> Optional[List[Dict[str, Any]]]:
    s = (txt or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", s).strip()
    try:
        obj = json.loads(s)
    except (ValueError, TypeError):
        return None
    res = obj.get("results") if isinstance(obj, dict) else None
    return res if isinstance(res, list) else None


def default_vision_call(product_name: str,
                        candidates: List[Dict[str, Any]]) -> str:
    """기존 get_report_llm_client(비전 가능) 재사용. 모델은 provider/model."""
    from scripts.config import PRODUCT_IMAGE_VISION_MODEL
    from scripts.reports.transcript_report import get_report_llm_client

    client = get_report_llm_client()
    resp = client.chat.completions.create(
        model=PRODUCT_IMAGE_VISION_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_user(product_name, candidates)},
        ],
        temperature=0,
        max_tokens=900,
    )
    return (resp.choices[0].message.content if resp.choices else "") or ""


def vision_select(
    product_name: str,
    candidates: List[Dict[str, Any]],
    *,
    vision_call: Optional[Callable[[str, List[Dict[str, Any]]], str]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """후보 일괄 평가 → (채택 1개 or None, 평가목록, perf).

    채택 규칙: is_noise=true 는 탈락 / 남은 것 중 score 최고 1개 채택 /
    전부 노이즈일 때만 None. 평가목록 원소엔 score·is_noise·reason 부착.
    """
    perf: Dict[str, Any] = {"vision_calls": 0, "ms": 0.0,
                            "candidates": len(candidates)}
    if not candidates:
        perf["error"] = "no_candidates"
        return None, [], perf

    fn = vision_call or default_vision_call
    t0 = perf_counter()
    raw = fn(product_name, candidates)
    perf["ms"] = round((perf_counter() - t0) * 1000, 1)
    perf["vision_calls"] = 1

    parsed = _parse(raw)
    evals: List[Dict[str, Any]] = []
    if parsed is None:
        # 파싱 실패 → 평가 불가. 명백한 노이즈로 단정하지 않고, 검색 1순위를
        # 최선으로 채택(이미지 없음 회피 — §4 철학). 사유 기록.
        perf["parse_failed"] = True
        chosen = dict(candidates[0])
        chosen["vision"] = {"score": None, "is_noise": False,
                            "reason": "비전 응답 파싱 실패 → 검색 1순위 채택"}
        for j, c in enumerate(candidates):
            evals.append({**c, "vision": {
                "score": None, "is_noise": False,
                "reason": "parse_failed" if j else "parse_failed(채택)"}})
        return chosen, evals, perf

    by_idx = {int(r.get("idx", -1)): r for r in parsed
              if isinstance(r, dict)}
    best = None
    best_score = -1.0
    for i, c in enumerate(candidates):
        r = by_idx.get(i, {})
        score = r.get("product_visible_score")
        is_noise = bool(r.get("is_noise", False))
        reason = str(r.get("reason", "")).strip()
        try:
            sval = float(score) if score is not None else -1.0
        except (TypeError, ValueError):
            sval = -1.0
        rec = {**c, "vision": {"score": score, "is_noise": is_noise,
                               "reason": reason}}
        evals.append(rec)
        if not is_noise and sval > best_score:
            best_score = sval
            best = rec

    if best is None:
        perf["all_noise"] = True
        return None, evals, perf
    return best, evals, perf
