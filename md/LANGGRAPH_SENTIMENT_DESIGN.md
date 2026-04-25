# LangGraph 감성 분석 설계 문서

> 기준일: 2026-04-18  
> 목적: 필터링 통과 댓글의 감성 분석을 **1차 경량 모델 → confidence 체크 → (필요 시) 2차 LLM** 구조로 전환  
> 현재 구조: 모든 댓글을 `GroqAspectSentimentAnalyzer`(llama-3.3-70b)로 직접 분석  

---

## 1. 추천 1차 감성 분석 모델 (3가지)

### 비교 요약

| 항목 | KoELECTRA | XLM-RoBERTa | KLUE-BERT |
|------|-----------|-------------|-----------|
| HuggingFace ID | `monologg/koelectra-base-v3-finetuned-sentiment` | `cardiffnlp/twitter-xlm-roberta-base-sentiment` | `hun3359/klue-bert-base-sentiment` |
| 학습 데이터 | NSMC (네이버 영화 리뷰 150만) | 다국어 Twitter | KLUE 벤치마크 + 다양한 한국어 도메인 |
| 출력 클래스 | positive / negative (2-class) | positive / neutral / negative (3-class) | positive / neutral / negative (3-class) |
| 언어 | 한국어 전용 | 다국어 (한국어 포함) | 한국어 전용 |
| 추론 속도 | **빠름** (~50ms/comment CPU) | 보통 (~100ms) | 보통 (~80ms) |
| 모델 크기 | 110M params | 270M params | 110M params |
| 강점 | 한국어 특화, 가장 빠름 | 한/영 혼용 댓글, neutral 클래스 보유 | KLUE 벤치마크 기준 최고 정확도, neutral 보유 |
| 약점 | binary만 지원 (neutral 없음), 영어 포함 댓글 취약 | 트위터 도메인 편향, 제품 리뷰 정확도 불확실 | NSMC 외 도메인 검증 데이터 부족 |

---

### 모델별 상세

#### ① KoELECTRA (`monologg/koelectra-base-v3-finetuned-sentiment`)
- **추천 상황**: 댓글이 거의 한국어이고, 속도가 중요한 경우
- **주의**: neutral 클래스 없음 → confidence가 낮은 중립적 댓글을 pos/neg 중 하나로 강제 분류하므로 confidence 임계값을 높게 잡아야 함 (≥ 0.85 권장)
- **설치**: `transformers`, `torch`

```python
from transformers import pipeline
classifier = pipeline(
    "sentiment-analysis",
    model="monologg/koelectra-base-v3-finetuned-sentiment",
    tokenizer="monologg/koelectra-base-v3-finetuned-sentiment"
)
result = classifier("배터리 수명이 생각보다 짧네요")
# [{'label': 'negative', 'score': 0.91}]
```

---

#### ② XLM-RoBERTa (`cardiffnlp/twitter-xlm-roberta-base-sentiment`)
- **추천 상황**: 한/영 혼용 댓글이 많거나, neutral을 명시적으로 구분해야 할 때
- **주의**: Twitter 데이터 기반이므로 제품 리뷰 도메인 정확도가 약간 떨어질 수 있음
- **장점**: neutral 클래스가 있어 binary 강제 분류 오류 없음

```python
from transformers import pipeline
classifier = pipeline(
    "sentiment-analysis",
    model="cardiffnlp/twitter-xlm-roberta-base-sentiment"
)
result = classifier("성능은 괜찮은데 가격이 좀...")
# [{'label': 'neutral', 'score': 0.73}]
```

---

#### ③ KLUE-BERT (`hun3359/klue-bert-base-sentiment`)
- **추천 상황**: 정확도를 최우선으로 할 때, 제품 리뷰/뉴스/SNS 등 혼합 도메인
- **장점**: KLUE 벤치마크 기반으로 다양한 한국어 도메인에서 검증됨, neutral 보유
- **주의**: KoELECTRA보다 약간 느림, 한국어 전용이므로 영어 포함 댓글은 tokenizer가 처리하나 정확도 저하 가능

