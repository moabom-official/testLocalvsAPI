# 댓글 필터링 Agent DB 설계

## 1. 설계 원칙

### 1.1 핵심 철학
- **파이프라인 추적 가능성**: 댓글 수집 → 1차 필터 → Agent 판단 → 분석 전 과정을 추적
- **재처리 가능성**: 원본 데이터 보존, 분류/분석 결과는 재생성 가능
- **정규화와 성능의 균형**: 분석 결과는 정규화하되, 집계는 뷰/materialized view 활용
- **버전 관리**: 분류 모델, 프롬프트, 규칙 버전 추적으로 A/B 테스트 및 롤백 가능
- **확장성**: aspect, 질문 카테고리 등 동적 추가 가능한 구조

### 1.2 데이터 흐름
```
[YouTube API]
    ↓
┌─────────────────────────┐
│ 1. raw_comments         │ ← 원본 댓글 저장
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 2. rule_filter_results  │ ← 1차 규칙 필터 결과
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 3. llm_classifications  │ ← 2차 LLM 분류 결과
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 4. agent_decisions      │ ← Agent 최종 판단
└─────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 5a. sentiment_analysis                  │ ← 감정 분석
│ 5b. aspect_extractions                  │ ← aspect 추출
│ 5c. product_questions                   │ ← 제품 질문
│ 5d. excluded_comments_log               │ ← 제외 댓글 추적
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────┐
│ 6. analysis_reports     │ ← 보고서 집계 (뷰)
└─────────────────────────┘
```

---

## 2. ERD 및 테이블 목록

### 2.1 테이블 분류

#### Core Tables (핵심 테이블)
1. `raw_comments` - 원본 댓글 저장
2. `rule_filter_results` - 1차 규칙 필터 결과
3. `llm_classifications` - 2차 LLM 분류 결과
4. `agent_decisions` - Agent 최종 결정

#### Analysis Tables (분석 결과 테이블)
5. `sentiment_analysis` - 감정 분석 결과
6. `aspect_extractions` - aspect 추출 결과 (정규화)
7. `aspect_sentiments` - aspect별 감정 (조인 테이블)
8. `product_questions` - 제품 질문 댓글

#### Metadata Tables (메타데이터 테이블)
9. `aspect_definitions` - aspect 정의 (발열, 성능, 배터리 등)
10. `question_categories` - 질문 카테고리 정의
11. `filter_rules_versions` - 규칙 필터 버전 관리
12. `classifier_versions` - 분류기 버전 관리

#### Tracking Tables (추적 테이블)
13. `excluded_comments_log` - 제외 댓글 추적
14. `comment_processing_logs` - 댓글 처리 이력
15. `reclassification_queue` - 재분류 대기열

#### Aggregation (집계 뷰)
16. `v_product_sentiment_summary` - 제품별 감정 집계 뷰
17. `v_aspect_analysis_summary` - aspect별 분석 뷰
18. `v_question_frequency` - 질문 빈도 뷰
19. `v_filter_performance` - 필터 성능 모니터링 뷰

---

## 3. 테이블 상세 설계

### 3.1 Core Tables

#### 3.1.1 `raw_comments` - 원본 댓글
**목적**: YouTube에서 수집한 원본 댓글을 변경 없이 저장. 재처리의 기준점.

```sql
CREATE TABLE raw_comments (
    -- PK
    comment_id VARCHAR(255) PRIMARY KEY,  -- YouTube comment ID
    
    -- YouTube 메타데이터
    video_id VARCHAR(255) NOT NULL,
    author_name VARCHAR(500),
    author_channel_id VARCHAR(255),
    
    -- 댓글 내용
    text_original TEXT NOT NULL,  -- 원본 텍스트 (보존)
    text_display TEXT,            -- 표시용 텍스트 (HTML 태그 제거)
    
    -- 통계
    like_count INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    
    -- 시간
    published_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ,
    
    -- 수집 정보
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    collection_batch_id UUID,  -- 배치 수집 추적용
    
    -- 메타
    is_reply BOOLEAN DEFAULT FALSE,  -- 답글 여부
    parent_comment_id VARCHAR(255),  -- 답글인 경우 부모 댓글 ID
    
    -- 제약
    CONSTRAINT fk_parent_comment 
        FOREIGN KEY (parent_comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE SET NULL
);

-- 인덱스
CREATE INDEX idx_raw_comments_video_id ON raw_comments(video_id);
CREATE INDEX idx_raw_comments_published_at ON raw_comments(published_at DESC);
CREATE INDEX idx_raw_comments_collected_at ON raw_comments(collected_at DESC);
CREATE INDEX idx_raw_comments_batch_id ON raw_comments(collection_batch_id);

-- 중복 방지 제약
CREATE UNIQUE INDEX uk_raw_comments_dedup 
    ON raw_comments(video_id, author_channel_id, text_original, published_at)
    WHERE parent_comment_id IS NULL;  -- 최상위 댓글만 중복 체크
```

