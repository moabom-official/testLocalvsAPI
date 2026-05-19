"""비전 LLM 검증 (Phase 3 단계 2-ⓑ + 보강 A).

★ 보강 A — 방향 ③: 우리 서버가 각 후보 이미지를 직접 다운로드해 base64
   data: URI 로 비전에 넘긴다(게이트웨이 base64 지원 실측 확인). 효과:
   - 비전 제공자측 URL 다운로드 실패(invalid_image_url 400)가 원천 소멸.
   - 후보 1개 다운로드 실패 = 그 후보만 탈락, 나머지는 정상 평가.
"첫 적합 채택"이 아니라 "명백한 노이즈만 탈락 + 남은 것 중 최선 채택"
(§4 검증 철학). 비전 LLM 은 검증 전용 — 이미지 생성 절대 금지. 인물이
크게 나온 사진은 명백한 노이즈로 탈락(§15 인물 금지).
"""
from __future__ import annotations

import base64
import json
import re
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple

_SYSTEM = (
    "당신은 제품 사진 검증관입니다. 주어진 이미지들이 특정 제품의 '깔끔한 "
    "실제 제품 사진'으로 적절한지 평가합니다. 이미지를 만들지 않습니다."
)


def _download_one(url: str, *, timeout: float, max_bytes: int):
    """후보 이미지 1장 다운로드 → (data_uri, None) | (None, 실패사유).

    예외 격리: 어떤 실패도 그 후보만 탈락시키고 사유를 돌려준다.
    """
    import requests  # 지연 import

    try:
        r = requests.get(url, timeout=timeout, stream=True)
    except Exception as e:  # noqa: BLE001
        return None, f"다운로드 실패({type(e).__name__})"
    try:
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ct.startswith("image/"):
            return None, f"비이미지 응답({ct or 'unknown'})"
        data = r.content
        if not data:
            return None, "빈 응답"
        if len(data) > max_bytes:
            return None, f"용량 초과({len(data)}B>{max_bytes}B)"
        b64 = base64.b64encode(data).decode()
        return f"data:{ct};base64,{b64}", None
    except Exception as e:  # noqa: BLE001
        return None, f"수신 오류({type(e).__name__})"
    finally:
        r.close()


def default_download_fn(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """각 후보를 서버가 직접 다운로드. 후보별 격리 — 한 개 실패가 전체를
    막지 않는다. 반환: 각 원소에 _dl_ok / _data_uri 또는 _dl_reason 부착.
    """
    from scripts.config import (
        PRODUCT_IMAGE_DL_TIMEOUT,
        PRODUCT_IMAGE_MAX_BYTES,
    )

    out: List[Dict[str, Any]] = []
    for c in candidates:
        uri, reason = _download_one(
            c.get("image_url") or "",
            timeout=PRODUCT_IMAGE_DL_TIMEOUT,
            max_bytes=PRODUCT_IMAGE_MAX_BYTES,
        )
        if uri:
            out.append({**c, "_dl_ok": True, "_data_uri": uri})
        else:
            out.append({**c, "_dl_ok": False, "_dl_reason": reason})
    return out


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
            # 보강 A: 우리 서버가 받은 base64 data URI (제공자 다운로드 X)
            "image_url": {"url": c.get("_data_uri") or c.get("image_url")},
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
    download_fn: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """후보 다운로드(격리)→평가 → (채택 1개 or None, 평가목록, perf).

    보강 A 결과 불변식: 후보 일부가 다운로드/평가 불가여도 평가 가능한
    후보가 1개라도 있으면 그중 채택. 평가 가능 후보 0개일 때만 None.
    시그니처·반환 계약 유지(collector 의존). download_fn 은 테스트 주입용.
    """
    perf: Dict[str, Any] = {"vision_calls": 0, "ms": 0.0,
                            "candidates": len(candidates),
                            "downloaded": 0, "download_failed": 0}
    if not candidates:
        perf["error"] = "no_candidates"
        return None, [], perf

    # 1) 서버측 다운로드 (후보별 격리)
    dfn = download_fn or default_download_fn
    t_dl = perf_counter()
    prepared = dfn(candidates)
    perf["download_ms"] = round((perf_counter() - t_dl) * 1000, 1)
    ok = [c for c in prepared if c.get("_dl_ok")]
    failed = [c for c in prepared if not c.get("_dl_ok")]
    perf["downloaded"] = len(ok)
    perf["download_failed"] = len(failed)

    # 다운로드 실패 후보 → 평가목록에 사유와 함께(선택 대상 아님)
    evals: List[Dict[str, Any]] = []
    for c in failed:
        evals.append({**c, "vision": {
            "score": None, "is_noise": False,
            "reason": f"이미지 다운로드 실패: {c.get('_dl_reason')}",
            "download_failed": True}})

    if not ok:
        # 평가 가능한 후보 0 → 안전 퇴화(no_image)
        perf["error"] = "no_downloadable"
        return None, evals, perf

    # 2) 다운로드 성공분만 비전 평가(일괄 1회)
    fn = vision_call or default_vision_call
    t0 = perf_counter()
    try:
        raw = fn(product_name, ok)
    except Exception as e:  # noqa: BLE001 — 비전 호출 자체 실패도 격리
        perf["vision_error"] = f"{type(e).__name__}"
        # 평가 불가 → 이미지 없음 회피: 다운로드된 1순위 채택(§4 철학)
        chosen = dict(ok[0])
        chosen["vision"] = {"score": None, "is_noise": False,
                            "reason": f"비전 호출 실패({type(e).__name__}) → "
                                      "다운로드 1순위 채택"}
        for j, c in enumerate(ok):
            evals.append({**c, "vision": {
                "score": None, "is_noise": False,
                "reason": "vision_error(채택)" if j == 0 else "vision_error"}})
        return chosen, evals, perf
    perf["ms"] = round((perf_counter() - t0) * 1000, 1)
    perf["vision_calls"] = 1

    parsed = _parse(raw)
    if parsed is None:
        # 파싱 실패 → 이미지 없음 회피: 다운로드된 1순위 채택(§4 철학).
        perf["parse_failed"] = True
        chosen = dict(ok[0])
        chosen["vision"] = {"score": None, "is_noise": False,
                            "reason": "비전 응답 파싱 실패 → 다운로드 1순위 채택"}
        for j, c in enumerate(ok):
            evals.append({**c, "vision": {
                "score": None, "is_noise": False,
                "reason": "parse_failed(채택)" if j == 0 else "parse_failed"}})
        return chosen, evals, perf

    by_idx = {int(r.get("idx", -1)): r for r in parsed
              if isinstance(r, dict)}
    best = None
    best_score = -1.0
    for i, c in enumerate(ok):
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
