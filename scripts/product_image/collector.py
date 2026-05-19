"""제품 이미지 수집 오케스트레이터 (Phase 3).

단계: 캐시확인 → 검색(Serper) → 메타필터 → 비전검증 → 저장.
어떤 예외도 호출부(보고서 ④ 생성·제품 조회)를 죽이지 않는다 — 절대
raise 하지 않고 결과 dict 만 반환(안전 퇴화). 이미지는 보조이며 필수 아님.

★ 측정: 채택 이미지 URL + 탈락 후보 URL·사유를 로그에 명시 출력 —
사용자가 로그만 보고 채택 URL 을 브라우저로 열어 육안 검증 가능.
"""
from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, Optional


def collect_and_store_product_image(
    product_id: int,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """반환: {status, image_url, ...}. status ∈ {cached, stored,
    no_image, disabled, error}. 절대 예외를 던지지 않는다.
    """
    result: Dict[str, Any] = {"product_id": product_id, "status": "error",
                              "image_url": None}
    t0 = perf_counter()
    try:
        from scripts.config import (
            PRODUCT_IMAGE_ENABLED,
            PRODUCT_IMAGE_MIN_PX,
            PRODUCT_IMAGE_SEARCH_NUM,
        )
        from scripts.product_image.store import get_product, set_product_image

        if not PRODUCT_IMAGE_ENABLED:
            print(f"[IMG] product={product_id} skipped — PRODUCT_IMAGE_ENABLED=off")
            result["status"] = "disabled"
            return result

        prod = get_product(product_id)
        if not prod:
            print(f"[IMG] product={product_id} not found → skip")
            result["status"] = "error"
            result["reason"] = "product_not_found"
            return result

        # 캐시: 이미 image_url 있으면 재검색·재검증 안 함
        existing = prod.get("image_url")
        if existing and str(existing).strip() and not force:
            print(f"[IMG] product={product_id}({prod.get('name')}) "
                  f"CACHE-HIT reuse url={existing}")
            result["status"] = "cached"
            result["image_url"] = existing
            return result

        from scripts.product_image.search import (
            build_query, serper_image_search,
        )
        from scripts.product_image.metadata_filter import metadata_prefilter
        from scripts.product_image.vision_verify import vision_select

        name = prod.get("name") or ""
        query = build_query(name, prod.get("brand") or "")

        # 1) 검색 (Serper)
        try:
            candidates, s_perf = serper_image_search(
                query, PRODUCT_IMAGE_SEARCH_NUM)
        except Exception as e:  # noqa: BLE001 — API 오류 안전 퇴화
            print(f"[IMG] product={product_id} search FAILED "
                  f"{type(e).__name__}: {e} → no_image")
            result["status"] = "no_image"
            result["reason"] = f"search_error:{type(e).__name__}"
            return result
        print(f"[PERF][img] product={product_id} query={query!r} "
              f"received={s_perf.get('received')} "
              f"search_ms={s_perf.get('ms')} "
              f"err={s_perf.get('error')}")
        if not candidates:
            print(f"[IMG] product={product_id} 검색 0건 → no_image")
            result["status"] = "no_image"
            result["reason"] = s_perf.get("error") or "search_empty"
            return result

        # 2) 메타데이터 1차 필터 (명백한 노이즈만)
        # 보강 B: 검색 순위 컷 없음 — 명백한 노이즈만 거르고 전부 비전으로.
        kept, meta_rejected = metadata_prefilter(
            candidates, min_px=PRODUCT_IMAGE_MIN_PX)
        for r in meta_rejected:
            print(f"[IMG]   ✗ meta-reject ({r.get('reject_reason')}) "
                  f"url={r.get('image_url')}")
        # 로그 보강: 비전에 넘기는(=1차 통과) 후보 URL 전부 출력.
        for k in kept:
            print(f"[IMG]   → vision-candidate url={k.get('image_url')}")
        print(f"[PERF][img] product={product_id} meta_kept={len(kept)} "
              f"meta_rejected={len(meta_rejected)} → vision={len(kept)}")
        if not kept:
            print(f"[IMG] product={product_id} 1차 필터 후 후보 0 → no_image")
            result["status"] = "no_image"
            result["reason"] = "all_metadata_rejected"
            return result

        # 3) 비전 검증 — 보강 A: 서버가 후보를 다운로드(격리)해 base64 로
        #    평가. 후보 1개 다운로드 실패는 그 후보만 탈락.
        try:
            chosen, evals, v_perf = vision_select(name, kept)
        except Exception as e:  # noqa: BLE001 — 최후 안전망(예외 격리)
            print(f"[IMG] product={product_id} vision FAILED "
                  f"{type(e).__name__}: {e} → no_image")
            result["status"] = "no_image"
            result["reason"] = f"vision_error:{type(e).__name__}"
            return result
        for e in evals:
            v = e.get("vision", {})
            if v.get("download_failed"):
                mark = "✗ dl-fail"
            elif chosen and e.get("image_url") == chosen.get("image_url"):
                mark = "✓ pick"
            else:
                mark = "✗"
            print(f"[IMG]   {mark} score={v.get('score')} "
                  f"noise={v.get('is_noise')} "
                  f"reason={v.get('reason')!r} url={e.get('image_url')}")
        print(f"[PERF][img] product={product_id} "
              f"downloaded={v_perf.get('downloaded')} "
              f"dl_failed={v_perf.get('download_failed')} "
              f"vision_calls={v_perf.get('vision_calls')} "
              f"vision_ms={v_perf.get('ms')} "
              f"all_noise={v_perf.get('all_noise')} "
              f"parse_failed={v_perf.get('parse_failed')} "
              f"err={v_perf.get('error')}")

        if not chosen:
            print(f"[IMG] product={product_id} 모든 후보 명백한 노이즈 "
                  f"→ no_image (안전 퇴화)")
            result["status"] = "no_image"
            result["reason"] = "all_candidates_noise"
            return result

        # 4) 저장 (URL 만)
        url = chosen["image_url"]
        try:
            set_product_image(product_id, url)
        except Exception as e:  # noqa: BLE001 — 저장 실패도 호출부 안 죽임
            print(f"[IMG] product={product_id} store FAILED "
                  f"{type(e).__name__}: {e}")
            result["status"] = "error"
            result["reason"] = f"store_error:{type(e).__name__}"
            result["image_url"] = url
            return result

        vv = chosen.get("vision", {})
        print(f"[IMG] product={product_id}({name}) ✅ STORED "
              f"score={vv.get('score')} reason={vv.get('reason')!r} "
              f"url={url}")
        result["status"] = "stored"
        result["image_url"] = url
        return result
    except Exception as e:  # noqa: BLE001 — 최후 안전망: 절대 raise 안 함
        print(f"[IMG] product={product_id} UNEXPECTED "
              f"{type(e).__name__}: {e} → 안전 퇴화")
        result["status"] = "error"
        result["reason"] = f"unexpected:{type(e).__name__}"
        return result
    finally:
        result["total_ms"] = round((perf_counter() - t0) * 1000, 1)
        print(f"[PERF][img] product={product_id} "
              f"status={result.get('status')} "
              f"total_ms={result.get('total_ms')}")