**설계 이유**:
- `comment_id`는 YouTube 제공 ID 그대로 사용 (PK)
- `text_original`과 `text_display` 분리: 원본 보존 + 분석용 전처리
- `collection_batch_id`: 대량 수집 시 배치 단위 추적
- 답글 구조: self-referencing FK로 계층 구조 표현
- 중복 방지: 동일 비디오에서 같은 작성자가 같은 시간에 같은 내용 방지

---

#### 3.1.2 `rule_filter_results` - 1차 규칙 필터 결과
**목적**: 각 댓글이 규칙 필터를 통과했는지, 어떤 규칙에 걸렸는지 추적

```sql
CREATE TYPE filter_status AS ENUM ('PASS', 'REJECT');

CREATE TABLE rule_filter_results (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL,
    
    -- 필터 결과
    filter_status filter_status NOT NULL,
    
    -- Reject 사유
    rejected_by_rule VARCHAR(100),  -- 'length', 'emoji_only', 'url', 'profanity', etc.
    reject_reason TEXT,             -- 상세 사유
    
    -- 규칙 버전
    rule_version_id INTEGER,  -- FK to filter_rules_versions
    
    -- 필터 메타데이터 (JSON)
    filter_metadata JSONB,  -- {detected_patterns: [...], scores: {...}}
    
    -- 시간
    filtered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_rule_filter 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_rule_version
        FOREIGN KEY (rule_version_id)
        REFERENCES filter_rules_versions(id)
        ON DELETE SET NULL
);

-- 인덱스
CREATE INDEX idx_rule_filter_comment_id ON rule_filter_results(comment_id);
CREATE INDEX idx_rule_filter_status ON rule_filter_results(filter_status);
CREATE INDEX idx_rule_filter_rejected_by ON rule_filter_results(rejected_by_rule);
CREATE INDEX idx_rule_filter_version ON rule_filter_results(rule_version_id);

-- 한 댓글당 하나의 최신 필터 결과만 (재처리 시 교체)
CREATE UNIQUE INDEX uk_one_filter_result_per_comment 
    ON rule_filter_results(comment_id, rule_version_id);
```

**설계 이유**:
- `PASS`/`REJECT` ENUM으로 명확한 상태 표현
- `rejected_by_rule`: 어떤 규칙에 걸렸는지 추적 → 필터 성능 분석
- `filter_metadata` JSONB: 유연한 메타데이터 저장 (패턴 매칭 결과, 점수 등)
- `rule_version_id`: A/B 테스트, 규칙 변경 추적
- Unique constraint: 같은 버전으로 중복 필터링 방지

---

#### 3.1.3 `llm_classifications` - 2차 LLM 분류 결과
**목적**: LLM이 댓글을 5개 라벨로 분류한 결과 저장

```sql
CREATE TYPE comment_label AS ENUM (
    'PRODUCT_OPINION',
    'VIDEO_REACTION',
    'CHATTER',
    'QUESTION',
    'OFF_TOPIC'
);

CREATE TYPE classifier_type AS ENUM (
    'FEW_SHOT',
    'FINE_TUNED',
    'HYBRID'
);

CREATE TABLE llm_classifications (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL,
    
    -- 분류 결과
    label comment_label NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL,  -- 0.0000 ~ 1.0000
    reasoning TEXT,  -- LLM이 제공한 분류 근거
    
    -- 분류기 정보
    classifier_type classifier_type NOT NULL,
    classifier_version_id INTEGER,  -- FK to classifier_versions
    model_name VARCHAR(100),        -- 'llama-3.1-70b', 'kobert-finetuned-v1', etc.
    prompt_version VARCHAR(50),     -- 'few_shot_ko_v2', etc.
    
    -- LLM API 메타데이터
    llm_provider VARCHAR(50),       -- 'groq', 'openai', 'huggingface', etc.
    tokens_used INTEGER,
    latency_ms INTEGER,
    
    -- 추가 분류 정보 (JSON)
    classification_metadata JSONB,  -- {top_3_labels: [...], raw_response: ...}
    
    -- 시간
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_classification 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_classifier_version
        FOREIGN KEY (classifier_version_id)
        REFERENCES classifier_versions(id)
        ON DELETE SET NULL,
    CONSTRAINT chk_confidence_range 
        CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

-- 인덱스
CREATE INDEX idx_classification_comment_id ON llm_classifications(comment_id);
CREATE INDEX idx_classification_label ON llm_classifications(label);
CREATE INDEX idx_classification_confidence ON llm_classifications(confidence);
CREATE INDEX idx_classification_classifier_type ON llm_classifications(classifier_type);
CREATE INDEX idx_classification_version ON llm_classifications(classifier_version_id);

-- Composite index for filtering
CREATE INDEX idx_classification_label_confidence 
    ON llm_classifications(label, confidence DESC);

-- 한 댓글당 하나의 최신 분류 결과 (같은 버전)
CREATE UNIQUE INDEX uk_one_classification_per_comment 
    ON llm_classifications(comment_id, classifier_version_id);
```

