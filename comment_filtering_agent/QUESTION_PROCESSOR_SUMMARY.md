# 제품 질문 처리 모듈 - 최종 요약

## ✅ 구현 완료

QUESTION 댓글을 처리하여 **제품 관련 질문을 보조 분석 데이터로 저장**하는 시스템이 완성되었습니다!

---

## 📦 생성된 파일 (5개)

### 1. **데이터 모델**
- `analyzers/question_models.py` (4.5 KB)
  - QuestionCategory (14개 카테고리)
  - UrgencyLevel (3단계)
  - ProductQuestion
  - QuestionProcessorConfig
  - CATEGORY_KEYWORDS 매핑

### 2. **프로세서**
- `analyzers/question_processor.py` (12 KB)
  - ProductQuestionProcessor 클래스
  - 제품 무관 질문 자동 필터링
  - 배치 처리
  - 통계 생성

### 3. **프롬프트**
- `prompts/question_analysis_prompt.md` (7.9 KB)
  - System Prompt
  - **8개 Few-shot Examples**
  - User Prompt Template
  - JSON Schema

### 4. **예시**
- `examples/example_question_processor.py` (8.2 KB)
  - **8개 사용 예시**
  - FAQ 생성 시뮬레이션
  - Agent 통합
  - 우선순위 추출

### 5. **문서**
- `QUESTION_PROCESSOR_IMPLEMENTATION.md` (7.9 KB)
  - 구현 가이드
  - DB 매핑
  - **5가지 활용 방안**

---

## 🎯 핵심 기능

### 1. 제품 관련 여부 판단
```python
{
  "is_product_related": true,  # 제품 관련
  "is_product_related": false  # 영상/음악/기타 → 제외
}
```

### 2. 질문 카테고리 분류 (14개)
```
성능, 게임, 발열, 배터리, 가격, 카메라, 호환성,
내구성, 디스플레이, 디자인, 기능, 구매추천, 비교, 기타
```

### 3. 구매 의도 파악
```python
{
  "has_buying_intent": true,    # "살까요?", "추천하시나요?"
  "urgency": "HIGH"              # 긴급도 (HIGH/MEDIUM/LOW)
}
```

### 4. 영상 답변 가능 여부
```python
{
  "answerable_from_video": true  # 영상에서 답변 가능
}
```

---

## 🚀 사용법

```python
from comment_filtering_agent.analyzers.question_processor import create_processor

# 프로세서 생성
processor = create_processor()

# 단일 질문 처리
question = processor.process_single("이거 게임 돌아가나요?")

if question:
    print(f"카테고리: {question.primary_category.value}")
    print(f"구매 의도: {question.has_buying_intent}")
    print(f"키워드: {question.keywords}")

# 배치 처리 (제품 무관 자동 필터링)
questions = processor.process_batch([
    "게임 돌아가나요?",           # ✓ 제품 관련
    "배경음악 제목 뭔가요?"       # ✗ 제품 무관 → 자동 제외
])

# 통계
stats = processor.get_statistics(questions)
```

---

## 💾 데이터베이스 매핑

### product_questions 테이블
```sql
INSERT INTO product_questions (
    comment_id,
    question_text,              -- "게임 돌아가나요?"
    question_category_id,       -- question_categories FK
    is_product_related,         -- true
    mentioned_aspects,          -- ["게임", "성능"]
    question_keywords,          -- ["게임", "돌아가나요"]
    priority,                   -- urgency 기반 점수
    stored_at
) VALUES (...)
```

---

## 📈 활용 방안 (5가지)

### 1. FAQ 자동 생성
```python
# 카테고리별 자주 묻는 질문 TOP 10
category_questions = defaultdict(list)
for q in questions:
    category_questions[q.primary_category.value].append(q.question_text)

# FAQ 출력
for category, q_list in category_questions.items():
    print(f"## {category}")
    for q in q_list[:5]:
        print(f"Q: {q}")
```

