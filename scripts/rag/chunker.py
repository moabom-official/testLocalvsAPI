"""①②③ 구조 보존 청킹 (순수 — 무거운 import 없음, 오프라인 안전).

①②③ 은 이미 LLM 이 정제·구조화한 산출물이라 단순 N자 절단은 구조를 깬다.
의미 단위(섹션/항목)로 청크를 만들고 검색·재구성용 메타데이터를 붙인다.
부수효과 없음 — Phase 4 가 노드로 흡수 가능.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

# 청크 길이 가이드 (상수 — 근거: ①②③ 항목 평균 길이 + LLM 컨텍스트 효율)
_MAX_CHUNK_CHARS = 900
_MIN_CHUNK_CHARS = 60        # 이보다 짧으면 인접 청크와 병합 시도


def _content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()


def _chunk_id(product_key: str, video_id: str, source: str, idx: int,
              text: str) -> str:
    raw = f"{product_key}|{video_id}|{source}|{idx}|{_content_hash(text)}"
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()


def _split_long(text: str, cap: int = _MAX_CHUNK_CHARS) -> List[str]:
    """의미 경계를 넘는 긴 텍스트를 문장/공백 우선으로 보조 분할."""
    text = text.strip()
    if len(text) <= cap:
        return [text] if text else []
    parts: List[str] = []
    buf = ""
    for sent in re.split(r"(?<=[.!?。\n])\s+", text):
        if not sent:
            continue
        if len(buf) + len(sent) + 1 > cap and buf:
            parts.append(buf.strip())
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf.strip():
        parts.append(buf.strip())
    return parts or [text[:cap]]


def _merge_tiny(units: List[str]) -> List[str]:
    """너무 짧은 단위를 인접 단위와 병합(의미 경계 우선 유지)."""
    out: List[str] = []
    for u in units:
        u = (u or "").strip()
        if not u:
            continue
        if out and len(u) < _MIN_CHUNK_CHARS:
            if len(out[-1]) + len(u) + 1 <= _MAX_CHUNK_CHARS:
                out[-1] = f"{out[-1]}\n{u}"
                continue
        out.append(u)
    return out


# ── ① 마크다운: 헤더/리스트 항목 경계 ────────────────────────────

def _chunk_report1_md(md: str) -> List[Dict[str, str]]:
    """(text, semantic_tag) 단위 리스트. ## / ### 헤더와 불릿이 자연 경계."""
    if not md or not md.strip():
        return []
    lines = md.splitlines()
    sections: List[Dict[str, Any]] = []
    cur_tag = "개요"
    cur: List[str] = []

    def _flush():
        if cur:
            body = "\n".join(cur).strip()
            if body:
                sections.append({"tag": cur_tag, "text": body})

    _TAG_MAP = [
        ("장점", "장점"), ("단점", "단점"), ("전작", "전작비교"),
        ("비교", "전작비교"), ("평가", "평가차원"), ("점수", "평가차원"),
        ("추천", "추천"), ("결론", "종합판정"), ("총평", "종합판정"),
    ]
    for ln in lines:
        h = re.match(r"^\s{0,3}#{1,4}\s+(.*)$", ln)
        if h:
            _flush()
            cur = []
            title = h.group(1).strip()
            cur_tag = "개요"
            for kw, tag in _TAG_MAP:
                if kw in title:
                    cur_tag = tag
                    break
            cur.append(ln.strip())
        else:
            cur.append(ln)
    _flush()

    chunks: List[Dict[str, str]] = []
    for sec in sections:
        for piece in _split_long(sec["text"]):
            chunks.append({"text": piece, "semantic_tag": sec["tag"]})
    # 텍스트만 기준으로 tiny 병합(같은 tag 끼리만 자연 인접)
    return _merge_chunk_dicts(chunks)