**설계 이유**:
- `comment_label` ENUM: 5개 라벨 타입 안전성
- `classifier_type`: few-shot vs fine-tuned 구분 → 성능 비교 분석
- `confidence` NUMERIC(5,4): 정확한 소수점 저장 (0.9523 같은 값)
- `reasoning`: LLM의 판단 근거 저장 → 디버깅, 학습 데이터 생성
- `tokens_used`, `latency_ms`: 비용/성능 모니터링
- `classification_metadata` JSONB: top-3 라벨, raw response 등 유연한 저장

---

#### 3.1.4 `agent_decisions` - Agent 최종 결정
**목적**: Agent가 1차 필터 + 2차 분류를 종합하여 내린 최종 결정

```sql
CREATE TYPE agent_action AS ENUM (
    'ANALYZE',          -- 감정/aspect 분석으로 전달
    'AUXILIARY_STORE',  -- 제품 질문으로 저장
    'EXCLUDE',          -- 제외 (로그만 남김)
    'HOLD',             -- 보류 (수동 검토 필요)
    'RECLASSIFY'        -- 재분류 요청
);

CREATE TYPE exclusion_reason AS ENUM (
    'VIDEO_REACTION',
    'CHATTER',
    'OFF_TOPIC',
    'SPAM',
    'DUPLICATE',
    'PROFANITY',
    'RULE_FILTERED',
    'LOW_CONFIDENCE',
    'OTHER'
);

CREATE TABLE agent_decisions (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL,
    rule_filter_result_id BIGINT,
    llm_classification_id BIGINT,
    
    -- Agent 결정
    final_action agent_action NOT NULL,
    next_stage VARCHAR(100),  -- 'sentiment_analysis', 'auxiliary_data', NULL
    
    -- 제외 사유 (final_action = 'EXCLUDE'인 경우)
    exclusion_reason exclusion_reason,
    exclusion_details TEXT,
    
    -- 신뢰도 관련
    is_low_confidence BOOLEAN DEFAULT FALSE,
    needs_human_review BOOLEAN DEFAULT FALSE,
    needs_reclassification BOOLEAN DEFAULT FALSE,
    
    -- Agent 판단 근거
    decision_reasoning TEXT,
    
    -- Agent 메타데이터
    agent_version VARCHAR(50),
    confidence_threshold NUMERIC(3, 2),  -- Agent가 사용한 threshold
    
    -- 추가 메타데이터
    decision_metadata JSONB,  -- {spam_score: 0.8, duplicate_of: 'comment_xyz', ...}
    
    -- 시간
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_decision 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_rule_filter_result
        FOREIGN KEY (rule_filter_result_id)
        REFERENCES rule_filter_results(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_llm_classification
        FOREIGN KEY (llm_classification_id)
        REFERENCES llm_classifications(id)
        ON DELETE SET NULL
);

-- 인덱스
CREATE INDEX idx_agent_comment_id ON agent_decisions(comment_id);
CREATE INDEX idx_agent_action ON agent_decisions(final_action);
CREATE INDEX idx_agent_exclusion_reason ON agent_decisions(exclusion_reason);
CREATE INDEX idx_agent_low_confidence ON agent_decisions(is_low_confidence) 
    WHERE is_low_confidence = TRUE;
CREATE INDEX idx_agent_needs_review ON agent_decisions(needs_human_review) 
    WHERE needs_human_review = TRUE;

-- Composite index for processing queue
CREATE INDEX idx_agent_action_decided 
    ON agent_decisions(final_action, decided_at DESC);

-- 한 댓글당 하나의 최신 Agent 결정
CREATE UNIQUE INDEX uk_one_decision_per_comment 
    ON agent_decisions(comment_id, agent_version);
```

**설계 이유**:
- `final_action` ENUM: Agent의 5가지 결정 타입
- `exclusion_reason` 별도 ENUM: 제외 사유 추적 → 필터 성능 분석
- `is_low_confidence`, `needs_human_review`: 워크플로우 관리
- `rule_filter_result_id`, `llm_classification_id` FK: 결정 근거 추적
- `decision_metadata` JSONB: 스팸 점수, 중복 댓글 ID 등 유연한 저장

---

### 3.2 Analysis Tables

#### 3.2.1 `sentiment_analysis` - 감정 분석 결과
**목적**: ANALYZE 액션을 받은 댓글의 전체 감정 분석 결과

