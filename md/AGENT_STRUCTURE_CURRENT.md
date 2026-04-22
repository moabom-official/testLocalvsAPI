# 댓글 필터링 Agent 현재 구조

> 기준일: 2026-04-21  
> 진입점: `scripts/api/sync.py` → `POST /products/{product_id}/sync`

---

## 1. 전체 파이프라인 흐름

```
POST /products/{product_id}/sync
        │
        ▼
[Phase 1] 영상 메타데이터 INSERT (순차)
  ← execute_update() × len(videos)
        │
        ▼
[Phase 2] 댓글 처리 병렬 실행
  ← ThreadPoolExecutor(max_workers=PARALLEL_WORKERS)
        │
   ┌────┼────┐  ... (PARALLEL_WORKERS개 동시)
   ▼    ▼    ▼
  [V1] [V2] [V3]
   │
   │  process_comments_with_agent(video_id, product_name)
   │
   ├─ Step 1: YouTube 댓글 수집
   │   └─ YouTubeCommentCollector.collect_comments()  max=1,000
   │
   ├─ Step 2: Spark 전처리
   │   └─ _spark_preprocess_comments()
   │       ├─ null/공백 제거
   │       ├─ exact dedup (video_id, author, text)
   │       └─ 메타 플래그 부착 (char_count, is_short, has_url, is_repetitive)
   │
   ├─ Step 3: DB 저장 + 규칙 필터 (Hard Gate)
   │   ├─ comments 테이블 INSERT
   │   ├─ RuleBasedFilter.filter_single() → PASS/REJECT
   │   ├─ rule_filter_results 테이블 INSERT
   │   └─ PASS만 candidate_comments에 추가
   │
   ├─ Step 4: 후보군 점수화 + 상위 300개 컷
   │   └─ _preprocess_candidate_pool()
   │       └─ score = keyword×4.0 + length×2.0 + engagement×1.0
   │
   ├─ Step 5: 다중 기준 선발 (상위 20개)
   │   └─ _select_comments_multicriteria()
   │       └─ 6개 소스 (like/reply/long/new/old/random) → hit_count 기반 선발
   │
   ├─ Step 5.5: 토큰 예산 트리밍
   │   └─ TOKEN_BUDGET_PER_VIDEO=2,000 초과 시 점수 낮은 댓글 제거
   │
   ├─ Step 6: LLM 배치 분류
   │   └─ OptimizedBatchClassifier.classify_batch()  batch_size=8
   │       └─ LangChain ChatGroq (GROQ_MODEL) → PRODUCT_OPINION / CHATTER / ...
   │
   └─ Step 7: Agent 판단 + 감성 분석 + DB 저장
       ├─ AgentDecisionEngine.decide()
       ├─ ANALYZE → GroqAspectSentimentAnalyzer.analyze_single()
       └─ comment_sentiments / aspect_extractions / agent_decisions INSERT
```

---

## 2. 컴포넌트 목록

### 2-1. 진입점 & 오케스트레이터

| 파일 | 역할 |
|------|------|
| `scripts/api/sync.py` | FastAPI 라우트, 전체 파이프라인 실행, 병렬 처리 |

**주요 상수** (`sync.py` 상단에서 수정)

| 상수 | 값 | 설명 |
|------|----|------|
| `PARALLEL_WORKERS` | 5 | 동시 처리 영상 수 (Groq 무료: 2~3 권장) |
| `TOKEN_BUDGET_PER_VIDEO` | 2,000 | 영상당 LLM 토큰 예산 |
| `MAX_LLM_COMMENTS` | 20 | LLM에 넘길 최대 댓글 수 |
| `CLASSIFICATION_BATCH_SIZE` | 8 | LLM 배치 크기 |
| `RAW_COMMENT_FETCH_LIMIT` | 1,000 | YouTube 수집 최대 댓글 수 |
| `PREPROCESS_CANDIDATE_MAX` | 300 | 점수화 후 상위 컷 수 |

---

### 2-2. 수집 레이어

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `comment_filtering_agent/services/comment_collector.py` | `YouTubeCommentCollector` | YouTube API 댓글 수집, 페이지네이션 처리 |

