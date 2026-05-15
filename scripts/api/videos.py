"""
Video-related API routes (video detail, PDF downloads)
"""
import json
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from scripts.database.queries import query_one, query_all, execute_update
from scripts.youtube.transcript_service import fetch_video_transcript
from scripts.reports.integrated_report import generate_and_save_all_reports
from scripts.reports.pdf_generator import render_report_pdf
from scripts.utils.markdown_renderer import markdown_to_html

templates = Jinja2Templates(directory="templates")


# ─────────────────────────────────────────────────────────────────────────────
# v2 (보고서 ②③) JSON ↔ PDF/Plain-text 변환 헬퍼
# - DB 에 저장된 video_reports.comment_report / integrated_report 는 v2 부터 JSON.
# - PDF 다운로드 라우트가 ReportLab(render_report_pdf) 에 넘기려면 markdown-like
#   plain text 로 평탄화 필요. 본 함수가 그 변환을 담당.
# - v1 (마크다운) 캐시 row 가 남아 있을 수 있으므로 호출부에서 isinstance 분기.
# ─────────────────────────────────────────────────────────────────────────────

def _parse_report_json(raw: Any) -> Optional[dict]:
    """v2 JSON 문자열을 dict 로 안전 파싱. v1 마크다운/기타 입력은 None."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or not s.startswith("{"):
        return None
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _fmt_quote_line(c: dict) -> list:
    """대표 댓글 1건 → PDF용 markdown 라인 (인용 + 좋아요/저자 메타)."""
    text = (c.get("text_raw") or "").strip()
    likes = c.get("like_count", 0)
    author = c.get("author_name") or ""
    meta = f"좋아요 {likes}"
    if author:
        meta += f", {author}"
    meta += " (원문 그대로)"
    return [f"> {text}", f"  - {meta}"]


def _comment_report_to_text(data: dict, product_name: str = "제품") -> str:
    """보고서 ② dict → PDF 용 markdown 텍스트."""
    out: list = [f"# {product_name} 댓글 기반 소비자 여론 보고서", ""]

    # S1
    s = data.get("sentiment_summary") or {}
    meta = data.get("_meta") or {}
    total = meta.get("total_analyzed_comments", 0)
    out.append("## 1. 소비자 민심 한눈에")
    if s.get("one_line_mood"):
        out.append(f"전반: {s['one_line_mood']}")
    out.append(f"- 긍정: {s.get('positive_pct', 0)}%")
    out.append(f"- 중립: {s.get('neutral_pct', 0)}%")
    out.append(f"- 부정: {s.get('negative_pct', 0)}%")
    out.append(f"(분석 대상 댓글 {total}건, 가중 비율)")
    out.append("")

    # S2/S3
    for title, key in (
        ("## 2. 긍정 핵심 인사이트", "positive_points"),
        ("## 3. 부정 핵심 인사이트", "negative_points"),
    ):
        out.append(title)
        pts = data.get(key) or []
        if not pts:
            out.append("- 도출된 포인트가 없습니다.")
        else:
            for p in pts:
                aspect = p.get("aspect_name") or ""
                cnt = p.get("comment_count", 0)
                summary = p.get("summary_line") or ""
                out.append(f"### {aspect} (관련 댓글 {cnt}건)")
                if summary:
                    out.append(summary)
                for c in (p.get("representative_comments") or []):
                    out.extend(_fmt_quote_line(c))
                out.append("")
        out.append("")

    # S4
    out.append("## 4. 주요 언급 이슈")
    issues = data.get("top_issues") or []
    if not issues:
        out.append("- 언급 이슈 데이터가 없습니다.")
    else:
        for it in issues:
            out.append(f"- {it.get('keyword', '')}: {it.get('count', 0)}회")
    return "\n".join(out)


def _comparison_report_to_text(data: dict, product_name: str = "제품") -> str:
    """보고서 ③ dict → PDF 용 markdown 텍스트."""
    out: list = [f"# {product_name} 리뷰어 vs 소비자 비교 보고서", ""]

    # S1 / S2
    for title, key in (
        ("## 1. 의견 일치 포인트", "agreement_points"),
        ("## 2. 의견 불일치 포인트", "disagreement_points"),
    ):
        out.append(title)
        items = data.get(key) or []
        if not items:
            out.append("- 도출된 항목이 없습니다.")
        else:
            for p in items:
                topic = p.get("topic") or ""
                quote = (p.get("reviewer_quote") or "").strip()
                out.append(f"### {topic}")
                out.append(f'- 리뷰어 자막: "{quote}"')
                out.append("- 소비자 댓글:")
                for c in (p.get("consumer_comments") or []):
                    out.extend(_fmt_quote_line(c))
                out.append("")
        out.append("")

    # S3
    out.append("## 3. 리뷰어만 언급 / 소비자만 언급")
    out.append("[리뷰어만 언급]")
    rev_only = data.get("reviewer_only") or []
    if rev_only:
        for t in rev_only:
            out.append(f"- {t}")
    else:
        out.append("- 없음")
    out.append("")
    out.append("[소비자만 언급]")
    cons_only = data.get("consumer_only") or []
    if cons_only:
        for t in cons_only:
            out.append(f"- {t}")
    else:
        out.append("- 없음")
    out.append("")

    # S4
    out.append("## 4. 종합 판단")
    verdict = data.get("verdict") or {}
    meta = data.get("_meta") or {}
    out.append(f"리뷰 신뢰도: {verdict.get('trust_score', 0)}%")
    out.append("")
    summary = (verdict.get("summary") or "").strip()
    if summary:
        out.append(summary)
        out.append("")
    agree = meta.get("agreement_count", 0)
    dis = meta.get("disagreement_count", 0)
    out.append(f"(계산 근거: 일치 {agree}건 / 불일치 {dis}건)")
    return "\n".join(out)


def register_video_routes(app):
    """Register all video-related routes"""
    
    @app.get("/products/{product_id}/videos/{video_id}", response_class=HTMLResponse)
    async def video_detail(request: Request, product_id: int, video_id: str, page: int = 1, sentiment: str = None):
        """Show video detail page with sentiment analysis and pagination."""
        print(f"[VIDEO_DETAIL] page={page}, sentiment={sentiment}")
        
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        video = query_one(
            "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
            (video_id, product_id)
        )
        
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")
        
        # Pagination params
        page = max(1, page)
        per_page = 10
        offset = (page - 1) * per_page
        
        # Build WHERE clause for final analyzed comments
        # (LLM+Agent final_action=ANALYZE and sentiment already computed)
        where_clause = "c.video_id = %s AND ad.final_action = 'ANALYZE'"
        query_params = [video_id]
        
        if sentiment in ['positive', 'neutral', 'negative']:
            where_clause += " AND cs.sentiment_label = %s"
            query_params.append(sentiment)
            print(f"[FILTER] Applying sentiment filter: {sentiment}")
        else:
            print(f"[FILTER] No sentiment filter (sentiment={sentiment})")
        
        # Get final analyzed comments with sentiment (paginated, optionally filtered)
        comments = query_all(
            f"""SELECT c.comment_id, c.text_raw, cs.sentiment_label, cs.sentiment_score
                FROM comments c
               INNER JOIN agent_decisions ad ON c.comment_id = ad.comment_id
               INNER JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
               WHERE {where_clause}
                ORDER BY c.created_at DESC LIMIT %s OFFSET %s""",
            tuple(query_params + [per_page, offset])
        )
        
        # Count total final analyzed comments (filtered)
        analyzed_count_row = query_one(
            f"""SELECT COUNT(*) as count
                FROM comments c
                INNER JOIN agent_decisions ad ON c.comment_id = ad.comment_id
                INNER JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
                WHERE {where_clause}""",
            tuple(query_params)
        )
        total_comments = analyzed_count_row["count"] if analyzed_count_row else 0
        total_pages = (total_comments + per_page - 1) // per_page
        
        # Count sentiment distribution
        sentiment_counts = query_all(
            """SELECT cs.sentiment_label, COUNT(*) as count
               FROM comments c
               INNER JOIN agent_decisions ad ON c.comment_id = ad.comment_id
               INNER JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
               WHERE c.video_id = %s AND ad.final_action = 'ANALYZE'
               GROUP BY cs.sentiment_label""",
            (video_id,)
        )
        
        sentiment_map = {row["sentiment_label"]: row["count"] for row in sentiment_counts}

        transcript_row = query_one(
            "SELECT transcript_text, language_code, segment_count, updated_at FROM video_transcripts WHERE video_id = %s",
            (video_id,),
        )

        # Auto-recover missing transcript once at page load
        if not transcript_row:
            fetched_transcript = fetch_video_transcript(video_id)
            if fetched_transcript:
                execute_update(
                    """INSERT INTO video_transcripts (video_id, transcript_text, language_code, segment_count, source)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (video_id)
                       DO UPDATE SET
                         transcript_text = EXCLUDED.transcript_text,
                         language_code = EXCLUDED.language_code,
                         segment_count = EXCLUDED.segment_count,
                         source = EXCLUDED.source,
                         updated_at = NOW()""",
                    (
                        video_id,
                        fetched_transcript["transcript_text"],
                        fetched_transcript["language_code"],
                        fetched_transcript["segment_count"],
                        "youtube_transcript_api",
                    ),
                )
                transcript_row = query_one(
                    "SELECT transcript_text, language_code, segment_count, updated_at FROM video_transcripts WHERE video_id = %s",
                    (video_id,),
                )

        # Load cached reports if available
        print(f"[VIDEO_DETAIL] Loading video page: product_id={product_id}, video_id={video_id}")
        transcript_report, comment_sentiment_report, integrated_analysis = await generate_and_save_all_reports(
            video_id, product["name"], force_rewrite=False
        )
        
        # 보고서 ① (자막) → 마크다운 HTML 변환 (기존 .tr-* enhancer 가 DOM 위에서 동작)
        # 보고서 ②③ (댓글/비교) → dict 그대로 템플릿에 전달.
        #   템플릿이 {{ var|tojson }} 으로 <script type="application/json"> 에 직렬화하면
        #   JS enhancer (.cm-* / .cmp-*) 가 안전하게 JSON.parse 후 렌더한다.
        transcript_report_html = markdown_to_html(transcript_report) if isinstance(transcript_report, str) else None
        comment_report_json = comment_sentiment_report if isinstance(comment_sentiment_report, dict) else None
        integrated_report_json = integrated_analysis if isinstance(integrated_analysis, dict) else None

        # Get report metadata
        report_metadata = query_one(
            "SELECT updated_at FROM video_reports WHERE video_id = %s",
            (video_id,)
        )
        report_updated_at = report_metadata.get("updated_at") if report_metadata else None

        print(
            f"[VIDEO_DETAIL] Reports loaded: transcript={bool(transcript_report)}, "
            f"comment={bool(comment_report_json)}, integrated={bool(integrated_report_json)}, "
            f"updated_at={report_updated_at}"
        )

        return templates.TemplateResponse("video_detail.html", {
            "request": request,
            "product_id": product_id,
            "product": product,
            "video": video,
            "comments": comments,
            "product_related_count": total_comments,
            "analyzed_comment_count": total_comments,
            "current_page": page,
            "total_pages": total_pages,
            "per_page": per_page,
            "sentiment_positive": sentiment_map.get("positive", 0),
            "sentiment_neutral": sentiment_map.get("neutral", 0),
            "sentiment_negative": sentiment_map.get("negative", 0),
            "current_sentiment": sentiment,
            "transcript_row": transcript_row,
            "transcript_report": transcript_report_html,
            "comment_report_json": comment_report_json,
            "integrated_report_json": integrated_report_json,
            "report_updated_at": report_updated_at,
        })
    
    @app.get("/products/{product_id}/videos/{video_id}/transcript-report.pdf")
    async def download_transcript_report(product_id: int, video_id: str):
        """Download transcript report as PDF."""
        video = query_one(
            "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
            (video_id, product_id),
        )
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        report_row = query_one(
            "SELECT transcript_report FROM video_reports WHERE video_id = %s",
            (video_id,),
        )
        
        if not report_row or not report_row.get("transcript_report"):
            raise HTTPException(status_code=404, detail="Transcript report not available")
        
        report_text = report_row["transcript_report"]
        pdf_bytes = render_report_pdf(f"[자막 기반 분석] {video.get('title', 'Unknown')}", report_text)

        filename = f"transcript_report_{video_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    
    @app.get("/products/{product_id}/videos/{video_id}/comment-report.pdf")
    async def download_comment_report(product_id: int, video_id: str):
        """Download comment sentiment report as PDF."""
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        video = query_one(
            "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
            (video_id, product_id),
        )
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        report_row = query_one(
            "SELECT comment_report FROM video_reports WHERE video_id = %s",
            (video_id,),
        )

        if not report_row or not report_row.get("comment_report"):
            raise HTTPException(status_code=404, detail="Comment report not available")

        raw = report_row["comment_report"]
        data = _parse_report_json(raw)
        if isinstance(data, dict):
            report_text = _comment_report_to_text(data, product["name"])
        else:
            # v1 (legacy markdown) 호환: 원문 그대로 PDF 화
            report_text = raw if isinstance(raw, str) else ""
        pdf_bytes = render_report_pdf(f"[댓글 분석] {video.get('title', 'Unknown')}", report_text)

        filename = f"comment_report_{video_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    
    @app.get("/products/{product_id}/videos/{video_id}/integrated-analysis.pdf")
    async def download_integrated_analysis(product_id: int, video_id: str):
        """Download integrated analysis as PDF."""
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        video = query_one(
            "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
            (video_id, product_id),
        )
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        report_row = query_one(
            "SELECT integrated_report FROM video_reports WHERE video_id = %s",
            (video_id,),
        )

        if not report_row or not report_row.get("integrated_report"):
            raise HTTPException(status_code=404, detail="Integrated analysis not available")

        raw = report_row["integrated_report"]
        data = _parse_report_json(raw)
        if isinstance(data, dict):
            report_text = _comparison_report_to_text(data, product["name"])
        else:
            report_text = raw if isinstance(raw, str) else ""
        pdf_bytes = render_report_pdf(f"[통합 분석] {video.get('title', 'Unknown')}", report_text)

        filename = f"integrated_analysis_{video_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    
    @app.get("/api/ai-analysis-status")
    async def get_ai_analysis_status():
        """Get status of AI analysis tasks (Airflow integration placeholder)."""
        ai_tasks = {
            "comment_filter_batch": {
                "status": "active",
                "description": "Filter comments by product relevance",
            },
            "summarize_transcripts_batch": {
                "status": "active",
                "description": "Generate transcript summaries with AI",
            },
            "generate_product_report_batch": {
                "status": "active",
                "description": "Create comprehensive product analysis reports",
            },
        }
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "ai_tasks": ai_tasks,
            "total_tasks": len(ai_tasks),
            "all_active": all(t["status"] == "active" for t in ai_tasks.values()),
        }
