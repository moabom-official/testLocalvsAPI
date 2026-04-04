# 제품 질문 처리 모듈 - 구현 가이드

## 📦 개요

QUESTION으로 분류된 댓글을 처리하여 **제품 관련 질문을 보조 분석 데이터로 저장**하는 모듈입니다.

---

## 🎯 목적

- ✅ 제품 관련 질문만 선별하여 저장
- ✅ 질문의 주제/카테고리 분류
- ✅ 구매 의도 및 긴급도 파악
- ✅ FAQ 생성 및 콘텐츠 개선 포인트 도출

---

## 📁 파일 구조

```
comment_filtering_agent/analyzers/
├── question_models.py              # 데이터 모델 (4.5 KB)
└── question_processor.py           # 프로세서 (12 KB)

comment_filtering_agent/prompts/
└── question_analysis_prompt.md     # 프롬프트 (7.9 KB)

comment_filtering_agent/examples/
└── example_question_processor.py   # 예시 (8 examples)
```

---

## 🔍 추출 정보

### 1. 기본 정보
- `question_text`: 추출된 질문 텍스트
- `is_product_related`: 제품 관련 여부 (TRUE/FALSE)

### 2. 분류 정보
- `categories`: 질문 카테고리 리스트 (다중 가능)
- `primary_category`: 주 카테고리 (단일)

### 3. 구매 관련
- `has_buying_intent`: 구매 의도 포함 여부
- `urgency`: 긴급도 (HIGH / MEDIUM / LOW)

### 4. 답변 가능성
- `answerable_from_video`: 영상에서 답변 가능 여부

### 5. 추가 정보
- `mentioned_aspects`: 언급된 제품 특성
- `keywords`: 주요 키워드

---

## 📊 질문 카테고리 (14개)

| 카테고리 | 설명 | 예시 |
|---------|------|------|
| **성능** | 전반적인 성능 | "빠른가요?", "버벅이나요?" |
| **게임** | 게임 성능 | "게임 돌아가나요?", "프레임은?" |
| **발열** | 발열 관련 | "뜨거운가요?", "발열 심한가요?" |
| **배터리** | 배터리 관련 | "오래가나요?", "충전 빠른가요?" |
| **가격** | 가격 관련 | "얼마인가요?", "할인하나요?" |
| **카메라** | 카메라 성능 | "사진 잘 나오나요?" |
| **호환성** | 호환성/연결 | "맥북에서 되나요?" |
| **내구성** | 내구성/품질 | "튼튼한가요?", "고장 잘 나나요?" |
| **디스플레이** | 화면 관련 | "화면 밝나요?" |
| **디자인** | 디자인/외관 | "예쁜가요?", "크기는?" |
| **기능** | 기능/스펙 | "이 기능 있나요?" |
| **구매추천** | 구매 추천 | "살까요?", "괜찮을까요?" |
| **비교** | 제품 비교 | "A vs B 어느게 좋나요?" |
| **기타** | 기타 | 위에 해당 안 됨 |

---

## 🚀 사용법

### 기본 사용
```python
from comment_filtering_agent.analyzers.question_processor import create_processor

# 프로세서 생성
processor = create_processor()

# 단일 질문 처리
comment = "이거 게임 돌아가나요?"
question = processor.process_single(comment)

if question:
    print(f"카테고리: {question.primary_category.value}")
    print(f"구매 의도: {question.has_buying_intent}")
    print(f"키워드: {question.keywords}")
```

### 배치 처리
```python
comments = [
    "이거 게임 돌아가나요?",
    "배터리 오래가나요?",
    "배경음악 제목 뭔가요?"  # 제품 무관 → 자동 필터링
]

# 제품 관련 질문만 반환
questions = processor.process_batch(comments)
```

### 통계 생성
```python
stats = processor.get_statistics(questions)

print(f"총 질문: {stats['total_questions']}개")
print(f"제품 관련: {stats['product_related_pct']}%")
print(f"구매 의도: {stats['buying_intent_pct']}%")
print(f"TOP 카테고리: {stats['top_categories'][:3]}")
```

---

## 📤 출력 형식

```json
{
  "question_text": "이거 게임 돌아가나요?",
  "is_product_related": true,
  "categories": ["게임", "성능"],
  "primary_category": "게임",
  "has_buying_intent": false,
  "urgency": "LOW",
  "answerable_from_video": true,
  "mentioned_aspects": ["게임"],
  "keywords": ["게임", "돌아가나요"],
  "reasoning": "게임 성능에 대한 질문",
  "confidence": 0.95
}
```

---

## 💾 데이터베이스 매핑

### product_questions 테이블

```sql
INSERT INTO product_questions (
    comment_id,
    question_text,              -- question.question_text
    question_category_id,       -- question_categories 테이블 FK
    is_product_related,         -- question.is_product_related
    is_answered,                -- (향후 사용)
    mentioned_aspects,          -- question.mentioned_aspects (ARRAY)
    question_keywords,          -- question.keywords (ARRAY)
    priority,                   -- urgency 기반 (HIGH=3, MEDIUM=2, LOW=1)
    stored_at
) VALUES (...)
```

### question_categories 테이블 (메타데이터)

```sql
-- 미리 정의된 카테고리
INSERT INTO question_categories (category_name, category_name_en) VALUES
('성능', 'performance'),
('게임', 'gaming'),
('발열', 'heat'),
('배터리', 'battery'),
...
```

---

## 🔗 Agent와 통합

