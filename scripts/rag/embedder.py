"""임베딩 — 기존 OpenAI 호환 경로(get_report_llm_client) 재활용, 배치 호출.

무거운 새 의존성 0(openai 는 이미 requirements). openai import 는 함수
내부 지연 — 순수 단계(chunker/store)·오프라인 테스트에서 끌려오지 않게.
"""
from __future__ import annotations

from time import perf_counter
from typing import Callable, Dict, List, Optional, Tuple

_EMBED_BATCH = 64


def default_embed_fn(texts: List[str]) -> Tuple[List[List[float]], Dict]:
    """기존 RunYourAI/OpenAI 호환 클라이언트로 배치 임베딩.

    반환: (벡터리스트, perf dict). 실패 시 예외 — 호출부(retriever)가
    안전 퇴화(절삭 폴백)로 처리한다.
    """
    from scripts.config import REPORT4_RAG_EMBED_MODEL
    from scripts.reports.transcript_report import get_report_llm_client

    client = get_report_llm_client()
    vecs: List[List[float]] = []
    calls = 0
    t0 = perf_counter()
    for i in range(0, len(texts), _EMBED_BATCH):
        batch = texts[i: i + _EMBED_BATCH]
        resp = client.embeddings.create(
            model=REPORT4_RAG_EMBED_MODEL, input=batch
        )
        calls += 1
        # OpenAI SDK: resp.data 는 input 순서 보장
        for d in resp.data:
            vecs.append(list(d.embedding))
    ms = (perf_counter() - t0) * 1000
    return vecs, {"embed_calls": calls, "embed_ms": round(ms, 1),
                  "embedded": len(vecs)}


def embed_with_cache(
    db_path: str,
    product_key: str,
    chunk_records: List[Dict],
    embed_fn: Callable[[List[str]], Tuple[List[List[float]], Dict]],
) -> Dict:
    """이미 인덱싱된 content_hash 는 재임베딩 건너뛰고, 새 청크만 임베딩·적재.

    반환 perf: {indexed_total, embedded_new, cached_skipped, embed_calls,
                embed_ms}
    """
    from scripts.rag import store

    store.ensure_schema(db_path)
    have = store.existing_hashes(db_path, product_key)
    new_recs = [r for r in chunk_records if r["content_hash"] not in have]
    cached = len(chunk_records) - len(new_recs)

    perf = {"indexed_total": len(chunk_records), "embedded_new": 0,
            "cached_skipped": cached, "embed_calls": 0, "embed_ms": 0.0}
    if new_recs:
        vecs, ep = embed_fn([r["text"] for r in new_recs])
        if len(vecs) != len(new_recs):
            raise RuntimeError(
                f"embedding count mismatch: {len(vecs)} != {len(new_recs)}"
            )
        for r, v in zip(new_recs, vecs):
            r["embedding"] = v
        store.upsert_chunks(db_path, new_recs)
        perf["embedded_new"] = len(new_recs)
        perf["embed_calls"] = ep.get("embed_calls", 0)
        perf["embed_ms"] = ep.get("embed_ms", 0.0)
    return perf