```python
from transformers import pipeline
classifier = pipeline(
    "text-classification",
    model="hun3359/klue-bert-base-sentiment"
)
result = classifier("발열이 너무 심해요. 손에 쥐기 불편할 정도")
# [{'label': 'negative', 'score': 0.94}]
```

---

### 권장 선택

> 이 프로젝트 조건 (한국어 제품 리뷰, neutral 구분 필요, 속도 중요):  
> **① KLUE-BERT** (`hun3359/klue-bert-base-sentiment`) — 3-class + 한국어 특화 + 정확도 우선

---

## 2. LangGraph 구조 설계

### 2-1. 전체 흐름

```
[필터링 완료 댓글]
        │
        ▼
┌─────────────────────┐
│  run_sentiment_model │  ← HuggingFace 경량 모델 (1차 분석)
│  (KLUE-BERT 등)     │    출력: label, confidence_score
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   check_confidence  │  ← confidence 임계값 판단 (조건 분기)
└─────────────────────┘
        │
   ┌────┴────┐
   │         │
[≥ 0.80]  [< 0.80]
   │         │
   │         ▼
   │  ┌──────────────────┐
   │  │  run_llm_analysis │  ← GroqAspectSentimentAnalyzer
   │  │  (llama-3.3-70b) │    ABSA 전체 분석
   │  └──────────────────┘
   │         │
   └────┬────┘
        │
        ▼
┌─────────────────────┐
│    save_results     │  ← DB 저장 (comment_sentiments, aspect_extractions)
└─────────────────────┘
        │
       END
```

---

### 2-2. State 정의

```python
from typing import TypedDict, Optional
from comment_filtering_agent.analyzers.models import SentimentAnalysisResult

class CommentSentimentState(TypedDict):
    # 입력
    comment_id: str
    comment_text: str
    video_id: str

    # 1차 모델 결과
    model_label: Optional[str]          # "positive" | "neutral" | "negative"
    model_confidence: Optional[float]   # 0.0 ~ 1.0

    # 분기 결정
    needs_llm: bool                     # confidence < threshold 시 True
    analysis_path: str                  # "model_only" | "model+llm"

    # 2차 LLM 결과
    llm_result: Optional[SentimentAnalysisResult]

    # 최종 저장할 결과
    final_sentiment: Optional[str]
    final_score: Optional[float]
    final_aspects: Optional[list]

    # 에러
    error: Optional[str]
```

---

### 2-3. Node 정의

#### Node 1: `run_sentiment_model`
```python
def run_sentiment_model(state: CommentSentimentState) -> CommentSentimentState:
    """
    HuggingFace 경량 모델로 1차 감성 분류.
    label과 confidence_score를 State에 기록.
    """
    result = hf_classifier(state["comment_text"])[0]
    return {
        **state,
        "model_label": result["label"],       # e.g. "negative"
        "model_confidence": result["score"],  # e.g. 0.61
    }
```

#### Node 2: `run_llm_analysis`
```python
def run_llm_analysis(state: CommentSentimentState) -> CommentSentimentState:
    """
    GroqAspectSentimentAnalyzer로 전체 ABSA 실행.
    aspect 추출 + 감성 점수 포함.
    """
    result = groq_analyzer.analyze_single(state["comment_text"])
    return {
        **state,
        "llm_result": result,
        "analysis_path": "model+llm",
    }
```

#### Node 3: `save_results`
```python
def save_results(state: CommentSentimentState) -> CommentSentimentState:
    """
    최종 결과를 DB에 저장.
    - LLM 결과가 있으면 LLM 결과 우선 (ABSA 포함)
    - 없으면 모델 결과만 저장 (aspect 없음)
    """
    if state.get("llm_result"):
        # LLM path: 전체 ABSA 저장
        save_to_db(state["comment_id"], state["llm_result"])
    else:
        # model-only path: 감성만 저장 (aspect 비어있음)
        save_model_only_result(
            state["comment_id"],
            state["model_label"],
            state["model_confidence"]
        )
    return {**state, "analysis_path": state.get("analysis_path", "model_only")}
```

