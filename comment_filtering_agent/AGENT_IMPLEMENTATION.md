# 댓글 필터링 Agent 구현 완료 ✅

## 📦 생성된 파일

### 1. 핵심 모듈
- **`core/models.py`** - 데이터 모델 (AgentDecision, AgentAction, ExclusionReason, AgentPolicyConfig)
- **`core/agent.py`** - AgentDecisionEngine 메인 엔진 (560줄)
- **`core/AGENT_DECISION_POLICY.md`** - 의사결정 정책 문서

### 2. 테스트
- **`tests/test_agent.py`** - 13개 테스트 케이스

---

## 🎯 Agent 역할

**조정자(Coordinator)**: 단순 분류기가 아닌 의사결정 엔진

```
[1차 규칙 필터 결과] + [2차 LLM 분류 결과]
            ↓
    [Agent Decision Engine]
            ↓
[최종 액션 결정] + [다음 단계 플래그]
```

---

## 🔄 최종 액션 (5가지)

| 액션 | 설명 | 다음 단계 |
|------|------|-----------|
| **ANALYZE** | 제품 평가 댓글 분석 | 감정 분석 + 항목 추출 |
| **AUXILIARY_STORE** | 보조 데이터 저장 | product_questions 테이블 |
| **EXCLUDE** | 제외 (분석 안 함) | excluded_comments_log |
| **HOLD** | 보류 (판단 불가) | 수동 검토 대기 |
| **RECLASSIFY** | 재분류 필요 | reclassification_queue |

---

## 📊 의사결정 테이블

### 우선순위 1: 1차 필터 결과

| 1차 필터 | 최종 액션 | 설명 |
|---------|----------|------|
| **REJECT** (모든 사유) | **EXCLUDE** | 규칙 위반 → 무조건 제외 |
| **PASS** | → 2차 분류 검토 | |

### 우선순위 2: 2차 LLM 분류 (1차 PASS인 경우)

| LLM 라벨 | 조건 | 최종 액션 |
|---------|------|----------|
| **PRODUCT_OPINION** | 확신도 ≥ 0.6 | **ANALYZE** |
| **PRODUCT_OPINION** | 확신도 < 0.6 | **HOLD** |
| **PRODUCT_OPINION** | needs_recheck=true | **RECLASSIFY** |
| **QUESTION** | 제품 관련 | **AUXILIARY_STORE** |
| **QUESTION** | 제품 무관 | **EXCLUDE** |
| **VIDEO_REACTION** | - | **EXCLUDE** |
| **CHATTER** | - | **EXCLUDE** |
| **CHATTER** | needs_recheck + 확신도<0.7 | **RECLASSIFY** |
| **OFF_TOPIC** | - | **EXCLUDE** |

### 특수 케이스

| 조건 | 최종 액션 |
|------|----------|
| 1차 PASS + LLM 실패 | **HOLD** |
| 확신도 < 0.5 | **HOLD** |
| needs_recheck=true | **RECLASSIFY** |

---

## 🚀 사용 예시

### 기본 사용
```python
from comment_filtering_agent.core.agent import AgentDecisionEngine
from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier

# 1. 엔진 생성
rule_filter = RuleBasedFilter()
llm_classifier = create_groq_classifier()
agent = AgentDecisionEngine()

# 2. 파이프라인 실행
comments = ["발열은 심한데 성능은 좋네요", "ㅋㅋㅋㅋㅋ"]

# 1차 필터
filter_results = rule_filter.filter_batch(comments)

# 2차 분류 (1차 통과만)
passed_comments = [c for c, r in zip(comments, filter_results) if r.is_passed]
classification_results = llm_classifier.classify_batch(passed_comments)

# 3. Agent 결정
decisions = agent.decide_batch(
    comments=comments,
    filter_results=filter_results,
    classification_results=classification_results
)

# 4. 액션별 처리
for decision in decisions:
    if decision.final_action == AgentAction.ANALYZE:
        # 감정/항목 분석
        print(f"Analyze: {decision.original_comment}")
    elif decision.final_action == AgentAction.AUXILIARY_STORE:
        # 질문 저장
        print(f"Store Question: {decision.original_comment}")
    elif decision.final_action == AgentAction.EXCLUDE:
        # 제외 로그
        print(f"Exclude: {decision.exclusion_reason.value}")
```

---

## 📐 출력 구조