---

### 2-3. 필터 레이어

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `comment_filtering_agent/filters/rule_based_filter.py` | `RuleBasedFilter` | 규칙 기반 Hard Gate 필터 |
| `comment_filtering_agent/filters/models.py` | `RuleConfig`, `FilterResult` | 필터 설정 및 결과 모델 |

**활성화된 규칙** (`RuleConfig` 설정값)

| 규칙 | 활성화 | 기준 |
|------|--------|------|
| `TOO_SHORT` | ✅ | 길이 < 5자 |
| `SPECIAL_CHARS_ONLY` | ✅ | 특수문자만 |
| `EMOJI_HEAVY` | ✅ | 이모지 비율 > 70% |
| `LOW_INFORMATION` | ✅ | 반복문자 비율 > 70% |
| `GREETING_ONLY` | ✅ | 인사말만 |
| `REACTION_ONLY` | ✅ | 반응어만 (ㅋㅋ, 와, 대박) |
| `CREATOR_PRAISE_ONLY` | ✅ | 유튜버 칭찬/구독 유도만 |
| `PROMOTIONAL` | ✅ | 광고·홍보 |
| `ABUSIVE` | ✅ | 욕설 |
| `URL_SPAM` | ❌ | 비활성화 (LLM이 판단) |
| `DUPLICATE_CANDIDATE` | ❌ | 비활성화 (Spark에서 처리) |

---

### 2-4. 분류 레이어

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `comment_filtering_agent/classifiers/optimized_batch_classifier.py` | `OptimizedBatchClassifier` | LangChain ChatGroq 배치 분류 |
| `comment_filtering_agent/classifiers/models.py` | `ClassificationResult`, `CommentLabel` | 분류 결과 모델 |
| `comment_filtering_agent/prompts/batch_prompt_optimized.py` | `COMPACT_SYSTEM_PROMPT` | 배치 분류 프롬프트 |
| `comment_filtering_agent/cache/classification_cache.py` | `ClassificationCache` | 분류 결과 캐싱 |

**댓글 라벨 종류**

| 라벨 | 의미 |
|------|------|
| `PRODUCT_OPINION` | 제품 평가 의견 → **감성 분석 진행** |
| `QUESTION` | 질문 댓글 |
| `VIDEO_REACTION` | 영상/리뷰어 반응 |
| `CHATTER` | 잡담·무의미 |
| `OFF_TOPIC` | 제품 무관 |

**LangChain 체인 구조** (`OptimizedBatchClassifier.__init__`)

```python
chain = (
    ChatPromptTemplate.from_messages([
        SystemMessage(content=COMPACT_SYSTEM_PROMPT),  # {} 이스케이프 불필요
        ("human", "{user_prompt}"),
    ])
    | ChatGroq(model=GROQ_MODEL, ...)
    | JsonOutputParser()
).with_retry(stop_after_attempt=3, wait_exponential_jitter=True)
```

---

### 2-5. Agent 의사결정 레이어

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `comment_filtering_agent/core/agent.py` | `AgentDecisionEngine` | 규칙필터 + LLM분류 결과 종합 판단 |
| `comment_filtering_agent/core/models.py` | `AgentDecision`, `AgentAction`, `AgentPolicyConfig` | Agent 결정 모델 및 정책 설정 |

**AgentAction (최종 판정)**

| 액션 | 조건 | 다음 단계 |
|------|------|----------|
| `ANALYZE` | `PRODUCT_OPINION` 또는 제품특성 다수 언급 `VIDEO_REACTION` | 감성 분석 실행 |
| `AUXILIARY_STORE` | 제품 관련 `QUESTION` | 질문 저장 |
| `EXCLUDE` | `CHATTER` / `OFF_TOPIC` / 제품 무관 질문 | 제외 로그 |
| `HOLD` | LLM 분류 실패 | 수동 검토 대기 |
| `RECLASSIFY` | `CHATTER` + 재확인 필요 + 낮은 확신도 | 재분류 큐 |

