from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import psycopg2
from psycopg2.extras import DictCursor

from services.analysis.analysis_pipeline_service import AnalysisPipelineService

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/techdb"


def _get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _connect():
    return psycopg2.connect(_get_database_url())


def _normalize_ids(values: Optional[Iterable[Any]]) -> List[str]:
    if not values:
        return []
    normalized: List[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


def _fetch_targets(
    conn,
    product_ids: Optional[Iterable[Any]] = None,
    video_ids: Optional[Iterable[Any]] = None,
) -> List[Dict[str, Any]]:
    normalized_product_ids = _normalize_ids(product_ids)
    normalized_video_ids = _normalize_ids(video_ids)

    with conn.cursor(cursor_factory=DictCursor) as cur:
        if normalized_video_ids:
            cur.execute(
                """
                SELECT v.video_id, v.product_id, p.name AS product_name, COALESCE(v.description, '') AS transcript_text
                FROM videos v
                JOIN tech_products p ON p.product_id = v.product_id
                WHERE v.video_id = ANY(%s)
                ORDER BY v.created_at DESC NULLS LAST
                """,
                (normalized_video_ids,),
            )
            return [dict(row) for row in cur.fetchall()]

        if normalized_product_ids:
            cur.execute(
                """
                SELECT v.video_id, v.product_id, p.name AS product_name, COALESCE(v.description, '') AS transcript_text
                FROM videos v
                JOIN tech_products p ON p.product_id = v.product_id
                WHERE v.product_id = ANY(%s::int[])
                ORDER BY v.created_at DESC NULLS LAST
                """,
                (normalized_product_ids,),
            )
            return [dict(row) for row in cur.fetchall()]

        return []


def _fetch_related_comments(conn, video_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            """
            SELECT c.comment_id, c.text_raw
            FROM comments c
            WHERE c.video_id = %s AND c.is_product_related = TRUE
            ORDER BY c.created_at DESC
            LIMIT %s
            """,
            (video_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _ensure_analysis_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS video_analysis_reports (
                id SERIAL PRIMARY KEY,
                video_id VARCHAR(64) NOT NULL,
                product_id INT,
                report_json JSONB NOT NULL,
                generated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (video_id)
            )
            """
        )


def _save_result(conn, video_id: str, product_id: Any, report: Dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO video_analysis_reports (video_id, product_id, report_json, generated_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (video_id)
            DO UPDATE SET
                product_id = EXCLUDED.product_id,
                report_json = EXCLUDED.report_json,
                generated_at = NOW()
            """,
            (video_id, product_id, json.dumps(report, ensure_ascii=False)),
        )


def run_analysis_pipeline(
    *,
    product_ids: Optional[Iterable[Any]] = None,
    video_ids: Optional[Iterable[Any]] = None,
    save_results: bool = False,
    return_results: bool = True,
) -> Dict[str, Any]:
    """
    Reusable pipeline runner for both Airflow and FastAPI paths.

    - Input: product_ids or video_ids
    - Output: dict (pydantic-friendly)
    - Optionally saves per-video report rows when save_results=True
    """
    pipeline = AnalysisPipelineService()

    analyzed = 0
    skipped = 0
    results: List[Dict[str, Any]] = []

    with _connect() as conn:
        if save_results:
            _ensure_analysis_table(conn)

        targets = _fetch_targets(conn, product_ids=product_ids, video_ids=video_ids)

        for target in targets:
            video_id = str(target["video_id"])
            product_id = target.get("product_id")
            product_name = target.get("product_name") or "제품"
            transcript_text = target.get("transcript_text") or ""

            comments = _fetch_related_comments(conn, video_id=video_id)
            if not comments:
                skipped += 1
                continue

            payload = pipeline.run(
                product_info={
                    "product_id": product_id,
                    "name": product_name,
                },
                comments=comments,
                transcript_text=transcript_text,
            )

            report = {
                "video_id": video_id,
                "product_id": product_id,
                "product_name": product_name,
                "analysis": payload,
            }

            if save_results:
                _save_result(conn, video_id=video_id, product_id=product_id, report=report)

            if return_results:
                results.append(report)

            analyzed += 1

        conn.commit()

    return {
        "input": {
            "product_ids": _normalize_ids(product_ids),
            "video_ids": _normalize_ids(video_ids),
        },
        "videos_analyzed": analyzed,
        "videos_skipped": skipped,
        "results": results,
        "saved": save_results,
        "generated_at_utc": datetime.utcnow().isoformat(),
    }


def run_analysis_pipeline_for_airflow(
    product_ids: Optional[Iterable[Any]] = None,
    video_ids: Optional[Iterable[Any]] = None,
    save_results: bool = True,
) -> Dict[str, Any]:
    """Airflow task callable wrapper."""
    return run_analysis_pipeline(
        product_ids=product_ids,
        video_ids=video_ids,
        save_results=save_results,
        return_results=True,
    )