```sql
CREATE TYPE sentiment_type AS ENUM ('POSITIVE', 'NEUTRAL', 'NEGATIVE');

CREATE TABLE sentiment_analysis (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL UNIQUE,
    agent_decision_id BIGINT NOT NULL,
    
    -- 감정 분석 결과
    sentiment sentiment_type NOT NULL,
    sentiment_score NUMERIC(5, 4) NOT NULL,  -- -1.0000 ~ 1.0000 (또는 0 ~ 1)
    
    -- 세부 점수
    positive_score NUMERIC(5, 4),
    neutral_score NUMERIC(5, 4),
    negative_score NUMERIC(5, 4),
    
    -- 감정 강도
    intensity VARCHAR(20),  -- 'weak', 'moderate', 'strong'
    
    -- 분석 모델 정보
    sentiment_model VARCHAR(100),  -- 'kobert-sentiment-v1', 'groq-llama-3.1', etc.
    model_version VARCHAR(50),
    
    -- 분석 근거 (선택)
    analysis_reasoning TEXT,
    
    -- 시간
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_sentiment 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_agent_decision_sentiment
        FOREIGN KEY (agent_decision_id)
        REFERENCES agent_decisions(id)
        ON DELETE CASCADE,
    CONSTRAINT chk_sentiment_score_range
        CHECK (sentiment_score >= -1.0 AND sentiment_score <= 1.0)
);

-- 인덱스
CREATE INDEX idx_sentiment_comment_id ON sentiment_analysis(comment_id);
CREATE INDEX idx_sentiment_type ON sentiment_analysis(sentiment);
CREATE INDEX idx_sentiment_score ON sentiment_analysis(sentiment_score DESC);
```

**설계 이유**:
- 댓글당 하나의 전체 감정 (UNIQUE constraint)
- `sentiment_score`: 연속값으로 세밀한 분석
- `positive_score`, `neutral_score`, `negative_score`: 확률 분포 저장
- `intensity`: 감정 강도 추가 정보

---

#### 3.2.2 `aspect_definitions` - Aspect 정의 마스터 테이블
**목적**: 제품 평가 항목(aspect) 정의

```sql
CREATE TABLE aspect_definitions (
    -- PK
    id SERIAL PRIMARY KEY,
    
    -- Aspect 정보
    aspect_name VARCHAR(100) NOT NULL UNIQUE,  -- '발열', '성능', '배터리', ...
    aspect_name_en VARCHAR(100),               -- 'heating', 'performance', 'battery'
    category VARCHAR(50),                      -- 'hardware', 'software', 'design', 'price'
    
    -- 설명
    description TEXT,
    keywords TEXT[],  -- {'발열', '뜨겁', '열', 'heating', 'hot'}
    
    -- 활성화
    is_active BOOLEAN DEFAULT TRUE,
    
    -- 우선순위 (정렬용)
    display_order INTEGER DEFAULT 0,
    
    -- 시간
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- 초기 데이터 예시
INSERT INTO aspect_definitions (aspect_name, aspect_name_en, category, keywords) VALUES
    ('발열', 'heating', 'hardware', ARRAY['발열', '뜨겁', '열', '온도', 'hot', 'heat']),
    ('성능', 'performance', 'hardware', ARRAY['성능', '속도', '빠르', '느리', 'performance', 'speed']),
    ('배터리', 'battery', 'hardware', ARRAY['배터리', '충전', '전력', 'battery', 'power']),
    ('카메라', 'camera', 'hardware', ARRAY['카메라', '사진', '화질', 'camera', 'photo']),
    ('디자인', 'design', 'design', ARRAY['디자인', '외관', '예쁘', 'design', 'looks']),
    ('가격', 'price', 'price', ARRAY['가격', '비싸', '저렴', '가성비', 'price', 'cost']);
```

---

#### 3.2.3 `aspect_extractions` - Aspect 추출 결과
**목적**: 한 댓글에서 추출된 여러 aspect (정규화)

```sql
CREATE TABLE aspect_extractions (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL,
    aspect_id INTEGER NOT NULL,
    
    -- Aspect 언급 정보
    mention_text TEXT,  -- 원문에서 해당 aspect 언급 부분
    mention_context TEXT,  -- 문맥 (전후 문장)
    
    -- Aspect 감정
    aspect_sentiment sentiment_type,
    aspect_sentiment_score NUMERIC(5, 4),
    
    -- 추출 정보
    extraction_confidence NUMERIC(5, 4),  -- aspect 추출 신뢰도
    extraction_method VARCHAR(50),        -- 'keyword_match', 'llm_extraction', 'hybrid'
    
    -- 시간
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_aspect 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_aspect_definition
        FOREIGN KEY (aspect_id)
        REFERENCES aspect_definitions(id)
        ON DELETE CASCADE
);

-- 인덱스
CREATE INDEX idx_aspect_comment_id ON aspect_extractions(comment_id);
CREATE INDEX idx_aspect_id ON aspect_extractions(aspect_id);
CREATE INDEX idx_aspect_sentiment ON aspect_extractions(aspect_sentiment);

-- Composite index
CREATE INDEX idx_aspect_comment_aspect 
    ON aspect_extractions(comment_id, aspect_id);

-- 한 댓글에서 같은 aspect 중복 추출 방지
CREATE UNIQUE INDEX uk_one_aspect_per_comment 
    ON aspect_extractions(comment_id, aspect_id);
```

**설계 이유**:
- 정규화 설계: 한 댓글이 여러 aspect 가질 수 있음
- `aspect_definitions` 참조: aspect 동적 추가 가능
- aspect별 감정 저장: "발열은 심한데 성능은 좋네요" → 발열(부정), 성능(긍정)

---

#### 3.2.4 `product_questions` - 제품 질문 댓글
**목적**: AUXILIARY_STORE 액션을 받은 제품 관련 질문 저장

