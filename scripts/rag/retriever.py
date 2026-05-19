"""RAG retriever — _pir_input.truncate_bundles 와 동일 입출력 계약.

입력  = serialized bundles (video_id/title + transcript_report/comment_text/
        integrated_text + comment_report/integrated_report dict)
출력  = (가공된 bundles, measure dict)  ← truncate_bundles 와 동일 계약
이래야 serialize_bundles → retriever → assemble_input_blocks 가 안 깨진다.

설계: 절삭 대체물이 아니라 "관련도 기반 재정렬". 입력이 상한 안이어도
④ 측면 쿼리로 청크를 관련도순 재정렬(앞=고관련) → lost-in-the-middle 완화.
상한 초과 시 관련도 하위 청크부터(절삭의 위치 편향 없이) 제외.
부수효과(임베딩 API·SQLite I/O)는 embed_fn·db_path 로 명시 격리 — Phase 4
가 노드로 흡수 가능. 어떤 예외도 호출부가 절삭 폴백으로 안전 퇴화.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# ④의 7섹션이 다루는 측면 쿼리 (상수 — ④ 프롬프트 측면과 매칭).
ASPECT_QUERIES: List[str] = [
    "이 제품의 전반적인 구매 가치와 종합 평가",
    "배터리 지속 시간과 충전",
    "가격과 가성비",
    "카메라 화질과 촬영 성능",
    "성능과 발열, 처리 속도",
    "디스플레이 화면 밝기와 주사율",
    "디자인과 휴대성, 무게",
    "리뷰어가 강조한 장점",
    "리뷰어가 지적한 단점과 아쉬운 점",
    "전작 대비 달라진 점과 스펙 변화",
    "소비자 댓글 여론과 실사용 불만",
    "리뷰어와 소비자의 평가가 갈리는 지점",
]

_SOURCE_KEYS = {
    "report_1": "transcript_report",
    "report_2": "comment_text",
    "report_3": "integrated_text",
}


def retrieve_bundles(
    bundles: List[Dict[str, Any]],
    *,
    product_key: str,
    db_path: str,
    top_k: int = 8,
    total_cap: int = 60000,
    embed_fn: Optional[Callable[[List[str]], Tuple[List[List[float]], Dict]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from scripts.rag import store
    from scripts.rag.chunker import chunk_bundle
    from scripts.rag.embedder import default_embed_fn, embed_with_cache

    ef = embed_fn or default_embed_fn

    # 1) 청킹 (구조 보존)
    all_chunks: List[Dict[str, Any]] = []
    for b in bundles:
        all_chunks.extend(chunk_bundle(b, product_key))
    if not all_chunks:
        # 청크가 전혀 없으면 RAG 의미 없음 → 빈 결과로 폴백 유도
        raise RuntimeError("no chunks produced from bundles")

    by_id: Dict[str, Dict[str, Any]] = {c["chunk_id"]: c for c in all_chunks}

    # 2) 임베딩 (캐시 — 이미 인덱싱된 것 재임베딩 skip)
    idx_perf = embed_with_cache(db_path, product_key, all_chunks, ef)

    # 3) ④ 측면 쿼리 임베딩 + 제품 범위 검색 → 청크별 최대 관련도
    q_vecs, q_perf = ef(ASPECT_QUERIES)
    best: Dict[str, float] = {}
    for qv in q_vecs:
        for sc, ch in store.search(db_path, product_key, qv, top_k):
            cid = ch["chunk_id"]
            if sc > best.get(cid, -2.0):
                best[cid] = sc

    # 4) 영상별 재구성 (입력 영상 순서·video_id·제목 보존).
    #    영상 번호(④ '영상 N')의 결정성을 위해 영상 순서는 입력 그대로 두고,
    #    각 (영상, source) 안에서만 관련도 내림차순 정렬(앞=고관련).
    grouped: Dict[Tuple[str, str], List[Tuple[float, Dict[str, Any]]]] = {}
    for c in all_chunks:
        key = (c["video_id"], c["source"])
        grouped.setdefault(key, []).append((best.get(c["chunk_id"], -1.0), c))

    retrieved_set = set(best.keys())
    kept: Dict[Tuple[str, str], List[Tuple[float, Dict[str, Any]]]] = {}
    for key, lst in grouped.items():
        lst.sort(key=lambda x: (x[0], -x[1]["chunk_idx"]), reverse=True)
        # §5-3 최소 보장: 검색에 안 걸려도 (영상,source)당 최소 1청크 유지
        sel = [(s, c) for s, c in lst if c["chunk_id"] in retrieved_set]
        if not sel and lst:
            sel = [lst[0]]  # 최고 관련도(또는 첫) 청크 1개 바닥 보장
        kept[key] = sel

    # 5) 총 길이 상한 — 관련도 하위 청크부터 제외(위치 편향 없음).
    def _total() -> int:
        return sum(len(c["text"]) for lst in kept.values() for _, c in lst)

    dropped = 0
    if _total() > total_cap:
        # (영상,source)당 마지막 1청크는 보존하며, 전역 최저 관련도부터 제거
        while _total() > total_cap:
            cand: Optional[Tuple[float, Tuple[str, str], int]] = None
            for key, lst in kept.items():
                if len(lst) <= 1:
                    continue
                s, _ = lst[-1]
                if cand is None or s < cand[0]:
                    cand = (s, key, len(lst) - 1)
            if cand is None:
                break
            kept[cand[1]].pop(cand[2])
            dropped += 1

    # 6) bundle 재조립 (assemble_input_blocks 가 읽는 형태 그대로)
    out: List[Dict[str, Any]] = []
    for b in bundles:
        vid = b.get("video_id", "")
        nb = dict(b)
        for source, field in _SOURCE_KEYS.items():
            lst = kept.get((vid, source), [])
            # 관련도순(앞=고관련) 청크 텍스트로 재구성. 비면 빈 값
            # (assemble_input_blocks 가 '(없음)' 처리 — 안전 퇴화).
            nb[field] = "\n".join(c["text"] for _, c in lst).strip() if lst else ""
        out.append(nb)

    total_after = sum(
        len(x.get("transcript_report") or "")
        + len(x.get("comment_text") or "")
        + len(x.get("integrated_text") or "")
        for x in out
    )
    measure = {
        "rag": True,
        "rag_fallback": False,
        "indexed_total": idx_perf["indexed_total"],
        "embedded_new": idx_perf["embedded_new"],
        "cached_skipped": idx_perf["cached_skipped"],
        "embed_calls": idx_perf["embed_calls"] + q_perf.get("embed_calls", 0),
        "embed_ms": round(idx_perf["embed_ms"] + q_perf.get("embed_ms", 0.0), 1),
        "queries": len(ASPECT_QUERIES),
        "retrieved_chunks": len(retrieved_set),
        "dropped_low_relevance": dropped,
        # truncate_bundles 호환 키 (기존 [INPUT] 로그·소비자 보존)
        "cut_chars": {"r1": 0, "r2": 0, "r3": 0},
        "proportional_shrink": dropped > 0,
        "total_chars_after": total_after,
        "total_cap": total_cap,
    }
    return out, measure
