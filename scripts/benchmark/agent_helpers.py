"""댓글 처리 agent 의 fetch/preprocess/select 헬퍼 — 비교 도구 전용 minimal 복제.

운영 ``scripts/api/sync.py`` 의 동일 이름 함수들에서 비교 도구가 필요로 하는
부분만 발췌. 운영 의존성 (DB / FastAPI / scripts.config 등) 0.

원본과 동기 유지 필요. 운영 sync.py 가 바뀌면 여기도 같이 업데이트.
"""
from __future__ import annotations

import re
import random
from datetime import datetime
from typing import Dict, List


# === 운영 sync.py 와 동일한 상수 ============================================

MAX_COMMENT_CHARS = 140
MAX_LLM_COMMENTS = 20
RAW_COMMENT_FETCH_LIMIT = 1000
TOP_PER_SOURCE = 30


# === 정규화 / 키워드 ========================================================

PRODUCT_ASPECT_KEYWORDS = [
    # 성능/처리
    "성능", "속도", "처리", "발열", "온도", "쿨링",
    # 배터리
    "배터리", "충전", "배터리수명", "전력",
    # 디스플레이
    "화면", "디스플레이", "해상도", "밝기",
    # 디자인/외형
    "디자인", "무게", "크기", "마감", "색상", "두께",
    # 카메라
    "카메라", "화질", "사진",
    # 가격/가성비
    "가격", "가성비", "성가비",
    # 소프트웨어/UI
    "소프트웨어", "앱", "업데이트", "버그",
    # 내구성/서비스
    "내구성", "AS", "서비스", "품질",
    # 음향
    "소리", "음질", "스피커",
]


