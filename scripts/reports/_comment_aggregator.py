"""
보고서 ② / ③ 공통 데이터 집계 헬퍼 (v2).

역할:
  - DB 읽기 (comments / comment_sentiments / aspect_extractions / agent_decisions)
  - Python 측 가공 (가중 비율, aspect 그룹핑, 후보 댓글 추림)
  - LLM 응답 JSON 스키마 검증
  - representative_comment_ids → comments.text_raw 원문 첨부

⚠️ aspect_extractions 는 READ ONLY. INSERT/UPDATE 금지.
LLM 호출과 video_reports UPSERT 는 호출부(comment_report.py / integrated_report.py)의 책임.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from scripts.database.queries import query_all


# ── 튜닝 상수 ──────────────────────────────────────────────────

# aspect 한 그룹당 LLM 에 넘기는 후보 댓글 수
CANDIDATE_PER_ASPECT = 8

# 대표 댓글로 우선 고려할 텍스트 길이 범위 (너무 짧지도 길지도 않은 댓글)
SWEET_LEN_MIN = 30
SWEET_LEN_MAX = 200

# 프롬프트 토큰 비용 보호용: text_raw 가 너무 긴 경우 truncate 길이
PROMPT_TEXT_MAX = 200

# 보고서 ② positive_aspects / negative_aspects 각 상한
TOP_K_ASPECTS_PER_SENTIMENT = 8


# ── 가중 sentiment 비율 ───────────────────────────────────────

def compute_weighted_ratio(sentiment_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """analysis_weight 가중 비율 → {positive_pct, neutral_pct, negative_pct}.

    sentiment_rows: [{"sentiment_label": "positive"|..., "analysis_weight": float|None}, ...]
    NULL weight 는 1.0 으로 간주 (comment_report.py 의 기존 fallback 과 동일).
    """
    totals = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
    total_w = 0.0
    for r in sentiment_rows:
        label = r.get("sentiment_label")
        if label not in totals:
            continue
        w = r.get("analysis_weight")
        w = float(w) if w is not None else 1.0
        totals[label] += w
        total_w += w
    if total_w <= 0:
        return {"positive_pct": 0.0, "neutral_pct": 0.0, "negative_pct": 0.0}
    return {
        "positive_pct": round(totals["positive"] / total_w * 100, 1),
        "neutral_pct":  round(totals["neutral"]  / total_w * 100, 1),
        "negative_pct": round(totals["negative"] / total_w * 100, 1),
    }


# ── 텍스트 가공 헬퍼 ──────────────────────────────────────────

def _sweet_length_priority(text: str) -> int:
    """길이가 sweet 범위면 0(최우선), 아니면 1(차순위)."""
    n = len(text or "")
    if SWEET_LEN_MIN <= n <= SWEET_LEN_MAX:
        return 0
    return 1


def _truncate(text: str, n: int = PROMPT_TEXT_MAX) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


# ── 보고서 ② 입력 집계 ───────────────────────────────────────

def aggregate_comment_report_inputs(
    video_id: str,
    product_name: str,
    video_title: str = "",
) -> Optional[Dict[str, Any]]:
    """
    보고서 ② 프롬프트 입력 dict 를 만든다.

    필터: agent_decisions.final_action='ANALYZE' 한 댓글만.
    반환: build_comment_analysis_prompt 가 기대하는 dict.
          ANALYZE 댓글 0건이면 None.
    """
    sentiment_rows = query_all(
        """
        SELECT cs.sentiment_label, cs.analysis_weight
        FROM comments c
        INNER JOIN agent_decisions   ad ON c.comment_id = ad.comment_id
        INNER JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
        WHERE c.video_id = %s AND ad.final_action = 'ANALYZE'
        """,
        (video_id,),
    )
    if not sentiment_rows:
        return None

    total = len(sentiment_rows)
    weighted = compute_weighted_ratio(sentiment_rows)

    top_rows = query_all(
        """
        SELECT ae.aspect_name, COUNT(*) AS cnt
        FROM aspect_extractions ae
        INNER JOIN agent_decisions ad ON ae.comment_id = ad.comment_id
        INNER JOIN comments         c ON ae.comment_id =  c.comment_id
        WHERE c.video_id = %s
          AND ad.final_action = 'ANALYZE'
          AND ae.aspect_name IS NOT NULL
          AND ae.aspect_name <> ''
        GROUP BY ae.aspect_name
        ORDER BY cnt DESC
        LIMIT 8
        """,
        (video_id,),
    )
    top_aspect_frequencies = [
        {"aspect_name": r["aspect_name"], "count": int(r["cnt"])} for r in top_rows
    ]

    pos_aspects = _aggregate_aspects_for_sentiment(video_id, "POSITIVE", TOP_K_ASPECTS_PER_SENTIMENT)
    neg_aspects = _aggregate_aspects_for_sentiment(video_id, "NEGATIVE", TOP_K_ASPECTS_PER_SENTIMENT)

    return {
        "product_name": product_name,
        "video_title": video_title,
        "total_analyzed_comments": total,
        "weighted_ratio": weighted,
        "positive_aspects": pos_aspects,
        "negative_aspects": neg_aspects,
        "top_aspect_frequencies": top_aspect_frequencies,
    }


def _aggregate_aspects_for_sentiment(
    video_id: str,
    aspect_sentiment: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    """
    한 sentiment 방향(POSITIVE / NEGATIVE)의 aspect_name 별 그룹 + 후보 댓글.

    aspect_extractions 는 한 댓글이 여러 aspect 를 가질 수 있으므로 댓글 중복은
    GROUP BY c.comment_id 로 제거한다.
    """
    aspect_rows = query_all(
        """
        SELECT ae.aspect_name, COUNT(DISTINCT ae.comment_id) AS cnt
        FROM aspect_extractions ae
        INNER JOIN agent_decisions ad ON ae.comment_id = ad.comment_id
        INNER JOIN comments         c ON ae.comment_id =  c.comment_id
        WHERE c.video_id = %s
          AND ad.final_action = 'ANALYZE'
          AND ae.aspect_sentiment = %s
          AND ae.aspect_name IS NOT NULL
          AND ae.aspect_name <> ''
        GROUP BY ae.aspect_name
        ORDER BY cnt DESC
        LIMIT %s
        """,
        (video_id, aspect_sentiment, top_k),
    )
    result: List[Dict[str, Any]] = []
    for ar in aspect_rows:
        aname = ar["aspect_name"]
        cnt = int(ar["cnt"])
        cand_rows = query_all(
            """
            SELECT c.comment_id, c.text_raw, c.like_count
            FROM aspect_extractions ae
            INNER JOIN comments         c ON ae.comment_id =  c.comment_id
            INNER JOIN agent_decisions ad ON ae.comment_id = ad.comment_id
            WHERE c.video_id = %s
              AND ad.final_action = 'ANALYZE'
              AND ae.aspect_name = %s
              AND ae.aspect_sentiment = %s
            GROUP BY c.comment_id, c.text_raw, c.like_count
            ORDER BY c.like_count DESC NULLS LAST
            LIMIT %s
            """,
            (video_id, aname, aspect_sentiment, CANDIDATE_PER_ASPECT * 2),
        )
        cand_sorted = sorted(
            cand_rows,
            key=lambda r: (
                _sweet_length_priority(r.get("text_raw") or ""),
                -(int(r.get("like_count") or 0)),
            ),
        )[:CANDIDATE_PER_ASPECT]
        candidates = [
            {
                "comment_id": r["comment_id"],
                "text_raw":   _truncate(r.get("text_raw") or ""),
                "like_count": int(r.get("like_count") or 0),
            }
            for r in cand_sorted
        ]
        result.append({
            "aspect_name": aname,
            "comment_count": cnt,
            "candidate_comments": candidates,
        })
    return result


# ── 보고서 ③ 입력 집계 ───────────────────────────────────────

# transcript 본문에서 aspect 언급 여부 판정용 동의어 사전.
# aspect_name 자체 + 흔히 함께 쓰이는 표현을 모은다.
ASPECT_KEYWORDS: Dict[str, List[str]] = {
    "배터리":      ["배터리", "지속", "충전", "방전", "mah", "wh"],
    "발열":        ["발열", "쓰로틀", "쓰로틀링", "뜨겁"],
    "성능":        ["성능", "프로세서", "칩", "벤치", "벤치마크", "ap",
                   "snapdragon", "exynos", "스냅드래곤", "엑시노스", "ram", "램"],
    "카메라":      ["카메라", "렌즈", "조리개", "화소", "촬영", "사진", "동영상", "줌", "셔터"],
    "디스플레이":  ["디스플레이", "화면", "밝기", "주사율", "해상도", "패널",
                   "nit", "니트", "hz", "amoled", "lcd", "oled"],
    "디자인":      ["디자인", "외관", "색상", "프레임", "티타늄", "알루미늄",
                   "그립", "무게", "두께", "마감", "재질"],
    "가격":        ["가격", "만원", "비싸", "가성비", "달러"],
    "휴대성":      ["휴대", "사이즈", "크기"],
    "소음":        ["소음", "팬 소리"],
    "내구성":      ["내구", "튼튼", "파손", "내수성", "방수"],
    "기능":        ["기능", "ai", "인공지능"],
}

# transcript 헤딩이 보고서 ①의 구조 헤딩이면 reviewer_only 후보에서 제외
SKELETON_HEADING_PATTERN = re.compile(
    r"^(장점|단점|장점\s*/\s*단점|장점/단점|전작 대비|핵심 포인트|구매 판정|"
    r"차별성|이런 사람|추천|리뷰어가 강조한|제품 핵심 인사이트 보고서|제품명|"
    r"수치 정보|기타 주요 언급|장점/강점|단점/아쉬운 점|전작 비교|"
    r"추천/비추 대상|이런 사람한테 맞습니다|이런 사람한테는 비추)"
)

# 헤딩에서 제거할 이모지/기호
HEADING_LEADING_TOKENS = "📦📊🔋📷📱⚡💰🔊🔗🎨🛒🌐🧩🕒🗺📋⚖🔥👥💡✅❌⬇▶📅😊😐😠"


def _normalize(text: str) -> str:
    return (text or "").lower()


def _transcript_mentions_aspect(transcript_text: str, aspect_name: str) -> bool:
    """aspect_name 또는 그 동의어 1개라도 transcript 에 등장하면 True."""
    t = _normalize(transcript_text)
    if not t or not aspect_name:
        return False
    if _normalize(aspect_name) in t:
        return True
    for kw in ASPECT_KEYWORDS.get(aspect_name, []):
        if _normalize(kw) in t:
            return True
    return False


def _is_covered_by_aspects(text: str, aspect_names: set) -> bool:
    """text 가 aspect_names 중 하나의 키워드 사전과 매칭되는지."""
    if not text:
        return False
    for aspect in aspect_names:
        if _transcript_mentions_aspect(text, aspect):
            return True
    return False


def _extract_reviewer_only_hints(transcript_md: str, covered_aspect_names: set) -> List[str]:
    """
    transcript_md 에서 reviewer_only_aspect_hints 후보를 추출.

    추출 소스:
      1) ## / ### / #### 헤딩 텍스트 (보고서 골격 헤딩은 제외)
      2) "핵심 포인트" 섹션의 bullet 첫 절(구두점 전)

    필터: covered_aspect_names 와 키워드 매칭되는 항목 제외, 50자 이하만, 최대 12개.
    """
    if not transcript_md:
        return []

    hints: List[str] = []
    seen: set = set()

    # 1) 헤딩
    for h in re.findall(r"^\s*#{2,4}\s+(.+)$", transcript_md, flags=re.MULTILINE):
        text = h.strip()
        # leading 이모지/마커 제거
        text = re.sub(f"^[{re.escape(HEADING_LEADING_TOKENS)}\\s]+", "", text)
        text = text.strip()
        if not text or len(text) > 50:
            continue
        if SKELETON_HEADING_PATTERN.search(text):
            continue
        if _is_covered_by_aspects(text, covered_aspect_names):
            continue
        if text in seen:
            continue
        hints.append(text)
        seen.add(text)
        if len(hints) >= 12:
            return hints

    # 2) 핵심 포인트 / 차별성 섹션 bullet
    section_blocks = re.findall(
        r"###\s*[^\n]*(?:핵심 포인트|차별성)[^\n]*\n((?:.*\n)+?)(?=\n*(?:---|###|##|\Z))",
        transcript_md,
    )
    for section in section_blocks:
        for line in section.split("\n"):
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^\d+\.\s*", "", line)
            line = re.sub(r"^[\-\*·]\s*", "", line)
            line = re.split(r"[—·,()]", line, maxsplit=1)[0].strip()
            if not line or len(line) > 40:
                continue
            if SKELETON_HEADING_PATTERN.search(line):
                continue
            if _is_covered_by_aspects(line, covered_aspect_names):
                continue
            if line in seen:
                continue
            hints.append(line)
            seen.add(line)
            if len(hints) >= 12:
                return hints
    return hints


def aggregate_comparison_inputs(
    video_id: str,
    product_name: str,
    transcript_text: str,
) -> Optional[Dict[str, Any]]:
    """
    보고서 ③ 프롬프트 입력 dict (aspect_summary).

    transcript_text 는 자막 원문이 아니라 보고서 ①(video_reports.transcript_report,
    마크다운 텍스트) 을 사용한다. 호출부가 ①을 확보한 뒤 넘긴다.
    """
    rows = query_all(
        """
        SELECT
            ae.aspect_name,
            ae.aspect_sentiment,
            COUNT(DISTINCT ae.comment_id) AS cnt
        FROM aspect_extractions ae
        INNER JOIN comments         c ON ae.comment_id =  c.comment_id
        INNER JOIN agent_decisions ad ON ae.comment_id = ad.comment_id
        WHERE c.video_id = %s
          AND ad.final_action = 'ANALYZE'
          AND ae.aspect_name IS NOT NULL AND ae.aspect_name <> ''
          AND ae.aspect_sentiment IS NOT NULL
        GROUP BY ae.aspect_name, ae.aspect_sentiment
        """,
        (video_id,),
    )
    if not rows:
        return None

    # aspect_name -> {POSITIVE, NEGATIVE, NEUTRAL: count}
    aspect_counts: Dict[str, Dict[str, int]] = {}
    for r in rows:
        a = r["aspect_name"]
        s = r["aspect_sentiment"]
        aspect_counts.setdefault(a, {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0})
        if s in aspect_counts[a]:
            aspect_counts[a][s] = int(r["cnt"])

    common_aspects: List[Dict[str, Any]] = []
    consumer_only_aspects: List[str] = []

    for aname, counts in aspect_counts.items():
        total = counts["POSITIVE"] + counts["NEGATIVE"] + counts["NEUTRAL"]
        if total == 0:
            continue

        mentioned = _transcript_mentions_aspect(transcript_text, aname)
        if not mentioned:
            consumer_only_aspects.append(aname)
            continue

        # dominant sentiment 결정 (POSITIVE > NEGATIVE > NEUTRAL 동률시 위)
        if counts["POSITIVE"] >= counts["NEGATIVE"] and counts["POSITIVE"] >= counts["NEUTRAL"]:
            dominant = "POSITIVE"
        elif counts["NEGATIVE"] >= counts["POSITIVE"] and counts["NEGATIVE"] >= counts["NEUTRAL"]:
            dominant = "NEGATIVE"
        else:
            dominant = "NEUTRAL"

        # 대표 후보: dominant sentiment 쪽 댓글, 단 NEUTRAL 이면 후보 댓글이 빈약하므로
        # POSITIVE/NEGATIVE 중 더 많은 쪽으로 fallback
        fetch_sent = dominant
        if dominant == "NEUTRAL":
            fetch_sent = "POSITIVE" if counts["POSITIVE"] >= counts["NEGATIVE"] else "NEGATIVE"

        cand_rows = query_all(
            """
            SELECT c.comment_id, c.text_raw, c.like_count
            FROM aspect_extractions ae
            INNER JOIN comments         c ON ae.comment_id =  c.comment_id
            INNER JOIN agent_decisions ad ON ae.comment_id = ad.comment_id
            WHERE c.video_id = %s
              AND ad.final_action = 'ANALYZE'
              AND ae.aspect_name = %s
              AND ae.aspect_sentiment = %s
            GROUP BY c.comment_id, c.text_raw, c.like_count
            ORDER BY c.like_count DESC NULLS LAST
            LIMIT %s
            """,
            (video_id, aname, fetch_sent, CANDIDATE_PER_ASPECT * 2),
        )
        cand_sorted = sorted(
            cand_rows,
            key=lambda r: (
                _sweet_length_priority(r.get("text_raw") or ""),
                -(int(r.get("like_count") or 0)),
            ),
        )[:CANDIDATE_PER_ASPECT]
        candidates = [
            {
                "comment_id": r["comment_id"],
                "text_raw":   _truncate(r.get("text_raw") or ""),
                "like_count": int(r.get("like_count") or 0),
            }
            for r in cand_sorted
        ]
        common_aspects.append({
            "aspect_name": aname,
            "consumer_dominant_sentiment": dominant,
            "consumer_positive_count": counts["POSITIVE"],
            "consumer_negative_count": counts["NEGATIVE"],
            "consumer_neutral_count":  counts["NEUTRAL"],
            "candidate_comments": candidates,
        })

    # 프롬프트 비용 보호: common_aspects 상위 10개, consumer_only_aspects 상위 10개
    common_aspects.sort(
        key=lambda x: -(x["consumer_positive_count"] + x["consumer_negative_count"])
    )
    common_aspects = common_aspects[:10]
    consumer_only_aspects = consumer_only_aspects[:10]

    reviewer_only_hints = _extract_reviewer_only_hints(transcript_text, set(aspect_counts.keys()))

    return {
        "product_name": product_name,
        "common_aspects": common_aspects,
        "reviewer_only_aspect_hints": reviewer_only_hints,
        "consumer_only_aspects": consumer_only_aspects,
    }


# ── 댓글 원문 첨부 (LLM 응답 후처리) ───────────────────────────

def fetch_comment_texts(comment_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """comment_id 리스트 → {comment_id: {text_raw, like_count, author_name}} 매핑.

    text_raw 는 원문 그대로 반환 (truncate 하지 않음). 화면 노출 시 line-clamp 처리.
    """
    if not comment_ids:
        return {}
    unique_ids = list(dict.fromkeys(comment_ids))  # 순서 유지, 중복 제거
    placeholders = ",".join(["%s"] * len(unique_ids))
    rows = query_all(
        f"""
        SELECT comment_id, text_raw, like_count, author_name
        FROM comments
        WHERE comment_id IN ({placeholders})
        """,
        tuple(unique_ids),
    )
    return {
        r["comment_id"]: {
            "text_raw":    r.get("text_raw") or "",
            "like_count":  int(r.get("like_count") or 0),
            "author_name": r.get("author_name") or "",
        }
        for r in rows
    }


def attach_comment_texts(data: Dict[str, Any], id_paths: List[tuple]) -> Dict[str, Any]:
    """
    data 안의 ID 리스트들에 원문을 첨부한다 (in-place).

    id_paths: [(parent_key, id_field_key, attach_target_key), ...]
      예: [("positive_points", "representative_comment_ids", "representative_comments")]
      → data["positive_points"][i]["representative_comments"] = [{comment_id, text_raw, like_count, author_name}, ...]
    """
    all_ids: List[str] = []
    for parent, idkey, _ in id_paths:
        for item in data.get(parent, []):
            for cid in (item.get(idkey) or []):
                if cid:
                    all_ids.append(cid)
    text_map = fetch_comment_texts(all_ids)

    for parent, idkey, attach in id_paths:
        for item in data.get(parent, []):
            comments: List[Dict[str, Any]] = []
            for cid in (item.get(idkey) or []):
                if cid in text_map:
                    comments.append({"comment_id": cid, **text_map[cid]})
            item[attach] = comments
    return data


# ── JSON 스키마 검증 ──────────────────────────────────────────

REQUIRED_REPORT2_TOP_KEYS = ("sentiment_summary", "positive_points", "negative_points", "top_issues")
REQUIRED_REPORT2_SENT_KEYS = ("positive_pct", "neutral_pct", "negative_pct", "one_line_mood")
REQUIRED_REPORT2_POINT_KEYS = ("aspect_name", "summary_line", "comment_count", "representative_comment_ids")

REQUIRED_REPORT3_TOP_KEYS = ("agreement_points", "disagreement_points", "reviewer_only", "consumer_only", "verdict")
REQUIRED_REPORT3_POINT_KEYS = ("topic", "reviewer_quote", "consumer_comment_ids")
REQUIRED_REPORT3_VERDICT_KEYS = ("trust_score", "summary")


def validate_report2_json(data: Any) -> bool:
    """보고서 ② JSON 의 필수 키 존재 + 약식 타입 검증."""
    if not isinstance(data, dict):
        return False
    if not all(k in data for k in REQUIRED_REPORT2_TOP_KEYS):
        return False
    if not isinstance(data["sentiment_summary"], dict):
        return False
    if not all(k in data["sentiment_summary"] for k in REQUIRED_REPORT2_SENT_KEYS):
        return False
    for grp in ("positive_points", "negative_points"):
        if not isinstance(data[grp], list):
            return False
        for item in data[grp]:
            if not isinstance(item, dict):
                return False
            if not all(k in item for k in REQUIRED_REPORT2_POINT_KEYS):
                return False
            if not isinstance(item["representative_comment_ids"], list):
                return False
    if not isinstance(data["top_issues"], list):
        return False
    return True


def validate_report3_json(data: Any) -> bool:
    """보고서 ③ JSON 의 필수 키 존재 + 약식 타입 검증."""
    if not isinstance(data, dict):
        return False
    if not all(k in data for k in REQUIRED_REPORT3_TOP_KEYS):
        return False
    for grp in ("agreement_points", "disagreement_points"):
        if not isinstance(data[grp], list):
            return False
        for item in data[grp]:
            if not isinstance(item, dict):
                return False
            if not all(k in item for k in REQUIRED_REPORT3_POINT_KEYS):
                return False
            if not isinstance(item["consumer_comment_ids"], list):
                return False
    for grp in ("reviewer_only", "consumer_only"):
        if not isinstance(data[grp], list):
            return False
    if not isinstance(data["verdict"], dict):
        return False
    if not all(k in data["verdict"] for k in REQUIRED_REPORT3_VERDICT_KEYS):
        return False
    return True
