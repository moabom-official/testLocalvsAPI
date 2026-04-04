# 댓글 필터링 Agent 의사결정 정책

## 개요

Agent는 **조정자(Coordinator)** 역할로서, 1차 규칙 필터와 2차 LLM 분류 결과를 종합하여 최종 결정을 내립니다.

---

## 최종 액션 (Final Action)

| 액션 | 설명 | 다음 단계 |
|------|------|-----------|
| **ANALYZE** | 제품 평가 댓글로 분석 진행 | 감정 분석 + 항목 추출 |
| **AUXILIARY_STORE** | 보조 데이터로 저장 | product_questions 테이블 저장 |
| **EXCLUDE** | 제외 (분석 안 함) | excluded_comments_log 저장 |
| **HOLD** | 보류 (판단 불가) | 수동 검토 대기 |
| **RECLASSIFY** | 재분류 필요 | reclassification_queue 추가 |

---

## 의사결정 테이블

### 우선순위 1: 1차 필터 결과

| 1차 필터 상태 | 제외 사유 | 최종 액션 | 이유 |
|--------------|-----------|----------|------|
| **REJECT** | TOO_SHORT | **EXCLUDE** | 정보량 부족 |
| **REJECT** | EMOJI_HEAVY | **EXCLUDE** | 의미 없는 이모지 |
| **REJECT** | LOW_INFORMATION | **EXCLUDE** | 반복 문자 (ㅋㅋㅋ) |
| **REJECT** | GREETING_ONLY | **EXCLUDE** | 인사만 |
| **REJECT** | REACTION_ONLY | **EXCLUDE** | 반응만 |
| **REJECT** | URL_SPAM | **EXCLUDE** | 광고/스팸 |
| **REJECT** | PROMOTIONAL | **EXCLUDE** | 홍보성 |
| **REJECT** | CREATOR_PRAISE_ONLY | **EXCLUDE** | 유튜버 칭찬만 |
| **REJECT** | ABUSIVE | **EXCLUDE** | 욕설/비속어 |
| **REJECT** | DUPLICATE_CANDIDATE | **EXCLUDE** | 중복 댓글 |
| **REJECT** | SPECIAL_CHARS_ONLY | **EXCLUDE** | 특수문자만 |

**규칙**: 1차 필터에서 reject되면 **무조건 EXCLUDE** (예외 없음)

---

### 우선순위 2: 2차 LLM 분류 결과 (1차 PASS인 경우)

| LLM 라벨 | 제품 관련 | 확신도 | 재확인 필요 | 최종 액션 | 이유 |
|---------|----------|--------|------------|----------|------|
| **PRODUCT_OPINION** | ✓ | High (≥0.8) | ✗ | **ANALYZE** | 명확한 제품 평가 |
| **PRODUCT_OPINION** | ✓ | Medium (0.6-0.8) | ✗ | **ANALYZE** | 제품 평가 (중간 확신) |
| **PRODUCT_OPINION** | ✓ | Low (<0.6) | ✓ | **HOLD** | 확신 낮음 → 보류 |
| **PRODUCT_OPINION** | ✓ | Any | ✓ | **RECLASSIFY** | 재확인 필요 → 재분류 |
| **QUESTION** | ✓ | High | ✗ | **AUXILIARY_STORE** | 제품 질문 저장 |
| **QUESTION** | ✓ | Medium/Low | ✗ | **AUXILIARY_STORE** | 제품 질문 저장 |
| **QUESTION** | ✗ | Any | ✗ | **EXCLUDE** | 제품 무관 질문 |
| **VIDEO_REACTION** | - | Any | ✗ | **EXCLUDE** | 영상 반응 제외 |
| **CHATTER** | - | Any | ✗ | **EXCLUDE** | 잡담/무의미 |
| **OFF_TOPIC** | - | Any | ✗ | **EXCLUDE** | 제품 무관 |

---

### 우선순위 3: 특수 케이스

