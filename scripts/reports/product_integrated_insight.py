"""
제품 단위 통합 인사이트 보고서 (RunYourAI / openai/gpt-4.1-2025-04-14)

입력:
  - 동일 제품에 대한 N개 영상의 자막 기반 보고서(video_reports.transcript_report).
  - comment_filtering_agent 가 DB 에 저장한 댓글/감성/aspect 결과를 READ ONLY 로
    제품 단위로 집계한 소비자 여론 입력 (scripts.reports._pir_comment_aggregator).
출력: 위 두 입력만을 근거로 합성한 7섹션 통합 인사이트 보고서.
환각 방지: 입력에 등장하지 않은 사실은 절대 만들어 내지 않는다.

Self-healing:
  - 자막 self-healing: collect_transcript_reports_for_product 가 누락된 영상의
    transcript / transcript_report 를 fetch+build 후 DB UPSERT.
  - 댓글 self-healing: ensure_comment_analysis_for_videos 가 agent_decisions
    레코드가 아직 없는 영상에 대해 기존 process_comments_with_agent (sync.py 의
    7-step 댓글 agent 파이프라인) 를 그대로 호출한다. 댓글 파이프라인은 한 줄도
    수정하지 않는다 — 단순히 entry point 만 사용.
"""
import asyncio
import json
from datetime import date
from time import perf_counter
from typing import List, Dict, Optional, Tuple

from scripts.config import RUNYOURAI_API_KEY
from scripts.database.queries import query_one, query_all, execute_insert, execute_update
from scripts.reports.transcript_report import (
    build_transcript_report,
    fix_encoding,
    get_report_llm_client,
    REPORT_LLM_DEPLOYMENT,
)
from scripts.reports.integrated_report import upsert_video_report
from scripts.reports._pir_comment_aggregator import aggregate_pir_consumer_inputs
from scripts.utils.prompt_manager import build_product_integrated_insight_prompt
from scripts.youtube.transcript_service import fetch_video_transcript


# 영상별 보고서 1건당 입력 시 잘라낼 최대 길이 (토큰 한도 보호)
PER_VIDEO_REPORT_MAX_CHARS = 1500
# 통합 입력 전체에 대한 안전 상한 — 댓글 집계 입력(약 2~3K) 추가분 반영해 상향
TOTAL_INPUT_MAX_CHARS = 21000

HEURISTIC_MODEL_LABEL = "heuristic"

# Pass 2 동시성 상한 — feedback_llm_perf_lessons 측정 기준
COLLECT_MAX_CONCURRENCY = 5
# 댓글 self-healing 동시성 상한 — sync.py 의 PARALLEL_WORKERS=3 과 동일 (Groq 무료
# TPM 제한 대응). 상향하려면 sync.py 와 함께 조정.
COMMENT_HEAL_MAX_CONCURRENCY = 3

# 라우트가 즉시 읽을 수 있도록 마지막 호출의 perf breakdown 저장
_LAST_COLLECT_PERF: Dict = {}
_LAST_LLM_PERF: Dict = {}
_LAST_COMMENT_HEAL_PERF: Dict = {}


# ── 1) 입력 수집 ─────────────────────────────────────────────────

def _save_transcript_row(video_id: str, fetched: Dict) -> None:
    """fetch_video_transcript 결과를 video_transcripts에 UPSERT (메인 스레드 전용)."""
    execute_update(
        """INSERT INTO video_transcripts (video_id, transcript_text, language_code, segment_count, source)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (video_id)
           DO UPDATE SET
             transcript_text = EXCLUDED.transcript_text,
             language_code   = EXCLUDED.language_code,
             segment_count   = EXCLUDED.segment_count,
             source          = EXCLUDED.source,
             updated_at      = NOW()""",
        (
            video_id,
            fetched["transcript_text"],
            fetched.get("language_code"),
            fetched.get("segment_count"),
            "youtube_transcript_api",
        ),
    )


