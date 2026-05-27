"""run_agent_comparison.py — 제품명 입력 → 인기 영상 자동 검색 → 댓글 분류 비교.

전체 보고서 파이프라인 (자막+댓글 통합 등) 은 거치지 않고, **댓글 처리 agent
부분만** 자동으로 돌린다. API 분류기와 Local 분류기를 같은 영상의 같은 댓글
셋에 돌려서 결과를 비교 + JSON 저장 + 콘솔 표시.

흐름:
    제품명 → YouTube search.list (조회수 순) → top 1 video 선택
        → comment_filtering_agent 의 fetch + rule filter + Multi-Criteria 선정
        → 분류기 두 backend 로 분류 (API GPT-4.1 / Local KLUE-RoBERTa)
        → 댓글별 두 결과 + 일치 여부 출력 + JSON 저장

필수 환경변수:
    YOUTUBE_API_KEY     YouTube fetch (search + comment fetch)
    RUNYOURAI_API_KEY   API classifier
    DATABASE_URL        scripts.api.sync import 만 (실제 사용 안 함)

로컬 모델 경로:
    local_classifier/artifacts/3_labels/klue__roberta-large/model/best/

사용:
    # 인자로 제품명 전달
    python -m scripts.benchmark.run_agent_comparison --product "갤럭시 S25"

    # 또는 interactive 입력
    python -m scripts.benchmark.run_agent_comparison

    # 옵션
    --top-k 20         (분류기에 넣을 댓글 수, 기본 20)
    --skip-api / --skip-local  (단일 backend)
    --output PATH      (JSON 저장 경로, 기본: comparison_<product>_<ts>.json)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# YouTube 검색 — 제품명으로 인기 영상 1개
# ---------------------------------------------------------------------------

def search_top_video(product_name: str, max_candidates: int = 5) -> dict:
    """search.list + videos.list 로 조회수 가장 많은 영상 1개 반환."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "google-api-python-client 미설치.\n  pip install google-api-python-client"
        )
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY 환경변수 필수.")

    yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    # 1) 검색 — 한국 지역, 조회수 정렬, 리뷰 키워드 추가
    query = f"{product_name} 리뷰"
    resp = yt.search().list(
        part="snippet",
        q=query,
        type="video",
        order="viewCount",
        regionCode="KR",
        relevanceLanguage="ko",
        maxResults=max_candidates,
    ).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError(f"검색 결과 0건 — query='{query}'")

    # 2) videos.list 로 정확한 조회수 / 좋아요 조회
    video_ids = [it["id"]["videoId"] for it in items if it.get("id", {}).get("videoId")]
    if not video_ids:
        raise RuntimeError("video ID 추출 실패")

    stats = yt.videos().list(
        part="statistics,snippet,contentDetails",
        id=",".join(video_ids),
    ).execute()
    videos = stats.get("items", [])
    videos.sort(
        key=lambda v: int(v.get("statistics", {}).get("viewCount", 0)),
        reverse=True,
    )
    top = videos[0]
    snip = top["snippet"]
    s = top.get("statistics", {})
    return {
        "video_id": top["id"],
        "title": snip.get("title", ""),
        "channel": snip.get("channelTitle", ""),
        "published_at": snip.get("publishedAt", ""),
        "view_count": int(s.get("viewCount", 0)),
        "like_count": int(s.get("likeCount", 0)),
        "comment_count": int(s.get("commentCount", 0)),
        "url": f"https://www.youtube.com/watch?v={top['id']}",
    }


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def run_comparison(
    product_name: str,
    top_k: int = 20,
    skip_api: bool = False,
    skip_local: bool = False,
) -> dict:
    """전체 흐름 — return: 결과 dict (콘솔 출력 + JSON 저장용)."""
    # 1) YouTube 검색
    print(f"\n[1] YouTube 검색 — '{product_name}'")
    try:
        top = search_top_video(product_name)
    except RuntimeError as e:
        raise SystemExit(f"검색 실패: {e}")
    print(f"  ★ {top['title'][:70]}")
    print(f"    channel    : {top['channel']}")
    print(f"    view_count : {top['view_count']:,}")
    print(f"    like_count : {top['like_count']:,}")
    print(f"    comments   : {top['comment_count']:,}")
    print(f"    url        : {top['url']}")

    # 2) 댓글 fetch + 선정 (compare_classifiers 의 헬퍼 재사용)
    from scripts.benchmark.compare_classifiers import (
        fetch_and_select,
        bench_api,
        bench_local,
        LABEL_REMAP_3CLASS,
    )

    candidates = fetch_and_select(
        video_id=top["video_id"],
        product_name=product_name,
        max_comments=top_k,
    )
    if not candidates:
        raise SystemExit("[error] 후보 댓글 0건 (댓글 비활성 또는 fetch 실패)")

    texts = [c.get("comment_text") or c.get("text") or "" for c in candidates]

    # 3) 분류 — backend 별
    api_bench = None if skip_api else bench_api(texts)
    local_bench = None if skip_local else bench_local(texts)

    # 4) 댓글별 결과 dict 구성
    rows = []
    for i, c in enumerate(candidates):
        text = c.get("comment_text") or c.get("text") or ""
        row = {
            "rank": i + 1,
            "comment_id": c.get("comment_id"),
            "text": text,
            "like_count": c.get("like_count", 0),
            "reply_count": c.get("reply_count", 0),
        }
        if api_bench:
            r = api_bench["results"][i]
            row["api_label"] = r["label"]
            row["api_confidence"] = round(r["confidence"], 4)
            row["api_3class"] = LABEL_REMAP_3CLASS.get(r["label"], r["label"])
        if local_bench:
            r = local_bench["results"][i]
            row["local_label"] = r["label"]
            row["local_confidence"] = round(r["confidence"], 4)
            row["local_3class"] = LABEL_REMAP_3CLASS.get(r["label"], r["label"])
        if api_bench and local_bench:
            row["agree_3class"] = row["api_3class"] == row["local_3class"]
        rows.append(row)

    # 5) 요약 통계
    summary: dict = {
        "n_comments": len(rows),
    }
    if api_bench:
        summary["api_elapsed_s"] = round(api_bench["elapsed_s"], 2)
        summary["api_throughput_per_s"] = round(
            len(rows) / max(api_bench["elapsed_s"], 0.001), 2
        )
        summary["api_label_dist"] = dict(Counter(r["api_label"] for r in rows))
        summary["api_model"] = api_bench["model"]
    if local_bench:
        summary["local_elapsed_s"] = round(local_bench["elapsed_s"], 2)
        summary["local_throughput_per_s"] = round(
            len(rows) / max(local_bench["elapsed_s"], 0.001), 2
        )
        summary["local_label_dist"] = dict(Counter(r["local_label"] for r in rows))
        summary["local_model"] = local_bench["model"]
    if api_bench and local_bench:
        agree = sum(1 for r in rows if r["agree_3class"])
        summary["agreement_3class"] = round(agree / max(len(rows), 1), 4)
        summary["speedup_local_vs_api"] = round(
            api_bench["elapsed_s"] / max(local_bench["elapsed_s"], 0.001), 2
        )
        # 비용 추정 (GPT-4.1)
        n = len(rows)
        summary["api_cost_usd_est"] = round((n * 80 * 2 + n * 30 * 8) / 1_000_000, 4)

    return {
        "product_name": product_name,
        "generated_at": datetime.now().isoformat(),
        "video": top,
        "summary": summary,
        "comments": rows,
    }


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

