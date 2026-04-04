# LLM 댓글 분류기 설계 완료 ✅

## 📦 생성된 파일

### 1. 프롬프트 파일
- **`prompts/system_prompt.md`** - 시스템 프롬프트 (5개 라벨 정의, 분류 원칙)
- **`prompts/few_shot_examples.md`** - Few-shot 예시 25개
- **`prompts/user_prompt_template.md`** - 유저 프롬프트 템플릿
- **`prompts/classification_schema.json`** - JSON 스키마

### 2. 핵심 모듈
- **`classifiers/models.py`** - 데이터 모델 (ClassificationResult, CommentLabel, ClassificationConfig)
- **`classifiers/prompt_builder.py`** - 프롬프트 빌더 (290줄)
- **`classifiers/base_classifier.py`** - 추상 클래스 (220줄)
- **`classifiers/groq_classifier.py`** - Groq 구현체 (100줄)

### 3. 테스트 & 예시
- **`tests/test_llm_classifier.py`** - 7개 테스트 (프롬프트, 스키마 등)
- **`examples/example_llm_classifier.py`** - 7개 실사용 예시

---

## 🎯 5개 분류 라벨

### 1. PRODUCT_OPINION (제품 평가)
**제품 자체의 특성, 성능, 품질에 대한 평가**
- 성능, 발열, 배터리, 디자인, 가격, 소음, 카메라 등
- 예: "발열은 심한데 성능은 좋네요"

### 2. VIDEO_REACTION (영상 반응)
**영상 자체, 리뷰어, 편집에 대한 반응**
- 영상 재미, 리뷰어 설명, 편집 품질 등
- 예: "오늘 영상 재밌네요", "리뷰 설명 좋아요"

### 3. CHATTER (잡담/무의미)
**의미 있는 정보가 없는 댓글**
- 단순 반응 (ㅋㅋㅋ, 와, 오)
- 예: "ㅋㅋㅋㅋㅋ", "대박"

### 4. QUESTION (제품 관련 질문)
**제품에 대한 질문**
- 성능 질문, 기능 질문, 구매 관련 질문
- 예: "이거 게임도 잘 돌아가나요?", "배터리 몇 시간 가나요?"

### 5. OFF_TOPIC (제품 무관)
**제품과 완전히 무관한 댓글**
- 배경음악, 다른 주제, 개인적 이야기
- 예: "배경음악 제목 뭔가요?"

---

## 📊 출력 JSON 형식

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

### 필드 설명
- **label**: 5개 라벨 중 하나
- **confidence**: 0.0~1.0 (0.8+ 고확신, 0.6 미만 저확신)
- **rationale_short**: 분류 이유 (한 줄)
- **needs_recheck**: 애매해서 재확인 필요 여부
- **mentioned_product_features**: 언급된 제품 특성 리스트
- **is_product_related**: 제품 관련 여부

---

## 🚀 사용 예시

### 기본 사용
```python
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier

# 분류기 생성
classifier = create_groq_classifier(
    api_key="your_groq_api_key",
    model="llama-3.3-70b-versatile",
    temperature=0.1
)

# 단일 댓글 분류
result = classifier.classify_single(
    comment="발열은 심한데 성능은 좋네요",
    product_name="갤럭시 S25",
    product_category="스마트폰"
)

print(f"라벨: {result.label.value}")           # PRODUCT_OPINION
print(f"확신도: {result.confidence}")           # 0.95
print(f"제품 특성: {result.mentioned_product_features}")  # ['발열', '성능']
```

### 배치 처리
```python
comments = [
    "발열은 심한데 성능은 좋네요",
    "배터리가 빨리 닳네요",
    "오늘 영상 재밌네요",
    "이거 게임도 잘 돌아가나요?"
]

results = classifier.classify_batch(
    comments=comments,
    product_name="MacBook Pro"
)

# PRODUCT_OPINION만 추출
opinions = [r for r in results if r.should_analyze]
```

