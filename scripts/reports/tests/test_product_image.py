"""scripts/product_image/* 단위 테스트 (순수·오프라인 — Serper·LLM·DB 없음).

vision_call 주입으로 비전 API 없이 채택 규칙 검증.
"""
from scripts.product_image.search import build_query
from scripts.product_image.metadata_filter import metadata_prefilter
from scripts.product_image.vision_verify import vision_select


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


# ── vision_select: 노이즈만 탈락 + 최선 채택 ───────────────────


def test_vision_select_picks_best_non_noise():
    def fake(_name, cs):
        return ('{"results":['
                '{"idx":0,"product_visible_score":4,"is_noise":false,"reason":"ok"},'
                '{"idx":1,"product_visible_score":9,"is_noise":false,"reason":"best"},'
                '{"idx":2,"product_visible_score":10,"is_noise":true,"reason":"밈"}'
                ']}')

    chosen, evals, perf = vision_select(
        "p", _cands(3), vision_call=fake, download_fn=_all_ok)
    assert chosen is not None
    assert chosen["image_url"] == "http://x/1.jpg"
    assert perf["vision_calls"] == 1 and perf["downloaded"] == 3
    noisy = [e for e in evals if e["vision"]["is_noise"]]
    assert noisy and noisy[0]["image_url"] == "http://x/2.jpg"


def test_vision_select_all_noise_returns_none():
    def fake(_n, cs):
        rs = ",".join(
            f'{{"idx":{i},"product_visible_score":0,"is_noise":true,"reason":"x"}}'
            for i in range(len(cs)))
        return '{"results":[' + rs + "]}"

    chosen, _, perf = vision_select(
        "p", _cands(3), vision_call=fake, download_fn=_all_ok)
    assert chosen is None and perf.get("all_noise") is True


def test_vision_select_parse_fail_falls_back_to_first_downloadable():
    chosen, _, perf = vision_select(
        "p", _cands(3), vision_call=lambda n, c: "not-json",
        download_fn=_all_ok)
    assert chosen is not None
    assert chosen["image_url"] == "http://x/0.jpg"
    assert perf.get("parse_failed") is True


def test_vision_select_no_candidates():
    chosen, _, perf = vision_select(
        "p", [], vision_call=lambda n, c: "{}", download_fn=_all_ok)
    assert chosen is None and perf.get("error") == "no_candidates"


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
        return ('{"results":['
                '{"idx":0,"product_visible_score":7,"is_noise":false,"reason":"ok"},'
                '{"idx":1,"product_visible_score":9,"is_noise":false,"reason":"best"}'
                ']}')

    chosen, evals, perf = vision_select(
        "p", _cands(3), vision_call=fake, download_fn=dl)
    assert chosen is not None  # no_image 아님
    assert perf["downloaded"] == 2 and perf["download_failed"] == 1
    # 다운로드 실패 후보가 사유와 함께 평가목록에 남음
    dlf = [e for e in evals if e["vision"].get("download_failed")]
    assert dlf and "HTTP 404" in dlf[0]["vision"]["reason"]
    # 평가된 2개 중 최고점 채택
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