```python
from comment_filtering_agent.core.models import AgentAction
from comment_filtering_agent.analyzers.question_processor import create_processor

# Agent 결정 후
if decision.final_action == AgentAction.AUXILIARY_STORE:
    if classification.label == "QUESTION":
        # 질문 처리
        processor = create_processor()
        question = processor.process_single(comment)
        
        if question and question.is_product_related:
            # DB 저장
            # - product_questions 테이블
            pass
```

---

## 📈 활용 방안

### 1. FAQ 자동 생성
```python
# 자주 묻는 질문 TOP 10 추출
category_questions = defaultdict(list)

for question in questions:
    category_questions[question.primary_category.value].append(
        question.question_text
    )

# 카테고리별 FAQ
for category, q_list in category_questions.items():
    print(f"## {category}")
    for q in q_list[:5]:  # 상위 5개
        print(f"Q: {q}")
        print(f"A: [영상 참조 또는 수동 답변]")
```

### 2. 리뷰 콘텐츠 개선 포인트
```python
# 영상에서 답변 불가능한 질문 추출
unanswered_questions = [
    q for q in questions
    if not q.answerable_from_video
]

# 카테고리별 집계
category_counts = Counter([q.primary_category.value for q in unanswered_questions])

print("다음 리뷰 영상에서 다뤄야 할 주제:")
for category, count in category_counts.most_common(5):
    print(f"- {category}: {count}건")
```

### 3. 우선순위 질문 추출
```python
# 긴급 + 구매 의도 질문
priority_questions = [
    q for q in questions
    if q.has_buying_intent and q.urgency == UrgencyLevel.HIGH
]

# 빠른 답변 필요
for q in priority_questions:
    print(f"[긴급] {q.question_text}")
    # → 댓글 답변 또는 FAQ 업데이트
```

### 4. 제품 관심 포인트 파악
```python
# mentioned_aspects 집계
all_aspects = []
for question in questions:
    all_aspects.extend(question.mentioned_aspects)

aspect_counts = Counter(all_aspects)

print("사용자들이 가장 궁금해하는 제품 특성:")
for aspect, count in aspect_counts.most_common(10):
    print(f"{aspect}: {count}건")
```

### 5. 구매 전환율 분석
```python
# 구매 의도 질문 비율
buying_intent_ratio = sum(1 for q in questions if q.has_buying_intent) / len(questions)

print(f"구매 의도 질문 비율: {buying_intent_ratio * 100:.1f}%")

# 높으면 → 제품 관심도 높음
# 낮으면 → 정보 수집 단계
```

---

## 🧪 검증 예시

```python
"""간단한 검증"""
from comment_filtering_agent.analyzers.question_models import QuestionCategory

# 모델 import
assert QuestionCategory.GAMING.value == "게임"
assert QuestionCategory.BATTERY.value == "배터리"

print("[OK] Models imported")

# 프롬프트 파일 확인
from pathlib import Path
prompt_file = Path("comment_filtering_agent/prompts/question_analysis_prompt.md")
assert prompt_file.exists()

print("[OK] Prompt file exists")
print(f"[OK] Prompt size: {prompt_file.stat().st_size} bytes")
```

---

## ⚙️ 설정 옵션

```python
from comment_filtering_agent.analyzers.question_models import QuestionProcessorConfig

config = QuestionProcessorConfig(
    model_name="llama-3.3-70b-versatile",
    temperature=0.1,
    max_tokens=800,
    min_confidence=0.5,              # 최소 신뢰도
    require_product_related=True,    # 제품 무관 질문 자동 필터링
    max_retries=3,
    retry_delay=1.0
)

processor = ProductQuestionProcessor(config=config)
```

---

## 📊 통계 출력 예시

```
총 질문: 50개
제품 관련: 42개 (84.0%)
구매 의도: 15개 (30.0%)
영상 답변 가능: 38개 (76.0%)

긴급도 분포:
  HIGH: 5개
  MEDIUM: 12개
  LOW: 25개

카테고리 분포 (TOP 5):
  게임: 12개
  배터리: 8개
  발열: 7개
  가격: 6개
  성능: 5개
```

---

## 🔮 향후 확장

### 1. 질문 답변 매칭
```python
# 질문 → FAQ 자동 매칭
# 유사도 기반 검색
```

### 2. 질문 우선순위 자동 정렬
```python
# 긴급도 + 구매 의도 + 빈도 기반 점수
priority_score = (
    urgency_weight * urgency +
    intent_weight * buying_intent +
    frequency_weight * frequency
)
```

### 3. 답변 제안 생성
```python
# LLM 기반 답변 초안 생성
# 영상 내용 기반 자동 답변
```

---

## 📝 완료 체크리스트

- [x] 데이터 모델 (QuestionCategory, ProductQuestion, Config)
- [x] 프롬프트 (system, few-shot 8개, user template)
- [x] 프로세서 (ProductQuestionProcessor)
- [x] 제품 무관 필터링
- [x] 배치 처리
- [x] 통계 생성
- [x] 예시 코드 (8개)
- [x] DB 매핑 가이드
- [x] 활용 방안 (5가지)

---

## 🎉 요약

**QUESTION 댓글 처리 모듈**이 완성되었습니다!

- ✅ 제품 관련 질문만 선별
- ✅ 14개 카테고리 분류
- ✅ 구매 의도 및 긴급도 파악
- ✅ FAQ 생성 가능
- ✅ 콘텐츠 개선 포인트 도출

**다음 단계**: 보고서 생성 모듈
