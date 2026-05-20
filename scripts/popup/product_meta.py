"""가격·스펙 외부 수집 + 캐시 (Phase 5 §5 + 보강 6).

전략(§5-B 옵션 (iii) 휴리스틱):
  Serper Web 검색 → 상위 결과의 title/snippet 텍스트에서 정규식으로
  가격·화면크기·출시연도를 추출. 무거운 스크래핑 의존성 없음(requests
  만, Phase 3 와 같은 의존성). 실패해도 §7 fallback 으로 팝업 계속 동작.

[보강 6] 가격을 **공식 제조사 출시가**로 좁힘:
  - 브랜드→공식 도메인 매핑(가벼움, Phase 3 출처등급 철학) → Serper 쿼리
    에 `site:<domain>` 한정자 추가. 매핑 없는 브랜드는 기존 일반 검색.
  - 캐시 정책 버전 태그(_POLICY_TAG)를 source 앞에 부착(예: 'v2|<url>').
    구 정책 캐시(태그 없음/다른 버전) 는 collect_and_cache_meta 에서
    무시·재수집(스키마 무변경 — 기존 source 컬럼만 사용).
순수 단계 분리:
  parse_price/parse_screen/parse_release_year — 순수, 텍스트 → 값
  serper_web_search — 외부 호출(예외 격리)
  fetch_meta — search_fn 주입 가능(테스트 오프라인)
  collect_and_cache_meta — 오케스트레이터(절대 raise 안 함)
"""
from __future__ import annotations

import re
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── 순수 파서 ────────────────────────────────────────────────────

# "129만 원", "1,290,000원", "1290000원" 등을 정수(원)로 환산해 최저값 선택.
_RE_PRICE_MAN = re.compile(r"(\d{2,4}(?:[,．]\d{3})?)\s*만\s*원")
_RE_PRICE_WON = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{6,9})\s*원")
_RE_SCREEN = re.compile(r"(\d{1,2}\.\d{1,2})\s*인치")
_RE_YEAR = re.compile(r"(20\d{2})\s*년")


# 보강 6 — 가벼운 브랜드→공식 도메인 매핑(소문자 키, 부분일치). 정밀
# 매핑이 아니라 "흔한 제조사 몇 개"만. 매핑 없으면 site: 한정 없이 일반 검색.
_BRAND_OFFICIAL_DOMAINS: Dict[str, str] = {
    "apple": "apple.com",
    "애플": "apple.com",
    "samsung": "samsung.com",
    "삼성": "samsung.com",
    "lg": "lge.co.kr",
    "엘지": "lge.co.kr",
    "sony": "sony.co.kr",
    "google": "store.google.com",
    "구글": "store.google.com",
    "microsoft": "microsoft.com",
    "xiaomi": "mi.com",
    "샤오미": "mi.com",
    "asus": "asus.com",
    "lenovo": "lenovo.com",
    "dell": "dell.com",
    "hp": "hp.com",
}

# 캐시 정책 버전 태그. 정책이 바뀌면 v3 등으로 올려 자연 invalidation.
_POLICY_TAG = "v2"


def official_domain_for(brand: str) -> Optional[str]:
    """브랜드 문자열에서 공식 도메인 추출(소문자 부분일치). 없으면 None."""
    b = (brand or "").strip().lower()
    if not b:
        return None
    for key, dom in _BRAND_OFFICIAL_DOMAINS.items():
        if key in b:
            return dom
    return None


def parse_prices(text: str) -> List[int]:
    """텍스트에서 가능한 모든 가격(원)을 정수로 추출. 합리적 범위 필터링."""
    if not text:
        return []
    out: List[int] = []
    for m in _RE_PRICE_MAN.finditer(text):
        digits = m.group(1).replace(",", "").replace(".", "")
        try:
            out.append(int(digits) * 10000)
        except ValueError:
            continue
    for m in _RE_PRICE_WON.finditer(text):
        digits = m.group(1).replace(",", "")
        try:
            v = int(digits)
            if v >= 100000:  # 10만 원 미만은 노이즈로 간주
                out.append(v)
        except ValueError:
            continue
    # 합리적 범위(5만~1500만)만 통과 — 광고/잡음 차단
    return [v for v in out if 50_000 <= v <= 15_000_000]


