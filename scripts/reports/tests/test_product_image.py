"""scripts/product_image/* 단위 테스트 (순수·오프라인 — Serper·LLM·DB 없음).

vision_call 주입으로 비전 API 없이 채택 규칙 검증.
"""
from scripts.product_image.search import build_query
from scripts.product_image.metadata_filter import metadata_prefilter
from scripts.product_image.vision_verify import source_tier, vision_select


def _cands(n=5):
    return [{"image_url": f"http://x/{i}.jpg", "title": f"t{i}",
             "domain": "store.com", "width": 800, "height": 800,
             "position": i} for i in range(n)]


# ── build_query ────────────────────────────────────────────────


def test_build_query_adds_brand_and_suffix():
    q = build_query("아이폰17", "Apple", suffix="공식 제품 사진")
    assert "아이폰17" in q and "Apple" in q and "제품 사진" in q
    # brand 가 name 에 이미 있으면 중복 안 함
    q2 = build_query("Apple 아이폰17", "Apple", suffix="공식 제품 사진")
    assert q2.count("Apple") == 1


# 테스트용 download_fn — 실제 네트워크 없이 전부 다운로드 성공 처리
def _all_ok(cs):
    return [{**c, "_dl_ok": True, "_data_uri": "data:image/jpeg;base64,AA"}
            for c in cs]


# ── metadata_prefilter: 명백한 노이즈만 (보강 B: 검색순위 컷 없음) ──


def test_metadata_prefilter_drops_only_obvious_noise():
    cands = _cands(3) + [
        {"image_url": "http://x/i.svg", "domain": "store.com",
         "width": 800, "height": 800},
        {"image_url": "http://x/s.jpg", "domain": "store.com",
         "width": 50, "height": 50},
        {"image_url": "http://pinterest.com/p.jpg",
         "domain": "pinterest.com", "width": 900, "height": 900},
    ]
    kept, rej = metadata_prefilter(cands, min_px=300)
    reasons = " ".join(r["reject_reason"] for r in rej)
    assert "형식 부적합" in reasons and "크기 미달" in reasons
    assert "노이즈 도메인" in reasons
    assert len(kept) == 3
    assert all(k["domain"] == "store.com" for k in kept)


def test_metadata_prefilter_no_search_rank_cut():
    # 보강 B: 노이즈가 아니면 검색 순위와 무관하게 전부 통과(컷 없음)
    kept, rej = metadata_prefilter(_cands(10), min_px=300)
    assert len(kept) == 10
    assert not any("상한 초과" in r.get("reject_reason", "") for r in rej)


def test_metadata_prefilter_keeps_when_size_unknown():
    kept, _ = metadata_prefilter(
        [{"image_url": "http://x/a.jpg", "domain": "d.com",
          "width": 0, "height": 0}], min_px=300)
    assert len(kept) == 1


# 새 스키마 비전 응답 빌더: front_back/not_cropped/clarity (각 0~5)
def _vr(*rows):
    items = []
    for i, (fb, cr, cl, noise, rs) in enumerate(rows):
        items.append(
            f'{{"idx":{i},"front_back":{fb},"not_cropped":{cr},'
            f'"clarity":{cl},"is_noise":{str(noise).lower()},'
            f'"reason":"{rs}"}}')
    return '{"results":[' + ",".join(items) + "]}"


# ── vision_select: 노이즈만 탈락 + 최선 채택 (1순위=제품 드러남) ──


def test_vision_select_picks_highest_reveal_non_noise():
    # idx1: 전후면·온전 → 드러남 최고. idx2: 노이즈. idx0: 한면/잘림.
    def fake(_n, cs):
        return _vr((1, 1, 2, False, "한면 잘림"),
                   (5, 5, 5, False, "전후면 온전"),
                   (5, 5, 5, True, "밈"))

    chosen, evals, perf = vision_select(
        "p", _cands(3), vision_call=fake, download_fn=_all_ok)
    assert chosen["image_url"] == "http://x/1.jpg"
    assert perf["vision_calls"] == 1 and perf["downloaded"] == 3
    noisy = [e for e in evals if e["vision"]["is_noise"]]
    assert noisy and noisy[0]["image_url"] == "http://x/2.jpg"