def _worker_fetch_and_build(vid: str, transcript_text: Optional[str]) -> Dict:
    """병렬 워커: DB 접근 금지. fetch_video_transcript + build_transcript_report만 수행.
    반환: {"video_id", "transcript_text", "fetched_payload", "transcript_report", "fetch_ms", "build_ms", "error"}
    """
    result: Dict = {
        "video_id": vid,
        "transcript_text": transcript_text,
        "fetched_payload": None,  # video_transcripts UPSERT용 raw payload (Pass 3에서 사용)
        "transcript_report": None,
        "fetch_ms": 0.0,
        "build_ms": 0.0,
        "error": None,
    }

    # 자막 없으면 받기
    if not transcript_text:
        t0 = perf_counter()
        try:
            fetched = fetch_video_transcript(vid)
        except Exception as e:
            result["error"] = f"fetch_failed: {type(e).__name__}: {e}"
            result["fetch_ms"] = (perf_counter() - t0) * 1000
            return result
        result["fetch_ms"] = (perf_counter() - t0) * 1000
        if not fetched or not fetched.get("transcript_text"):
            result["error"] = "fetch_empty"
            return result
        result["fetched_payload"] = fetched
        result["transcript_text"] = fetched["transcript_text"]

    # 자막 → 보고서 생성
    t0 = perf_counter()
    try:
        generated = build_transcript_report(result["transcript_text"])
    except Exception as e:
        result["error"] = f"build_failed: {type(e).__name__}: {e}"
        result["build_ms"] = (perf_counter() - t0) * 1000
        return result
    result["build_ms"] = (perf_counter() - t0) * 1000
    if not generated or generated.startswith("[ERROR]"):
        result["error"] = "build_empty_or_error"
        return result
    result["transcript_report"] = generated
    return result


async def collect_transcript_reports_for_product(
    product_id: int,
    video_ids: List[str],
) -> List[Dict]:
    """
    선택된 영상들에 대해 video_reports.transcript_report를 조회하고, 누락분은 병렬로 보완한다.

    Self-healing 3-pass 구조:
      Pass 1: 직렬 DB 일괄 조회 — 캐시 hit/miss 분류
      Pass 2: 병렬 워커 (asyncio.gather + to_thread, Semaphore=COLLECT_MAX_CONCURRENCY)
              fetch_video_transcript + build_transcript_report만. DB 접근 금지.
      Pass 3: 직렬 DB 쓰기 — video_transcripts UPSERT + upsert_video_report

    반환: [{"video_id": ..., "title": ..., "transcript_report": ...}, ...] (입력 순서 보존)
    """
    global _LAST_COLLECT_PERF
    route_t0 = perf_counter()

    if not video_ids:
        _LAST_COLLECT_PERF = {
            "total_ms": 0.0, "cache_hits": 0, "self_heal_count": 0,
            "fetch_ms_sum": 0.0, "build_report_ms_sum": 0.0, "per_video": [],
        }
        return []

    # ── Pass 1: 직렬 DB 일괄 조회 ───────────────────────────
    # video_ids는 사용자가 보낸 임의 문자열이라 placeholder 동적 생성 (psycopg2가 escape 처리)
    placeholders = ",".join(["%s"] * len(video_ids))
    videos_params = tuple(video_ids) + (product_id,)
    video_rows = query_all(
        f"SELECT video_id, title FROM videos WHERE video_id IN ({placeholders}) AND product_id = %s",
        videos_params,
    )
    video_meta = {r["video_id"]: r for r in video_rows}

    report_rows = query_all(
        f"SELECT video_id, transcript_report FROM video_reports WHERE video_id IN ({placeholders})",
        tuple(video_ids),
    )
    cached_reports = {r["video_id"]: r.get("transcript_report") for r in report_rows if r.get("transcript_report")}

    # cached_reports에 없는 영상만 자막 캐시 조회
    need_after_report = [v for v in video_ids if v in video_meta and v not in cached_reports]
    cached_transcripts: Dict[str, str] = {}
    if need_after_report:
        placeholders2 = ",".join(["%s"] * len(need_after_report))
        transcript_rows = query_all(
            f"SELECT video_id, transcript_text FROM video_transcripts WHERE video_id IN ({placeholders2})",
            tuple(need_after_report),
        )
        cached_transcripts = {r["video_id"]: r.get("transcript_text") for r in transcript_rows if r.get("transcript_text")}

    # 영상별 상태 분류
    ready: Dict[str, str] = {}  # vid -> transcript_report
    pending: List[Tuple[str, Optional[str]]] = []  # (vid, transcript_text or None)
    not_found: List[str] = []
    for vid in video_ids:
        if vid not in video_meta:
            not_found.append(vid)
            continue
        if vid in cached_reports:
            ready[vid] = cached_reports[vid]
        else:
            pending.append((vid, cached_transcripts.get(vid)))

    for vid in not_found:
        print(f"[WARN] product_integrated_insight: video {vid} not found for product {product_id}")

    # ── Pass 2: 병렬 워커 ──────────────────────────────────
    worker_results: List[Dict] = []
    if pending:
        semaphore = asyncio.Semaphore(COLLECT_MAX_CONCURRENCY)

        async def _bounded(vid: str, ttext: Optional[str]) -> Dict:
            async with semaphore:
                return await asyncio.to_thread(_worker_fetch_and_build, vid, ttext)

        gathered = await asyncio.gather(
            *[_bounded(vid, ttext) for vid, ttext in pending],
            return_exceptions=True,
        )
        for vid_ttext, res in zip(pending, gathered):
            if isinstance(res, BaseException):
                print(f"[WARN] product_integrated_insight: worker exception for {vid_ttext[0]}: {type(res).__name__}: {res}")
                continue
            worker_results.append(res)

    # ── Pass 3: 직렬 DB 쓰기 ───────────────────────────────
    fetch_ms_sum = 0.0
    build_ms_sum = 0.0
    self_heal_success = 0
    per_video_perf: List[Dict] = []
    for res in worker_results:
        fetch_ms_sum += res["fetch_ms"]
        build_ms_sum += res["build_ms"]
        per_video_perf.append({
            "video_id": res["video_id"],
            "fetch_ms": round(res["fetch_ms"], 1),
            "build_ms": round(res["build_ms"], 1),
            "error": res["error"],
        })
        if res["error"]:
            print(f"[WARN] product_integrated_insight: skip {res['video_id']} — {res['error']}")
            continue
        if res["fetched_payload"]:
            _save_transcript_row(res["video_id"], res["fetched_payload"])
        upsert_video_report(res["video_id"], transcript_report=res["transcript_report"])
        ready[res["video_id"]] = res["transcript_report"]
        self_heal_success += 1

    # ── 결과 조립 (입력 순서 보존) ─────────────────────────
    results: List[Dict] = []
    for vid in video_ids:
        if vid not in ready:
            continue
        meta = video_meta.get(vid, {})
        results.append({
            "video_id": vid,
            "title": meta.get("title") or "",
            "transcript_report": ready[vid],
        })

    total_ms = (perf_counter() - route_t0) * 1000
    _LAST_COLLECT_PERF = {
        "total_ms": round(total_ms, 1),
        "cache_hits": len(cached_reports),
        "self_heal_count": self_heal_success,
        "fetch_ms_sum": round(fetch_ms_sum, 1),
        "build_report_ms_sum": round(build_ms_sum, 1),
        "per_video": per_video_perf,
    }
    print(
        f"[PERF][collect] product_id={product_id} total_ms={total_ms:.1f} "
        f"cache_hits={len(cached_reports)} self_heal={self_heal_success}/{len(pending)} "
        f"fetch_sum_ms={fetch_ms_sum:.1f} build_sum_ms={build_ms_sum:.1f}"
    )
    return results