```sql
CREATE TABLE question_categories (
    id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,  -- '성능문의', '호환성', '가격문의', ...
    category_name_en VARCHAR(100),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE product_questions (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL UNIQUE,
    agent_decision_id BIGINT NOT NULL,
    
    -- 질문 내용
    question_text TEXT NOT NULL,
    question_category_id INTEGER,
    
    -- 질문 분류
    is_product_related BOOLEAN DEFAULT TRUE,
    is_answered BOOLEAN DEFAULT FALSE,  -- 답변 여부 (추후 FAQ 생성)
    
    -- 질문 메타데이터
    mentioned_aspects INTEGER[],  -- aspect_definitions.id 배열
    question_keywords TEXT[],
    
    -- 우선순위 (FAQ 생성 시)
    priority INTEGER DEFAULT 0,  -- 중요도 (like_count 기반 등)
    
    -- 시간
    stored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_question 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_agent_decision_question
        FOREIGN KEY (agent_decision_id)
        REFERENCES agent_decisions(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_question_category
        FOREIGN KEY (question_category_id)
        REFERENCES question_categories(id)
        ON DELETE SET NULL
);

-- 인덱스
CREATE INDEX idx_question_comment_id ON product_questions(comment_id);
CREATE INDEX idx_question_category ON product_questions(question_category_id);
CREATE INDEX idx_question_answered ON product_questions(is_answered) 
    WHERE is_answered = FALSE;
CREATE INDEX idx_question_priority ON product_questions(priority DESC);
```

**설계 이유**:
- 질문 카테고리 정규화: 동적 추가 가능
- `is_answered`: FAQ 생성 워크플로우
- `mentioned_aspects` 배열: 어떤 aspect에 대한 질문인지 추적
- `priority`: 좋아요 수, 빈도 등 기반 중요도

---

### 3.3 Tracking Tables

#### 3.3.1 `excluded_comments_log` - 제외 댓글 추적
**목적**: EXCLUDE 액션을 받은 댓글의 상세 추적 (분석용)

```sql
CREATE TABLE excluded_comments_log (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL,
    agent_decision_id BIGINT NOT NULL,
    
    -- 제외 정보
    exclusion_reason exclusion_reason NOT NULL,
    exclusion_stage VARCHAR(50),  -- 'rule_filter', 'llm_classification', 'agent_decision'
    
    -- 상세 정보
    details TEXT,
    
    -- 통계용 메타데이터
    video_id VARCHAR(255),
    original_label comment_label,  -- LLM이 분류한 원래 라벨
    
    -- 시간
    excluded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_excluded 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_agent_decision_excluded
        FOREIGN KEY (agent_decision_id)
        REFERENCES agent_decisions(id)
        ON DELETE CASCADE
);

-- 인덱스
CREATE INDEX idx_excluded_reason ON excluded_comments_log(exclusion_reason);
CREATE INDEX idx_excluded_stage ON excluded_comments_log(exclusion_stage);
CREATE INDEX idx_excluded_video ON excluded_comments_log(video_id);
CREATE INDEX idx_excluded_at ON excluded_comments_log(excluded_at DESC);
```

---

#### 3.3.2 `comment_processing_logs` - 댓글 처리 이력
**목적**: 각 댓글의 전체 처리 파이프라인 추적

```sql
CREATE TYPE processing_stage AS ENUM (
    'COLLECTED',
    'RULE_FILTERED',
    'LLM_CLASSIFIED',
    'AGENT_DECIDED',
    'ANALYZED',
    'COMPLETED',
    'FAILED'
);

CREATE TABLE comment_processing_logs (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL,
    
    -- 처리 단계
    stage processing_stage NOT NULL,
    status VARCHAR(20) NOT NULL,  -- 'SUCCESS', 'FAILED', 'SKIPPED'
    
    -- 에러 정보
    error_message TEXT,
    error_stack TEXT,
    
    -- 처리 시간
    processing_time_ms INTEGER,  -- 밀리초
    
    -- 시간
    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- 제약
    CONSTRAINT fk_comment_log 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE
);

-- 인덱스
CREATE INDEX idx_processing_comment_id ON comment_processing_logs(comment_id);
CREATE INDEX idx_processing_stage ON comment_processing_logs(stage);
CREATE INDEX idx_processing_status ON comment_processing_logs(status);
CREATE INDEX idx_processing_failed ON comment_processing_logs(stage, status) 
    WHERE status = 'FAILED';
```

---

#### 3.3.3 `reclassification_queue` - 재분류 대기열
**목적**: RECLASSIFY 액션을 받거나 신뢰도가 낮은 댓글의 재분류 관리

