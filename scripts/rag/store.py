"""RAG 전용 SQLite 벡터 저장소 (Phase 2-b 폴백안).

기존 14테이블·PostgreSQL·schema.py·init_db() 와 완전 분리된 신규 자원.
stdlib sqlite3 + 순수 파이썬 코사인 — faiss 등 무거운 의존성 0, 오프라인 안전.
초기화는 ensure_schema() 한 곳에서만(기존 init_db 와 무관).

pgvector 미선택 사유: 운영 DB(native Homebrew postgresql@16)에 vector
확장이 시스템 레벨로 설치돼 있지 않아 `CREATE EXTENSION vector` 가
FeatureNotSupported 로 실패(실측). §4 폴백안으로 SQLite 채택.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple


def _connect(db_path: str):
    import sqlite3  # stdlib — 지연 import (일관성)

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(db_path: str) -> None:
    """벡터 테이블 생성 (idempotent). 기존 init_db 와 분리된 초기화 경로."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_report_chunks (
                chunk_id      TEXT PRIMARY KEY,
                product_key   TEXT NOT NULL,
                video_id      TEXT NOT NULL,
                source        TEXT NOT NULL,      -- report_1 / report_2 / report_3
                semantic_tag  TEXT,
                chunk_idx     INTEGER,
                text          TEXT NOT NULL,
                content_hash  TEXT NOT NULL,
                embedding     TEXT NOT NULL,      -- json list[float]
                dim           INTEGER NOT NULL,
                updated_at    TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_rag_product "
            "ON rag_report_chunks(product_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_rag_hash "
            "ON rag_report_chunks(content_hash)"
        )
        conn.commit()
    finally:
        conn.close()


def existing_hashes(db_path: str, product_key: str) -> set:
    """이미 인덱싱된 content_hash 집합 (재임베딩 캐시용)."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT content_hash FROM rag_report_chunks WHERE product_key=?",
            (product_key,),
        ).fetchall()
        return {r["content_hash"] for r in rows}
    finally:
        conn.close()


def upsert_chunks(db_path: str, records: List[Dict[str, Any]]) -> int:
    """임베딩이 채워진 청크 레코드 UPSERT. 반환: 기록한 행 수."""
    if not records:
        return 0
    from datetime import datetime

    conn = _connect(db_path)
    try:
        now = datetime.utcnow().isoformat()
        n = 0
        for r in records:
            emb = r.get("embedding") or []
            conn.execute(
                """
                INSERT INTO rag_report_chunks
                  (chunk_id, product_key, video_id, source, semantic_tag,
                   chunk_idx, text, content_hash, embedding, dim, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                  text=excluded.text, semantic_tag=excluded.semantic_tag,
                  embedding=excluded.embedding, dim=excluded.dim,
                  content_hash=excluded.content_hash,
                  updated_at=excluded.updated_at
                """,
                (
                    r["chunk_id"], r["product_key"], r["video_id"], r["source"],
                    r.get("semantic_tag", ""), int(r.get("chunk_idx", 0)),
                    r["text"], r["content_hash"],
                    json.dumps(emb, ensure_ascii=False), len(emb), now,
                ),
            )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = s = t = 0.0
    for x, y in zip(a, b):
        dot += x * y
        s += x * x
        t += y * y
    if s <= 0 or t <= 0:
        return -1.0
    return dot / (math.sqrt(s) * math.sqrt(t))


def search(
    db_path: str,
    product_key: str,
    query_vec: List[float],
    top_k: int,
) -> List[Tuple[float, Dict[str, Any]]]:
    """제품 범위 내에서만 코사인 유사도 상위 top_k 청크 반환.

    다른 제품 청크가 섞이지 않도록 product_key 로 가둠(§5-2.3).
    반환: [(score, chunk_dict), ...] score 내림차순.
    """
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT chunk_id, video_id, source, semantic_tag, chunk_idx, "
            "text, embedding FROM rag_report_chunks WHERE product_key=?",
            (product_key,),
        ).fetchall()
    finally:
        conn.close()
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for r in rows:
        try:
            emb = json.loads(r["embedding"])
        except (ValueError, TypeError):
            continue
        sc = _cosine(query_vec, emb)
        scored.append((sc, {
            "chunk_id": r["chunk_id"], "video_id": r["video_id"],
            "source": r["source"], "semantic_tag": r["semantic_tag"],
            "chunk_idx": r["chunk_idx"], "text": r["text"],
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[: max(1, top_k)]
