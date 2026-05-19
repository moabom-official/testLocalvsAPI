"""보고서 ④ 입력 수집 파이프라인 (Phase 2-a — 영상별 ①②③ 종합).

목적: ④ 가 영상 N개의 보고서 ①(자막)·②(댓글)·③(통합) 을 모두 종합하도록
입력을 확장한다. RAG 아님 — raw 자막/댓글 안 넣음. ⑤용 댓글 집계
(consumer_aggregate)는 호출부가 기존대로 별도 유지한다.

★ 노드 친화 설계 (Phase 2-b·Phase 4 대비):
  단계가 독립 순수 함수로 분리돼 있다. 부수효과(DB 읽기)는 collect 단계에만
  모이고, serialize/truncate/assemble 은 순수 변환이다. 특히 truncate 단계는
  Phase 2-b 에서 벡터DB 검색(RAG)으로 통째 교체될 자리이므로 독립 함수다.

  collect_report_bundles  : (DB READ) video_reports 에서 영상별 ①②③ 수집
  serialize_report2/3     : (순수) ②③ JSON → ④가 읽기 좋은 텍스트 (충실 변환)
  truncate_bundles        : (순수) 길이 관리 — ★ 2-b 가 교체할 단계
  assemble_input_blocks   : (순수) 영상별 ①②③ 블록 텍스트 조립
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from scripts.database.queries import query_all

# ── 길이 관리 상수 (근거: §4-3) ──────────────────────────────────
# 영상당 입력이 보고서 1개(①) → 3개(①②③) 로 늘었다. 일반 영상 수(5~10)면
# ①②③ 만으로 LLM 컨텍스트 한도 안에 들어오므로 절삭은 "느슨하게" 가져가되,
# 영상 수 폭증 대비 상한 개념은 유지한다(무한정 입력 금지). 어떤 보고서도
# 0 으로 잘리지 않게 한다.
R1_MAX_CHARS = 2200      # ① 자막 기반(마크다운) — 기존 1500 보다 상향(②③ 추가분 감안 후 ① 정보 보존)
R2_MAX_CHARS = 1400      # ② 댓글 기반(직렬화 텍스트)
R3_MAX_CHARS = 1600      # ③ 자막+댓글 통합(직렬화 텍스트)
# 전체 입력 상한 — 3종 × 다영상 누적 대비 상향(기존 21000). 초과 시 영상별
# 비례 축소(보고서 종류별 최소 바닥은 유지).
TOTAL_INPUT_MAX_CHARS = 60000
_MIN_FLOOR = 300         # 비례 축소 시에도 보고서별 최소 보존 길이(0 방지)

_TRUNC_MARK = "\n... (이하 생략)"


def _clip(text: str, cap: int) -> Tuple[str, int]:
    """text 를 cap 이내로 자르고 (잘린문자열, 잘려나간 길이) 반환.

    결과 길이는 절삭 표식 포함해 cap 을 넘지 않는다(총합 상한이 실제로
    지켜지도록 — §4-3 "상한 개념 유지").
    """
    text = text or ""
    if len(text) <= cap:
        return text, 0
    body_cap = max(0, cap - len(_TRUNC_MARK))
    clipped = text[:body_cap].rstrip() + _TRUNC_MARK
    return clipped, len(text) - len(clipped)


# ── 1) 수집 (DB READ ONLY) ───────────────────────────────────────

def collect_report_bundles(
    video_ids: List[str],
    video_meta: Dict[str, Dict[str, Any]],
    safe_json_loads,
) -> List[Dict[str, Any]]:
    """video_reports 에서 영상별 ①②③ 을 READ ONLY 로 모은다.

    self-healing 이 이미 ①②③ 을 보장했다는 전제(없으면 그 영상은 가능한
    보고서만 — 안전 퇴화). 입력 순서·video_id·제목 보존.
    반환 원소: {video_id, title, transcript_report(str|None),
                comment_report(dict|None), integrated_report(dict|None)}
    """
    if not video_ids:
        return []
    placeholders = ",".join(["%s"] * len(video_ids))
    rows = query_all(
        f"SELECT video_id, transcript_report, comment_report, integrated_report "
        f"FROM video_reports WHERE video_id IN ({placeholders})",
        tuple(video_ids),
    )
    by_id = {r["video_id"]: r for r in rows}
    bundles: List[Dict[str, Any]] = []
    for vid in video_ids:
        row = by_id.get(vid)
        if not row:
            continue
        tr = row.get("transcript_report")
        if isinstance(tr, str) and (
            not tr.strip()
            or tr.startswith("[ERROR]")
            or tr == "No transcript content available."
        ):
            tr = None
        if not tr:
            # ① 이 없으면 ④ 가 그 영상을 종합할 근거가 사실상 없음 → 제외
            continue
        bundles.append({
            "video_id": vid,
            "title": (video_meta.get(vid, {}) or {}).get("title") or "",
            "transcript_report": tr,
            "comment_report": safe_json_loads(row.get("comment_report")),
            "integrated_report": safe_json_loads(row.get("integrated_report")),
        })
    return bundles


# ── 2) ②③(JSON) → ④ 입력 텍스트 (순수, 충실 변환) ───────────────

def _fmt_points(points: List[Dict[str, Any]], limit: int = 6) -> List[str]:
    out = []
    for p in (points or [])[:limit]:
        name = str(p.get("aspect_name", "")).strip()
        line = str(p.get("summary_line", "")).strip()
        cnt = p.get("comment_count")
        seg = f"- {name}: {line}" if line else f"- {name}"
        if cnt is not None:
            seg += f" (언급 {cnt})"
        out.append(seg)
    return out


def serialize_report2(cr: Optional[Dict[str, Any]]) -> str:
    """보고서 ②(댓글 기반 dict) → 텍스트. 값을 충실히 옮김(재계산·창작 금지)."""
    if not isinstance(cr, dict):
        return ""
    lines: List[str] = []
    ss = cr.get("sentiment_summary") or {}
    if ss:
        lines.append(
            f"감성 요약: 긍정 {ss.get('positive_pct','?')}% / 중립 "
            f"{ss.get('neutral_pct','?')}% / 부정 {ss.get('negative_pct','?')}%"
            + (f" — {ss.get('one_line_mood','').strip()}" if ss.get("one_line_mood") else "")
        )
    pos = _fmt_points(cr.get("positive_points"))
    if pos:
        lines.append("긍정 포인트:")
        lines += pos
    neg = _fmt_points(cr.get("negative_points"))
    if neg:
        lines.append("부정 포인트:")
        lines += neg
    issues = cr.get("top_issues") or []
    if issues:
        kw = ", ".join(
            f"{str(i.get('keyword','')).strip()}({i.get('count','?')})"
            for i in issues[:8] if isinstance(i, dict)
        )
        if kw:
            lines.append(f"핵심 이슈: {kw}")
    return "\n".join(lines).strip()


def _fmt_cmp(items: List[Dict[str, Any]], limit: int = 6) -> List[str]:
    out = []
    for it in (items or [])[:limit]:
        topic = str(it.get("topic", "")).strip()
        rq = str(it.get("reviewer_quote", "")).strip()
        seg = f"- {topic}"
        if it.get("gap_type"):
            seg += f" [{it.get('gap_type')}]"
        if rq:
            seg += f' — 리뷰어: "{rq[:120]}"'
        out.append(seg)
    return out


def serialize_report3(ir: Optional[Dict[str, Any]]) -> str:
    """보고서 ③(자막+댓글 통합 dict) → 텍스트. 값을 충실히 옮김."""
    if not isinstance(ir, dict):
        return ""
    lines: List[str] = []
    v = ir.get("verdict") or {}
    if v:
        lines.append(
            f"판정: 신뢰도 {v.get('trust_score','?')} — "
            f"{str(v.get('summary','')).strip()}"
        )
    ag = _fmt_cmp(ir.get("agreement_points"))
    if ag:
        lines.append("리뷰어↔소비자 일치:")
        lines += ag
    dg = _fmt_cmp(ir.get("disagreement_points"))
    if dg:
        lines.append("리뷰어↔소비자 불일치:")
        lines += dg
    sc = ir.get("spec_changes") or []
    if sc:
        lines.append("전작 대비 스펙 변화:")
        for s in sc[:6]:
            if isinstance(s, dict):
                lines.append(
                    f"- {s.get('spec_name','')}: {s.get('before','')} → "
                    f"{s.get('after','')} ({s.get('delta','')})"
                )
    ro = [str(x).strip() for x in (ir.get("reviewer_only") or [])[:6] if str(x).strip()]
    co = [str(x).strip() for x in (ir.get("consumer_only") or [])[:6] if str(x).strip()]
    if ro:
        lines.append("리뷰어만 언급: " + ", ".join(ro))
    if co:
        lines.append("소비자만 언급: " + ", ".join(co))
    return "\n".join(lines).strip()


# ── 3) 길이 관리 (순수) — ★ Phase 2-b 가 교체할 단계 ─────────────

def truncate_bundles(
    bundles: List[Dict[str, Any]],
    *,
    r1_cap: int = R1_MAX_CHARS,
    r2_cap: int = R2_MAX_CHARS,
    r3_cap: int = R3_MAX_CHARS,
    total_cap: int = TOTAL_INPUT_MAX_CHARS,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """영상별 ①/②/③ 텍스트를 보고서별 상한으로 절삭, 총합 초과 시 비례 축소.

    ★ 이 함수가 Phase 2-b 에서 RAG 검색으로 교체된다(독립 단계). 어떤 보고서도
    0 으로 잘리지 않게 한다(_MIN_FLOOR). 반환: (절삭본, 측정치).
    입력 bundle 은 transcript_report(str) + comment_text(str) + integrated_text(str)
    를 가진다고 가정(serialize 단계가 채움).
    """
    out: List[Dict[str, Any]] = []
    cut_total = {"r1": 0, "r2": 0, "r3": 0}
    for b in bundles:
        t1, c1 = _clip(b.get("transcript_report") or "", r1_cap)
        t2, c2 = _clip(b.get("comment_text") or "", r2_cap)
        t3, c3 = _clip(b.get("integrated_text") or "", r3_cap)
        cut_total["r1"] += c1
        cut_total["r2"] += c2
        cut_total["r3"] += c3
        out.append({**b, "transcript_report": t1, "comment_text": t2,
                    "integrated_text": t3})

    def _sum(items):
        return sum(
            len(x.get("transcript_report") or "")
            + len(x.get("comment_text") or "")
            + len(x.get("integrated_text") or "")
            for x in items
        )

    total = _sum(out)
    shrunk_applied = False
    if total > total_cap and out:
        shrunk_applied = True
        # 영상별 통합 상한을 비례 축소(보고서별 최소 바닥 유지)
        per_video_cap = max(
            _MIN_FLOOR * 3, total_cap // max(1, len(out))
        )
        # 보고서 종류별 비중(① > ③ > ②) 유지하며 분배
        share = {"transcript_report": 0.45, "integrated_text": 0.33,
                 "comment_text": 0.22}
        re_out: List[Dict[str, Any]] = []
        for x in out:
            nx = dict(x)
            for key, frac in share.items():
                cap = max(_MIN_FLOOR, int(per_video_cap * frac))
                clipped, c = _clip(nx.get(key) or "", cap)
                nx[key] = clipped
            re_out.append(nx)
        out = re_out

    measure = {
        "cut_chars": cut_total,
        "proportional_shrink": shrunk_applied,
        "total_chars_after": _sum(out),
        "total_cap": total_cap,
    }
    return out, measure


# ── 4) 프롬프트 입력 블록 조립 (순수) ────────────────────────────

def assemble_input_blocks(bundles: List[Dict[str, Any]]) -> str:
    """영상별로 ①②③ 을 한 블록에 묶어 ④ 프롬프트 입력 텍스트로 조립.

    영상 경계·video_id·제목 보존(④ '영상 N 출처 표기' 규칙). 없는 보고서는
    그 항목만 비우고 진행(안전 퇴화).
    """
    blocks: List[str] = []
    for i, b in enumerate(bundles):
        title = (b.get("title") or "").strip()
        head = f"[영상 {i+1} | video_id={b.get('video_id','')} | 제목: {title}]"
        seg = [head, "〈① 자막 기반 보고서〉", (b.get("transcript_report") or "(없음)").strip()]
        ct = (b.get("comment_text") or "").strip()
        seg += ["〈② 댓글 기반 분석〉", ct if ct else "(없음)"]
        it = (b.get("integrated_text") or "").strip()
        seg += ["〈③ 자막+댓글 통합 분석〉", it if it else "(없음)"]
        blocks.append("\n".join(seg))
    return "\n\n".join(blocks)


def serialize_bundles(bundles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """collect → (serialize) 사이 단계: ②③ dict 를 텍스트로 변환해 bundle 에 부착.

    순수 변환. comment_report/integrated_report dict 는 보존, 텍스트 키 추가.
    """
    out = []
    for b in bundles:
        out.append({
            **b,
            "comment_text": serialize_report2(b.get("comment_report")),
            "integrated_text": serialize_report3(b.get("integrated_report")),
        })
    return out
