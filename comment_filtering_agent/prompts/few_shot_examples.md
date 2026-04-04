# Few-Shot Examples for Comment Classification

## PRODUCT_OPINION (제품 평가) - 6개

### Example 1
**Input**: "발열은 심한데 성능은 좋네요"
**Output**:
```json
{
  "label": "PRODUCT_OPINION",
  "confidence": 0.95,
  "rationale_short": "제품의 발열과 성능에 대한 직접적인 평가",
  "needs_recheck": false,
  "mentioned_product_features": ["발열", "성능"],
  "is_product_related": true
}
```

### Example 2
**Input**: "배터리가 생각보다 빨리 닳네요. 하루 종일 쓰기엔 부족해요."
**Output**:
```json
{
  "label": "PRODUCT_OPINION",
  "confidence": 0.98,
  "rationale_short": "배터리 지속 시간에 대한 사용 경험 평가",
  "needs_recheck": false,
  "mentioned_product_features": ["배터리"],
  "is_product_related": true
}
```

### Example 3
**Input**: "가격 대비 성능은 괜찮은 것 같아요. 근데 소음이 좀 있어요."
**Output**:
```json
{
  "label": "PRODUCT_OPINION",
  "confidence": 0.96,
  "rationale_short": "가격, 성능, 소음 등 제품 특성에 대한 종합 평가",
  "needs_recheck": false,
  "mentioned_product_features": ["가격", "성능", "소음"],
  "is_product_related": true
}
```

### Example 4
**Input**: "디자인은 예쁜데 무게가 좀 무겁네요"
**Output**:
```json
{
  "label": "PRODUCT_OPINION",
  "confidence": 0.94,
  "rationale_short": "제품의 디자인과 무게에 대한 평가",
  "needs_recheck": false,
  "mentioned_product_features": ["디자인", "무게"],
  "is_product_related": true
}
```

### Example 5
**Input**: "카메라 성능은 좋은데 야간 촬영이 조금 아쉽습니다"
**Output**:
```json
{
  "label": "PRODUCT_OPINION",
  "confidence": 0.97,
  "rationale_short": "카메라 기능에 대한 상세 평가",
  "needs_recheck": false,
  "mentioned_product_features": ["카메라", "야간촬영"],
  "is_product_related": true
}
```

### Example 6
**Input**: "충전이 빠른 건 좋은데 발열이 심해서 걱정됩니다"
**Output**:
```json
{
  "label": "PRODUCT_OPINION",
  "confidence": 0.95,
  "rationale_short": "충전 속도와 발열에 대한 평가",
  "needs_recheck": false,
  "mentioned_product_features": ["충전", "발열"],
  "is_product_related": true
}
```

---

## VIDEO_REACTION (영상 반응) - 4개

