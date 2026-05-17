"""
Product-related API routes
"""
import asyncio
import os
from time import perf_counter

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from scripts.database.queries import query_one, query_all, execute_insert, execute_update
from scripts.reports.pdf_generator import render_report_pdf
from scripts.reports.product_integrated_insight import (
    collect_transcript_reports_for_product,
    ensure_comment_analysis_for_videos,
    build_product_integrated_insight_report,
    save_product_integrated_report,
    get_latest_product_integrated_report,
    get_product_integrated_report,
    get_last_collect_perf,
    get_last_llm_perf,
    get_last_comment_heal_perf,
)
from scripts.utils.markdown_renderer import markdown_to_html

templates = Jinja2Templates(directory="templates")


def register_product_routes(app):
    """Register all product-related routes"""
    
    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Redirect to products page."""
        return "<script>window.location.href='/products'</script>"
    
    @app.get("/products", response_class=HTMLResponse)
    async def list_products(request: Request):
        """List all products."""
        show_product_list = os.getenv("SHOW_PRODUCT_LIST", "0") == "1"
        products = query_all("SELECT * FROM tech_products ORDER BY created_at DESC") if show_product_list else []
        return templates.TemplateResponse("products.html", {
            "request": request,
            "products": products,
            "show_product_list": show_product_list,
        })
    
    @app.post("/products")
    async def create_product(data: dict):
        """Create a new product."""
        name = data.get("name", "").strip()
        brand = data.get("brand", "").strip() or None
        category = data.get("category", "").strip() or None
        
        if not name:
            raise HTTPException(status_code=400, detail="Product name is required")
        
        product_id = execute_insert(
            "INSERT INTO tech_products (name, brand, category) VALUES (%s, %s, %s) RETURNING product_id",
            (name, brand, category)
        )
        
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        return product
    
    @app.get("/products/{product_id}", response_class=HTMLResponse)
    async def product_detail(request: Request, product_id: int):
        """Show product detail page with videos."""
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        videos = query_all(
            "SELECT * FROM videos WHERE product_id = %s ORDER BY view_count DESC",
            (product_id,)
        )
        
        return templates.TemplateResponse("product_detail.html", {
            "request": request,
            "product": product,
            "videos": videos,
        })

    @app.delete("/products/{product_id}")
    async def delete_product(product_id: int):
        """Delete a product. CASCADE removes related videos, comments, transcripts, reports."""
        affected = execute_update(
            "DELETE FROM tech_products WHERE product_id = %s",
            (product_id,)
        )
        if affected == 0:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"deleted": True, "product_id": product_id}

    # ────────────────────────────────────────────────────────────────
    # 제품 단위 통합 인사이트 보고서 (영상별 자막 보고서 N건 → 1건 합성)
    # ────────────────────────────────────────────────────────────────

    @app.post("/products/{product_id}/integrated-insight")
    async def create_product_integrated_insight(product_id: int, data: dict):
        """선택된 영상들의 자막 기반 보고서를 합성하여 제품 단위 통합 인사이트 보고서를 생성한다."""
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        raw_ids = data.get("video_ids") or []
        if not isinstance(raw_ids, list):
            raise HTTPException(status_code=400, detail="video_ids must be a list")
        # 중복 제거 및 정규화 (입력 순서 유지)
        seen = set()
        video_ids = []
        for v in raw_ids:
            if not v:
                continue
            sv = str(v).strip()
            if sv and sv not in seen:
                seen.add(sv)
                video_ids.append(sv)

        if len(video_ids) < 2:
            raise HTTPException(status_code=400, detail="영상 2개 이상을 선택해 주세요")

        route_t0 = perf_counter()

        # ── 자막·댓글 self-healing 병렬 실행 ────────────────────────────
        # 자막: collect_transcript_reports_for_product (기존)
        # 댓글: ensure_comment_analysis_for_videos — agent_decisions 미존재 영상에
        #       기존 process_comments_with_agent (sync.py 의 7-step 댓글 agent) 호출.
        # 두 self-healing 은 서로 다른 YouTube API endpoint + 다른 LLM 호출 + 다른
        # DB 테이블을 사용하므로 독립. asyncio.gather 로 동시 실행해 latency 단축.
        collect_t0 = perf_counter()
        per_video_reports, comment_heal_stats = await asyncio.gather(
            collect_transcript_reports_for_product(product_id, video_ids),
            ensure_comment_analysis_for_videos(product["name"], video_ids),
        )
        collect_ms = (perf_counter() - collect_t0) * 1000

        if len(per_video_reports) < 2:
            raise HTTPException(
                status_code=400,
                detail="자막 기반 보고서를 생성할 수 있는 영상이 2개 이상 필요합니다 (자막 부재 영상 제외 후 부족)",
            )

        # 선정 영상 수 vs 실제 분석 영상 수 — 자막 부재로 일부가 제외됐을 수
        # 있다. 보고서·UI 모두 정직 표기하도록 분리해 추적.
        selected_video_count = len(video_ids)
        analyzed_video_ids = [r["video_id"] for r in per_video_reports]
        excluded_video_ids = [v for v in video_ids if v not in set(analyzed_video_ids)]

        # build_product_integrated_insight_report 가 내부에서 댓글 self-healing 으로
        # 적재된 DB 를 READ ONLY 로 집계해 ⑤ 소비자 여론 섹션을 채운다.
        build_t0 = perf_counter()
        report_text, model_used = build_product_integrated_insight_report(
            product_name=product["name"],
            per_video_reports=per_video_reports,
            video_ids=analyzed_video_ids,
            selected_video_count=selected_video_count,
        )
        build_ms = (perf_counter() - build_t0) * 1000

        save_t0 = perf_counter()
        report_id = save_product_integrated_report(
            product_id=product_id,
            video_ids=[r["video_id"] for r in per_video_reports],
            report_text=report_text,
            model_used=model_used,
        )
        save_ms = (perf_counter() - save_t0) * 1000

        total_ms = (perf_counter() - route_t0) * 1000
        collect_detail = get_last_collect_perf()
        llm_detail = get_last_llm_perf()
        comment_heal_detail = get_last_comment_heal_perf()
        print(
            f"[PERF][insight_route] product_id={product_id} total_ms={total_ms:.1f} "
            f"collect_ms={collect_ms:.1f} build_ms={build_ms:.1f} llm_ms={llm_detail.get('llm_ms')} "
            f"save_ms={save_ms:.1f} self_heal={collect_detail.get('self_heal_count')}/{collect_detail.get('self_heal_count', 0) + collect_detail.get('cache_hits', 0)} "
            f"comment_heal={comment_heal_detail.get('healed', 0)}/{comment_heal_detail.get('total_videos', 0)} "
            f"comment_already={comment_heal_detail.get('already_analyzed', 0)} "
            f"comment_failed={comment_heal_detail.get('failed', 0)} "
            f"fallback={llm_detail.get('fallback')}"
        )

        return {
            "report_id": report_id,
            "product_id": product_id,
            "report_text": report_text,
            "report_html": markdown_to_html(report_text),
            "source_video_count": len(per_video_reports),       # 실제 분석된 영상 수 (분모 기준)
            "selected_video_count": selected_video_count,        # 사용자가 선정한 총 수
            "analyzed_video_count": len(per_video_reports),      # source_video_count 와 동일, 명확성 위해 중복
            "excluded_video_count": len(excluded_video_ids),     # 자막 부재로 제외된 수
            "excluded_video_ids": excluded_video_ids,            # 제외된 video_id 리스트 (디버그/UI 보조)
            "video_ids": analyzed_video_ids,
            "model_used": model_used,
            "perf_breakdown": {
                "total_ms": round(total_ms, 1),
                "collect_ms": round(collect_ms, 1),
                "build_ms": round(build_ms, 1),
                "llm_ms": llm_detail.get("llm_ms"),
                "save_ms": round(save_ms, 1),
                "llm_fallback": llm_detail.get("fallback"),
                "collect_detail": collect_detail,
                "comment_heal_detail": comment_heal_detail,
            },
        }

    @app.get("/products/{product_id}/integrated-insight/latest")
    async def get_latest_integrated_insight(product_id: int):
        """제품의 최신 통합 인사이트 보고서를 조회한다."""
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        latest = get_latest_product_integrated_report(product_id)
        if not latest:
            raise HTTPException(status_code=404, detail="통합 인사이트 보고서가 아직 없습니다")

        return {
            "report_id": latest["id"],
            "product_id": product_id,
            "report_text": latest["report_text"],
            "report_html": markdown_to_html(latest["report_text"]),
            "source_video_count": latest["source_video_count"],
            "video_ids": latest["video_ids"],
            "model_used": latest.get("model_used"),
            "created_at": latest.get("created_at").isoformat() if latest.get("created_at") else None,
        }

    @app.get("/products/{product_id}/integrated-insight/{report_id}.pdf")
    async def download_integrated_insight_pdf(product_id: int, report_id: int):
        """통합 인사이트 보고서를 PDF로 다운로드한다."""
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        report = get_product_integrated_report(product_id, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        title = f"[{product['name']}] 종합 인사이트 보고서"
        pdf_bytes = render_report_pdf(title, report["report_text"])
        filename = f"product_{product_id}_integrated_insight_{report_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