```sql
CREATE TABLE reclassification_queue (
    -- PK
    id BIGSERIAL PRIMARY KEY,
    
    -- FK
    comment_id VARCHAR(255) NOT NULL,
    original_classification_id BIGINT,
    
    -- 재분류 사유
    reason VARCHAR(100) NOT NULL,  -- 'low_confidence', 'ambiguous', 'manual_request'
    priority INTEGER DEFAULT 0,
    
    -- 상태
    status VARCHAR(20) DEFAULT 'PENDING',  -- 'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'
    
    -- 재분류 결과
    new_classification_id BIGINT,
    
    -- 시간
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
    -- 제약
    CONSTRAINT fk_comment_reclass 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_original_classification
        FOREIGN KEY (original_classification_id)
        REFERENCES llm_classifications(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_new_classification
        FOREIGN KEY (new_classification_id)
        REFERENCES llm_classifications(id)
        ON DELETE SET NULL
);

-- 인덱스
CREATE INDEX idx_reclass_status ON reclassification_queue(status) 
    WHERE status = 'PENDING';
CREATE INDEX idx_reclass_priority ON reclassification_queue(priority DESC, queued_at);
```

---

### 3.4 Metadata Tables

#### 3.4.1 `filter_rules_versions` - 규칙 필터 버전 관리
```sql
CREATE TABLE filter_rules_versions (
    id SERIAL PRIMARY KEY,
    version_name VARCHAR(50) NOT NULL UNIQUE,  -- 'v1.0', 'v1.1-strict', etc.
    description TEXT,
    rules_config JSONB NOT NULL,  -- 규칙 설정 (JSON)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deprecated_at TIMESTAMPTZ
);
```

#### 3.4.2 `classifier_versions` - 분류기 버전 관리
```sql
CREATE TABLE classifier_versions (
    id SERIAL PRIMARY KEY,
    version_name VARCHAR(50) NOT NULL UNIQUE,  -- 'few-shot-v1', 'finetuned-v2', etc.
    classifier_type classifier_type NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    prompt_template TEXT,  -- few-shot인 경우
    model_path VARCHAR(500),  -- fine-tuned인 경우
    performance_metrics JSONB,  -- {accuracy: 0.88, f1: 0.85, ...}
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deprecated_at TIMESTAMPTZ
);
```

---

### 3.5 Aggregation Views

#### 3.5.1 `v_product_sentiment_summary` - 제품별 감정 집계
```sql
CREATE OR REPLACE VIEW v_product_sentiment_summary AS
SELECT 
    rc.video_id,
    COUNT(*) AS total_analyzed_comments,
    COUNT(*) FILTER (WHERE sa.sentiment = 'POSITIVE') AS positive_count,
    COUNT(*) FILTER (WHERE sa.sentiment = 'NEUTRAL') AS neutral_count,
    COUNT(*) FILTER (WHERE sa.sentiment = 'NEGATIVE') AS negative_count,
    ROUND(AVG(sa.sentiment_score), 4) AS avg_sentiment_score,
    ROUND(
        COUNT(*) FILTER (WHERE sa.sentiment = 'POSITIVE')::NUMERIC / COUNT(*) * 100, 
        2
    ) AS positive_ratio
FROM raw_comments rc
JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
JOIN sentiment_analysis sa ON rc.comment_id = sa.comment_id
WHERE ad.final_action = 'ANALYZE'
GROUP BY rc.video_id;
```

#### 3.5.2 `v_aspect_analysis_summary` - Aspect별 분석
```sql
CREATE OR REPLACE VIEW v_aspect_analysis_summary AS
SELECT 
    rc.video_id,
    adef.aspect_name,
    adef.aspect_name_en,
    COUNT(*) AS mention_count,
    COUNT(*) FILTER (WHERE ae.aspect_sentiment = 'POSITIVE') AS positive_mentions,
    COUNT(*) FILTER (WHERE ae.aspect_sentiment = 'NEGATIVE') AS negative_mentions,
    ROUND(AVG(ae.aspect_sentiment_score), 4) AS avg_aspect_sentiment
FROM raw_comments rc
JOIN aspect_extractions ae ON rc.comment_id = ae.comment_id
JOIN aspect_definitions adef ON ae.aspect_id = adef.id
GROUP BY rc.video_id, adef.aspect_name, adef.aspect_name_en, adef.display_order
ORDER BY rc.video_id, adef.display_order;
```

#### 3.5.3 `v_question_frequency` - 질문 빈도
```sql
CREATE OR REPLACE VIEW v_question_frequency AS
SELECT 
    rc.video_id,
    qc.category_name,
    COUNT(*) AS question_count,
    COUNT(*) FILTER (WHERE pq.is_answered = FALSE) AS unanswered_count,
    ROUND(AVG(rc.like_count), 2) AS avg_likes
FROM raw_comments rc
JOIN product_questions pq ON rc.comment_id = pq.comment_id
LEFT JOIN question_categories qc ON pq.question_category_id = qc.id
GROUP BY rc.video_id, qc.category_name;
```