### Example 7
**Input**: "오늘 영상 재밌네요. 리뷰 잘 봤습니다"
**Output**:
```json
{
  "label": "VIDEO_REACTION",
  "confidence": 0.97,
  "rationale_short": "영상 자체에 대한 긍정적 반응",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 8
**Input**: "리뷰 설명이 상세해서 이해하기 좋았어요"
**Output**:
```json
{
  "label": "VIDEO_REACTION",
  "confidence": 0.96,
  "rationale_short": "리뷰어의 설명 방식에 대한 평가",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 9
**Input**: "편집 깔끔하고 자막도 보기 편하네요"
**Output**:
```json
{
  "label": "VIDEO_REACTION",
  "confidence": 0.98,
  "rationale_short": "영상 편집과 자막에 대한 평가",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 10
**Input**: "리뷰 보니까 발열이 심한가봐요. 영상 잘 만드셨네요"
**Output**:
```json
{
  "label": "VIDEO_REACTION",
  "confidence": 0.92,
  "rationale_short": "영상에서 본 정보 언급이지만 영상 자체 칭찬이 주 내용",
  "needs_recheck": false,
  "mentioned_product_features": ["발열"],
  "is_product_related": true
}
```

---

## QUESTION (제품 관련 질문) - 4개

### Example 11
**Input**: "이거 게임도 잘 돌아가나요?"
**Output**:
```json
{
  "label": "QUESTION",
  "confidence": 0.99,
  "rationale_short": "제품의 게임 성능에 대한 질문",
  "needs_recheck": false,
  "mentioned_product_features": ["게임", "성능"],
  "is_product_related": true
}
```

### Example 12
**Input**: "배터리 몇 시간 정도 가나요? 구매 고민 중입니다"
**Output**:
```json
{
  "label": "QUESTION",
  "confidence": 0.98,
  "rationale_short": "배터리 지속 시간에 대한 구체적 질문",
  "needs_recheck": false,
  "mentioned_product_features": ["배터리"],
  "is_product_related": true
}
```

### Example 13
**Input**: "이거랑 삼성 꺼랑 뭐가 더 나은가요?"
**Output**:
```json
{
  "label": "QUESTION",
  "confidence": 0.97,
  "rationale_short": "제품 비교에 대한 질문",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": true
}
```

### Example 14
**Input**: "어디서 사면 가장 싸게 살 수 있을까요?"
**Output**:
```json
{
  "label": "QUESTION",
  "confidence": 0.96,
  "rationale_short": "제품 구매처에 대한 질문",
  "needs_recheck": false,
  "mentioned_product_features": ["가격"],
  "is_product_related": true
}
```

---

## CHATTER (잡담/무의미) - 3개

### Example 15
**Input**: "ㅋㅋㅋㅋㅋ 진짜네"
**Output**:
```json
{
  "label": "CHATTER",
  "confidence": 0.95,
  "rationale_short": "의미 있는 정보 없는 단순 반응",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 16
**Input**: "오 신기하다"
**Output**:
```json
{
  "label": "CHATTER",
  "confidence": 0.93,
  "rationale_short": "구체적 내용 없는 짧은 반응",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 17
**Input**: "대박ㅋㅋ 이런게 있었네"
**Output**:
```json
{
  "label": "CHATTER",
  "confidence": 0.90,
  "rationale_short": "의미 있는 평가나 질문이 없는 감탄사",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

---

## OFF_TOPIC (제품 무관) - 3개

### Example 18
**Input**: "배경음악 제목이 뭔가요?"
**Output**:
```json
{
  "label": "OFF_TOPIC",
  "confidence": 0.99,
  "rationale_short": "제품과 무관한 배경음악 질문",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 19
**Input**: "리뷰어님 목소리 좋으시네요. 혹시 성우신가요?"
**Output**:
```json
{
  "label": "OFF_TOPIC",
  "confidence": 0.94,
  "rationale_short": "제품이나 영상 내용과 무관한 개인적 질문",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 20
**Input**: "오늘 날씨 좋네요. 주말 잘 보내세요"
**Output**:
```json
{
  "label": "OFF_TOPIC",
  "confidence": 0.99,
  "rationale_short": "제품/영상과 완전히 무관한 일상 대화",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

---

## 경계 케이스 (Boundary Cases) - 5개

### Example 21
**Input**: "이 영상 덕분에 제품 이해가 잘 됐어요"
**Output**:
```json
{
  "label": "VIDEO_REACTION",
  "confidence": 0.88,
  "rationale_short": "영상의 설명력에 대한 칭찬 (영상 평가)",
  "needs_recheck": false,
  "mentioned_product_features": [],
  "is_product_related": true
}
```

### Example 22
**Input**: "실제로 써보니 발열이 영상보다 더 심해요"
**Output**:
```json
{
  "label": "PRODUCT_OPINION",
  "confidence": 0.95,
  "rationale_short": "직접 사용 경험 기반 제품 평가",
  "needs_recheck": false,
  "mentioned_product_features": ["발열"],
  "is_product_related": true
}
```

### Example 23
**Input**: "좋네요"
**Output**:
```json
{
  "label": "CHATTER",
  "confidence": 0.65,
  "rationale_short": "맥락 없는 짧은 긍정 반응 (제품인지 영상인지 불명확)",
  "needs_recheck": true,
  "mentioned_product_features": [],
  "is_product_related": false
}
```

### Example 24
**Input**: "성능 좋다고 하는데 진짜 그런가요?"
**Output**:
```json
{
  "label": "QUESTION",
  "confidence": 0.94,
  "rationale_short": "제품 성능에 대한 확인 질문",
  "needs_recheck": false,
  "mentioned_product_features": ["성능"],
  "is_product_related": true
}
```

### Example 25
**Input**: "이거 쓰면서 영상 편집하면 버벅일까요?"
**Output**:
```json
{
  "label": "QUESTION",
  "confidence": 0.96,
  "rationale_short": "제품의 영상 편집 성능에 대한 질문",
  "needs_recheck": false,
  "mentioned_product_features": ["성능", "영상편집"],
  "is_product_related": true
}
```