def test_front_back_beats_single_face():
    # 전후면 다 보임(idx1) > 한 면만(idx0). 잘림·선명도는 동일.
    def fake(_n, cs):
        return _vr((1, 5, 5, False, "전면만"),
                   (5, 5, 5, False, "전후면"))

    chosen, _, _ = vision_select(
        "p", _cands(2), vision_call=fake, download_fn=_all_ok)
    assert chosen["image_url"] == "http://x/1.jpg"


def test_not_cropped_beats_cropped():
    # 온전(idx1) > 잘림(idx0). 전후면·선명도 동일.
    def fake(_n, cs):
        return _vr((5, 1, 5, False, "아래 잘림"),
                   (5, 5, 5, False, "온전"))

    chosen, _, _ = vision_select(
        "p", _cands(2), vision_call=fake, download_fn=_all_ok)
    assert chosen["image_url"] == "http://x/1.jpg"


def test_vision_select_all_noise_returns_none():
    def fake(_n, cs):
        return _vr(*[(0, 0, 0, True, "x") for _ in cs])

    chosen, _, perf = vision_select(
        "p", _cands(3), vision_call=fake, download_fn=_all_ok)
    assert chosen is None and perf.get("all_noise") is True


def test_vision_select_no_perfect_candidate_still_picks_best():
    # 아무도 완벽치 않아도(전부 부분 점수) 최선이 반드시 채택 — no_image X
    def fake(_n, cs):
        return _vr((1, 1, 1, False, "약함"),
                   (2, 3, 1, False, "그나마 나음"),
                   (1, 0, 2, False, "약함2"))

    chosen, _, perf = vision_select(
        "p", _cands(3), vision_call=fake, download_fn=_all_ok)
    assert chosen is not None and chosen["image_url"] == "http://x/1.jpg"
    assert perf.get("all_noise") is None


def test_vision_select_parse_fail_falls_back_to_first_downloadable():
    chosen, _, perf = vision_select(
        "p", _cands(3), vision_call=lambda n, c: "not-json",
        download_fn=_all_ok)
    assert chosen is not None
    assert chosen["image_url"] == "http://x/0.jpg"
    assert perf.get("parse_failed") is True


def test_vision_select_missing_fields_conservative_no_crash():
    # 새 항목 누락 → 보수적 0 처리, 크래시·무조건 no_image 아님
    def fake(_n, cs):
        return ('{"results":['
                '{"idx":0,"is_noise":false,"reason":"필드없음"},'
                '{"idx":1,"front_back":5,"not_cropped":5,"clarity":5,'
                '"is_noise":false,"reason":"풀"}'
                ']}')

    chosen, evals, _ = vision_select(
        "p", _cands(2), vision_call=fake, download_fn=_all_ok)
    assert chosen["image_url"] == "http://x/1.jpg"   # 필드있는 쪽이 우월
    assert evals[0]["vision"]["reveal_score"] == 0.0  # 누락→보수적 0


def test_vision_select_no_candidates():
    chosen, _, perf = vision_select(
        "p", [], vision_call=lambda n, c: "{}", download_fn=_all_ok)
    assert chosen is None and perf.get("error") == "no_candidates"


# ── 출처 등급(2순위) + 동점 깨기 ───────────────────────────────


def test_source_tier_light_classification():
    assert source_tier("apple.com") == 2
    assert source_tier("store.storeimages.cdn-apple.com") == 2  # 공식>‘store’
    assert source_tier("www.lge.co.kr") == 2
    assert source_tier("kt-mall.co.kr") == 0
    assert source_tier("i.namu.wiki") == 0
    assert source_tier("blog.naver.com") == 0
    assert source_tier("somerandomnews.co.kr") == 1   # 애매 → 기본 중간
    assert source_tier("") == 1


def _c(url, dom):
    return {"image_url": url, "domain": dom, "link": "", "title": "",
            "width": 800, "height": 800}