#### 3.5.4 `v_filter_performance` - 필터 성능 모니터링
```sql
CREATE OR REPLACE VIEW v_filter_performance AS
SELECT 
    DATE_TRUNC('day', rfr.filtered_at) AS filter_date,
    frv.version_name AS rule_version,
    COUNT(*) AS total_filtered,
    COUNT(*) FILTER (WHERE rfr.filter_status = 'PASS') AS pass_count,
    COUNT(*) FILTER (WHERE rfr.filter_status = 'REJECT') AS reject_count,
    COUNT(*) FILTER (WHERE rfr.rejected_by_rule = 'length') AS rejected_by_length,
    COUNT(*) FILTER (WHERE rfr.rejected_by_rule = 'emoji_only') AS rejected_by_emoji,
    COUNT(*) FILTER (WHERE rfr.rejected_by_rule = 'url') AS rejected_by_url,
    COUNT(*) FILTER (WHERE rfr.rejected_by_rule = 'profanity') AS rejected_by_profanity,
    ROUND(
        COUNT(*) FILTER (WHERE rfr.filter_status = 'REJECT')::NUMERIC / COUNT(*) * 100,
        2
    ) AS reject_ratio
FROM rule_filter_results rfr
LEFT JOIN filter_rules_versions frv ON rfr.rule_version_id = frv.id
GROUP BY DATE_TRUNC('day', rfr.filtered_at), frv.version_name
ORDER BY filter_date DESC;
```

---

## 4. 인덱스 전략

### 4.1 기본 인덱스
- **PK 인덱스**: 모든 테이블의 PRIMARY KEY는 자동으로 B-tree 인덱스 생성
- **FK 인덱스**: 모든 FOREIGN KEY 컬럼에 인덱스 생성 (JOIN 성능)

### 4.2 쿼리 패턴별 인덱스
| 쿼리 패턴 | 인덱스 | 목적 |
|----------|--------|------|
| 비디오별 댓글 조회 | `idx_raw_comments_video_id` | 특정 비디오의 모든 댓글 조회 |
| 최근 댓글 조회 | `idx_raw_comments_published_at` | 시간순 정렬 |
| 필터 통과 댓글 | `idx_rule_filter_status` | PASS/REJECT 필터링 |
| 라벨별 분류 조회 | `idx_classification_label` | 특정 라벨 댓글 조회 |
| Agent 액션별 조회 | `idx_agent_action` | 액션별 댓글 조회 |
| Aspect별 분석 | `idx_aspect_id` | 특정 aspect 언급 조회 |

### 4.3 Composite 인덱스
- `idx_classification_label_confidence`: 라벨 + 신뢰도 정렬
- `idx_aspect_comment_aspect`: 댓글 + aspect 조합 조회

### 4.4 Partial 인덱스
- `idx_agent_low_confidence WHERE is_low_confidence = TRUE`: 저신뢰도 댓글만
- `idx_agent_needs_review WHERE needs_human_review = TRUE`: 검토 필요 댓글만
- `idx_processing_failed WHERE status = 'FAILED'`: 실패한 처리만

### 4.5 JSONB 인덱스 (선택)
```sql
-- filter_metadata에서 특정 필드 검색
CREATE INDEX idx_rule_filter_metadata_gin 
    ON rule_filter_results USING GIN (filter_metadata);

-- classification_metadata 검색
CREATE INDEX idx_classification_metadata_gin 
    ON llm_classifications USING GIN (classification_metadata);
```

---

## 5. PostgreSQL DDL 전체

파일: `db_schema.sql` 참조

---

## 6. 설계 이유 및 장점

### 6.1 파이프라인 추적 가능성
- **각 단계별 독립 테이블**: 규칙 필터 → 분류 → Agent 결정을 각각 저장
- **FK 관계**: `agent_decisions`가 `rule_filter_results`, `llm_classifications` 참조
- **처리 로그**: `comment_processing_logs`로 전체 파이프라인 상태 추적

### 6.2 재처리 가능성
- **원본 보존**: `raw_comments`는 절대 변경하지 않음
- **결과 재생성**: 분류/분석 결과는 언제든 재생성 가능
- **버전 관리**: 규칙/분류기 버전 추적으로 롤백 가능

### 6.3 분석 유연성
- **정규화 설계**: aspect는 별도 테이블, 한 댓글이 여러 aspect 가능
- **동적 확장**: aspect, 질문 카테고리 동적 추가
- **집계 뷰**: 복잡한 집계 쿼리를 뷰로 캡슐화

### 6.4 성능 최적화
- **인덱스 전략**: 자주 쿼리하는 컬럼에 인덱스
- **Partial 인덱스**: 특정 조건만 인덱싱 (공간 절약)
- **ENUM 타입**: 문자열 대신 ENUM 사용 (저장 공간, 타입 안전성)

### 6.5 운영 효율성
- **재분류 큐**: 저신뢰도 댓글 자동 재처리
- **에러 추적**: 처리 실패 댓글 모니터링
- **성능 모니터링**: 필터/분류기 성능 뷰

### 6.6 확장성
- **JSONB 메타데이터**: 스키마 변경 없이 추가 정보 저장
- **버전 관리**: A/B 테스트, 모델 업그레이드 추적
- **모듈화**: 각 테이블이 독립적, 새 분석 추가 쉬움

---

## 7. 사용 예시