def parse_screen(text: str) -> Optional[str]:
    """첫 번째 매칭 화면 크기를 "X.X인치" 표기로."""
    if not text:
        return None
    m = _RE_SCREEN.search(text)
    if not m:
        return None
    return f"{m.group(1)}인치"


def parse_release_year(text: str) -> Optional[int]:
    """가장 최근에 가까운 4자리 연도(2015~현재+1) 중 처음 매칭."""
    if not text:
        return None
    from datetime import date

    cur = date.today().year
    for m in _RE_YEAR.finditer(text):
        try:
            y = int(m.group(1))
        except ValueError:
            continue
        if 2015 <= y <= cur + 1:
            return y
    return None


def format_price_display(price_raw: Optional[int]) -> Optional[str]:
    """원 단위 정수 → "최저 N만 원~" 표기(§5-A 사용자 결정 10).

    소수점 반올림(만원 단위). 가격이 None 이면 None.
    """
    if not price_raw or price_raw <= 0:
        return None
    man = max(1, round(price_raw / 10000))
    return f"최저 {man}만 원~"


# ── 외부 호출 (Serper Web) ───────────────────────────────────────


def serper_web_search(query: str, *, num: int = 5) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Serper Web 검색 → 상위 organic 결과 [{title, snippet, link}].

    예외(타임아웃/HTTP 오류)는 그대로 raise — 호출부(fetch_meta)가 격리.
    키 부재는 빈 결과로 안전 처리.
    """
    import requests

    from scripts.config import SERPER_API_KEY

    perf: Dict[str, Any] = {"query": query, "num": num,
                            "received": 0, "ms": 0.0}
    if not SERPER_API_KEY:
        perf["error"] = "no_serper_key"
        return [], perf
    t0 = perf_counter()
    resp = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": SERPER_API_KEY,
                 "Content-Type": "application/json"},
        json={"q": query, "num": num, "gl": "kr", "hl": "ko"},
        timeout=15,
    )
    perf["ms"] = round((perf_counter() - t0) * 1000, 1)
    perf["status_code"] = resp.status_code
    resp.raise_for_status()
    data = resp.json() or {}
    out = []
    for it in (data.get("organic") or []):
        out.append({
            "title": it.get("title") or "",
            "snippet": it.get("snippet") or "",
            "link": it.get("link") or "",
        })
    perf["received"] = len(out)
    return out, perf


# ── 조합기 ──────────────────────────────────────────────────────


def fetch_meta(
    name: str,
    brand: str = "",
    *,
    search_fn: Optional[Callable[[str], Tuple[List[Dict[str, Any]], Dict[str, Any]]]] = None,
    query_suffix: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """검색 결과 텍스트 → 가격·스펙 파싱. 반환: (fields, perf).

    fields 키: price_raw, price_display, screen_size, release_year, source.
    어느 항목이든 추출 실패 시 그 키만 None — 가능한 만큼만 채워 반환.
    search_fn / query_suffix 주입 시(테스트) Serper·config 없이 동작.
    """
    if query_suffix is None:
        from scripts.config import PRODUCT_META_QUERY_SUFFIX as _QS
        query_suffix = _QS

    base = (name or "").strip()
    b = (brand or "").strip()
    if b and b.lower() not in base.lower():
        base = f"{b} {base}"
    # 보강 6 — 옵션 (b) 후필터 채택(실측 사유: site:<dom> 쿼리 한정은
    # apple.com 안에 동일 시리즈 다른 모델 가격/사양이 섞여 노이즈가
    # 오히려 늘었음 — 5제품 실측 → 가격 None / 4.7인치 오추출 다발).
    # 새 정책: 일반 검색을 그대로 하되, **가격**은 공식 도메인으로 매칭된
    # 항목에서만 파싱(중고가·할인가 차단). 스펙(인치·연도)은 전체에서
    # 파싱(공식 페이지가 spec 노출에 인색해도 외부 매체에서 안정적).
    domain = official_domain_for(brand)
    query = f"{base} {query_suffix}".strip()

    fn = search_fn or serper_web_search
    try:
        items, perf = fn(query)
    except Exception as e:  # noqa: BLE001 — 외부 실패는 안전 퇴화
        return {"price_raw": None, "price_display": None,
                "screen_size": None, "release_year": None,
                "source": None}, {"query": query, "site": domain,
                                  "error": f"{type(e).__name__}"}

    text_blob = " ".join(
        f"{i.get('title','')} {i.get('snippet','')}" for i in items
    )
    # 스펙(인치·연도) — 전체 결과에서
    screen = parse_screen(text_blob)
    year = parse_release_year(text_blob)
    # 가격 — 공식 도메인 매칭 항목만(노이즈 차단). 매핑 없거나 매칭 0이면
    # 가격 None (§7 fallback) — 잘못된 중고/할인가 채택하느니 정보 없음.
    if domain:
        official_items = [it for it in items
                          if domain in (it.get("link") or "").lower()]
    else:
        official_items = items   # 매핑 없는 브랜드는 일반 검색 결과 사용
    if official_items:
        off_blob = " ".join(
            f"{i.get('title','')} {i.get('snippet','')}"
            for i in official_items
        )
        prices = parse_prices(off_blob)
        raw_link = official_items[0]["link"]
    else:
        prices = []
        raw_link = items[0]["link"] if items else None
    price_raw = min(prices) if prices else None
    # 정책 태그 부착 — 캐시 invalidation 용(스키마 무변경, source 컬럼만 사용)
    source = f"{_POLICY_TAG}|{raw_link}" if raw_link else _POLICY_TAG

    perf["site"] = domain
    perf["official_items"] = len(official_items)
    fields = {
        "price_raw": price_raw,
        "price_display": format_price_display(price_raw),
        "screen_size": screen,
        "release_year": year,
        "source": source,
    }
    return fields, perf


def collect_and_cache_meta(
    product_id: int,
    name: str,
    brand: str = "",
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """오케스트레이터: 캐시 확인 → 검색·파싱 → 저장. 절대 raise 안 함.

    반환: {price_display, screen_size, release_year, source, status}.
    status ∈ {cached, fetched, disabled, error}.
    """
    result: Dict[str, Any] = {"status": "error", "price_display": None,
                              "screen_size": None, "release_year": None,
                              "source": None}
    try:
        from scripts.config import PRODUCT_META_FETCH_ENABLED
        from scripts.popup import store

        if not force:
            cached = store.get_meta(product_id)
            # 보강 6 — 정책 버전 태그가 source 에 있는 캐시만 신뢰. 구 정책
            # 캐시(태그 없음/다른 버전)는 무시·재수집(스키마 무변경).
            src = (cached or {}).get("source") or ""
            if cached and src.startswith(_POLICY_TAG + "|") or src == _POLICY_TAG:
                result.update({
                    "status": "cached",
                    "price_display": cached.get("price_display"),
                    "screen_size": cached.get("screen_size"),
                    "release_year": cached.get("release_year"),
                    "source": cached.get("source"),
                })
                return result

        if not PRODUCT_META_FETCH_ENABLED:
            result["status"] = "disabled"
            return result

        fields, perf = fetch_meta(name, brand)
        print(f"[PERF][popup_meta] product={product_id} query="
              f"{perf.get('query')!r} ms={perf.get('ms')} "
              f"err={perf.get('error')} "
              f"price={fields.get('price_display')} "
              f"screen={fields.get('screen_size')} "
              f"year={fields.get('release_year')}")
        try:
            store.upsert_meta(product_id, **fields)
        except Exception as e:  # noqa: BLE001 — 저장 실패도 호출부 안 죽임
            print(f"[WARN][popup_meta] cache write failed "
                  f"{type(e).__name__}: {e}")
        result.update({
            "status": "fetched",
            "price_display": fields.get("price_display"),
            "screen_size": fields.get("screen_size"),
            "release_year": fields.get("release_year"),
            "source": fields.get("source"),
        })
        return result
    except Exception as e:  # noqa: BLE001 — 최후 안전망
        print(f"[WARN][popup_meta] unexpected {type(e).__name__}: {e}")
        result["status"] = "error"
        result["reason"] = f"unexpected:{type(e).__name__}"
        return result
