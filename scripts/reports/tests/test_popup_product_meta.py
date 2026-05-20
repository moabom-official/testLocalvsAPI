"""scripts/popup/product_meta.py 단위 테스트 (순수 파서 + 주입 search_fn).

오프라인 — 외부 Serper/DB 호출 없음.
"""
from scripts.popup.product_meta import (
    fetch_meta,
    format_price_display,
    official_domain_for,
    parse_prices,
    parse_release_year,
    parse_screen,
)


# ── 순수 파서 ────────────────────────────────────────────────


def test_parse_prices_man_won_formats():
    text = "최저 129만 원~ / 정가 1,290,000원 / 호환 5만원"
    prices = parse_prices(text)
    # 5만원(50000)은 합리범위 통과(>=50000) — 129만(1,290,000)·1,290,000 둘 다 통과
    assert 1_290_000 in prices
    # 가장 낮은 값이 출시가 추정으로 쓰임
    assert min(prices) <= 1_290_000


def test_parse_prices_ignores_noise():
    # 합리 범위(5만~1500만) 밖은 제외
    assert parse_prices("3원") == []
    assert parse_prices("99999999원") == []


def test_parse_screen_first_match():
    assert parse_screen("6.7인치 OLED 화면") == "6.7인치"
    assert parse_screen("화면 없음") is None


def test_parse_release_year_recent_first():
    assert parse_release_year("2026년 출시") == 2026
    # 너무 옛날 연도는 무시
    assert parse_release_year("1999년 모델") is None


def test_format_price_display_man_unit():
    assert format_price_display(1_290_000) == "최저 129만 원~"
    assert format_price_display(500_000) == "최저 50만 원~"
    assert format_price_display(None) is None
    assert format_price_display(0) is None


# ── 조합기 — search_fn 주입 ────────────────────────────────


def test_fetch_meta_combines_fields_from_search():
    def fake_search(q):
        return [
            {"title": "노바폰 5 Pro 출시", "snippet": "2026년 출시 6.7인치 OLED", "link": "https://x/1"},
            {"title": "가격 동향", "snippet": "최저 129만 원~ / 정가 1,290,000원", "link": "https://x/2"},
        ], {"query": q, "ms": 1.0}

    fields, perf = fetch_meta("노바폰 5 Pro", "노바", search_fn=fake_search, query_suffix="x")
    assert fields["screen_size"] == "6.7인치"
    assert fields["release_year"] == 2026
    assert fields["price_display"] == "최저 129만 원~"
    # 보강 6: 정책 버전 태그가 source 앞에 부착 (캐시 invalidation 용)
    assert fields["source"].startswith("v2|") and fields["source"].endswith("https://x/1")
    assert perf.get("ms") == 1.0


def test_fetch_meta_partial_fields_safe():
    # 검색 결과는 있는데 가격 파싱 실패
    def fake_search(q):
        return [{"title": "스펙", "snippet": "6.7인치 OLED", "link": ""}], {}

    fields, _ = fetch_meta("노바폰", "", search_fn=fake_search, query_suffix="x")
    assert fields["screen_size"] == "6.7인치"
    assert fields["price_display"] is None  # 가격 못 찾음 → None(§7 fallback)
    assert fields["release_year"] is None


def test_official_domain_for_light_mapping():
    # 보강 6: 가벼운 매핑 — 한/영 표기 모두 일치, 없는 브랜드는 None
    assert official_domain_for("Apple") == "apple.com"
    assert official_domain_for("애플") == "apple.com"
    assert official_domain_for("samsung electronics") == "samsung.com"
    assert official_domain_for("LG") == "lge.co.kr"
    assert official_domain_for("xiaomi") == "mi.com"
    assert official_domain_for("Nothing") is None  # 매핑 없음 → 일반 검색
    assert official_domain_for("") is None


def test_fetch_meta_price_only_from_official_items_for_mapped_brand():
    # 보강 6 옵션 (b): site: 쿼리 한정 X, 결과 후필터. 가격은 공식 도메인
    # 매칭 항목에서만 파싱 — 중고/할인가(타 도메인) 차단.
    def fake_search(q):
        return [
            {"title": "쇼핑몰 중고", "snippet": "최저 50만 원~", "link": "https://kt-mall.co.kr/p"},
            {"title": "Apple 공식", "snippet": "최저 129만 원~", "link": "https://apple.com/iphone"},
            {"title": "스펙", "snippet": "6.1인치 2023년 출시", "link": "https://news.x.com/p"},
        ], {}

    fields, perf = fetch_meta("아이폰15", "Apple", search_fn=fake_search, query_suffix="x")
    # 가격은 공식 도메인 항목(129만원)만, 쇼핑몰 50만원은 차단
    assert fields["price_display"] == "최저 129만 원~"
    assert perf.get("site") == "apple.com"
    assert perf.get("official_items") == 1
    # 스펙(인치·연도)은 전체 결과에서
    assert fields["screen_size"] == "6.1인치"
    assert fields["release_year"] == 2023


def test_fetch_meta_price_none_when_no_official_match():
    # 매핑된 브랜드인데 공식 도메인 매칭 0건 → 가격 None (잘못된 가격
    # 채택하지 않음, §7 fallback). 스펙은 가능한 만큼 파싱.
    def fake_search(q):
        return [{"title": "쇼핑몰", "snippet": "최저 99만 원~ 6.7인치",
                 "link": "https://kt-mall.co.kr/p"}], {}

    fields, perf = fetch_meta("아이폰15", "Apple", search_fn=fake_search, query_suffix="x")
    assert fields["price_display"] is None     # 공식 매칭 0 → 가격 X
    assert fields["screen_size"] == "6.7인치"   # 스펙은 전체에서 OK
    assert perf.get("official_items") == 0


def test_fetch_meta_search_exception_safe_degrade():
    def boom(q):
        raise RuntimeError("network")

    fields, perf = fetch_meta("x", "", search_fn=boom, query_suffix="x")
    # 어떤 필드도 채워지지 않지만 raise 안 함
    assert all(fields[k] is None for k in (
        "price_raw", "price_display", "screen_size", "release_year", "source"))
    assert perf.get("error") == "RuntimeError"