### 7.1 댓글 전체 파이프라인 조회
```sql
SELECT 
    rc.comment_id,
    rc.text_original,
    rfr.filter_status,
    rfr.rejected_by_rule,
    lc.label,
    lc.confidence,
    ad.final_action,
    ad.next_stage,
    sa.sentiment,
    sa.sentiment_score
FROM raw_comments rc
LEFT JOIN rule_filter_results rfr ON rc.comment_id = rfr.comment_id
LEFT JOIN llm_classifications lc ON rc.comment_id = lc.comment_id
LEFT JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
LEFT JOIN sentiment_analysis sa ON rc.comment_id = sa.comment_id
WHERE rc.video_id = 'VIDEO_ID_HERE'
ORDER BY rc.published_at DESC;
```

### 7.2 비디오별 aspect 분석
```sql
SELECT 
    adef.aspect_name,
    COUNT(*) AS mention_count,
    ROUND(AVG(ae.aspect_sentiment_score), 2) AS avg_sentiment,
    STRING_AGG(rc.text_original, ' | ' ORDER BY ae.aspect_sentiment_score DESC) AS sample_comments
FROM raw_comments rc
JOIN aspect_extractions ae ON rc.comment_id = ae.comment_id
JOIN aspect_definitions adef ON ae.aspect_id = adef.id
WHERE rc.video_id = 'VIDEO_ID_HERE'
GROUP BY adef.aspect_name
ORDER BY mention_count DESC;
```

### 7.3 재분류가 필요한 댓글 조회
```sql
SELECT 
    rc.comment_id,
    rc.text_original,
    lc.label,
    lc.confidence,
    ad.decision_reasoning
FROM raw_comments rc
JOIN llm_classifications lc ON rc.comment_id = lc.comment_id
JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
WHERE ad.needs_reclassification = TRUE
ORDER BY lc.confidence ASC
LIMIT 100;
```

---

## 8. Materialized View (성능 최적화)

자주 조회하는 집계는 Materialized View로 캐싱:

```sql
CREATE MATERIALIZED VIEW mv_video_analysis_summary AS
SELECT 
    rc.video_id,
    COUNT(DISTINCT rc.comment_id) AS total_comments,
    COUNT(DISTINCT CASE WHEN ad.final_action = 'ANALYZE' THEN rc.comment_id END) AS analyzed_count,
    COUNT(DISTINCT CASE WHEN ad.final_action = 'EXCLUDE' THEN rc.comment_id END) AS excluded_count,
    ROUND(AVG(sa.sentiment_score), 4) AS avg_sentiment,
    COUNT(DISTINCT ae.aspect_id) AS aspects_mentioned,
    COUNT(DISTINCT pq.comment_id) AS questions_count,
    MAX(rc.collected_at) AS last_updated
FROM raw_comments rc
LEFT JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
LEFT JOIN sentiment_analysis sa ON rc.comment_id = sa.comment_id
LEFT JOIN aspect_extractions ae ON rc.comment_id = ae.comment_id
LEFT JOIN product_questions pq ON rc.comment_id = pq.comment_id
GROUP BY rc.video_id;

-- 인덱스
CREATE UNIQUE INDEX idx_mv_video_analysis_video_id 
    ON mv_video_analysis_summary(video_id);

-- 주기적 REFRESH (cron 또는 trigger)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_video_analysis_summary;
```

---

## 9. 마이그레이션 전략

### 9.1 단계별 마이그레이션
1. **Phase 1**: Core 테이블 생성 (raw_comments ~ agent_decisions)
2. **Phase 2**: Analysis 테이블 추가 (sentiment ~ product_questions)
3. **Phase 3**: Metadata/Tracking 테이블 추가
4. **Phase 4**: 뷰 생성

### 9.2 기존 데이터 마이그레이션
```sql
-- 기존 comments 테이블에서 raw_comments로 이관
INSERT INTO raw_comments (comment_id, video_id, text_original, ...)
SELECT id, video_id, text, ...
FROM old_comments_table
ON CONFLICT (comment_id) DO NOTHING;
```

---

## 10. 백업 및 파티셔닝 전략

### 10.1 파티셔닝 (대용량 데이터)
댓글이 수백만 건 이상인 경우, 시간 기반 파티셔닝:

```sql
-- raw_comments 파티셔닝 예시
CREATE TABLE raw_comments (
    ...
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (collected_at);

CREATE TABLE raw_comments_2026_01 PARTITION OF raw_comments
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE raw_comments_2026_02 PARTITION OF raw_comments
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

### 10.2 아카이빙
오래된 제외 댓글은 별도 아카이브 테이블로 이동:

```sql
CREATE TABLE excluded_comments_archive (
    LIKE excluded_comments_log INCLUDING ALL
);

-- 6개월 이상 된 제외 댓글 아카이빙
INSERT INTO excluded_comments_archive
SELECT * FROM excluded_comments_log
WHERE excluded_at < NOW() - INTERVAL '6 months';

DELETE FROM excluded_comments_log
WHERE excluded_at < NOW() - INTERVAL '6 months';
```

---

이 설계로 전체 파이프라인을 완벽하게 추적하고, 분석하고, 최적화할 수 있습니다! 🚀
