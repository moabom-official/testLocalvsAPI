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


# ── metadata_prefilter: 명백한 노이즈만 ────────────────────────


def test_metadata_prefilter_drops_only_obvious_noise():
    cands = _cands(3) + [
        {"image_url": "http://x/i.svg", "domain": "store.com",
         "width": 800, "height": 800},
        {"image_url": "http://x/s.jpg", "domain": "store.com",
         "width": 50, "height": 50},
        {"image_url": "http://pinterest.com/p.jpg",
         "domain": "pinterest.com", "width": 900, "height": 900},
    ]
    kept, rej = metadata_prefilter(cands, min_px=300, max_keep=4)
    reasons = " ".join(r["reject_reason"] for r in rej)
    assert "형식 부적합" in reasons and "크기 미달" in reasons
    assert "노이즈 도메인" in reasons
    # 정상 후보는 살아남되 상한 4개
    assert len(kept) == 3
    assert all(k["domain"] == "store.com" for k in kept)


def test_metadata_prefilter_caps_to_max_keep():
    kept, rej = metadata_prefilter(_cands(10), min_px=300, max_keep=4)
    assert len(kept) == 4
    assert any("상한 초과" in r["reject_reason"] for r in rej)


def test_metadata_prefilter_keeps_when_size_unknown():
    # 크기 정보 없음(0) → 작다고 단정 말고 통과(애매하면 비전이 판단)
    kept, _ = metadata_prefilter(
        [{"image_url": "http://x/a.jpg", "domain": "d.com",
          "width": 0, "height": 0}], min_px=300, max_keep=4)
    assert len(kept) == 1


# ── vision_select: 노이즈만 탈락 + 최선 채택 ───────────────────


def test_vision_select_picks_best_non_noise():
    cands = _cands(3)

    def fake(_name, cs):
        return ('{"results":['
                '{"idx":0,"product_visible_score":4,"is_noise":false,"reason":"ok"},'
                '{"idx":1,"product_visible_score":9,"is_noise":false,"reason":"best"},'
                '{"idx":2,"product_visible_score":10,"is_noise":true,"reason":"밈"}'
                ']}')

    chosen, evals, perf = vision_select("p", cands, vision_call=fake)
    assert chosen is not None
    assert chosen["image_url"] == "http://x/1.jpg"  # 최고점 비노이즈
    assert perf["vision_calls"] == 1
    # 노이즈 후보는 탈락 표기
    noisy = [e for e in evals if e["vision"]["is_noise"]]
    assert noisy and noisy[0]["image_url"] == "http://x/2.jpg"


def test_vision_select_all_noise_returns_none():
    def fake(_n, cs):
        rs = ",".join(
            f'{{"idx":{i},"product_visible_score":0,"is_noise":true,"reason":"x"}}'
            for i in range(len(cs)))
        return '{"results":[' + rs + "]}"

    chosen, evals, perf = vision_select("p", _cands(3), vision_call=fake)
    assert chosen is None
    assert perf.get("all_noise") is True


def test_vision_select_parse_fail_falls_back_to_first():
    chosen, evals, perf = vision_select(
        "p", _cands(3), vision_call=lambda n, c: "not-json")
    # 파싱 실패 → 이미지 없음 회피, 검색 1순위 채택(§4 철학)
    assert chosen is not None
    assert chosen["image_url"] == "http://x/0.jpg"
    assert perf.get("parse_failed") is True


def test_vision_select_no_candidates():
    chosen, evals, perf = vision_select("p", [], vision_call=lambda n, c: "{}")
    assert chosen is None and perf.get("error") == "no_candidates"