def _merge_chunk_dicts(chunks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for c in chunks:
        t = (c.get("text") or "").strip()
        if not t:
            continue
        if (out and len(t) < _MIN_CHUNK_CHARS
                and out[-1]["semantic_tag"] == c["semantic_tag"]
                and len(out[-1]["text"]) + len(t) + 1 <= _MAX_CHUNK_CHARS):
            out[-1]["text"] = f"{out[-1]['text']}\n{t}"
            continue
        out.append({"text": t, "semantic_tag": c.get("semantic_tag", "개요")})
    return out


# ── ② dict: 포인트/이슈 항목 단위 ────────────────────────────────

def _chunk_report2(cr: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not isinstance(cr, dict):
        return []
    chunks: List[Dict[str, str]] = []
    ss = cr.get("sentiment_summary") or {}
    if ss:
        chunks.append({
            "text": "댓글 감성 요약: " + "; ".join(
                f"{k}={v}" for k, v in ss.items() if v not in (None, "")),
            "semantic_tag": "소비자여론",
        })
    for key, tag in (("positive_points", "장점"),
                     ("negative_points", "단점")):
        for p in (cr.get(key) or []):
            if not isinstance(p, dict):
                continue
            name = str(p.get("aspect_name", "")).strip()
            line = str(p.get("summary_line", "")).strip()
            cnt = p.get("comment_count")
            txt = f"[{tag}] {name}: {line}"
            if cnt is not None:
                txt += f" (언급 {cnt})"
            chunks.append({"text": txt.strip(), "semantic_tag": tag})
    iss = cr.get("top_issues") or []
    if iss:
        kw = ", ".join(
            f"{str(i.get('keyword','')).strip()}({i.get('count','?')})"
            for i in iss if isinstance(i, dict))
        if kw:
            chunks.append({"text": f"핵심 이슈: {kw}",
                           "semantic_tag": "소비자여론"})
    return _merge_chunk_dicts(chunks)


# ── ③ dict: 합의/불일치/스펙변화/판정 항목 단위 ──────────────────

def _chunk_report3(ir: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not isinstance(ir, dict):
        return []
    chunks: List[Dict[str, str]] = []
    v = ir.get("verdict") or {}
    if v:
        chunks.append({
            "text": f"종합 판정: 신뢰도 {v.get('trust_score','?')} — "
                    f"{str(v.get('summary','')).strip()}",
            "semantic_tag": "종합판정",
        })
    for key, tag in (("agreement_points", "합의점"),
                     ("disagreement_points", "불일치")):
        for it in (ir.get(key) or []):
            if not isinstance(it, dict):
                continue
            topic = str(it.get("topic", "")).strip()
            rq = str(it.get("reviewer_quote", "")).strip()
            seg = f"[{tag}] {topic}"
            if it.get("gap_type"):
                seg += f" ({it.get('gap_type')})"
            if rq:
                seg += f' — 리뷰어: "{rq[:160]}"'
            chunks.append({"text": seg, "semantic_tag": tag})
    for s in (ir.get("spec_changes") or []):
        if isinstance(s, dict):
            chunks.append({
                "text": f"[스펙변화] {s.get('spec_name','')}: "
                        f"{s.get('before','')} → {s.get('after','')} "
                        f"({s.get('delta','')})",
                "semantic_tag": "스펙변화",
            })
    ro = [str(x).strip() for x in (ir.get("reviewer_only") or []) if str(x).strip()]
    co = [str(x).strip() for x in (ir.get("consumer_only") or []) if str(x).strip()]
    if ro:
        chunks.append({"text": "리뷰어만 언급: " + ", ".join(ro),
                       "semantic_tag": "불일치"})
    if co:
        chunks.append({"text": "소비자만 언급: " + ", ".join(co),
                       "semantic_tag": "소비자여론"})
    return _merge_chunk_dicts(chunks)


def chunk_bundle(
    bundle: Dict[str, Any],
    product_key: str,
) -> List[Dict[str, Any]]:
    """한 영상 bundle 의 ①②③ 을 구조 보존 청크 레코드 리스트로.

    레코드: {chunk_id, product_key, video_id, source, semantic_tag,
             chunk_idx, text, content_hash}
    """
    vid = bundle.get("video_id", "")
    recs: List[Dict[str, Any]] = []
    plans = [
        ("report_1", _chunk_report1_md(bundle.get("transcript_report") or "")),
        ("report_2", _chunk_report2(bundle.get("comment_report"))),
        ("report_3", _chunk_report3(bundle.get("integrated_report"))),
    ]
    for source, chs in plans:
        for idx, c in enumerate(chs):
            text = (c.get("text") or "").strip()
            if not text:
                continue
            recs.append({
                "chunk_id": _chunk_id(product_key, vid, source, idx, text),
                "product_key": product_key,
                "video_id": vid,
                "source": source,
                "semantic_tag": c.get("semantic_tag", "개요"),
                "chunk_idx": idx,
                "text": text,
                "content_hash": _content_hash(text),
            })
    return recs