### 2. 리뷰 콘텐츠 개선 포인트
```python
# 영상에서 답변 불가능한 질문 추출
unanswered = [q for q in questions if not q.answerable_from_video]

# 다음 리뷰에서 다뤄야 할 주제
category_counts = Counter([q.primary_category.value for q in unanswered])
print("다음 영상에서 다룰 주제:")
for category, count in category_counts.most_common(5):
    print(f"- {category}: {count}건")
```

### 3. 우선순위 질문 추출
```python
# 긴급 + 구매 의도 질문 → 빠른 답변 필요
priority_questions = [
    q for q in questions
    if q.has_buying_intent and q.urgency == UrgencyLevel.HIGH
]
```

### 4. 제품 관심 포인트 파악
```python
# mentioned_aspects 집계
all_aspects = []
for q in questions:
    all_aspects.extend(q.mentioned_aspects)

aspect_counts = Counter(all_aspects)
print("가장 궁금해하는 제품 특성:")
for aspect, count in aspect_counts.most_common(10):
    print(f"{aspect}: {count}건")
```

### 5. 구매 전환율 분석
```python
buying_ratio = sum(1 for q in questions if q.has_buying_intent) / len(questions)
print(f"구매 의도 질문 비율: {buying_ratio * 100:.1f}%")

# 높으면 → 제품 관심도 높음
# 낮으면 → 단순 정보 수집
```

---

## 🔗 Agent와 통합

```python
from comment_filtering_agent.core.models import AgentAction

# Agent가 AUXILIARY_STORE 결정 후
if decision.final_action == AgentAction.AUXILIARY_STORE:
    if classification.label == "QUESTION":
        processor = create_processor()
        question = processor.process_single(comment)
        
        if question and question.is_product_related:
            # product_questions 테이블 저장
            save_to_db(question)
```

---

## 📊 출력 예시

```json
{
  "question_text": "지금 구매하려는데 발열이 심한가요?",
  "is_product_related": true,
  "categories": ["발열"],
  "primary_category": "발열",
  "has_buying_intent": true,
  "urgency": "HIGH",
  "answerable_from_video": true,
  "mentioned_aspects": ["발열"],
  "keywords": ["구매", "발열", "심한가요"],
  "reasoning": "구매 직전 상태, 발열 확인 질문",
  "confidence": 0.98
}
```

---

## 📊 통계 예시

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

## ✅ 검증 완료

```
[OK] Models imported successfully
[OK] QuestionCategory: 14 categories
[OK] UrgencyLevel: 3 levels
[OK] ProductQuestion: 게임
[OK] ProductQuestion.to_dict()
[OK] QuestionProcessorConfig
[OK] CATEGORY_KEYWORDS: 14 categories
[OK] All 5 files created
[OK] Prompt: 7,879 chars, 8 examples
```

---

## 📊 전체 파이프라인 완성도

```
[댓글 수집]
     ↓
[1차 규칙 필터] ✅ (11 rules)
     ↓
[2차 LLM 분류] ✅ (5 labels, 25 examples)
     ↓
[Agent 결정] ✅ (5 actions)
     ├─ ANALYZE → [감정 분석] ✅ (12 aspects)
     ├─ AUXILIARY → [질문 처리] ✅ (14 categories) ← NEW!
     └─ EXCLUDE → [제외 로그]
     ↓
[DB 저장] ✅
     ↓
[보고서 작성] ⏳ (다음 단계)
```

---

## 🎉 요약

**QUESTION 댓글 처리 모듈 구현 완료!**

- ✅ 제품 관련 질문만 선별 저장
- ✅ 14개 카테고리 자동 분류
- ✅ 구매 의도 및 긴급도 파악
- ✅ FAQ 생성 가능
- ✅ 콘텐츠 개선 포인트 도출
- ✅ 우선순위 질문 추출

**파이프라인 완성도**: ~95%  
**남은 작업**: 보고서 생성 모듈

---

**테스트 방법**:
```bash
# groq 패키지 설치
pip install groq

# API 키 설정
export GROQ_API_KEY="your-api-key"  # Linux/Mac
set GROQ_API_KEY=your-api-key       # Windows

# 예시 실행
python comment_filtering_agent/examples/example_question_processor.py
```

---

모든 핵심 모듈이 완성되었습니다! 🚀
