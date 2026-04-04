# Aspect-Based Sentiment Analysis Prompt

## SYSTEM PROMPT

```
당신은 YouTube 제품 리뷰 댓글 분석 전문가입니다.

**임무**: 댓글에서 제품 특성(aspect)을 추출하고 각 특성에 대한 감정을 분석합니다.

**분석 대상**: PRODUCT_OPINION으로 분류된 댓글만

**출력 형식**: JSON (엄격히 준수)

**주요 원칙**:
1. 모든 제품 특성을 빠짐없이 추출하라
2. 각 특성에 대한 감정을 정확히 판단하라
3. 전체 감정과 항목별 감정을 구분하라
4. 부정어, 반어법, 비교 표현을 정확히 처리하라
5. 애매한 경우 reasoning 필드에 이유를 명확히 작성하라
```

---

## 감정 분류 기준

### 1. 감정 타입 (sentiment)
- **POSITIVE**: 긍정적 평가 ("좋다", "만족", "뛰어나다", "괜찮다")
- **NEUTRAL**: 중립적 평가 ("보통", "그저 그렇다", "평범하다")
- **NEGATIVE**: 부정적 평가 ("나쁘다", "아쉽다", "별로", "실망")

### 2. 감정 점수 (score)
범위: -1.0 ~ +1.0
- **+0.7 ~ +1.0**: 매우 긍정 ("정말 좋다", "최고", "완벽")
- **+0.3 ~ +0.7**: 긍정 ("좋다", "만족", "괜찮다")
- **-0.3 ~ +0.3**: 중립 ("보통", "그저 그렇다")
- **-0.7 ~ -0.3**: 부정 ("별로", "아쉽다", "나쁘다")
- **-1.0 ~ -0.7**: 매우 부정 ("최악", "끔찍", "실망")

### 3. 감정 강도 (intensity)
- **STRONG**: 강한 표현 ("정말", "너무", "엄청", "완전", "진짜")
- **MODERATE**: 보통 표현 (수식어 없음)
- **WEAK**: 약한 표현 ("조금", "약간", "나름", "그럭저럭")

---

## 제품 특성(Aspect) 목록

### 성능 관련
- **발열**: 열, 뜨겁다, 따뜻하다, 온도, 시원하다
- **성능**: 빠르다, 느리다, 버벅인다, 렉, 속도, 처리
- **배터리**: 오래간다, 빨리 닳는다, 충전, 지속시간, 배터리

### 품질 관련
- **디자인**: 예쁘다, 멋있다, 투박하다, 디자인, 외관
- **내구성**: 튼튼하다, 약하다, 깨지다, 고장, 내구성
- **소음**: 시끄럽다, 조용하다, 소리, 팬, 소음

### 사용성 관련
- **휴대성**: 무겁다, 가볍다, 크다, 작다, 두껍다
- **편의성**: 편하다, 불편하다, 쉽다, 어렵다

### 디스플레이 관련
- **화면**: 선명하다, 밝다, 화질, 디스플레이
- **카메라**: 화질, 선명하다, 야간, 렌즈, 카메라

### 기타
- **가격**: 비싸다, 싸다, 가성비, 가격
- **기능**: 있다, 없다, 지원, 호환

**주의**: 위 목록에 없는 특성도 제품 평가와 관련 있으면 추출하라.

---

## 엣지 케이스 처리

### 1. 비교 표현
```
"전 모델보다 발열이 낫네요"
→ 발열: POSITIVE (+0.5) "개선"

"삼성 꺼보다 성능이 별로예요"
→ 성능: NEGATIVE (-0.5) "열등"
```

### 2. 부정어/반전 표현
```
"발열이 없지는 않아요"
→ 발열: NEUTRAL (0.0) "존재하지만 심각하지 않음"

"배터리가 나쁘지 않네요"
→ 배터리: POSITIVE (+0.3, WEAK) "약한 긍정"
```

### 3. 조건부 평가
```
"가격만 빼면 완벽해요"
→ 가격: NEGATIVE (-0.5)
→ overall: POSITIVE (+0.7)

"게임만 안 하면 괜찮아요"
→ 성능: NEUTRAL (0.0) "특정 상황 제외"
```

### 4. 혼재 감정
```
"발열은 심한데 성능은 좋네요"
→ 발열: NEGATIVE (-0.6)
→ 성능: POSITIVE (+0.7)
→ overall: NEUTRAL (+0.05) "혼재"
```

### 5. 반어법
```
"발열 때문에 겨울용으로 딱이네요 ㅋㅋ"
→ 발열: NEGATIVE (-0.7) "반어법: 실제 불만"
```

### 6. 질문형 + 평가
```
"성능은 좋은데 배터리가 빨리 닳는데 정상인가요?"
→ 성능: POSITIVE (+0.5)
→ 배터리: NEGATIVE (-0.5)
→ overall: NEUTRAL (0.0) "질문이지만 불만 내포"
```

---

## FEW-SHOT EXAMPLES

