"""
Centralized prompt definitions for LLM calls.

활성 프롬프트:
- build_product_integrated_insight_prompt: 보고서 ④ 제품 단위 9 섹션 통합 보고서
- build_comment_analysis_prompt:           보고서 ② 댓글 기반 소비자 여론 보고서 (JSON 응답)
- build_comparison_report_prompt:          보고서 ③ 리뷰어 vs 소비자 비교 보고서 (JSON 응답)

② / ③ 프롬프트는 댓글 원문을 LLM이 생성하지 못하도록 representative_comment_ids 만
지목하게 한다. 실제 원문은 백엔드가 ID로 comments.text_raw 를 다시 조회해 첨부 →
환각 0% 보장.
"""

from __future__ import annotations

import json


def build_transcript_report_prompt(transcript_text: str) -> str:
    """Build the prompt used for transcript-based product review reports using Llama."""
    return f"""
당신은 제품 리뷰 분석 전문가입니다. 다음 유튜브 영상 자막을 분석하여 전문적인 보고서를 작성해주세요.

📋 영상 자막
================
{transcript_text}

📊 분석 요청
================
위 자막을 기반으로 다음 항목을 포함한 상세 분석 보고서를 작성해주세요:

1. **제품 설명 및 특징**
   - 자막에서 언급된 제품의 주요 특징과 사양
   - 기술적 사양이나 디자인 요소

2. **리뷰어의 긍정 평가**
   - 리뷰어가 칭찬하는 부분
   - 제품의 강점으로 평가되는 항목들

3. **리뷰어의 부정 평가 및 우려사항**
   - 지적된 문제점이나 단점
   - 개선이 필요한 영역

4. **시장 평가 및 추천도**
   - 전반적인 제품 평가
   - 구매/추천 여부

5. **핵심 키워드**
   - 자막에서 반복되는 주요 개념 3~5개

✅ 작성 가이드:
- 한국어로 전문적이고 객관적인 톤 유지
- 자막의 실제 내용을 근거로 작성
- 본문은 1000자 이내로 작성 (공백 포함)
- 명확한 구조로 읽기 쉽게 작성
- 문장은 중간에 끊기지 않게 완결형으로 마무리
- 마지막 줄에 반드시 [END]만 단독으로 출력

보고서를 작성해주세요.
"""