---

## 📐 Few-Shot 예시 (25개)

### PRODUCT_OPINION (6개)
1. "발열은 심한데 성능은 좋네요"
2. "배터리가 생각보다 빨리 닳네요"
3. "가격 대비 성능은 괜찮아요"
4. "디자인은 예쁜데 무게가 무겁네요"
5. "카메라 성능은 좋은데 야간 촬영 아쉬워요"
6. "충전 빠른 건 좋은데 발열 심해요"

### VIDEO_REACTION (4개)
7. "오늘 영상 재밌네요"
8. "리뷰 설명이 상세해서 좋아요"
9. "편집 깔끔하고 자막 보기 편해요"
10. "리뷰 보니 발열이 심한가봐요. 영상 잘 만드셨네요"

### QUESTION (4개)
11. "이거 게임도 잘 돌아가나요?"
12. "배터리 몇 시간 가나요?"
13. "이거랑 삼성 꺼랑 뭐가 나은가요?"
14. "어디서 사면 가장 싸게 살 수 있나요?"

### CHATTER (3개)
15. "ㅋㅋㅋㅋㅋ 진짜네"
16. "오 신기하다"
17. "대박ㅋㅋ 이런게 있었네"

### OFF_TOPIC (3개)
18. "배경음악 제목 뭔가요?"
19. "리뷰어님 목소리 좋으시네요"
20. "오늘 날씨 좋네요"

### 경계 케이스 (5개)
21. "이 영상 덕분에 제품 이해했어요" → VIDEO_REACTION
22. "실제로 써보니 발열이 영상보다 더 심해요" → PRODUCT_OPINION
23. "좋네요" → CHATTER (맥락 불명확, needs_recheck=true)
24. "성능 좋다고 하는데 진짜 그런가요?" → QUESTION
25. "이거 쓰면서 영상 편집하면 버벅일까요?" → QUESTION

---

## 🎨 주요 특징

### 1. 명확한 분류 기준
- PRODUCT_OPINION vs VIDEO_REACTION 경계 명확히 정의
- 25개 Few-shot 예시로 분류 일관성 확보
- 경계 케이스 5개 포함

### 2. Explainable (설명 가능)
- `rationale_short`: 분류 이유
- `mentioned_product_features`: 언급된 제품 특성
- `confidence`: 확신도

### 3. 애매한 댓글 처리
- `needs_recheck`: 재확인 필요 플래그
- `confidence < 0.6`: 저확신 → Agent 재판단
- `reclassification_queue` 테이블 활용

### 4. 확장 가능
- 추상 클래스 설계 → OpenAI, Anthropic 등 쉽게 추가
- Few-shot → Fine-tuned 전환 가능
- `classifier_version_id`로 A/B 테스트

---

## 🔄 전체 파이프라인 통합

```
[YouTube 댓글 수집]
        ↓
[1차 규칙 필터] ✅
        ↓
[2차 LLM 분류] ✅ 현재 완료
  - PRODUCT_OPINION → 감정/항목 분석
  - VIDEO_REACTION → 제외
  - CHATTER → 제외
  - QUESTION → 보조 저장
  - OFF_TOPIC → 제외
        ↓
[Agent 최종 결정] (다음)
        ↓
[감정/항목 분석]
        ↓
[보고서 생성]
```

---

## 💾 DB 연동