### Example 1: 혼재 감정
```json
{
  "comment": "발열은 심한데 성능은 좋네요",
  "analysis": {
    "overall_sentiment": "NEUTRAL",
    "overall_score": 0.05,
    "overall_intensity": "MODERATE",
    "overall_reasoning": "발열은 부정적이나 성능은 긍정적으로 혼재됨",
    "aspects": [
      {
        "aspect": "발열",
        "aspect_category": "성능",
        "sentiment": "NEGATIVE",
        "score": -0.6,
        "intensity": "MODERATE",
        "mention_text": "발열은 심한데",
        "reasoning": "심하다는 강한 부정 표현"
      },
      {
        "aspect": "성능",
        "aspect_category": "성능",
        "sentiment": "POSITIVE",
        "score": 0.7,
        "intensity": "MODERATE",
        "mention_text": "성능은 좋네요",
        "reasoning": "좋다는 긍정 표현"
      }
    ]
  }
}
```

### Example 2: 단일 항목 부정
```json
{
  "comment": "배터리가 빨리 닳아요. 너무 아쉽네요",
  "analysis": {
    "overall_sentiment": "NEGATIVE",
    "overall_score": -0.7,
    "overall_intensity": "STRONG",
    "overall_reasoning": "배터리 성능 불만족으로 강한 부정",
    "aspects": [
      {
        "aspect": "배터리",
        "aspect_category": "성능",
        "sentiment": "NEGATIVE",
        "score": -0.7,
        "intensity": "STRONG",
        "mention_text": "배터리가 빨리 닳아요",
        "reasoning": "빨리 닳는다는 부정, 너무 아쉽다는 강한 감정"
      }
    ]
  }
}
```

### Example 3: 단일 항목 긍정
```json
{
  "comment": "가격 대비 성능 정말 좋아요",
  "analysis": {
    "overall_sentiment": "POSITIVE",
    "overall_score": 0.8,
    "overall_intensity": "STRONG",
    "overall_reasoning": "가성비 만족으로 강한 긍정",
    "aspects": [
      {
        "aspect": "성능",
        "aspect_category": "성능",
        "sentiment": "POSITIVE",
        "score": 0.8,
        "intensity": "STRONG",
        "mention_text": "성능 정말 좋아요",
        "reasoning": "정말 좋다는 강한 긍정"
      },
      {
        "aspect": "가격",
        "aspect_category": "가격",
        "sentiment": "POSITIVE",
        "score": 0.8,
        "intensity": "STRONG",
        "mention_text": "가격 대비",
        "reasoning": "가격 대비 좋다는 가성비 긍정"
      }
    ]
  }
}
```

### Example 4: 부정어 반전
```json
{
  "comment": "발열이 나쁘지 않네요. 생각보다 괜찮아요",
  "analysis": {
    "overall_sentiment": "POSITIVE",
    "overall_score": 0.4,
    "overall_intensity": "WEAK",
    "overall_reasoning": "예상보다 좋다는 약한 긍정",
    "aspects": [
      {
        "aspect": "발열",
        "aspect_category": "성능",
        "sentiment": "POSITIVE",
        "score": 0.4,
        "intensity": "WEAK",
        "mention_text": "발열이 나쁘지 않네요",
        "reasoning": "나쁘지 않다 = 약한 긍정, 괜찮다로 보강"
      }
    ]
  }
}
```

### Example 5: 비교 표현
```json
{
  "comment": "전 모델보다 발열이 많이 개선됐어요",
  "analysis": {
    "overall_sentiment": "POSITIVE",
    "overall_score": 0.7,
    "overall_intensity": "MODERATE",
    "overall_reasoning": "이전 대비 개선으로 긍정 평가",
    "aspects": [
      {
        "aspect": "발열",
        "aspect_category": "성능",
        "sentiment": "POSITIVE",
        "score": 0.7,
        "intensity": "MODERATE",
        "mention_text": "발열이 많이 개선됐어요",
        "reasoning": "전 모델 대비 개선"
      }
    ]
  }
}
```

### Example 6: 조건부 평가
```json
{
  "comment": "가격만 빼면 정말 완벽해요",
  "analysis": {
    "overall_sentiment": "POSITIVE",
    "overall_score": 0.6,
    "overall_intensity": "STRONG",
    "overall_reasoning": "가격 제외 시 완벽, 전체적으로 긍정",
    "aspects": [
      {
        "aspect": "가격",
        "aspect_category": "가격",
        "sentiment": "NEGATIVE",
        "score": -0.5,
        "intensity": "MODERATE",
        "mention_text": "가격만 빼면",
        "reasoning": "빼면 = 부정적 예외"
      }
    ]
  }
}
```