| 조건 | 최종 액션 | 이유 |
|------|----------|------|
| 1차 PASS + LLM 실패 | **HOLD** | LLM 오류 → 보류 |
| 1차 PASS + LLM timeout | **RECLASSIFY** | 재시도 가능 |
| 확신도 < 0.5 | **HOLD** | 매우 낮은 확신 → 보류 |
| needs_recheck = true + 확신도 < 0.7 | **RECLASSIFY** | 재분류 필요 |

---

## 의사결정 흐름도

```
[원본 댓글]
    ↓
[1차 규칙 필터]
    ↓
REJECT? ─── YES ──→ [EXCLUDE]
    ↓ NO
[2차 LLM 분류]
    ↓
┌─────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│PRODUCT_OPINION│  QUESTION   │VIDEO_REACTION│   CHATTER    │  OFF_TOPIC   │
└─────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
    ↓              ↓               ↓              ↓              ↓
확신도 체크?   제품 관련?        -             -              -
    ↓              ↓               ↓              ↓              ↓
High: ANALYZE  Yes: AUXILIARY    EXCLUDE      EXCLUDE        EXCLUDE
Med: ANALYZE   No: EXCLUDE
Low: HOLD/RECLASSIFY
```

---

## 플래그 결정 로직

### should_run_sentiment
- **True**: final_action = ANALYZE
- **False**: 그 외

### should_run_aspect_analysis
- **True**: final_action = ANALYZE
- **False**: 그 외

### should_store_as_question
- **True**: final_action = AUXILIARY_STORE AND label = QUESTION
- **False**: 그 외

### should_send_llm_recheck
- **True**: final_action = RECLASSIFY
- **False**: 그 외

---

## 제외 사유 매핑 (exclusion_reason)

| 최종 액션 | LLM 라벨/필터 사유 | exclusion_reason |
|----------|-------------------|------------------|
| EXCLUDE | 1차 필터 REJECT | `RULE_FILTERED` |
| EXCLUDE | VIDEO_REACTION | `VIDEO_REACTION` |
| EXCLUDE | CHATTER | `CHATTER` |
| EXCLUDE | OFF_TOPIC | `OFF_TOPIC` |
| EXCLUDE | QUESTION (제품 무관) | `OFF_TOPIC_QUESTION` |

---

## 확신도 임계값

| 임계값 | 범위 | 처리 |
|--------|------|------|
| **High** | ≥ 0.8 | 정상 처리 |
| **Medium** | 0.6 ~ 0.8 | 정상 처리 (주의) |
| **Low** | 0.5 ~ 0.6 | HOLD 또는 RECLASSIFY |
| **Very Low** | < 0.5 | HOLD (보류) |

기본값:
- `high_confidence_threshold` = 0.8
- `medium_confidence_threshold` = 0.6
- `low_confidence_threshold` = 0.5

---

## 의사결정 예시

### 예시 1: 명확한 제품 평가
```
입력:
  - 댓글: "발열은 심한데 성능은 좋네요"
  - 1차 필터: PASS
  - 2차 분류: PRODUCT_OPINION, confidence=0.95

출력:
  - final_action: ANALYZE
  - should_run_sentiment: True
  - should_run_aspect_analysis: True
```

### 예시 2: 제품 관련 질문
```
입력:
  - 댓글: "이거 게임도 잘 돌아가나요?"
  - 1차 필터: PASS
  - 2차 분류: QUESTION, is_product_related=True

출력:
  - final_action: AUXILIARY_STORE
  - should_store_as_question: True
```

### 예시 3: 영상 반응
```
입력:
  - 댓글: "오늘 영상 재밌네요"
  - 1차 필터: PASS
  - 2차 분류: VIDEO_REACTION

출력:
  - final_action: EXCLUDE
  - exclusion_reason: VIDEO_REACTION
```

### 예시 4: 저확신 댓글
```
입력:
  - 댓글: "좋네요" (애매함)
  - 1차 필터: PASS
  - 2차 분류: CHATTER, confidence=0.55, needs_recheck=True

출력:
  - final_action: RECLASSIFY
  - should_send_llm_recheck: True
```

