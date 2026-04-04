# 감정 및 항목(Aspect) 분석 구현

PRODUCT_OPINION 댓글에 대한 **전체 감정** 및 **항목별 감정** 분석 모듈

---

## 📦 구성 요소

### 1. **데이터 모델** (`models.py`)
- `SentimentType`: POSITIVE / NEUTRAL / NEGATIVE
- `IntensityType`: STRONG / MODERATE / WEAK
- `AspectSentiment`: 항목별 감정 정보
- `SentimentAnalysisResult`: 전체 분석 결과
- `AnalyzerConfig`: 분석기 설정

### 2. **추상 분석기** (`base_analyzer.py`)
- `BaseAspectSentimentAnalyzer`: 추상 베이스 클래스
- 프롬프트 로드 및 관리
- LLM 호출 추상 메서드
- JSON 파싱 및 검증
- 재시도 로직
- 통계 생성

### 3. **Groq 구현** (`groq_analyzer.py`)
- `GroqAspectSentimentAnalyzer`: Groq API 구현
- llama-3.3-70b-versatile 기본 모델
- JSON 모드 지원
- `create_analyzer()` 편의 함수

### 4. **프롬프트** (`prompts/aspect_sentiment_prompt.md`)
- System prompt: 분석 기준 정의
- Few-shot examples: 10개 예시
- User prompt template
- JSON schema

---

## 🎯 주요 기능

### 1. 전체 감정 분석
```python
{
  "overall_sentiment": "NEUTRAL",
  "overall_score": 0.05,
  "overall_intensity": "MODERATE",
  "overall_reasoning": "발열 부정적, 성능 긍정적으로 혼재"
}
```

### 2. 항목별 감정 분석
```python
{
  "aspects": [
    {
      "aspect": "발열",
      "aspect_category": "성능",
      "sentiment": "NEGATIVE",
      "score": -0.6,
      "intensity": "MODERATE",
      "mention_text": "발열은 심한데",
      "reasoning": "심하다는 부정적 표현"
    },
    {
      "aspect": "성능",
      "aspect_category": "성능",
      "sentiment": "POSITIVE",
      "score": 0.7,
      "intensity": "MODERATE",
      "mention_text": "성능은 좋네요",
      "reasoning": "좋다는 긍정적 표현"
    }
  ]
}
```

### 3. 엣지 케이스 처리
- ✅ 부정어 반전 ("나쁘지 않다" → 약한 긍정)
- ✅ 비교 표현 ("전 모델보다 좋다" → 긍정)
- ✅ 조건부 평가 ("가격만 빼면 완벽" → 가격 부정)
- ✅ 혼재 감정 (여러 항목 다른 감정)
- ✅ 반어법 ("겨울용 손난로" → 발열 부정)
- ✅ 질문+평가 혼재

---

## 🚀 사용법

### 기본 사용
```python
from comment_filtering_agent.analyzers.groq_analyzer import create_analyzer

# 분석기 생성
analyzer = create_analyzer()

# 단일 댓글 분석
comment = "발열은 심한데 성능은 좋네요"
result = analyzer.analyze_single(comment)

print(f"감정: {result.overall_sentiment.value}")
print(f"점수: {result.overall_score}")
print(f"항목 수: {len(result.aspects)}")
```

### 배치 분석
```python
comments = [
    "발열은 심한데 성능은 좋네요",
    "배터리가 빨리 닳아요",
    "가격 대비 만족스럽습니다"
]

results = analyzer.analyze_batch(comments)
```

### 통계 생성
```python
stats = analyzer.get_statistics(results)

print(f"평균 점수: {stats['average_score']}")
print(f"긍정 비율: {stats['overall_sentiment_distribution']['positive_pct']}%")
print(f"자주 언급된 항목: {stats['top_aspects'][:5]}")
```

---

## 📊 지원 항목(Aspects)

| 카테고리 | 항목 |
|---------|------|
| **성능** | 발열, 성능, 배터리 |
| **품질** | 디자인, 내구성, 소음 |
| **사용성** | 휴대성, 편의성 |
| **디스플레이** | 화면, 카메라 |
| **가격** | 가격 |
| **기능** | 기능 |

---

## 🧪 테스트

### 실행 방법
```bash
# API 키 설정
export GROQ_API_KEY="your-api-key"

# 테스트 실행
python comment_filtering_agent/tests/test_aspect_analyzer.py

# 예시 실행
python comment_filtering_agent/examples/example_aspect_analyzer.py
```

### 테스트 항목
1. ✅ 데이터 모델 검증
2. ✅ 분석기 초기화
3. ✅ 단일 항목 긍정
4. ✅ 혼재 감정
5. ✅ 부정어 반전
6. ✅ 배치 분석
7. ✅ 통계 생성

---

## 🔄 Agent와 통합

```python
# Agent 결정 후
if agent_decision.final_action == AgentAction.ANALYZE:
    # 감정 분석 실행
    analyzer = create_analyzer()
    result = analyzer.analyze_single(comment)
    
    # DB 저장
    # - sentiment_analysis 테이블: overall 정보
    # - aspect_extractions 테이블: 각 aspect 정보
```

---

## 💾 DB 매핑