def test_tie_broken_by_source_official_over_shop():
    # 제품 드러남 동점(둘 다 5/5/5) → 출처 등급으로 공식(뒤 순서) 채택
    cands = [_c("http://kt-mall.co.kr/a.jpg", "kt-mall.co.kr"),
             _c("http://apple.com/b.jpg", "apple.com")]

    def fake(_n, cs):
        return _vr((5, 5, 5, False, "shop"), (5, 5, 5, False, "official"))

    chosen, _, perf = vision_select(
        "p", cands, vision_call=fake, download_fn=_all_ok)
    assert chosen["domain"] == "apple.com"
    assert perf["chosen_source_tier"] == 2
    assert perf["tie_broken_by_source"] is True


def test_reveal_precedence_not_overridden_by_source():
    # 쇼핑몰 드러남 高 vs 공식 드러남 低 → 드러남 우선(쇼핑몰 채택)
    cands = [_c("http://kt-mall.co.kr/a.jpg", "kt-mall.co.kr"),
             _c("http://apple.com/b.jpg", "apple.com")]

    def fake(_n, cs):
        return _vr((5, 5, 5, False, "shop full"),
                   (1, 1, 1, False, "official partial"))

    chosen, _, perf = vision_select(
        "p", cands, vision_call=fake, download_fn=_all_ok)
    assert chosen["domain"] == "kt-mall.co.kr"   # 드러남 1순위
    assert perf["tie_broken_by_source"] is False


def test_full_tie_keeps_search_order():
    # 드러남도 출처등급도 동일(둘 다 tier1) → 먼저 온 후보 유지
    cands = [_c("http://news-a.com/a.jpg", "news-a.com"),
             _c("http://news-b.com/b.jpg", "news-b.com")]

    def fake(_n, cs):
        return _vr((4, 4, 4, False, "a"), (4, 4, 4, False, "b"))

    chosen, _, perf = vision_select(
        "p", cands, vision_call=fake, download_fn=_all_ok)
    assert chosen["domain"] == "news-a.com"
    assert perf["tie_broken_by_source"] is False


# ── 보강 A: 후보별 다운로드 실패 격리 ──────────────────────────


def test_vision_select_one_download_fail_others_proceed():
    # idx1 만 다운로드 실패 → 그 후보만 탈락, 나머지로 채택 진행
    def dl(cs):
        out = []
        for i, c in enumerate(cs):
            if i == 1:
                out.append({**c, "_dl_ok": False, "_dl_reason": "HTTP 404"})
            else:
                out.append({**c, "_dl_ok": True,
                            "_data_uri": "data:image/jpeg;base64,AA"})
        return out

    def fake(_n, cs):  # cs = 다운로드 성공분만 (idx 재부여)
        return _vr((3, 3, 3, False, "ok"), (5, 5, 5, False, "best"))

    chosen, evals, perf = vision_select(
        "p", _cands(3), vision_call=fake, download_fn=dl)
    assert chosen is not None  # no_image 아님
    assert perf["downloaded"] == 2 and perf["download_failed"] == 1
    # 다운로드 실패 후보가 사유와 함께 평가목록에 남음
    dlf = [e for e in evals if e["vision"].get("download_failed")]
    assert dlf and "HTTP 404" in dlf[0]["vision"]["reason"]
    # 평가된 2개 중 드러남 최고 채택 (다운로드 성공분 idx0=cands[0],
    # idx1=cands[2]; best 는 두 번째 → http://x/2.jpg)
    assert chosen["image_url"] == "http://x/2.jpg"


def test_vision_select_all_download_fail_no_image():
    def dl(cs):
        return [{**c, "_dl_ok": False, "_dl_reason": "timeout"} for c in cs]

    chosen, evals, perf = vision_select(
        "p", _cands(3), vision_call=lambda n, c: "{}", download_fn=dl)
    assert chosen is None
    assert perf.get("error") == "no_downloadable"
    assert perf["download_failed"] == 3
    assert all(e["vision"].get("download_failed") for e in evals)


def test_vision_select_vision_call_exception_falls_back():
    # 다운로드는 됐는데 비전 호출 자체가 예외 → 이미지 없음 회피(1순위 채택)
    def boom(_n, _c):
        raise RuntimeError("gateway 500")

    chosen, _, perf = vision_select(
        "p", _cands(3), vision_call=boom, download_fn=_all_ok)
    assert chosen is not None
    assert chosen["image_url"] == "http://x/0.jpg"
    assert "RuntimeError" in perf.get("vision_error", "")