def get_last_collect_perf() -> Dict:
    """라우트가 응답 JSON 조립용으로 마지막 collect perf breakdown을 읽는다."""
    return dict(_LAST_COLLECT_PERF)


def get_last_llm_perf() -> Dict:
    """라우트가 응답 JSON 조립용으로 마지막 build LLM perf breakdown을 읽는다."""
    return dict(_LAST_LLM_PERF)


def get_last_comment_heal_perf() -> Dict:
    """라우트가 응답 JSON 조립용으로 마지막 댓글 self-healing perf 를 읽는다."""
    return dict(_LAST_COMMENT_HEAL_PERF)


# ── 1.5) 댓글 self-healing ───────────────────────────────────────
#
# 통합 인사이트 버튼이 눌렸을 때, 선정된 영상 중 댓글 분석이 아직 안 된 영상을
# 감지해 기존 댓글 agent (sync.py 의 process_comments_with_agent — 7-step
# 파이프라인) 를 그대로 호출한다. 댓글 파이프라인 자체는 수정하지 않는다.
#
# 판정 기준: agent_decisions 테이블에 해당 video_id 의 행이 1건이라도 있으면
# "이미 처리됨" 으로 간주. _pir_comment_aggregator 의 ANALYZE 필터와 동일 모집단.

def _videos_with_existing_comment_analysis(video_ids: List[str]) -> set:
    """agent_decisions 에 행이 존재하는 video_id 집합 (READ ONLY)."""
    if not video_ids:
        return set()
    placeholders = ",".join(["%s"] * len(video_ids))
    rows = query_all(
        f"""
        SELECT DISTINCT c.video_id
        FROM comments c
        INNER JOIN agent_decisions ad ON c.comment_id = ad.comment_id
        WHERE c.video_id IN ({placeholders})
        """,
        tuple(video_ids),
    )
    return {r["video_id"] for r in rows}