def build_product_integrated_insight_prompt(
    product_name: str,
    per_video_reports: list,
    today_str: str = "",
) -> str:
    """
    제품 단위 통합 인사이트 보고서 프롬프트.

    per_video_reports: [{"video_id": str, "title": str, "transcript_report": str}, ...]

    환각 방지를 위해 절대 규칙을 강하게 명시한다 — 입력 보고서에 등장하지 않은
    사실/수치/사양/가격/비교 제품/출시일/리뷰어 이름을 만들어 내지 못하도록 한다.
    """
    joined_blocks = []
    for i, r in enumerate(per_video_reports):
        title = (r.get("title") or "").strip()
        body = (r.get("transcript_report") or "").strip()
        joined_blocks.append(
            f"[영상 {i+1} | video_id={r.get('video_id','')} | 제목: {title}]\n{body}"
        )
    joined = "\n\n".join(joined_blocks)
    n = len(per_video_reports)
    today_line = f"보고서 생성일: {today_str}" if today_str else "보고서 생성일: (오늘 날짜)"

    return f"""당신은 테크 제품 리뷰 메타분석 전문가입니다.

아래는 동일 제품 "{product_name}"에 대한 서로 다른 유튜브 리뷰 영상 {n}건의
"자막 기반 분석 보고서"입니다. 이 보고서들만을 유일한 근거로 사용하여,
제품 단위 통합 인사이트 보고서를 작성하세요.

================ 절대 규칙 (위반 시 작성 실패로 간주) ================
1. 아래 영상별 보고서에 등장하지 않은 사실, 수치, 사양, 가격, 비교 제품, 출시일,
   리뷰어 이름 등을 새로 만들어 내지 않는다.
2. 어떤 차원/항목에 대해 입력 보고서에 정보가 없으면 반드시 "데이터 부족"으로 표기한다.
   추정, 일반 상식, 사전 지식으로 빈칸을 채우지 않는다.
3. 점수, 합의도, 빈도수는 입력 보고서에 등장한 표현을 근거로만 산출한다.
   계산 근거가 없으면 "데이터 부족".
4. 인용 시 어느 영상(영상 N)에서 나온 의견인지 표기한다.

================ 입력: 영상별 자막 기반 보고서 ================
{joined}

================ 출력 형식 (마크다운, 9개 섹션 + 메타 박스) ================
## ① 한줄 구매 판정 + 종합 점수
- 한 문장 결론
- 종합 평가: X.X / 10  (분석 영상 {n}개 기반)
- 리뷰어 합의도: 높음 / 중간 / 낮음

## ② 핵심 요약 (3~5문장)

## ③ 6차원 종합 평가
| 차원 | 점수 | 커버리지 | 리뷰어 합의 | 핵심 코멘트 |
| --- | --- | --- | --- | --- |
| 배터리 | ... | N/{n} 영상 | ... | ... |
| 가격 | ... | ... | ... | ... |
| 카메라 | ... | ... | ... | ... |
| 성능 | ... | ... | ... | ... |
| 디스플레이 | ... | ... | ... | ... |
| 디자인 | ... | ... | ... | ... |
- 1개 영상에서만 언급된 차원은 점수 대신 "데이터 부족"으로 표기

## ④ 장점 / 단점 (합의 기반)
- 2명 이상 영상에서 언급된 항목만 합의 항목으로 채택, 빈도수(N/{n})를 함께 표기
- 1명만 언급한 항목은 별도 "개별 리뷰어 의견"으로 분리

## ⑤ 리뷰어 간 의견이 갈리는 지점 (Divergence)
- 같은 항목에 대해 영상별 평가가 다른 케이스를 그대로 노출
- 가능한 경우 리뷰어 성향(엄격/관대)도 함께 표기

## ⑥ 리뷰어 vs 실사용자 갭
- 영상별 보고서 안에 댓글/실사용자 언급이 있는 경우만 작성
- 입력 보고서에 없는 댓글 데이터를 새로 만들지 말 것
- 해당 정보가 없으면 "데이터 부족"

## ⑦ 전작 대비 달라진 점 (표)
| 항목 | 전작 | 현재 | 변화 평가 | 언급 영상 수 |

## ⑧ 이런 사람에게 추천 / 비추
- 각 항목 옆에 근거(영상 N) 표기

## ⑨ 경쟁/대체 제품 비교
- 입력 보고서에 등장한 경쟁 제품에 한해서만 비교

---
📊 분석 기반
   분석 영상: {n}개
   리뷰어 성향: (영상별 보고서에 명시된 경우에만)
   {today_line}
"""