```python
import psycopg2
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier

conn = psycopg2.connect(...)
cursor = conn.cursor()

# 1차 필터 통과 댓글 가져오기
cursor.execute('''
    SELECT comment_id, text_original
    FROM raw_comments rc
    JOIN rule_filter_results rfr ON rc.comment_id = rfr.comment_id
    WHERE rfr.filter_status = 'PASS'
    AND rc.comment_id NOT IN (SELECT comment_id FROM llm_classifications)
''')

comments = cursor.fetchall()

# LLM 분류
classifier = create_groq_classifier()
texts = [c[1] for c in comments]
results = classifier.classify_batch(texts)

# llm_classifications 테이블 저장
for (comment_id, _), result in zip(comments, results):
    cursor.execute('''
        INSERT INTO llm_classifications (
            comment_id, label, confidence, reasoning,
            classifier_type, model_name, prompt_version, llm_provider
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        comment_id,
        result.label.value,
        result.confidence,
        result.rationale_short,
        result.classifier_type.value,
        result.model_name,
        result.prompt_version,
        result.llm_provider
    ))

conn.commit()
```

---

## 📊 성능 지표

### Few-shot 방식 (현재)
- **모델**: Groq Llama-3.3-70b-versatile
- **처리 속도**: ~2-3초/댓글
- **비용**: 매우 저렴 (Groq 무료 티어)
- **정확도**: 85-90% (예상)

### Fine-tuned 방식 (향후)
- **처리 속도**: ~0.5-1초/댓글
- **비용**: 초기 학습 비용 필요
- **정확도**: 90-95% (예상)

---

## 🔧 설정 커스터마이징

```python
from comment_filtering_agent.classifiers.models import ClassificationConfig

# 엄격한 분류 (프리미엄 제품)
strict_config = ClassificationConfig(
    model_name="llama-3.3-70b-versatile",
    temperature=0.0,              # 낮은 temperature
    include_examples=True,        # 예시 포함
    max_retries=5                 # 재시도 많이
)

# 빠른 분류 (일반 제품)
fast_config = ClassificationConfig(
    model_name="llama-3.1-8b-instant",
    temperature=0.2,
    include_examples=False,       # 예시 없음 (빠름)
    max_retries=2
)
```

---

## 📂 폴더 구조

```
comment_filtering_agent/
├── prompts/
│   ├── system_prompt.md              # 시스템 프롬프트
│   ├── few_shot_examples.md          # 25개 예시
│   ├── user_prompt_template.md       # 유저 프롬프트
│   └── classification_schema.json    # JSON 스키마
├── classifiers/
│   ├── models.py                     # 데이터 모델
│   ├── prompt_builder.py             # 프롬프트 빌더
│   ├── base_classifier.py            # 추상 클래스
│   └── groq_classifier.py            # Groq 구현체
├── tests/
│   └── test_llm_classifier.py        # 테스트 (7개)
└── examples/
    └── example_llm_classifier.py     # 예시 (7개)
```

---

## 🧪 테스트 실행

```bash
# 테스트 실행 (API 호출 없음)
cd comment_filtering_agent
python -m tests.test_llm_classifier

# 예시 실행 (의사 코드만)
python -m examples.example_llm_classifier
```

---

## ⚙️ 의존성

```bash
# 필수
pip install groq>=0.4.0

# 환경변수 설정
export GROQ_API_KEY="your_api_key"
```

---

## 📌 다음 단계

1. **Agent 결정 로직** 구현
   - 규칙 필터 + LLM 분류 결과 조합
   - 최종 액션 결정 (ANALYZE/AUXILIARY/EXCLUDE/HOLD/RECLASSIFY)
   - 저확신 댓글 재판단

2. **감정 분석** 구현
   - PRODUCT_OPINION 댓글 대상
   - Positive/Neutral/Negative
   - Sentiment score

3. **항목 추출** 구현
   - Aspect extraction (발열, 배터리, 성능 등)
   - Aspect-level sentiment

---

## ✨ 완료!

2단계 LLM 댓글 분류기가 완벽하게 설계되었습니다! 🎉

- ✅ 5개 라벨 명확히 정의
- ✅ 25개 Few-shot 예시
- ✅ JSON 스키마
- ✅ Python 구현체 (Groq)
- ✅ 프롬프트 빌더
- ✅ DB 연동 준비

다음은 **Agent 결정 로직**을 구현하면 됩니다!