def _normalize_comment_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.lower()
    cleaned = re.sub(r"[^0-9a-zA-Z가-힣\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _keyword_hit_count(comment_text: str, product_name: str) -> int:
    text = _normalize_comment_text(comment_text)
    product_tokens = [t for t in _normalize_comment_text(product_name).split() if t]
    all_keywords = PRODUCT_ASPECT_KEYWORDS + product_tokens
    return sum(1 for kw in all_keywords if kw and kw in text)


def _to_timestamp(value) -> float:
    if not value:
        return 0.0
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _normalize_feature(value: float, min_value: float, max_value: float) -> float:
    if max_value <= min_value:
        return 0.0
    return (value - min_value) / (max_value - min_value)


# === preprocess (운영 sync.py 와 동일 로직) ================================

def _preprocess_comments(raw_comments, video_id: str):
    """Python preprocessing:
    1) Remove null/blank rows
    2) Drop exact duplicates by (video_id, author, text)
    3) Attach flags for downstream scoring/LLM reference
    """
    base_rows: List[Dict] = []
    for c in raw_comments:
        base_rows.append({
            "comment_id": c.comment_id,
            "video_id": video_id,
            "author": c.author_name or "",
            "author_channel_id": c.author_channel_id or "",
            "text": c.text_original,
            "like_count": c.like_count or 0,
            "reply_count": c.reply_count or 0,
            "published_at": c.published_at,
            "is_reply": c.is_reply,
            "parent_comment_id": c.parent_comment_id,
        })

    if not base_rows:
        return [], {"input_count": 0, "output_count": 0,
                    "removed_null_blank": 0, "removed_duplicates": 0}

    valid_rows = []
    for r in base_rows:
        text = r.get("text")
        if text is None:
            continue
        if not str(text).strip():
            continue
        valid_rows.append(r)

    seen = set()
    dedup_rows = []
    for r in valid_rows:
        key = (r["video_id"], r["author"], r["text"])
        if key in seen:
            continue
        seen.add(key)
        dedup_rows.append(r)

    for r in dedup_rows:
        cleaned = str(r["text"]).strip()
        r["text_cleaned"] = cleaned
        r["char_count"] = len(cleaned)
        r["is_short"] = len(cleaned) < 5
        r["has_url"] = bool(re.search(r"https?://|www\.", cleaned))
        r["is_repetitive"] = bool(re.match(r"^(.)\1{9,}$", cleaned))

    return dedup_rows, {
        "input_count": len(base_rows),
        "output_count": len(dedup_rows),
        "removed_null_blank": max(0, len(base_rows) - len(valid_rows)),
        "removed_duplicates": max(0, len(valid_rows) - len(dedup_rows)),
    }


# === Multi-Criteria 선정 (운영 sync.py 와 동일 로직) =======================

def _select_comments_multicriteria(comment_items, product_name: str):
    if not comment_items:
        return [], {
            "entry_count": 0,
            "primary_pool_count": 0,
            "secondary_pool_count": 0,
            "primary_selected_count": 0,
            "secondary_selected_count": 0,
        }

    per_source = min(TOP_PER_SOURCE, len(comment_items))
    by_like = sorted(comment_items, key=lambda x: (x["like_count"], x["reply_count"]), reverse=True)[:per_source]
    by_reply = sorted(comment_items, key=lambda x: (x["reply_count"], x["like_count"]), reverse=True)[:per_source]
    by_length = sorted(comment_items, key=lambda x: len(x["comment_text"]), reverse=True)[:per_source]
    by_new = sorted(comment_items, key=lambda x: x["published_ts"], reverse=True)[:per_source]
    by_old = sorted(comment_items, key=lambda x: x["published_ts"])[:per_source]
    by_random = random.sample(comment_items, k=per_source)

    source_groups = {
        "like": by_like,
        "many": by_reply,
        "long": by_length,
        "new": by_new,
        "old": by_old,
        "random": by_random,
    }

    meta = {}
    for source_name, group in source_groups.items():
        for item in group:
            cid = item["comment_id"]
            if cid not in meta:
                meta[cid] = {"item": item, "sources": set()}
            meta[cid]["sources"].add(source_name)

    entries = []
    for v in meta.values():
        item = v["item"]
        sources = v["sources"]
        entries.append({
            "item": item,
            "hit_count": len(sources),
            "sources": sorted(sources),
            "secondary_score": 0.0,
        })

    primary = [e for e in entries if e["hit_count"] >= 2]
    primary.sort(
        key=lambda e: (
            e["hit_count"],
            e["item"]["like_count"],
            e["item"]["reply_count"],
            len(e["item"]["comment_text"])
        ),
        reverse=True
    )

    secondary_pool = [e for e in entries if e["hit_count"] == 1]

    if len(primary) >= MAX_LLM_COMMENTS:
        selected = primary[:MAX_LLM_COMMENTS]
        return selected, {
            "entry_count": len(entries),
            "primary_pool_count": len(primary),
            "secondary_pool_count": len(secondary_pool),
            "primary_selected_count": len(selected),
            "secondary_selected_count": 0,
        }

    if secondary_pool:
        likes = [e["item"]["like_count"] for e in secondary_pool]
        replies = [e["item"]["reply_count"] for e in secondary_pool]
        min_like, max_like = min(likes), max(likes)
        min_reply, max_reply = min(replies), max(replies)

        for e in secondary_pool:
            item = e["item"]
            normalized_like = _normalize_feature(item["like_count"], min_like, max_like)
            normalized_reply = _normalize_feature(item["reply_count"], min_reply, max_reply)
            keyword_hits = _keyword_hit_count(item["comment_text"], product_name)
            e["secondary_score"] = normalized_like + normalized_reply + keyword_hits

        secondary_pool.sort(
            key=lambda e: (e["secondary_score"], len(e["item"]["comment_text"])),
            reverse=True
        )

    needed = MAX_LLM_COMMENTS - len(primary)
    selected = primary + secondary_pool[:max(0, needed)]
    selected = selected[:MAX_LLM_COMMENTS]
    return selected, {
        "entry_count": len(entries),
        "primary_pool_count": len(primary),
        "secondary_pool_count": len(secondary_pool),
        "primary_selected_count": sum(1 for e in selected if e["hit_count"] >= 2),
        "secondary_selected_count": sum(1 for e in selected if e["hit_count"] == 1),
    }