def build_comment_analysis_prompt(aggregated: dict) -> str:
    """
    보고서 ② (댓글 기반 소비자 여론 보고서) 생성용 프롬프트.

    입력 스키마 (호출부 책임):
      {
        "product_name": str,
        "video_title": str,
        "total_analyzed_comments": int,
        "weighted_ratio": {"positive_pct": float, "neutral_pct": float, "negative_pct": float},
        "positive_aspects": [
          { "aspect_name": str, "comment_count": int,
            "candidate_comments": [
              {"comment_id": str, "text_raw": str, "like_count": int}, ...
            ]
          }, ...
        ],
        "negative_aspects": [동일 구조],
        "top_aspect_frequencies": [{"aspect_name": str, "count": int}, ...]
      }

    LLM 역할 (오직 이 두 가지):
      1) 각 aspect 그룹의 한 줄 요약(summary_line) 생성
      2) 각 그룹의 candidate_comments 중 대표 1~2개 comment_id 선별

    LLM이 절대 하지 말 것:
      - 댓글 원문(text_raw)을 생성·요약·재구성 (백엔드가 ID로 다시 조회 첨부)
      - 입력에 없는 comment_id / aspect_name 생성
      - top_issues 항목을 새로 만들거나 카운트 변형

    response_format json_object 는 호출부에서 지정. 본 함수는 프롬프트 문자열만 반환.
    """
    product_name = aggregated.get("product_name", "제품")
    video_title = aggregated.get("video_title", "")
    total = aggregated.get("total_analyzed_comments", 0)
    weighted = aggregated.get("weighted_ratio", {})
    pos_aspects = aggregated.get("positive_aspects", [])
    neg_aspects = aggregated.get("negative_aspects", [])
    top_freqs = aggregated.get("top_aspect_frequencies", [])

    pos_json = json.dumps(pos_aspects, ensure_ascii=False, indent=2)
    neg_json = json.dumps(neg_aspects, ensure_ascii=False, indent=2)
    top_json = json.dumps(top_freqs, ensure_ascii=False)
    weighted_json = json.dumps(weighted, ensure_ascii=False)

    return f"""당신은 유튜브 댓글 기반 소비자 여론 분석 전문가입니다.

대상 영상: "{video_title}" (제품: {product_name})
이 영상 댓글에 대해 이미 ABSA(aspect-based sentiment analysis)가 완료된
집계 결과를 바탕으로 소비자 여론 보고서를 JSON으로 생성하세요.

================ 절대 규칙 (위반 시 응답 무효) ================
1. 댓글 원문(text_raw)을 절대 생성·요약·재구성하지 않는다.
   당신은 representative_comment_ids만 지목한다. 원문은 백엔드가 ID로 다시
   조회해 첨부한다.
2. representative_comment_ids 의 각 ID는 반드시 해당 aspect 그룹의
   candidate_comments 에 등장한 comment_id 중에서만 선택한다.
   새 ID를 만들거나 다른 aspect의 ID를 끌어오지 않는다.
3. aspect_name 은 입력에 등장한 값만 사용. 신규 aspect 생성 금지.
4. summary_line: 해당 aspect 그룹 댓글들의 공통 의견을 30자 이내로 한 줄 요약.
   특정 댓글을 그대로 인용하거나 ◎○△ 기호를 쓰지 않는다.
5. positive_points / negative_points: comment_count 내림차순 상위 3~5개.
   입력 aspect 수가 3개 미만이면 있는 만큼만 반환. 5개 초과면 상위 5개만.
6. one_line_mood: 가중 비율을 보고 분위기를 한 줄로 (예: "전반적 긍정 — 가성비·디자인에 호평").
7. top_issues: 입력 top_aspect_frequencies 상위 6~8개를 그대로 복사. 가공·재정렬 금지.
8. 대표 댓글 선별 기준: like_count 높고 텍스트가 너무 짧지 않은(=의미가 있는) 것.

================ 입력 데이터 ================
총 분석 대상 댓글 수: {total}
가중 sentiment 비율 (analysis_weight 반영): {weighted_json}

[긍정 aspect 후보 (POSITIVE)]
{pos_json}

[부정 aspect 후보 (NEGATIVE)]
{neg_json}

[전체 aspect 빈도 상위 (top_issues 입력)]
{top_json}

================ 응답 형식 (JSON ONLY, 마크다운 코드펜스 금지) ================
{{
  "sentiment_summary": {{
    "positive_pct": <float, 입력 weighted_ratio.positive_pct 그대로>,
    "neutral_pct":  <float>,
    "negative_pct": <float>,
    "one_line_mood": "<str, 한 줄>"
  }},
  "positive_points": [
    {{
      "aspect_name": "<str, 입력 그대로>",
      "summary_line": "<str, 30자 이내>",
      "comment_count": <int, 입력값 그대로>,
      "representative_comment_ids": ["<str>", ...]   // 1~2개
    }}
  ],
  "negative_points": [ /* 동일 구조 */ ],
  "top_issues": [ {{ "keyword": "<str>", "count": <int> }} ]   // 6~8개
}}

JSON 객체 하나만 출력. 설명문·인사말·코드펜스 모두 금지.
"""


