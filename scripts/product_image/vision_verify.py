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
    "실제 제품 사진'으로 적절한지, 특히 제품의 전/후면이 한 이미지에 모두 "
    "보이는지와 제품이 잘리지 않고 온전히 보이는지를 세밀하게 평가합니다. "
    "이미지를 만들지 않습니다."
)

# ── 제품 드러남 점수 가중치 (1순위) ──────────────────────────────
# 사용자 정의: "전/후면이 한 이미지에 모두 보임 + 위/아래 잘림 없이 전체가
# 다 보임". 이 둘이 핵심 비중. clarity(선명도)는 보조. 각 항목 0~5 → 가중합
# 0~5. 근거: 전후면·잘림이 채택 품질을 좌우(아이폰15 실측: 다 10점이라
# 변별 실패) 했으므로 두 항목에 0.45/0.40, 보조 선명도 0.15.
_W_FRONT_BACK = 0.45
_W_NOT_CROPPED = 0.40
_W_CLARITY = 0.15
_REVEAL_MAX = 5.0


def _clamp5(v: Any) -> float:
    """0~5 정도 점수로 안전 변환. 누락·깨짐 → 보수적으로 0."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f < 0 else (5.0 if f > 5 else f)


def reveal_score(front_back: Any, not_cropped: Any, clarity: Any) -> float:
    """제품 드러남 종합 점수(0~5). 전후면·잘림 핵심, 선명도 보조."""
    return round(
        _clamp5(front_back) * _W_FRONT_BACK
        + _clamp5(not_cropped) * _W_NOT_CROPPED
        + _clamp5(clarity) * _W_CLARITY,
        4,
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
            "- front_back: 제품의 전면과 후면이 '한 이미지 안에 모두' 보이는 "
            "정도 0~5 (한 면만 보이면 0~2, 전후면 다 보이면 4~5)\n"
            "- not_cropped: 제품이 프레임에서 위/아래로 잘리지 않고 '전체가 "
            "다' 보이는 정도 0~5 (많이 잘림 0~2, 온전 4~5)\n"
            "- clarity: 제품이 얼마나 선명·명확히 보이는가 0~5 (보조)\n"
            "- is_noise: 다음이면 true — 밈/짤, 비교 이미지, 액세서리만, "
            "다른 제품, 사람이 크게 나옴, 제품이 거의 안 보임, 워터마크 과다\n"
            "- reason: 한 줄 사유\n"
            'JSON 만 출력: {"results":[{"idx":0,"front_back":0,'
            '"not_cropped":0,"clarity":0,"is_noise":false,"reason":""}, ...]}'
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


# ── 출처 등급 (가벼운 도메인 분류 — 동점 깨기 2차 기준) ──────────
#
# 팀 결정: 브랜드→공식도메인 매핑 테이블을 만들지 않는다. 도메인 문자열에
# 든 "공식/제조사 신호" vs "쇼핑몰·중고·위키·블로그 신호"를 가볍게 보는
# 수준이면 충분(완벽한 제조사 판정 불필요). 점수 동점일 때만 작동한다.
#
#  2 = 신뢰 출처: 제조사 공식·공식 CDN·뉴스룸/프레스
#  1 = 일반 출처: 위 둘 어디에도 안 드는 기본값(뉴스·미디어 등)
#  0 = 비공식/상업·UGC: 오픈마켓·쇼핑몰·중고·위키·블로그·핀터레스트류

# 제조사/공식 신호 (대표적인 것 몇 개 — 망라 목적 아님, 가벼운 분류).
_OFFICIAL_HINTS = (
    "apple.com", "cdsassets.apple", "store.storeimages",  # Apple/공식 CDN
    "samsung.com", "samsungmobilepress", "news.samsung",
    "lg.com", "lge.co.kr", "lgnewsroom",
    "sony.", "sony.co", "google.com/", "store.google",
    "microsoft.com", "xiaomi.com", "mi.com", "asus.com",
    "lenovo.com", "dell.com", "hp.com",
    "newsroom", "/press", "press.", "official",
)
# 비공식/상업·UGC 신호 (쇼핑몰·중고·위키·블로그). 'store'/'mall' 단순
# 부분일치는 공식 스토어 CDN 을 잘못 잡으므로 _OFFICIAL_HINTS 를 먼저 본다.
_LOW_HINTS = (
    "kt-mall", "istore", "11st", "gmarket", "auction.", "coupang",
    "danawa", "enuri", "ssg.com", "ssgcdn", "smartstore", "shopping.",
    "11dims", "etlandmall", "himart", "kream", "hypebeast",
    "bunjang", "joonggo", "danggn", "namu.wiki", "wikipedia",
    "pinterest", "tistory", "blog.", "blogspot", "brunch.",
)


def source_tier(domain: str = "", image_url: str = "", link: str = "") -> int:
    """후보 출처 등급(2>1>0). 순수 함수 — 도메인/URL 문자열만 본다."""
    blob = " ".join(
        s for s in (domain or "", image_url or "", link or "") if s
    ).lower()
    if not blob:
        return 1
    if any(h in blob for h in _OFFICIAL_HINTS):
        return 2
    if any(h in blob for h in _LOW_HINTS):
        return 0
    return 1


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
    # 채택 키: (제품드러남점수 1순위, 출처등급 2순위). strict > 비교라
    # 둘 다 같으면 먼저 온 후보 유지(3순위=검색 순서).
    best_key = (-1.0, -1)
    best_tie_by_source = False
    for i, c in enumerate(ok):
        r = by_idx.get(i, {})
        is_noise = bool(r.get("is_noise", False))
        reason = str(r.get("reason", "")).strip()
        fb = _clamp5(r.get("front_back"))
        crop = _clamp5(r.get("not_cropped"))
        clar = _clamp5(r.get("clarity"))
        reveal = reveal_score(fb, crop, clar)
        tier = source_tier(c.get("domain", ""), c.get("image_url", ""),
                           c.get("link", ""))
        rec = {**c, "vision": {
            "front_back": fb, "not_cropped": crop, "clarity": clar,
            "reveal_score": reveal, "is_noise": is_noise,
            "source_tier": tier,
            # 새 평가를 collector 의 reason 출력에서 보이게 부기
            "reason": (f"{reason} [전후면:{fb} 잘림없음:{crop} 선명:{clar} "
                       f"→ 드러남:{reveal} 출처등급:{tier}]")}}
        evals.append(rec)
        if is_noise:
            continue
        # 1순위 제품 드러남 점수 / 2순위 출처 등급. 드러남 점수가 더 높으면
        # 출처와 무관히 우선(출처가 1순위를 덮어쓰지 않음). 드러남 동점일
        # 때만 출처가 가른다.
        key = (reveal, tier)
        if key > best_key:
            best_tie_by_source = (best is not None
                                  and reveal == best_key[0]
                                  and tier > best_key[1])
            best_key = key
            best = rec

    if best is None:
        perf["all_noise"] = True
        return None, evals, perf

    perf["chosen_reveal_score"] = best_key[0]
    perf["chosen_source_tier"] = best_key[1]
    perf["tie_broken_by_source"] = best_tie_by_source
    if best_tie_by_source:
        best["vision"]["reason"] += " [드러남 동점→출처등급 우선 채택]"
    return best, evals, perf