---

### 2-4. Conditional Edge (분기 로직)

```python
CONFIDENCE_THRESHOLD = 0.80

def route_by_confidence(state: CommentSentimentState) -> str:
    """
    confidence >= 0.80 → "save_results"   (model-only, LLM 스킵)
    confidence <  0.80 → "run_llm_analysis"  (LLM 에스컬레이션)
    """
    if state.get("model_confidence", 0.0) >= CONFIDENCE_THRESHOLD:
        return "save_results"
    return "run_llm_analysis"
```

---

### 2-5. Graph 조립

```python
from langgraph.graph import StateGraph, END

def build_sentiment_graph():
    graph = StateGraph(CommentSentimentState)

    # 노드 등록
    graph.add_node("run_sentiment_model", run_sentiment_model)
    graph.add_node("run_llm_analysis", run_llm_analysis)
    graph.add_node("save_results", save_results)

    # 엣지 연결
    graph.set_entry_point("run_sentiment_model")

    graph.add_conditional_edges(
        "run_sentiment_model",
        route_by_confidence,
        {
            "save_results": "save_results",
            "run_llm_analysis": "run_llm_analysis",
        }
    )

    graph.add_edge("run_llm_analysis", "save_results")
    graph.add_edge("save_results", END)

    return graph.compile()

sentiment_graph = build_sentiment_graph()
```

---

### 2-6. 실행 (기존 pipeline_orchestrator에서 호출)

```python
# 기존: groq_analyzer.analyze_single(comment_text)
# 변경: 아래로 대체

result_state = sentiment_graph.invoke({
    "comment_id": comment_id,
    "comment_text": comment_text,
    "video_id": video_id,
    "model_label": None,
    "model_confidence": None,
    "needs_llm": False,
    "analysis_path": "model_only",
    "llm_result": None,
    "final_sentiment": None,
    "final_score": None,
    "final_aspects": None,
    "error": None,
})
```

---

## 3. 현재 코드 통합 포인트

| 현재 위치 | 현재 동작 | 변경 후 |
|-----------|-----------|---------|
| `scripts/api/sync.py` > `process_comments_with_agent()` | Agent ANALYZE 판정 시 `groq_analyzer.analyze_single()` 직접 호출 | `sentiment_graph.invoke()` 로 교체 |
| `comment_filtering_agent/analyzers/groq_analyzer.py` | 모든 댓글 LLM 분석 | confidence < 0.80 댓글만 호출 (Node 2) |
| `comment_filtering_agent/analyzers/base_analyzer.py` | 변경 없음 | 그대로 유지 |
| `comment_filtering_agent/analyzers/models.py` | 변경 없음 | `CommentSentimentState`에서 `SentimentAnalysisResult` 재사용 |

---

## 4. 예상 효과

| 지표 | 현재 | 변경 후 |
|------|------|---------|
| LLM 호출 비율 | 100% | ~20~40% (confidence < 0.80 케이스만) |
| 평균 분석 시간 | ~1.5s/댓글 (Groq latency) | ~0.08s (모델) or ~1.5s (LLM 에스컬레이션) |
| ABSA 정확도 | 높음 (LLM) | confidence ≥ 0.80 → 모델만 (aspect 없음), < 0.80 → LLM 동일 |
| API 비용 | 전체 댓글 Groq 토큰 | 약 60~80% 절감 예상 |

> **트레이드오프**: confidence ≥ 0.80인 댓글은 aspect 추출 없이 sentiment만 저장됨.  
> aspect_extractions 완전성이 필요하면 임계값을 낮추거나 model-only path에도 rule-based aspect 추출 추가 고려.

---

## 5. 설치 패키지

```bash
pip install langgraph langchain-core
pip install transformers torch  # HuggingFace 모델
# GPU 사용 시: pip install torch --index-url https://download.pytorch.org/whl/cu121
```