```python
AgentDecision(
    index=0,
    original_comment="발열은 심한데 성능은 좋네요",
    
    # 최종 결정
    final_action=AgentAction.ANALYZE,
    final_reason="제품 평가 댓글 분석 진행 (확신도: 0.95)",
    
    # 다음 단계 플래그
    should_run_sentiment=True,
    should_run_aspect_analysis=True,
    should_store_as_question=False,
    should_send_llm_recheck=False,
    
    # 제외 정보
    exclusion_reason=None,
    exclusion_details=None,
    
    # 메타정보
    is_low_confidence=False,
    needs_human_review=False,
    needs_reclassification=False,
    decision_reasoning="1차 필터 PASS → 2차 분류: PRODUCT_OPINION, 확신도: 0.95 (HIGH) → ...",
    agent_version="1.0",
    decided_at=datetime.now(),
    
    # 입력 참조
    rule_filter_passed=True,
    llm_label="PRODUCT_OPINION",
    llm_confidence=0.95
)
```

---

## 🧪 테스트 케이스 (13개)

### 통과한 테스트
1. ✅ 1차 필터 REJECT → EXCLUDE
2. ✅ PRODUCT_OPINION + 고확신 → ANALYZE
3. ✅ PRODUCT_OPINION + 저확신 → HOLD
4. ✅ QUESTION + 제품 관련 → AUXILIARY_STORE
5. ✅ QUESTION + 제품 무관 → EXCLUDE
6. ✅ VIDEO_REACTION → EXCLUDE
7. ✅ CHATTER → EXCLUDE
8. ✅ OFF_TOPIC → EXCLUDE
9. ✅ needs_recheck=True → RECLASSIFY
10. ✅ LLM 실패 → HOLD
11. ✅ CHATTER + 낮은 확신 + needs_recheck → RECLASSIFY
12. ✅ 커스텀 정책 (exclude_all_questions=True)
13. ✅ 배치 처리

```
모든 테스트 통과! (13/13)
```

---

## ⚙️ 정책 설정

### 기본 설정
```python
AgentPolicyConfig(
    version="1.0",
    description="기본 의사결정 정책",
    
    # 확신도 임계값
    high_confidence_threshold=0.8,
    medium_confidence_threshold=0.6,
    low_confidence_threshold=0.5,
    hold_below_confidence=0.5,
    
    # 정책 플래그
    exclude_all_questions=False,
    allow_video_reaction_with_features=False,
    hold_instead_of_reclassify=False
)
```

### 커스텀 설정
```python
# 엄격한 정책
strict_policy = AgentPolicyConfig(
    high_confidence_threshold=0.9,      # 더 높은 기준
    exclude_all_questions=True,         # 모든 질문 제외
    hold_instead_of_reclassify=True     # 재분류 대신 보류
)

strict_agent = AgentDecisionEngine(policy_config=strict_policy)
```

---

## 🔧 정책 수정 포인트

### 1. 확신도 임계값 조정
```python
policy = AgentPolicyConfig(
    high_confidence_threshold=0.85,  # 0.8 → 0.85 (더 엄격)
    medium_confidence_threshold=0.65,
    low_confidence_threshold=0.50
)
```

### 2. QUESTION 처리 변경
```python
# 현재: 제품 관련 → AUXILIARY_STORE
# 변경: 모든 질문 → EXCLUDE
policy = AgentPolicyConfig(
    exclude_all_questions=True
)
```

### 3. VIDEO_REACTION 예외
```python
# 현재: 무조건 EXCLUDE
# 변경: 제품 특성 3개 이상 언급 → ANALYZE
policy = AgentPolicyConfig(
    allow_video_reaction_with_features=True,
    min_product_features_for_analysis=3
)
```

### 4. 저확신 처리 전략
```python
# 현재: 저확신 → RECLASSIFY
# 변경: 저확신 → HOLD (보류)
policy = AgentPolicyConfig(
    hold_instead_of_reclassify=True
)
```

### 5. 1차 필터 예외 허용
```python
# 현재: 1차 REJECT → 무조건 EXCLUDE
# 변경: 특정 사유는 2차 분류로 넘김
policy = AgentPolicyConfig(
    allow_llm_override_rules=["TOO_SHORT", "EMOJI_HEAVY"]
)
# (코드 수정 필요)
```

---

## 💾 DB 연동

```python
import psycopg2
from comment_filtering_agent.core.agent import AgentDecisionEngine

conn = psycopg2.connect(...)
cursor = conn.cursor()

# 1~2단계 결과 가져오기
cursor.execute('''
    SELECT 
        rc.comment_id,
        rc.text_original,
        rfr.filter_status,
        lc.label,
        lc.confidence
    FROM raw_comments rc
    JOIN rule_filter_results rfr ON rc.comment_id = rfr.comment_id
    LEFT JOIN llm_classifications lc ON rc.comment_id = lc.comment_id
    WHERE rc.comment_id NOT IN (
        SELECT comment_id FROM agent_decisions
    )
''')

# Agent 결정
agent = AgentDecisionEngine()
for row in cursor.fetchall():
    comment_id, text, filter_status, label, confidence = row
    
    # ... FilterResult, ClassificationResult 생성 ...
    
    decision = agent.decide(text, filter_result, classification_result)
    
    # agent_decisions 테이블 저장
    cursor.execute('''
        INSERT INTO agent_decisions (
            comment_id,
            final_action,
            next_stage,
            exclusion_reason,
            is_low_confidence,
            needs_human_review,
            needs_reclassification,
            decision_reasoning,
            agent_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        comment_id,
        decision.final_action.value,
        decision.next_stage,
        decision.exclusion_reason.value if decision.exclusion_reason else None,
        decision.is_low_confidence,
        decision.needs_human_review,
        decision.needs_reclassification,
        decision.decision_reasoning,
        decision.agent_version
    ))

conn.commit()
```