async def ensure_comment_analysis_for_videos(
    product_name: str,
    video_ids: List[str],
) -> Dict:
    """
    선정된 영상들 중 댓글 분석이 아직 안 된 영상에 대해 댓글 self-healing 수행.

    흐름:
      Pass 1 (직렬, READ ONLY): agent_decisions 행 유무로 처리/미처리 분류.
      Pass 2 (병렬): 미처리 video_id 에 대해 process_comments_with_agent 를
                     asyncio.to_thread + Semaphore 로 호출. 각 워커는 sync.py 의
                     기존 댓글 agent 함수를 그대로 실행 — DB 쓰기는 그 함수가
                     내부에서 수행한다.

    반환: {
        "total_videos": int,
        "already_analyzed": int,   # 이미 댓글 분석돼 있던 영상 수
        "healed": int,             # self-healing 으로 새로 분석한 영상 수
        "failed": int,             # self-healing 시도 후 실패한 영상 수
        "total_ms": float,
        "per_video": [{"video_id": str, "status": str, "duration_ms": float, "error": str|None}, ...],
    }
    AGENT_AVAILABLE=False 환경(import 실패)에서는 self-healing 을 skip 하고
    already_analyzed=기존, healed=0, failed=미처리 영상 수 로 표기한다.
    """
    global _LAST_COMMENT_HEAL_PERF
    route_t0 = perf_counter()

    base_stats = {
        "total_videos": len(video_ids),
        "already_analyzed": 0,
        "healed": 0,
        "failed": 0,
        "total_ms": 0.0,
        "per_video": [],
        "agent_available": True,
    }
    if not video_ids:
        _LAST_COMMENT_HEAL_PERF = base_stats
        return base_stats

    # Pass 1: 이미 분석된 영상 분류
    analyzed_set = _videos_with_existing_comment_analysis(video_ids)
    pending = [v for v in video_ids if v not in analyzed_set]
    base_stats["already_analyzed"] = len(analyzed_set)

    if not pending:
        base_stats["total_ms"] = round((perf_counter() - route_t0) * 1000, 1)
        _LAST_COMMENT_HEAL_PERF = base_stats
        print(
            f"[PERF][comment_heal] product={product_name} videos={len(video_ids)} "
            f"already_analyzed={len(analyzed_set)} healed=0 total_ms={base_stats['total_ms']:.1f}"
        )
        return base_stats

    # Pass 2: 미처리 영상에 댓글 agent 호출 (병렬)
    # sync.py 에서 import — 모듈 import 실패 시 (AGENT_AVAILABLE=False) self-healing 자체 skip.
    # sync.py 모듈 자체의 import 가 깨졌으면 (드문 케이스) traceback 까지 출력.
    try:
        from scripts.api.sync import process_comments_with_agent, AGENT_AVAILABLE
        # AGENT_IMPORT_ERROR 는 sync.py 의 새 진단 변수. 옛 버전과 호환 위해 getattr.
        from scripts.api import sync as _sync_module
        agent_import_error = getattr(_sync_module, 'AGENT_IMPORT_ERROR', None)
    except Exception as e:
        import traceback as _tb
        msg = f"{type(e).__name__}: {e}"
        print(f"[WARN] comment self-healing unavailable: sync.py import failed — {msg}")
        print(_tb.format_exc())
        for vid in pending:
            base_stats["per_video"].append({
                "video_id": vid, "status": "skipped_no_agent",
                "duration_ms": 0.0, "error": "sync_import_failed",
            })
        base_stats["agent_available"] = False
        base_stats["agent_import_error"] = msg
        base_stats["failed"] = len(pending)
        base_stats["total_ms"] = round((perf_counter() - route_t0) * 1000, 1)
        _LAST_COMMENT_HEAL_PERF = base_stats
        return base_stats

    if not AGENT_AVAILABLE:
        # sync.py 가 startup 시 AGENT_IMPORT_ERROR 에 원인을 저장해 둠. 사용자
        # 환경 진단 자체가 핵심이므로 자세히 노출.
        print("[WARN] comment self-healing skipped — AGENT_AVAILABLE=False in sync.py.")
        if agent_import_error:
            print(f"[WARN]   AGENT_IMPORT_ERROR (sync.py startup): {agent_import_error}")
            print(f"[WARN]   서버 startup 로그의 첫 [WARN] 블록에 traceback 이 출력돼 있습니다.")
        else:
            print(f"[WARN]   원인 변수 미노출 (sync.py 옛 버전). 서버 startup 로그 확인 권장.")
        for vid in pending:
            base_stats["per_video"].append({
                "video_id": vid, "status": "skipped_no_agent",
                "duration_ms": 0.0, "error": "agent_unavailable",
            })
        base_stats["agent_available"] = False
        base_stats["agent_import_error"] = agent_import_error
        base_stats["failed"] = len(pending)
        base_stats["total_ms"] = round((perf_counter() - route_t0) * 1000, 1)
        _LAST_COMMENT_HEAL_PERF = base_stats
        return base_stats

    semaphore = asyncio.Semaphore(COMMENT_HEAL_MAX_CONCURRENCY)

    async def _heal_one(vid: str) -> Dict:
        async with semaphore:
            t0 = perf_counter()
            try:
                # process_comments_with_agent 는 sync 함수. to_thread 로 분리.
                stats = await asyncio.to_thread(process_comments_with_agent, vid, product_name)
                ms = (perf_counter() - t0) * 1000
                analyzed = (stats or {}).get("analyzed", 0)
                return {
                    "video_id": vid,
                    "status": "healed" if analyzed > 0 else "healed_zero_analyzed",
                    "duration_ms": round(ms, 1),
                    "analyzed_count": int(analyzed),
                    "error": None,
                }
            except Exception as e:
                ms = (perf_counter() - t0) * 1000
                msg = f"{type(e).__name__}: {e}"
                print(f"[WARN] comment self-healing failed for {vid}: {msg}")
                return {
                    "video_id": vid,
                    "status": "failed",
                    "duration_ms": round(ms, 1),
                    "error": msg,
                }

    gathered = await asyncio.gather(*[_heal_one(v) for v in pending], return_exceptions=False)

    healed = sum(1 for r in gathered if r["status"].startswith("healed"))
    failed = sum(1 for r in gathered if r["status"] == "failed")

    base_stats["healed"] = healed
    base_stats["failed"] = failed
    base_stats["per_video"] = gathered
    base_stats["total_ms"] = round((perf_counter() - route_t0) * 1000, 1)
    _LAST_COMMENT_HEAL_PERF = base_stats

    print(
        f"[PERF][comment_heal] product={product_name} videos={len(video_ids)} "
        f"already_analyzed={len(analyzed_set)} healed={healed} failed={failed} "
        f"total_ms={base_stats['total_ms']:.1f}"
    )
    return base_stats