**AgentPolicyConfig 주요 임계값**

| 설정 | 값 |
|------|----|
| `high_confidence_threshold` | 0.8 |
| `medium_confidence_threshold` | 0.6 |
| `low_confidence_threshold` | 0.5 |
| `min_product_features_for_analysis` | 2 (VIDEO_REACTION 예외 처리) |
| `reclassify_priority_high_confidence_threshold` | 0.7 |

---

### 2-6. 감성 분석 레이어

| 파일 | 클래스 | 역할 |
|------|--------|------|
| `comment_filtering_agent/analyzers/groq_analyzer.py` | `GroqAspectSentimentAnalyzer` | LangChain ChatGroq ABSA 실행 |
| `comment_filtering_agent/analyzers/base_analyzer.py` | `BaseAspectSentimentAnalyzer` | 추상 베이스, 재시도 루프 포함 |
| `comment_filtering_agent/analyzers/models.py` | `AnalyzerConfig`, `SentimentAnalysisResult` | 분석 설정 및 결과 모델 |

**AnalyzerConfig 기본값**

| 설정 | 값 |
|------|----|
| `model_name` | `GROQ_MODEL` env (기본: llama-3.3-70b-versatile) |
| `temperature` | 0.1 |
| `max_tokens` | 1,000 |
| `max_retries` | 3 |

**SentimentAnalysisResult 주요 필드**

```
overall_sentiment: POSITIVE / NEUTRAL / NEGATIVE
overall_score: -1.0 ~ +1.0
aspects: [{ aspect, sentiment, score, intensity, mention_text }]
analyzer_type: "LLM"
```

---

## 3. DB 테이블 연결 구조

```
comments              ← Step 3: 원본 댓글 저장
rule_filter_results   ← Step 3: PASS/REJECT 기록
llm_classifications   ← Step 7: LLM 배치 분류 결과
agent_decisions       ← Step 7: Agent 최종 판정
comment_sentiments    ← Step 7: 감성 레이블/점수
aspect_extractions    ← Step 7: 속성별 감성 (ABSA)
```

---

## 4. 모델 설정 (env 기반)

`.env`의 `GROQ_MODEL` 하나로 전체 파이프라인 모델 일괄 변경:

| 컴포넌트 | 적용 방식 |
|---------|----------|
| `OptimizedBatchClassifier` | `_GROQ_MODEL = os.getenv("GROQ_MODEL", ...)` |
| `AnalyzerConfig.model_name` | `os.getenv("GROQ_MODEL", ...)` 기본값 |
| `sync.py` sentiment_analyzer | `GROQ_MODEL` from `scripts.config` |
| `transcript_report.py` 외 보고서 | `GROQ_MODEL` from `scripts.config` |

```env
# .env
GROQ_MODEL=openai/gpt-oss-20b       # 현재 설정값
# GROQ_MODEL=llama-3.3-70b-versatile  # 고정확도
# GROQ_MODEL=llama-3.1-8b-instant     # 고속/저정확도
```

---

## 5. 기술 스택

| 영역 | 기술 |
|------|------|
| API 프레임워크 | FastAPI |
| LLM 호출 | LangChain (`ChatGroq`, `JsonOutputParser`, `ChatPromptTemplate`) |
| LLM 제공자 | Groq API (`langchain-groq`) |
| 전처리 | PySpark (없으면 Python fallback) |
| DB | PostgreSQL (`psycopg2`) |
| 병렬 처리 | `concurrent.futures.ThreadPoolExecutor` |
| 캐싱 | `ClassificationCache` (in-memory) |

---

## 6. 퍼널 요약

| 단계 | 출력 수 |
|------|--------|
| YouTube 수집 | ~1,000 |
| Spark dedup | ~950+ |
| 규칙 필터 PASS | ~300 |
| 점수화 상위 컷 | ≤ 300 |
| 다중기준 선발 | ≤ 20 |
| 토큰 예산 트리밍 | ≤ 20 |
| Agent ANALYZE 판정 | N |
| 감성/ABSA 저장 | N |