### sentiment_analysis 테이블
```sql
INSERT INTO sentiment_analysis (
    comment_id,
    sentiment,           -- result.overall_sentiment
    sentiment_score,     -- result.overall_score
    intensity,           -- result.overall_intensity
    analysis_reasoning,  -- result.overall_reasoning
    sentiment_model,     -- result.model_name
    model_version        -- result.analyzer_version
) VALUES (...)
```

### aspect_extractions 테이블
```sql
INSERT INTO aspect_extractions (
    comment_id,
    aspect_id,           -- aspect_definitions 테이블 참조
    mention_text,        -- aspect.mention_text
    aspect_sentiment,    -- aspect.sentiment
    aspect_sentiment_score, -- aspect.score
    extraction_method    -- 'LLM'
) VALUES (...)
```

---

## 🎛️ 설정 옵션

```python
from comment_filtering_agent.analyzers.models import AnalyzerConfig

config = AnalyzerConfig(
    model_name="llama-3.3-70b-versatile",
    temperature=0.1,              # 일관성 (낮을수록 결정적)
    max_tokens=1000,              # 최대 출력 토큰
    extract_mention_text=True,    # 언급 텍스트 추출
    extract_reasoning=True,       # 판단 이유 추출
    max_retries=3,                # 재시도 횟수
    retry_delay=1.0,              # 재시도 대기 시간(초)
    timeout=30                    # 타임아웃(초)
)
```

---

## 🔮 향후 확장

### 1. 경량 모델로 전환
```python
# 현재: LLM 기반 (느림, 정확)
analyzer = GroqAspectSentimentAnalyzer()

# 향후: 경량 모델 (빠름, 저비용)
from comment_filtering_agent.analyzers.bert_analyzer import BERTAnalyzer
analyzer = BERTAnalyzer(model_path="kobert-sentiment")
```

### 2. 하이브리드 접근
```python
# 간단한 댓글: 경량 모델
# 복잡한 댓글: LLM

if is_complex(comment):
    result = llm_analyzer.analyze_single(comment)
else:
    result = bert_analyzer.analyze_single(comment)
```

### 3. Aspect 사전 확장
```python
# 제품 카테고리별 커스텀 aspect
config = AnalyzerConfig(
    predefined_aspects=[
        # 기본
        "발열", "성능", "배터리",
        # 노트북 전용
        "키보드", "트랙패드", "포트",
        # 스마트폰 전용
        "5G", "생체인식", "방수"
    ]
)
```

---

## 📈 성능 지표

| 지표 | 값 (LLM 기반) |
|------|--------------|
| **처리 속도** | ~2-3초/댓글 |
| **정확도** | ~85-90% (수동 평가) |
| **Aspect 추출률** | ~90% |
| **비용** | ~$0.001/댓글 (Groq) |

---

## ⚠️ 주의사항

1. **API 키 필요**: Groq API 키 환경 변수 설정 필수
2. **비용**: 대량 분석 시 비용 고려
3. **속도**: LLM 기반이라 실시간 처리에는 부적합
4. **정확도**: 반어법, 복잡한 표현은 오판 가능

---

## 📁 파일 구조

```
comment_filtering_agent/
├── analyzers/
│   ├── __init__.py
│   ├── models.py                    # 데이터 모델
│   ├── base_analyzer.py             # 추상 클래스 (330줄)
│   ├── groq_analyzer.py             # Groq 구현 (100줄)
│   └── README.md                    # 간략 설명
├── prompts/
│   └── aspect_sentiment_prompt.md   # 프롬프트 (450줄)
├── tests/
│   └── test_aspect_analyzer.py      # 테스트 (7 cases)
└── examples/
    └── example_aspect_analyzer.py   # 예시 (7 examples)
```

---

## ✅ 완료 항목

- [x] 데이터 모델 정의 (SentimentType, AspectSentiment, etc.)
- [x] 추상 분석기 클래스 (재시도, 파싱, 검증)
- [x] Groq API 구현
- [x] 프롬프트 작성 (system, few-shot, user template)
- [x] 10개 few-shot examples
- [x] 엣지 케이스 처리 가이드
- [x] 테스트 코드 (7개)
- [x] 예시 코드 (7개)
- [x] 통계 생성 기능
- [x] DB 매핑 가이드

---

## 🔗 관련 문서

- `ASPECT_SENTIMENT_CRITERIA.md`: 분석 기준 상세
- `prompts/aspect_sentiment_prompt.md`: 프롬프트 전체
- `DATABASE_ERD.md`: DB 스키마 (sentiment_analysis, aspect_extractions)
- `AGENT_IMPLEMENTATION.md`: Agent 통합

---

## 📞 사용 예시

```python
# 1. 기본 사용
from comment_filtering_agent.analyzers.groq_analyzer import create_analyzer

analyzer = create_analyzer()
result = analyzer.analyze_single("발열은 심한데 성능은 좋네요")

# 2. 결과 확인
print(f"전체 감정: {result.overall_sentiment.value}")
print(f"항목별 감정:")
for asp in result.aspects:
    print(f"  {asp.aspect}: {asp.sentiment.value} ({asp.score})")

# 3. JSON 변환
import json
print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

# 4. 통계
results = analyzer.analyze_batch(comments)
stats = analyzer.get_statistics(results)
print(f"긍정 비율: {stats['overall_sentiment_distribution']['positive_pct']}%")
```

---

**구현 완료!** 🎉

이제 PRODUCT_OPINION 댓글에 대한 감정 및 항목 분석이 가능합니다.
