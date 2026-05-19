"""scripts/rag/* 단위 테스트 (순수·오프라인 — 네트워크·openai·DB 서버 없음).

embed_fn 주입으로 임베딩 API 없이 전 단계 검증. SQLite 는 tmp 파일.
"""
import os
import tempfile

from scripts.rag.chunker import chunk_bundle
from scripts.rag import store
from scripts.rag.retriever import retrieve_bundles

# 결정론적 키워드 벡터 임베더 (네트워크 없음). 키워드 겹침 = 유사도.
_VOCAB = ["배터리", "가격", "카메라", "성능", "디스플레이", "디자인",
          "장점", "단점", "전작", "합의", "불일치", "스펙", "판정",
          "소비자", "댓글", "여론", "구매", "제품"]


def _embed_fn(texts):
    vecs = []
    for t in texts:
        v = [float(t.count(w)) for w in _VOCAB]
        if not any(v):
            v[-1] = 1.0  # 0 벡터 방지
        vecs.append(v)
    return vecs, {"embed_calls": 1, "embed_ms": 0.0, "embedded": len(vecs)}


CR = {
    "sentiment_summary": {"positive_pct": 60, "negative_pct": 20},
    "positive_points": [{"aspect_name": "디스플레이", "summary_line": "화면 밝다",
                         "comment_count": 9}],
    "negative_points": [{"aspect_name": "배터리", "summary_line": "배터리 부족",
                         "comment_count": 7}],
    "top_issues": [{"keyword": "발열", "count": 4}],
}
IR = {
    "verdict": {"trust_score": 80, "summary": "대체로 일치"},
    "agreement_points": [{"topic": "카메라", "reviewer_quote": "좋다"}],
    "disagreement_points": [{"topic": "가격", "gap_type": "opp",
                             "reviewer_quote": "비싸다"}],
    "spec_changes": [{"spec_name": "배터리", "before": "4000", "after": "5000",
                      "delta": "+1000"}],
}
R1 = ("## 장점\n- 배터리 오래간다\n- 디스플레이 밝다\n\n"
      "## 단점\n- 가격이 비싸다\n\n## 전작 대비\n- 성능 향상")


def _bundles():
    return [
        {"video_id": "v1", "title": "리뷰1", "transcript_report": R1,
         "comment_report": CR, "integrated_report": IR,
         "comment_text": "직렬화②", "integrated_text": "직렬화③"},
        {"video_id": "v2", "title": "리뷰2",
         "transcript_report": "## 장점\n- 카메라 훌륭",
         "comment_report": None, "integrated_report": None,
         "comment_text": "", "integrated_text": ""},
    ]


# ── chunker: 구조 보존 ─────────────────────────────────────────


def test_chunker_structure_preserving_with_metadata():
    recs = chunk_bundle(_bundles()[0], "그램16")
    srcs = {r["source"] for r in recs}
    assert srcs == {"report_1", "report_2", "report_3"}
    for r in recs:
        assert r["video_id"] == "v1" and r["product_key"] == "그램16"
        assert r["semantic_tag"] and r["chunk_id"] and r["content_hash"]
    # ① 마크다운 섹션 태그가 분리됨
    tags = {r["semantic_tag"] for r in recs if r["source"] == "report_1"}
    assert "장점" in tags and "단점" in tags
    # ② 부정 포인트가 단점 태그로
    assert any(r["source"] == "report_2" and r["semantic_tag"] == "단점"
               for r in recs)
    # ③ 스펙변화 청크 존재
    assert any(r["semantic_tag"] == "스펙변화" for r in recs)


def test_chunker_empty_reports_no_chunks():
    b = {"video_id": "x", "transcript_report": "", "comment_report": None,
         "integrated_report": None}
    assert chunk_bundle(b, "p") == []


# ── store: schema/upsert/cache/search ──────────────────────────


def test_store_roundtrip_cache_and_scoped_search():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "v.sqlite3")
        store.ensure_schema(db)
        recs = [
            {"chunk_id": "c1", "product_key": "P", "video_id": "v1",
             "source": "report_1", "semantic_tag": "장점", "chunk_idx": 0,
             "text": "배터리 좋다", "content_hash": "h1",
             "embedding": [1.0, 0.0]},
            {"chunk_id": "c2", "product_key": "P", "video_id": "v1",
             "source": "report_1", "semantic_tag": "단점", "chunk_idx": 1,
             "text": "가격 비싸다", "content_hash": "h2",
             "embedding": [0.0, 1.0]},
            {"chunk_id": "c3", "product_key": "OTHER", "video_id": "v9",
             "source": "report_1", "semantic_tag": "장점", "chunk_idx": 0,
             "text": "딴제품", "content_hash": "h3", "embedding": [1.0, 0.0]},
        ]
        assert store.upsert_chunks(db, recs) == 3
        assert store.existing_hashes(db, "P") == {"h1", "h2"}
        res = store.search(db, "P", [1.0, 0.0], top_k=5)
        # 제품 P 로만 가둠 — OTHER 안 섞임
        assert all(c["video_id"] == "v1" for _, c in res)
        # [1,0] 쿼리 → c1 이 최상위
        assert res[0][1]["chunk_id"] == "c1"


# ── retriever: truncate_bundles 와 동일 계약 ───────────────────


def test_retriever_contract_and_per_video_preservation():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "v.sqlite3")
        out, m = retrieve_bundles(
            _bundles(), product_key="그램16", db_path=db, top_k=6,
            total_cap=60000, embed_fn=_embed_fn,
        )
        # 계약: (list, measure dict)
        assert isinstance(out, list) and isinstance(m, dict)
        assert len(out) == 2
        assert [b["video_id"] for b in out] == ["v1", "v2"]
        assert out[0]["title"] == "리뷰1"
        # 필드 키 동일(assemble_input_blocks 가 읽는 것)
        for b in out:
            assert "transcript_report" in b and "comment_text" in b
            assert "integrated_text" in b
        # measure 호환 키
        for k in ("total_chars_after", "total_cap", "proportional_shrink",
                  "rag", "rag_fallback", "retrieved_chunks"):
            assert k in m
        assert m["rag"] is True and m["rag_fallback"] is False


def test_retriever_min_floor_keeps_each_source():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "v.sqlite3")
        out, _ = retrieve_bundles(
            _bundles(), product_key="P", db_path=db, top_k=1,
            total_cap=60000, embed_fn=_embed_fn,
        )
        v1 = next(b for b in out if b["video_id"] == "v1")
        # ①②③ 모두 내용이 있던 v1 은 어느 것도 통째로 0 이 아니어야
        assert v1["transcript_report"].strip()
        assert v1["comment_text"].strip()
        assert v1["integrated_text"].strip()


def test_retriever_total_cap_drops_low_relevance_not_position():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "v.sqlite3")
        out, m = retrieve_bundles(
            _bundles(), product_key="P", db_path=db, top_k=20,
            total_cap=120, embed_fn=_embed_fn,   # 매우 작은 상한 → 강제 제외
        )
        assert m["dropped_low_relevance"] >= 1
        assert m["proportional_shrink"] is True
        assert m["total_chars_after"] <= m["total_cap"] + 200  # 바닥 보존 여유
        # 바닥 보장: v1 의 각 source 최소 1청크는 남음
        v1 = next(b for b in out if b["video_id"] == "v1")
        assert v1["transcript_report"].strip()
