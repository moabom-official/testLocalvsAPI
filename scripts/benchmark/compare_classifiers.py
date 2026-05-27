"""compare_classifiers.py — API (GPT-4.1) vs Local (KLUE-RoBERTa) 분류기 비교.

같은 video_id 의 같은 댓글 셋에 대해 두 backend 를 모두 돌려서 비교한다.
DB 에 쓰지 않음 (read-only). agent 의 fetch + rule filter + Multi-Criteria
선정 까지 공통으로 거친 뒤 분류 단계만 두 번 (각각) 수행.

수집 지표:
  - Wall clock time (초)
  - Throughput (comments/s)
  - 라벨 분포 (PO / VR / Q / NOISE)
  - 라벨 일치율 (4-class agreement)
  - 운영 등가 일치율 (3-class agreement, NOISE → VR 흡수)
  - GPT-4.1 비용 추정 ($)
  - per-class confusion (API → Local)

사용:
    python -m scripts.benchmark.compare_classifiers \\
        --video-id <youtube_video_id> \\
        --max-comments 100 \\
        [--product-name "갤럭시 S25"] \\
        [--output benchmark_results.json]

필수 환경변수:
    YOUTUBE_API_KEY     YouTube fetch
    RUNYOURAI_API_KEY   API classifier (GPT-4.1)
    DATABASE_URL        scripts.api.sync 임포트 시 필요 (실제 사용 안 함)

로컬 모델 경로:
    local_classifier/artifacts/3_labels/klue__roberta-large/model/best/
    (학습 후 미리 다운로드 필요)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 공통: fetch + 1차 필터 + Multi-Criteria 선정 (sync.py 헬퍼 재사용, DB X)
# ---------------------------------------------------------------------------

def fetch_and_select(video_id: str, product_name: str, max_comments: int) -> list[dict]:
    """sync.process_comments_with_agent 의 Step 1~4 를 재현 (DB write 없이).

    반환: 각 원소는 평면 dict — comment_id / comment_text / like_count /
    reply_count / published_ts. (sync.py 가 select 단계로 넘기는 candidate
    스키마와 동일.)
    """
    from scripts.api.sync import (
        YOUTUBE_API_KEY,
        RAW_COMMENT_FETCH_LIMIT,
        MAX_COMMENT_CHARS,
        _preprocess_comments,
        _select_comments_multicriteria,
        _to_timestamp,
    )
    from comment_filtering_agent.services.comment_collector import YouTubeCommentCollector
    from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
    from comment_filtering_agent.filters.models import RuleConfig

    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY 환경변수 필수.")

    print(f"[1] YouTube fetch (target={RAW_COMMENT_FETCH_LIMIT})...")
    collector = YouTubeCommentCollector(api_key=YOUTUBE_API_KEY)
    raw = collector.collect_comments(video_id, max_results=RAW_COMMENT_FETCH_LIMIT)
    print(f"    raw: {len(raw)}")
    if not raw:
        return []

    print("[2] Preprocess (dedup + flags)...")
    rows, _diag = _preprocess_comments(raw, video_id)
    print(f"    preprocessed: {len(rows)}")
    if not rows:
        return []

    print("[3] Rule filter (PASS only) + 스키마 변환...")
    rule_filter = RuleBasedFilter(config=RuleConfig(
        enable_url_check=False,
        enable_duplicate_check=False,
        max_repeated_char_ratio=0.7,
    ))
    # sync.py 의 candidate_comments 와 같은 평면 dict 로 변환.
    # _select_comments_multicriteria 가 요구하는 키: comment_text, published_ts, like_count, reply_count, comment_id
    candidates: list[dict] = []
    for i, row in enumerate(rows):
        comment_text = row.get("text_cleaned") or str(row.get("text") or "").strip()
        if not comment_text:
            continue
        res = rule_filter.filter_single(comment_text, index=i)
        if not res.is_passed:
            continue
        candidates.append({
            "comment_id": row["comment_id"],
            "comment_text": comment_text[:MAX_COMMENT_CHARS],
            "like_count": int(row.get("like_count") or 0),
            "reply_count": int(row.get("reply_count") or 0),
            "published_ts": _to_timestamp(row.get("published_at")),
        })
    print(f"    rule passed: {len(candidates)}")
    if not candidates:
        return []

    print("[4] Multi-Criteria selection (top by like / reply / length / new)...")
    entries, _stats = _select_comments_multicriteria(candidates, product_name)
    # entries 는 [{"item": <candidate row>, "hit_count": ..., "sources": [...], "secondary_score": ...}]
    # 우리 비교 스크립트는 평면 row 가 필요하므로 unwrap.
    selected = [e["item"] for e in entries[:max_comments]]
    print(f"    selected: {len(selected)}")
    return selected


# ---------------------------------------------------------------------------
# Backend 별 분류 + 메트릭 수집
# ---------------------------------------------------------------------------

def _label_to_str(label) -> str:
    """ClassificationResult.label 이 enum (CommentLabel) 일 수도 str 일 수도 있음.

    - API (comment_filtering_agent.classifiers.models.ClassificationResult):
      label = CommentLabel(Enum) → .value 로 string.
    - Local (comment_filtering_agent.classifiers.classifier_interface.ClassificationResult):
      label = str → 그대로.
    """
    if label is None:
        return ""
    return label.value if hasattr(label, "value") else str(label)


def bench_api(texts: list[str]) -> dict:
    """OptimizedBatchClassifier (RunYourAI GPT-4.1)."""
    print("\n[API] OptimizedBatchClassifier (GPT-4.1 via RunYourAI)...")
    from comment_filtering_agent.classifiers.optimized_batch_classifier import (
        OptimizedBatchClassifier,
    )
    clf = OptimizedBatchClassifier(batch_size=25, confidence_threshold=0.75)
    t0 = time.perf_counter()
    results = clf.classify_batch(texts)
    elapsed = time.perf_counter() - t0
    print(f"    done in {elapsed:.2f}s ({len(texts)/max(elapsed, 0.001):.1f} comments/s)")
    return {
        "backend": "api",
        "model": os.environ.get("RUNYOURAI_MODEL", "openai/gpt-4.1-2025-04-14"),
        "elapsed_s": elapsed,
        "results": [
            {"label": _label_to_str(r.label), "confidence": float(r.confidence)}
            for r in results
        ],
    }


def bench_local(texts: list[str]) -> dict:
    """LocalRobertaClassifier (KLUE-RoBERTa-large 3-class)."""
    print("\n[Local] LocalRobertaClassifier (KLUE-RoBERTa-large 3-class)...")
    from local_classifier.classifier import LocalRobertaClassifier
    clf = LocalRobertaClassifier(use_gpu=True)
    t0 = time.perf_counter()
    results = clf.classify_batch(texts)
    elapsed = time.perf_counter() - t0
    print(f"    done in {elapsed:.2f}s ({len(texts)/max(elapsed, 0.001):.1f} comments/s)")
    return {
        "backend": "local",
        "model": "klue/roberta-large (3-class)",
        "elapsed_s": elapsed,
        "results": [
            {"label": _label_to_str(r.label), "confidence": float(r.confidence)}
            for r in results
        ],
        "model_stats": clf.get_stats(),
    }


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

# 4-class API 출력을 3-class 운영 등가로 변환 (NOISE/CHATTER/OFF_TOPIC → VR).
LABEL_REMAP_3CLASS = {
    "PRODUCT_OPINION": "PRODUCT_OPINION",
    "VIDEO_REACTION": "VIDEO_REACTION",
    "QUESTION": "QUESTION",
    "NOISE": "VIDEO_REACTION",
    "CHATTER": "VIDEO_REACTION",
    "OFF_TOPIC": "VIDEO_REACTION",
}


def _agreement(a: list[str], b: list[str]) -> float:
    if not a:
        return 0.0
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


def _estimate_api_cost(n: int) -> dict:
    """GPT-4.1 (2025-04-14) pricing 기준 추정.
       in:  $2.0 / 1M tokens
       out: $8.0 / 1M tokens
       댓글당 amortized 입력 ~80 tokens, 출력 ~30 tokens (batch 25 기준).
    """
    in_tokens = n * 80
    out_tokens = n * 30
    cost = (in_tokens * 2.0 + out_tokens * 8.0) / 1_000_000
    return {
        "estimated_input_tokens": in_tokens,
        "estimated_output_tokens": out_tokens,
        "estimated_cost_usd": round(cost, 4),
        "pricing_note": "GPT-4.1 (2025-04-14): $2/$8 per 1M in/out tokens",
    }


def compare(api: dict, local: dict, candidates: list[dict]) -> dict:
    api_labels = [r["label"] for r in api["results"]]
    local_labels = [r["label"] for r in local["results"]]
    n = len(api_labels)

    # 4-class raw
    raw_agreement = _agreement(api_labels, local_labels)

    # 3-class equivalent (운영 액션 단위)
    api_3 = [LABEL_REMAP_3CLASS.get(l, l) for l in api_labels]
    local_3 = [LABEL_REMAP_3CLASS.get(l, l) for l in local_labels]
    op_agreement = _agreement(api_3, local_3)

    # confusion: API → Local (3-class space)
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a, l in zip(api_3, local_3):
        confusion[a][l] += 1

    cost = _estimate_api_cost(n)

    return {
        "n_comments": n,
        # time
        "api_elapsed_s": round(api["elapsed_s"], 2),
        "local_elapsed_s": round(local["elapsed_s"], 2),
        "api_throughput_per_s": round(n / max(api["elapsed_s"], 0.001), 2),
        "local_throughput_per_s": round(n / max(local["elapsed_s"], 0.001), 2),
        "speedup_local_vs_api": round(
            api["elapsed_s"] / max(local["elapsed_s"], 0.001), 2
        ),
        # cost
        **cost,
        "local_cost_usd": 0.0,
        # agreement
        "raw_4class_agreement": round(raw_agreement, 4),
        "operational_3class_agreement": round(op_agreement, 4),
        # distributions
        "api_label_dist": dict(Counter(api_labels)),
        "local_label_dist": dict(Counter(local_labels)),
        "api_3class_dist": dict(Counter(api_3)),
        "local_3class_dist": dict(Counter(local_3)),
        # confusion (3-class)
        "confusion_api_to_local_3class": {a: dict(d) for a, d in confusion.items()},
        # meta
        "api_model": api["model"],
        "local_model": local["model"],
        # per-comment (작으면 그대로 포함)
        "per_comment": [
            {
                "comment_id": c.get("comment_id"),
                "text": c.get("comment_text", c.get("text", ""))[:100],
                "api_label": a,
                "local_label": l,
                "api_3class": a3,
                "local_3class": l3,
                "agree": a3 == l3,
            }
            for c, a, l, a3, l3 in zip(candidates, api_labels, local_labels, api_3, local_3)
        ] if n <= 200 else "omitted (n>200)",
    }


def print_report(r: dict) -> None:
    print()
    print("=" * 72)
    print(f"비교 결과 — {r['n_comments']} comments")
    print("=" * 72)
    print()
    print(f"{'metric':<30} {'API':>18} {'Local':>18}")
    print("-" * 70)
    print(f"{'wall time (s)':<30} {r['api_elapsed_s']:>18.2f} {r['local_elapsed_s']:>18.2f}")
    print(f"{'throughput (cmt/s)':<30} {r['api_throughput_per_s']:>18.2f} {r['local_throughput_per_s']:>18.2f}")
    print(f"{'cost ($)':<30} {r['estimated_cost_usd']:>18.4f} {r['local_cost_usd']:>18.4f}")
    print()
    print(f"speedup (local vs api)        : {r['speedup_local_vs_api']}x")
    print(f"raw 4-class agreement         : {r['raw_4class_agreement']*100:.1f}%")
    print(f"operational 3-class agreement : {r['operational_3class_agreement']*100:.1f}%")
    print()
    print(f"API model   : {r['api_model']}")
    print(f"Local model : {r['local_model']}")
    print()
    print("Label distribution (raw):")
    print(f"  API   : {r['api_label_dist']}")
    print(f"  Local : {r['local_label_dist']}")
    print()
    print("Label distribution (3-class operational):")
    print(f"  API   : {r['api_3class_dist']}")
    print(f"  Local : {r['local_3class_dist']}")
    print()
    print("Confusion (rows=API, cols=Local, 3-class):")
    labels = sorted(set(r['api_3class_dist']) | set(r['local_3class_dist']))
    print(f"  {'':18s}  " + "  ".join(f"{l[:8]:>8s}" for l in labels))
    for row in labels:
        cells = r['confusion_api_to_local_3class'].get(row, {})
        print(f"  {row:18s}  " + "  ".join(f"{cells.get(c, 0):>8d}" for c in labels))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video-id", required=True, help="YouTube 영상 ID")
    ap.add_argument("--product-name", default="제품",
                    help="Multi-Criteria 선정에 사용 (운영 sync 동일).")
    ap.add_argument("--max-comments", type=int, default=100,
                    help="분류기에 보낼 댓글 최대 개수 (선정 후 cap).")
    ap.add_argument("--output", type=str, default=None,
                    help="JSON 결과 저장 경로.")
    ap.add_argument("--skip-api", action="store_true",
                    help="API 분류 건너뛰기 (Local 만 측정).")
    ap.add_argument("--skip-local", action="store_true",
                    help="Local 분류 건너뛰기 (API 만 측정).")
    args = ap.parse_args()

    if args.skip_api and args.skip_local:
        ap.error("--skip-api 와 --skip-local 동시 불가.")

    # ---- 공통 파이프라인 ----
    candidates = fetch_and_select(
        args.video_id, args.product_name, args.max_comments
    )
    if not candidates:
        print("[error] 후보 댓글 0건. 비교 중단.")
        return

    texts = [c.get("comment_text", c.get("text", "")) for c in candidates]

    api_bench = bench_api(texts) if not args.skip_api else None
    local_bench = bench_local(texts) if not args.skip_local else None

    if api_bench and local_bench:
        report = compare(api_bench, local_bench, candidates)
        print_report(report)
    else:
        # 단일 backend 측정만 — 간단 출력
        bench = api_bench or local_bench
        print(f"\n단일 backend ({bench['backend']}) 측정 완료:")
        print(f"  elapsed: {bench['elapsed_s']:.2f}s")
        print(f"  throughput: {len(texts)/max(bench['elapsed_s'], 0.001):.2f} comments/s")
        report = {
            "n_comments": len(texts),
            "backend": bench["backend"],
            "elapsed_s": bench["elapsed_s"],
            "results": bench["results"],
        }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