---

## 📂 폴더 구조

```
comment_filtering_agent/
├── core/
│   ├── __init__.py
│   ├── models.py                      ← 데이터 모델
│   ├── agent.py                       ← Agent 엔진 (560줄)
│   └── AGENT_DECISION_POLICY.md       ← 정책 문서
├── filters/
│   └── rule_based_filter.py           ← 1차 필터
├── classifiers/
│   └── groq_classifier.py             ← 2차 분류기
└── tests/
    └── test_agent.py                  ← 테스트 (13개)
```

---

## 🔄 전체 파이프라인

```
[YouTube 댓글 수집]
        ↓
[1차 규칙 필터] ✅
        ↓
[2차 LLM 분류] ✅
        ↓
[Agent 최종 결정] ✅ 현재 완료
        ↓
┌───────────┬──────────────┬──────────┬──────┬─────────────┐
│  ANALYZE  │ AUXILIARY_   │ EXCLUDE  │ HOLD │ RECLASSIFY  │
│           │   STORE      │          │      │             │
└───────────┴──────────────┴──────────┴──────┴─────────────┘
     ↓              ↓            ↓        ↓         ↓
[감정/항목]    [질문 저장]  [제외 로그] [수동]  [재분류큐]
  분석                                   검토
```

---

## 📊 통계 추적

```python
from collections import Counter

decisions = agent.decide_batch(comments, filter_results, classification_results)

# 액션별 분포
action_counts = Counter(d.final_action.value for d in decisions)
print("액션 분포:")
for action, count in action_counts.most_common():
    print(f"  {action}: {count}개")

# 제외 사유별 분포
exclusion_counts = Counter(
    d.exclusion_reason.value
    for d in decisions
    if d.exclusion_reason
)
print("\n제외 사유:")
for reason, count in exclusion_counts.most_common():
    print(f"  {reason}: {count}개")

# 저확신 비율
low_confidence = sum(1 for d in decisions if d.is_low_confidence)
print(f"\n저확신 댓글: {low_confidence}개 ({low_confidence/len(decisions)*100:.1f}%)")
```

---

## 🎨 주요 특징

### 1. 명확한 우선순위
- **1순위**: 1차 필터 (REJECT → 무조건 EXCLUDE)
- **2순위**: 2차 분류 라벨
- **3순위**: 확신도 & needs_recheck

### 2. Explainable (설명 가능)
```python
decision.decision_reasoning
# "1차 필터 PASS → 2차 분류: PRODUCT_OPINION, 확신도: 0.95 (HIGH) → 제품 평가 댓글 → ANALYZE"
```

### 3. 확장 가능
- **AgentPolicyConfig**로 정책 커스터마이징
- 라벨별 처리 로직 분리
- 버전 관리 (`agent_version`)

### 4. 안전한 기본값
- 애매한 경우 → HOLD (보류)
- LLM 실패 → HOLD
- 매우 낮은 확신 → HOLD

---

## 📌 다음 단계

1. **감정 분석** 구현 (ANALYZE 액션 처리)
   - Positive/Neutral/Negative
   - Sentiment score
   - sentiment_analysis 테이블 저장

2. **항목 추출** 구현 (ANALYZE 액션 처리)
   - Aspect extraction (발열, 배터리, 성능 등)
   - Aspect-level sentiment
   - aspect_extractions 테이블 저장

3. **질문 저장** 구현 (AUXILIARY_STORE 액션 처리)
   - product_questions 테이블
   - 카테고리 분류
   - FAQ 생성 준비

4. **재분류 로직** 구현 (RECLASSIFY 액션 처리)
   - reclassification_queue 테이블
   - 우선순위 관리
   - 재분류 실행

---

## ✨ 완료!

댓글 필터링 Agent가 완벽하게 구현되었습니다! 🎉

- ✅ 5개 최종 액션
- ✅ 명확한 의사결정 테이블
- ✅ 13개 테스트 케이스 통과
- ✅ 정책 커스터마이징 가능
- ✅ DB 연동 준비
- ✅ 전체 파이프라인 3단계 완료

다음은 **감정 분석과 항목 추출**을 구현하면 됩니다!