# ── 2) 통합 보고서 생성 ──────────────────────────────────────────

def _truncate_per_video(per_video_reports: List[Dict]) -> List[Dict]:
    """각 영상 보고서를 안전 길이로 자르고, 전체 입력이 너무 길면 추가 축소."""
    truncated: List[Dict] = []
    for r in per_video_reports:
        body = (r.get("transcript_report") or "").strip()
        if len(body) > PER_VIDEO_REPORT_MAX_CHARS:
            body = body[:PER_VIDEO_REPORT_MAX_CHARS].rstrip() + "\n... (이하 생략)"
        truncated.append({
            "video_id": r.get("video_id", ""),
            "title": r.get("title", ""),
            "transcript_report": body,
        })

    total = sum(len(t["transcript_report"]) for t in truncated)
    if total <= TOTAL_INPUT_MAX_CHARS or not truncated:
        return truncated

    # 전체 길이가 한도를 넘으면 영상별 한도를 비례 축소
    per_video_cap = max(400, TOTAL_INPUT_MAX_CHARS // max(1, len(truncated)))
    shrunk: List[Dict] = []
    for t in truncated:
        body = t["transcript_report"]
        if len(body) > per_video_cap:
            body = body[:per_video_cap].rstrip() + "\n... (이하 생략)"
        shrunk.append({**t, "transcript_report": body})
    return shrunk


def _fallback_render_consumer_section(consumer_aggregate: Optional[Dict]) -> List[str]:
    """LLM 미사용 모드용 ⑤ 소비자 여론 섹션 본문을 렌더한다.
    집계가 없으면 단순히 "데이터 부족" 한 줄.
    """
    if not consumer_aggregate or consumer_aggregate.get("total_analyzed_comments", 0) <= 0:
        return ["- 데이터 부족 (분석 가능한 댓글 없음)"]

    total = int(consumer_aggregate.get("total_analyzed_comments", 0))
    wr = consumer_aggregate.get("weighted_ratio") or {}
    pos = wr.get("positive_pct", 0.0)
    neu = wr.get("neutral_pct", 0.0)
    neg = wr.get("negative_pct", 0.0)

    lines: List[str] = [
        f"- 분석 댓글 수: {total}건",
        f"- 가중 비율: 긍정 {pos}% / 중립 {neu}% / 부정 {neg}%",
    ]

    pos_aspects = consumer_aggregate.get("top_positive_aspects") or []
    neg_aspects = consumer_aggregate.get("top_negative_aspects") or []
    reps = consumer_aggregate.get("representative_comments") or []

    lines.append("### 소비자가 꼽은 강점")
    if pos_aspects:
        for a in pos_aspects[:5]:
            lines.append(f"- {a.get('aspect_name','')} ({int(a.get('comment_count',0))}건)")
    else:
        lines.append("- 데이터 부족")

    lines.append("### 소비자가 꼽은 불만")
    if neg_aspects:
        for a in neg_aspects[:5]:
            lines.append(f"- {a.get('aspect_name','')} ({int(a.get('comment_count',0))}건)")
    else:
        lines.append("- 데이터 부족")

    lines.append("### 대표 댓글")
    if reps:
        for c in reps[:3]:
            text = (c.get("text_raw") or "").replace("\n", " ").strip()
            like = int(c.get("like_count", 0))
            lines.append(f'> "{text}" (👍 {like})')
    else:
        lines.append("- 데이터 부족")
    return lines


def _heuristic_fallback_report(
    product_name: str,
    per_video_reports: List[Dict],
    consumer_aggregate: Optional[Dict] = None,
    selected_video_count: Optional[int] = None,
) -> str:
    """LLM 미사용 모드. 7개 섹션 헤더만 깔끔히 출력하고 본문은 '데이터 부족'으로 채운다.
    환각을 만들지 않는 것이 최우선. ⑤ 소비자 여론 섹션만은 댓글 집계가 존재하면
    수치/aspect/대표 댓글을 LLM 없이 그대로 렌더해 정보를 보존한다.

    selected_video_count: 사용자가 선정한 영상 총 수 (자막 부재 제외 전).
        per_video_reports 보다 크면 메타박스에 "선정 N개 중 M개 분석 (X개 자막
        부재)" 표기. None/같은 값이면 단순히 "분석 영상: M개".
    """
    n = len(per_video_reports)
    today_str = date.today().isoformat()

    section5_lines = _fallback_render_consumer_section(consumer_aggregate)

    if selected_video_count is not None and selected_video_count > n:
        excluded = selected_video_count - n
        analyzed_line = f"   분석 영상: {n}개 (선정 {selected_video_count}개 중 {excluded}개 자막 부재로 제외)"
    else:
        analyzed_line = f"   분석 영상: {n}개"

    sections = [
        f"# {product_name} 종합 인사이트 보고서 (LLM 미사용 모드)",
        "",
        "## ① 한줄 구매 판정 + 종합 점수",
        "- 데이터 부족 (LLM 미사용 모드)",
        "",
        "## ② 핵심 요약",
        "- [데이터 부족] LLM 미사용 모드 — 핵심 요약 카드를 생성할 수 없습니다.",
        "- [데이터 부족] LLM 미사용 모드 — 입력 보고서 근거가 충분하지 않습니다.",
        "- [데이터 부족] LLM 미사용 모드 — 카드 본문을 채울 수 없습니다.",
        "",
        "## ③ 6차원 종합 평가",
        "- 데이터 부족 (LLM 미사용 모드)",
        "",
        "## ④ 장점 / 단점 (합의 기반)",
        "### 장점",
        "- 데이터 부족",
        "### 단점",
        "- 데이터 부족",
        "",
        "## ⑤ 소비자 여론 (댓글 기반)",
        *section5_lines,
        "",
        "## ⑥ 전작 대비 달라진 점",
        "- 데이터 부족 (LLM 미사용 모드)",
        "",
        "## ⑦ 이런 사람에게 추천 / 비추",
        "### 추천",
        "- 데이터 부족",
        "### 비추",
        "- 데이터 부족",
        "",
        "---",
        "📊 분석 기반",
        analyzed_line,
        f"   보고서 생성일: {today_str}",
        "",
        "## 입력 영상별 보고서 (참고)",
    ]
    for i, r in enumerate(per_video_reports):
        sections.append("")
        sections.append(f"### 영상 {i+1} — {r.get('title','')} (video_id={r.get('video_id','')})")
        body = (r.get("transcript_report") or "").strip()
        if len(body) > PER_VIDEO_REPORT_MAX_CHARS:
            body = body[:PER_VIDEO_REPORT_MAX_CHARS].rstrip() + "\n... (이하 생략)"
        sections.append(body)
    return "\n".join(sections)


def build_product_integrated_insight_report(
    product_name: str,
    per_video_reports: List[Dict],
    video_ids: Optional[List[str]] = None,
    selected_video_count: Optional[int] = None,
) -> Tuple[str, str]:
    """
    7섹션 통합 인사이트 보고서를 생성한다.
    RunYourAI 우선 사용, 미설정/실패 시 heuristic fallback.

    video_ids: ⑤ 소비자 여론 섹션을 위한 제품 단위 댓글 집계 대상. None / 빈 리스트면
               집계를 건너뛰고 ⑤ 섹션은 "데이터 부족" 으로 처리된다. 호환을 위해
               기본값은 None — 호출부가 per_video_reports.video_id 로 자동 도출.
    selected_video_count: 사용자가 선정한 영상 총 수 (자막 부재 제외 전).
        None / per_video_reports 길이와 동일하면 추가 표기 안 함 (호환 기본값).
        per_video_reports 보다 크면 메타박스에 "선정 N개 중 M개 분석 (X개 자막
        부재)" 표기. 분모 (장점/단점 N/M 의 M) 자체는 항상 실제 분석 영상 수
        (= len(per_video_reports)) 기준이다.

    반환: (report_text, model_used)
    """
    global _LAST_LLM_PERF
    _LAST_LLM_PERF = {"llm_ms": None, "fallback": False, "consumer_aggregate_ms": None}

    if not per_video_reports:
        _LAST_LLM_PERF["fallback"] = True
        return ("[ERROR] 입력 보고서가 없습니다.", HEURISTIC_MODEL_LABEL)

    truncated = _truncate_per_video(per_video_reports)
    today_str = date.today().isoformat()

    # ⑤ 소비자 여론 — 제품 단위 댓글 집계 (READ ONLY)
    if video_ids is None:
        video_ids = [r.get("video_id", "") for r in per_video_reports if r.get("video_id")]
    consumer_aggregate: Optional[Dict] = None
    if video_ids:
        agg_t0 = perf_counter()
        try:
            consumer_aggregate = aggregate_pir_consumer_inputs(video_ids)
        except Exception as e:
            print(f"[WARN] _pir_comment_aggregator failed: {type(e).__name__}: {e} — ⑤ section will be 'data insufficient'")
            consumer_aggregate = None
        _LAST_LLM_PERF["consumer_aggregate_ms"] = round((perf_counter() - agg_t0) * 1000, 1)
        if consumer_aggregate:
            print(
                f"[DEBUG] PIR consumer aggregate: comments={consumer_aggregate.get('total_analyzed_comments', 0)} "
                f"pos_aspects={len(consumer_aggregate.get('top_positive_aspects', []))} "
                f"neg_aspects={len(consumer_aggregate.get('top_negative_aspects', []))}"
            )

    prompt = build_product_integrated_insight_prompt(
        product_name, truncated, today_str=today_str, consumer_aggregate=consumer_aggregate,
        selected_video_count=selected_video_count,
    )

    if not RUNYOURAI_API_KEY:
        print("[WARN] RUNYOURAI_API_KEY not configured — using heuristic fallback")
        _LAST_LLM_PERF["fallback"] = True
        return (_heuristic_fallback_report(product_name, truncated, consumer_aggregate, selected_video_count=selected_video_count), HEURISTIC_MODEL_LABEL)

    try:
        client = get_report_llm_client()
    except ValueError as e:
        print(f"[WARN] RunYourAI client unavailable: {e} — using heuristic fallback")
        _LAST_LLM_PERF["fallback"] = True
        return (_heuristic_fallback_report(product_name, truncated, consumer_aggregate, selected_video_count=selected_video_count), HEURISTIC_MODEL_LABEL)

    try:
        print(f"[DEBUG] product_integrated_insight: calling {REPORT_LLM_DEPLOYMENT} for {product_name} (n={len(truncated)})")
        llm_t0 = perf_counter()
        response = client.chat.completions.create(
            model=REPORT_LLM_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2800,  # ⑤ 댓글 섹션 추가분 반영해 상향
        )
        llm_ms = (perf_counter() - llm_t0) * 1000
        _LAST_LLM_PERF["llm_ms"] = round(llm_ms, 1)
        print(f"[PERF][insight_llm] product={product_name} n={len(truncated)} llm_ms={llm_ms:.1f}")
        if not response.choices:
            print("[WARN] product_integrated_insight: empty response — using heuristic fallback")
            _LAST_LLM_PERF["fallback"] = True
            return (_heuristic_fallback_report(product_name, truncated, consumer_aggregate, selected_video_count=selected_video_count), HEURISTIC_MODEL_LABEL)
        text = response.choices[0].message.content or ""
        text = fix_encoding(text.strip())
        if not text:
            print("[WARN] product_integrated_insight: empty text — using heuristic fallback")
            _LAST_LLM_PERF["fallback"] = True
            return (_heuristic_fallback_report(product_name, truncated, consumer_aggregate, selected_video_count=selected_video_count), HEURISTIC_MODEL_LABEL)
        print(f"[DEBUG] product_integrated_insight: report length={len(text)}")
        return (text, REPORT_LLM_DEPLOYMENT)
    except Exception as e:
        print(f"[ERROR] product_integrated_insight LLM call failed: {type(e).__name__}: {e}")
        _LAST_LLM_PERF["fallback"] = True
        return (_heuristic_fallback_report(product_name, truncated, consumer_aggregate, selected_video_count=selected_video_count), HEURISTIC_MODEL_LABEL)


# ── 3) 저장 / 조회 ───────────────────────────────────────────────

def save_product_integrated_report(
    product_id: int,
    video_ids: List[str],
    report_text: str,
    model_used: str,
) -> int:
    """product_integrated_reports에 INSERT 후 id 반환 (이력 보존)."""
    video_ids_json = json.dumps(list(video_ids), ensure_ascii=False)
    new_id = execute_insert(
        """INSERT INTO product_integrated_reports
              (product_id, video_ids, source_video_count, report_text, model_used)
           VALUES (%s, %s, %s, %s, %s)
           RETURNING id""",
        (product_id, video_ids_json, len(video_ids), report_text, model_used),
    )
    return new_id


def get_latest_product_integrated_report(product_id: int) -> Optional[Dict]:
    """최신 통합 보고서 1건 조회 (없으면 None)."""
    row = query_one(
        """SELECT id, product_id, video_ids, source_video_count, report_text, model_used, created_at
           FROM product_integrated_reports
           WHERE product_id = %s
           ORDER BY created_at DESC
           LIMIT 1""",
        (product_id,),
    )
    if not row:
        return None
    parsed_video_ids: List[str] = []
    raw_ids = row.get("video_ids") or ""
    try:
        loaded = json.loads(raw_ids)
        if isinstance(loaded, list):
            parsed_video_ids = [str(x) for x in loaded]
    except (ValueError, TypeError):
        parsed_video_ids = [s.strip() for s in raw_ids.split(",") if s.strip()]
    return {
        "id": row["id"],
        "product_id": row["product_id"],
        "video_ids": parsed_video_ids,
        "source_video_count": row["source_video_count"],
        "report_text": row["report_text"],
        "model_used": row.get("model_used"),
        "created_at": row.get("created_at"),
    }


def get_product_integrated_report(product_id: int, report_id: int) -> Optional[Dict]:
    """특정 통합 보고서 조회 (PDF 다운로드용)."""
    row = query_one(
        """SELECT id, product_id, video_ids, source_video_count, report_text, model_used, created_at
           FROM product_integrated_reports
           WHERE product_id = %s AND id = %s""",
        (product_id, report_id),
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "product_id": row["product_id"],
        "source_video_count": row["source_video_count"],
        "report_text": row["report_text"],
        "model_used": row.get("model_used"),
        "created_at": row.get("created_at"),
    }