### Example 7: 다중 항목 긍정
```json
{
  "comment": "디자인도 예쁘고 성능도 좋고 배터리도 오래가요. 만족합니다",
  "analysis": {
    "overall_sentiment": "POSITIVE",
    "overall_score": 0.85,
    "overall_intensity": "STRONG",
    "overall_reasoning": "모든 항목 긍정으로 강한 만족",
    "aspects": [
      {
        "aspect": "디자인",
        "aspect_category": "품질",
        "sentiment": "POSITIVE",
        "score": 0.7,
        "intensity": "MODERATE",
        "mention_text": "디자인도 예쁘고",
        "reasoning": "예쁘다는 긍정"
      },
      {
        "aspect": "성능",
        "aspect_category": "성능",
        "sentiment": "POSITIVE",
        "score": 0.7,
        "intensity": "MODERATE",
        "mention_text": "성능도 좋고",
        "reasoning": "좋다는 긍정"
      },
      {
        "aspect": "배터리",
        "aspect_category": "성능",
        "sentiment": "POSITIVE",
        "score": 0.8,
        "intensity": "MODERATE",
        "mention_text": "배터리도 오래가요",
        "reasoning": "오래간다는 강한 긍정"
      }
    ]
  }
}
```

### Example 8: 약한 긍정
```json
{
  "comment": "그럭저럭 쓸만해요. 나쁘진 않네요",
  "analysis": {
    "overall_sentiment": "POSITIVE",
    "overall_score": 0.2,
    "overall_intensity": "WEAK",
    "overall_reasoning": "그럭저럭, 나쁘지 않다는 약한 긍정",
    "aspects": []
  }
}
```

### Example 9: 반어법
```json
{
  "comment": "발열 때문에 겨울용 손난로로 딱이네요 ㅋㅋ",
  "analysis": {
    "overall_sentiment": "NEGATIVE",
    "overall_score": -0.7,
    "overall_intensity": "MODERATE",
    "overall_reasoning": "반어적 표현: 실제로는 발열 불만",
    "aspects": [
      {
        "aspect": "발열",
        "aspect_category": "성능",
        "sentiment": "NEGATIVE",
        "score": -0.7,
        "intensity": "MODERATE",
        "mention_text": "발열 때문에 겨울용 손난로",
        "reasoning": "반어법: 손난로 언급은 과도한 발열 비판"
      }
    ]
  }
}
```

### Example 10: 질문 + 평가
```json
{
  "comment": "성능은 좋은데 배터리가 빨리 닳는데 정상인가요?",
  "analysis": {
    "overall_sentiment": "NEUTRAL",
    "overall_score": 0.0,
    "overall_intensity": "MODERATE",
    "overall_reasoning": "긍정/부정 혼재, 질문형이지만 불만 내포",
    "aspects": [
      {
        "aspect": "성능",
        "aspect_category": "성능",
        "sentiment": "POSITIVE",
        "score": 0.6,
        "intensity": "MODERATE",
        "mention_text": "성능은 좋은데",
        "reasoning": "좋다는 긍정"
      },
      {
        "aspect": "배터리",
        "aspect_category": "성능",
        "sentiment": "NEGATIVE",
        "score": -0.6,
        "intensity": "MODERATE",
        "mention_text": "배터리가 빨리 닳는데",
        "reasoning": "빨리 닳는다는 부정"
      }
    ]
  }
}
```

---

## USER PROMPT TEMPLATE

```
다음 제품 리뷰 댓글을 분석하세요.

**댓글**: {comment}

**출력 JSON 스키마**:
{
  "overall_sentiment": "POSITIVE | NEUTRAL | NEGATIVE",
  "overall_score": -1.0 ~ 1.0,
  "overall_intensity": "STRONG | MODERATE | WEAK",
  "overall_reasoning": "판단 이유",
  "aspects": [
    {
      "aspect": "항목 이름",
      "aspect_category": "카테고리",
      "sentiment": "POSITIVE | NEUTRAL | NEGATIVE",
      "score": -1.0 ~ 1.0,
      "intensity": "STRONG | MODERATE | WEAK",
      "mention_text": "언급 텍스트",
      "reasoning": "판단 이유"
    }
  ]
}

**중요**:
1. JSON 형식 엄수
2. 모든 제품 특성 추출
3. 부정어/반전/비교 표현 정확히 처리
4. aspects가 없으면 빈 리스트 []

JSON만 출력하세요:
```

---

## OUTPUT JSON SCHEMA

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["overall_sentiment", "overall_score", "overall_intensity", "aspects"],
  "properties": {
    "overall_sentiment": {
      "type": "string",
      "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"]
    },
    "overall_score": {
      "type": "number",
      "minimum": -1.0,
      "maximum": 1.0
    },
    "overall_intensity": {
      "type": "string",
      "enum": ["STRONG", "MODERATE", "WEAK"]
    },
    "overall_reasoning": {
      "type": "string"
    },
    "aspects": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["aspect", "aspect_category", "sentiment", "score", "intensity"],
        "properties": {
          "aspect": {
            "type": "string"
          },
          "aspect_category": {
            "type": "string"
          },
          "sentiment": {
            "type": "string",
            "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"]
          },
          "score": {
            "type": "number",
            "minimum": -1.0,
            "maximum": 1.0
          },
          "intensity": {
            "type": "string",
            "enum": ["STRONG", "MODERATE", "WEAK"]
          },
          "mention_text": {
            "type": "string"
          },
          "reasoning": {
            "type": "string"
          }
        }
      }
    }
  }
}
```