### 예시 5: 1차 필터 제외
```
입력:
  - 댓글: "ㅋㅋㅋㅋㅋㅋㅋ"
  - 1차 필터: REJECT (REACTION_ONLY)

출력:
  - final_action: EXCLUDE
  - exclusion_reason: RULE_FILTERED
  - (2차 분류 실행 안 됨)
```

---

## 정책 수정 포인트

### 1. 확신도 임계값 조정
```python
# config에서 조정 가능
policy_config = AgentPolicyConfig(
    high_confidence_threshold=0.85,  # 더 엄격하게
    medium_confidence_threshold=0.65,
    low_confidence_threshold=0.50
)
```

### 2. QUESTION 처리 정책 변경
```python
# 현재: 제품 관련 질문 → AUXILIARY_STORE
# 변경 가능: 모든 질문 → EXCLUDE
if policy_config.exclude_all_questions:
    return AgentAction.EXCLUDE
```

### 3. VIDEO_REACTION 예외 처리
```python
# 현재: 무조건 EXCLUDE
# 변경 가능: 제품 언급 많으면 → ANALYZE
if label == CommentLabel.VIDEO_REACTION:
    if len(mentioned_product_features) >= 3:
        return AgentAction.ANALYZE  # 제품 특성 많이 언급
```

### 4. 저확신 처리 전략
```python
# 현재: needs_recheck=True → RECLASSIFY
# 변경 가능: 일정 조건 충족 시 → HOLD (보류)
if needs_recheck and confidence < 0.6:
    if policy_config.hold_instead_of_reclassify:
        return AgentAction.HOLD
```

### 5. 1차 필터 예외 허용
```python
# 현재: 1차 REJECT → 무조건 EXCLUDE
# 변경 가능: 특정 사유는 2차 분류로 넘김
if filter_status == "REJECT":
    if reject_reason in policy_config.allow_llm_override:
        # 2차 분류 진행
        pass
```

---

## 성능 지표 추적

추적할 메트릭:
1. **액션별 분포**
   - ANALYZE: X%
   - AUXILIARY_STORE: Y%
   - EXCLUDE: Z%
   - HOLD: W%
   - RECLASSIFY: V%

2. **제외 사유별 분포**
   - RULE_FILTERED: X%
   - VIDEO_REACTION: Y%
   - CHATTER: Z%
   - OFF_TOPIC: W%

3. **재분류율**
   - RECLASSIFY 비율
   - 재분류 후 ANALYZE 전환율

4. **보류율**
   - HOLD 비율
   - 평균 확신도

---

## 정책 버전 관리

```python
class AgentPolicyConfig:
    version: str = "1.0"
    description: str = "기본 의사결정 정책"
    
    # 버전별 정책 변경 이력
    # v1.0 (2024-04-02):
    #   - 1차 필터 REJECT → 무조건 EXCLUDE
    #   - PRODUCT_OPINION → ANALYZE
    #   - QUESTION (제품 관련) → AUXILIARY_STORE
    #
    # v1.1 (예정):
    #   - 저확신 임계값 조정
    #   - VIDEO_REACTION 예외 처리 추가
```

---

## 요약

| 조건 | 최종 액션 | 한 줄 설명 |
|------|----------|-----------|
| 1차 REJECT | **EXCLUDE** | 규칙 위반 |
| PRODUCT_OPINION + 고확신 | **ANALYZE** | 감정/항목 분석 |
| PRODUCT_OPINION + 저확신 | **HOLD** | 보류 |
| QUESTION + 제품 관련 | **AUXILIARY_STORE** | 질문 저장 |
| QUESTION + 제품 무관 | **EXCLUDE** | 제외 |
| VIDEO_REACTION | **EXCLUDE** | 영상 반응 |
| CHATTER / OFF_TOPIC | **EXCLUDE** | 잡담/무관 |
| needs_recheck | **RECLASSIFY** | 재분류 |

이 정책은 **agent_decisions** 테이블의 설계와 1:1 매핑됩니다.