def build_comparison_report_prompt(
    transcript_report_md: str,
    comment_report_json: dict,
    aspect_summary: dict,
) -> str:
    """
    보고서 ③ (리뷰어 vs 소비자 비교 보고서) 생성용 프롬프트.

    입력:
      - transcript_report_md: 보고서 ①의 자막 기반 마크다운 보고서 전문
      - comment_report_json:  보고서 ②의 JSON 응답 dict
        (sentiment_summary / positive_points / negative_points / top_issues)
      - aspect_summary: 백엔드가 사전 집계한 aspect 단위 비교 기초 데이터:
        {
          "product_name": str,
          "common_aspects": [
            {
              "aspect_name": str,
              "consumer_dominant_sentiment": "POSITIVE"|"NEGATIVE"|"NEUTRAL",
              "consumer_positive_count": int,
              "consumer_negative_count": int,
              "consumer_neutral_count": int,
              "candidate_comments": [
                {"comment_id": str, "text_raw": str, "like_count": int}, ...
              ]
            }, ...
          ],
          "reviewer_only_aspect_hints": [str, ...],
          "consumer_only_aspects": [str, ...]
        }

    LLM 역할:
      - common_aspects 의 reviewer 자막 톤 vs consumer 다수 sentiment 비교 →
        agreement / disagreement 판정
      - 각 항목별 reviewer_quote 을 transcript_report_md 에서 1~2문장 발췌
      - 각 항목별 consumer_comment_ids 1~2개를 candidate_comments 에서 선별
      - reviewer_only / consumer_only 정리
      - trust_score (0~100) + 2~3줄 종합 판단

    LLM이 절대 하지 말 것:
      - 입력에 없는 reviewer 발언 / 소비자 댓글 원문 생성
      - candidate_comments 에 없는 comment_id 사용
      - reviewer_quote 을 transcript_report_md 에서 발췌하지 않고 상상으로 생성
      - reviewer_only_aspect_hints / consumer_only_aspects 외 토픽 추가
    """
    product_name = aspect_summary.get("product_name", "제품")
    common_json = json.dumps(
        aspect_summary.get("common_aspects", []), ensure_ascii=False, indent=2
    )
    rev_only_json = json.dumps(
        aspect_summary.get("reviewer_only_aspect_hints", []), ensure_ascii=False
    )
    cons_only_json = json.dumps(
        aspect_summary.get("consumer_only_aspects", []), ensure_ascii=False
    )
    comment_json_str = json.dumps(comment_report_json, ensure_ascii=False, indent=2)

    return f"""당신은 리뷰어(자막) vs 소비자(댓글) 의견을 비교 분석하는 전문가입니다.

대상 제품: {product_name}

다음 세 가지 입력만 근거로 비교 보고서 JSON을 생성하세요.
입력 외 사실·수치·인용을 추가로 만들어 내면 응답이 무효 처리됩니다.

================ 입력 1: 리뷰어 자막 분석 보고서 (마크다운) ================
{transcript_report_md}

================ 입력 2: 소비자 댓글 분석 보고서 (JSON, 보고서 ② 결과) ================
{comment_json_str}

================ 입력 3: 사전 집계된 aspect 단위 비교 기초 데이터 ================
[양쪽 모두 다룬 aspect (common_aspects)]
{common_json}

[리뷰어 자막에 자주 등장하나 댓글 ABSA에 없는 토픽 힌트 (reviewer_only_aspect_hints)]
{rev_only_json}

[댓글 ABSA에는 있으나 리뷰어 자막에 거의 없는 aspect (consumer_only_aspects)]
{cons_only_json}

================ 절대 규칙 (위반 시 응답 무효) ================
1. consumer_comment_ids 의 각 ID는 반드시 해당 aspect의 candidate_comments 에
   등장한 comment_id 중에서만 선택. 다른 aspect의 ID를 끌어오거나 새 ID 생성 금지.
2. 소비자 댓글 원문을 생성·요약·재구성 금지. comment_id 만 지목.
3. reviewer_quote 은 반드시 입력 1의 transcript_report_md 에서 1~2문장을
   거의 그대로 발췌. 상상으로 생성 금지. 해당 aspect가 transcript_report_md 에서
   언급되지 않으면 그 aspect는 agreement/disagreement 양쪽에서 모두 제외.
4. agreement_points 판정: reviewer가 긍정적으로 언급한 항목을 consumer 도 다수 긍정
   (consumer_positive_count > consumer_negative_count), 또는 양쪽 모두 부정.
5. disagreement_points 판정: reviewer는 긍정인데 consumer 다수 부정,
   또는 reviewer 부정인데 consumer 다수 긍정.
6. reviewer_only / consumer_only 는 입력 reviewer_only_aspect_hints /
   consumer_only_aspects 안의 문자열에서만 선택. 새 토픽 생성 금지.
   각 칼럼당 최대 6개까지.
7. trust_score (0~100): agreement 가 많을수록 높게.
   계산 가이드: round(100 * agreement_count / max(1, agreement_count + disagreement_count)).
   판단상 보정은 ±10 이내로만.
8. verdict.summary: 2~3줄. 리뷰 신뢰도와 구매 시 주의점(불일치 항목 기반)을 포함.

================ 응답 형식 (JSON ONLY, 마크다운 코드펜스 금지) ================
{{
  "agreement_points": [
    {{
      "topic": "<str, common_aspects.aspect_name>",
      "reviewer_quote": "<str, transcript_report_md 발췌 1~2문장>",
      "consumer_comment_ids": ["<str>", ...]   // 1~2개
    }}
  ],
  "disagreement_points": [ /* 동일 구조 */ ],
  "reviewer_only": [ "<str>", ... ],   // 입력 reviewer_only_aspect_hints 에서 선택
  "consumer_only": [ "<str>", ... ],   // 입력 consumer_only_aspects 에서 선택
  "verdict": {{
    "trust_score": <int, 0-100>,
    "summary": "<str, 2~3줄>"
  }}
}}

JSON 객체 하나만 출력. 설명문·인사말·코드펜스 모두 금지.
"""
