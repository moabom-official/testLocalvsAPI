# 감정 및 항목(Aspect) 분석 기준 (간략)

PRODUCT_OPINION 댓글에 대한 전체 감정 + 항목별 감정 분석

## 감정 분류
- **POSITIVE** / **NEUTRAL** / **NEGATIVE**
- Score: -1.0 ~ +1.0

## 주요 Aspects
발열, 성능, 배터리, 소음, 카메라, 가격, 디스플레이, 디자인, 휴대성, 내구성

## 출력 형식
```json
{
  "overall_sentiment": "NEUTRAL",
  "overall_score": 0.05,
  "aspects": [
    {"aspect": "발열", "sentiment": "NEGATIVE", "score": -0.6},
    {"aspect": "성능", "sentiment": "POSITIVE", "score": 0.7}
  ]
}
```

## 엣지 케이스
- 질문형 + 평가
- 비교형
- 부정어/반전
- 혼재 감정