def _truncate(text: str, n: int) -> str:
    text = " ".join(text.split())  # 줄바꿈 제거
    return text if len(text) <= n else text[: n - 1] + "…"


def print_results(result: dict) -> None:
    rows = result["comments"]
    summary = result["summary"]

    print("\n" + "=" * 100)
    print(f"댓글 분류 결과 — {len(rows)} 건")
    print("=" * 100)

    has_api = any("api_label" in r for r in rows)
    has_local = any("local_label" in r for r in rows)

    for r in rows:
        print(f"\n[{r['rank']:2d}]  좋아요 {r['like_count']:>5d}  · 답글 {r['reply_count']:>3d}")
        print(f"     {_truncate(r['text'], 90)}")
        if has_api:
            print(f"     API   : {r['api_label']:<18s} (conf={r['api_confidence']:.3f})")
        if has_local:
            print(f"     Local : {r['local_label']:<18s} (conf={r['local_confidence']:.3f})")
        if has_api and has_local:
            mark = "✓" if r.get("agree_3class") else "✗"
            print(f"     일치  : {mark}  (운영 3-class 기준)")

    # 요약
    print("\n" + "=" * 100)
    print("요약")
    print("=" * 100)
    if has_api:
        print(f"  API   분포 : {summary.get('api_label_dist')}")
        print(f"  API   시간 : {summary.get('api_elapsed_s'):.2f}s  "
              f"({summary.get('api_throughput_per_s'):.2f} cmt/s)")
        print(f"  API   비용 추정 (GPT-4.1) : ${summary.get('api_cost_usd_est', 0):.4f}")
    if has_local:
        print(f"  Local 분포 : {summary.get('local_label_dist')}")
        print(f"  Local 시간 : {summary.get('local_elapsed_s'):.2f}s  "
              f"({summary.get('local_throughput_per_s'):.2f} cmt/s)")
    if has_api and has_local:
        print(f"\n  >> speedup (Local vs API) : {summary.get('speedup_local_vs_api')}x")
        print(f"  >> 일치율 (3-class 운영)  : "
              f"{summary.get('agreement_3class', 0) * 100:.1f}%")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--product", type=str, default=None,
                    help="제품명 (생략 시 콘솔에서 입력 받음)")
    ap.add_argument("--top-k", type=int, default=20,
                    help="분류기에 넘길 댓글 최대 개수 (기본 20)")
    ap.add_argument("--skip-api", action="store_true", help="API 분류 건너뜀")
    ap.add_argument("--skip-local", action="store_true", help="Local 분류 건너뜀")
    ap.add_argument("--output", type=str, default=None,
                    help="JSON 저장 경로 (기본: comparison_<product>_<timestamp>.json)")
    args = ap.parse_args()

    if args.skip_api and args.skip_local:
        ap.error("--skip-api 와 --skip-local 동시 불가.")

    product = args.product
    if not product:
        try:
            product = input("제품명을 입력하세요: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
    if not product:
        ap.error("제품명이 비었습니다.")

    result = run_comparison(
        product_name=product,
        top_k=args.top_k,
        skip_api=args.skip_api,
        skip_local=args.skip_local,
    )

    print_results(result)

    # JSON 저장
    if args.output:
        out_path = Path(args.output)
    else:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in product)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = REPO_ROOT / "scripts" / "benchmark" / "results" / f"{safe}_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
