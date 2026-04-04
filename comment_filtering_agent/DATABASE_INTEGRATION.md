# 기존 DB와 댓글 필터링 Agent DB 통합 설계

## 1. 기존 DB 구조 분석

### 1.1 기존 테이블
```sql
-- 제품 테이블
tech_products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    brand VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
)

-- 비디오 테이블
videos (
    video_id VARCHAR(64) PRIMARY KEY,
    product_id INT NOT NULL REFERENCES tech_products(product_id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    published_at TIMESTAMP,
    thumbnail_url TEXT,
    view_count BIGINT,
    like_count BIGINT,
    comment_count BIGINT,
    created_at TIMESTAMP DEFAULT NOW()
)
```

---

## 2. 통합 전략

### 2.1 재사용 테이블 (기존 사용)
✅ **`tech_products`** - 그대로 사용
✅ **`videos`** - 그대로 사용

### 2.2 새로 추가할 테이블 (Agent용)
🆕 **댓글 관련 19개 테이블** - 새로 생성

### 2.3 통합 포인트
- `raw_comments.video_id` → `videos.video_id` (FK)
- 제품 분석 시 `videos.product_id` → `tech_products.product_id` 조인

---

## 3. 통합 ERD

```
┌─────────────────────────┐
│    tech_products        │ ← 기존 테이블 (재사용)
│  product_id (PK)        │
│  name                   │
│  brand                  │
└─────────────────────────┘
            │ 1
            │
            │ N
┌─────────────────────────┐
│    videos               │ ← 기존 테이블 (재사용)
│  video_id (PK)          │
│  product_id (FK)        │
│  title                  │
│  view_count             │
└─────────────────────────┘
            │ 1
            │
            │ N
┌─────────────────────────┐
│    raw_comments         │ ← 새 테이블
│  comment_id (PK)        │
│  video_id (FK) ────────┘
│  text_original          │
│  author_name            │
└─────────────────────────┘
            │
            ↓
    [1차 규칙 필터]
            │
            ↓
┌─────────────────────────┐
│  rule_filter_results    │
└─────────────────────────┘
            │
            ↓
    [2차 LLM 분류]
            │
            ↓
┌─────────────────────────┐
│  llm_classifications    │
└─────────────────────────┘
            │
            ↓
    [Agent 최종 결정]
            │
            ↓
┌─────────────────────────┐
│  agent_decisions        │
└─────────────────────────┘
            │
            ├─────────────┬─────────────┬─────────────┐
            ↓             ↓             ↓             ↓
    ┌───────────┐ ┌──────────┐ ┌────────────┐ ┌─────────┐
    │sentiment  │ │aspect    │ │product     │ │excluded │
    │_analysis  │ │extraction│ │_questions  │ │_log     │
    └───────────┘ └──────────┘ └────────────┘ └─────────┘
```

---

## 4. 수정된 raw_comments 테이블 (FK 추가)

```sql
CREATE TABLE raw_comments (
    comment_id VARCHAR(255) PRIMARY KEY,
    video_id VARCHAR(64) NOT NULL,  -- videos.video_id 참조
    author_name VARCHAR(500),
    author_channel_id VARCHAR(255),
    text_original TEXT NOT NULL,
    text_display TEXT,
    like_count INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    published_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    collection_batch_id UUID,
    is_reply BOOLEAN DEFAULT FALSE,
    parent_comment_id VARCHAR(255),
    
    -- FK 제약 (기존 videos 테이블과 연결)
    CONSTRAINT fk_video
        FOREIGN KEY (video_id)
        REFERENCES videos(video_id)
        ON DELETE CASCADE,  -- 비디오 삭제 시 댓글도 삭제
        
    CONSTRAINT fk_parent_comment 
        FOREIGN KEY (parent_comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE SET NULL
);
```

**변경 사항**:
- `video_id VARCHAR(64)` → 기존 `videos` 테이블과 동일한 타입
- `CONSTRAINT fk_video` 추가 → `videos.video_id` 참조

---

## 5. 통합 후 전체 테이블 구조

### 5.1 기존 테이블 (2개)
```
[Core - Products & Videos]
├── tech_products          (기존, 그대로 사용)
└── videos                 (기존, 그대로 사용)
```

### 5.2 새 테이블 (19개)
```
[Core - Comments Pipeline]
├── raw_comments           (NEW, videos와 FK 연결)
├── rule_filter_results    (NEW)
├── llm_classifications    (NEW)
└── agent_decisions        (NEW)

[Analysis Results]
├── sentiment_analysis     (NEW)
├── aspect_extractions     (NEW)
└── product_questions      (NEW)

[Metadata]
├── aspect_definitions     (NEW)
├── question_categories    (NEW)
├── filter_rules_versions  (NEW)
└── classifier_versions    (NEW)

[Tracking]
├── excluded_comments_log  (NEW)
├── comment_processing_logs (NEW)
└── reclassification_queue (NEW)

[Views]
├── v_product_sentiment_summary      (NEW)
├── v_aspect_analysis_summary        (NEW)
├── v_question_frequency             (NEW)
└── v_filter_performance             (NEW)
```

**총 21개 테이블 + 4개 뷰**

---

## 6. 제품별 분석 통합 쿼리

### 6.1 제품별 댓글 감정 분석
```sql
-- 제품별 감정 집계 (tech_products → videos → raw_comments 조인)
SELECT 
    tp.product_id,
    tp.name AS product_name,
    tp.brand,
    COUNT(DISTINCT v.video_id) AS video_count,
    COUNT(DISTINCT rc.comment_id) AS total_comments,
    COUNT(DISTINCT CASE WHEN ad.final_action = 'ANALYZE' THEN rc.comment_id END) AS analyzed_comments,
    COUNT(DISTINCT CASE WHEN sa.sentiment = 'POSITIVE' THEN rc.comment_id END) AS positive_comments,
    COUNT(DISTINCT CASE WHEN sa.sentiment = 'NEGATIVE' THEN rc.comment_id END) AS negative_comments,
    ROUND(AVG(sa.sentiment_score), 4) AS avg_sentiment_score
FROM tech_products tp
JOIN videos v ON tp.product_id = v.product_id
JOIN raw_comments rc ON v.video_id = rc.video_id
LEFT JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
LEFT JOIN sentiment_analysis sa ON rc.comment_id = sa.comment_id
GROUP BY tp.product_id, tp.name, tp.brand
ORDER BY tp.product_id DESC;
```

### 6.2 제품별 Aspect 분석
```sql
-- 제품별 Aspect 언급 및 감정
SELECT 
    tp.product_id,
    tp.name AS product_name,
    adef.aspect_name,
    COUNT(*) AS mention_count,
    COUNT(*) FILTER (WHERE ae.aspect_sentiment = 'POSITIVE') AS positive_mentions,
    COUNT(*) FILTER (WHERE ae.aspect_sentiment = 'NEGATIVE') AS negative_mentions,
    ROUND(AVG(ae.aspect_sentiment_score), 2) AS avg_aspect_sentiment,
    ARRAY_AGG(rc.text_original ORDER BY ae.aspect_sentiment_score DESC LIMIT 3) AS top_comments
FROM tech_products tp
JOIN videos v ON tp.product_id = v.product_id
JOIN raw_comments rc ON v.video_id = rc.video_id
JOIN aspect_extractions ae ON rc.comment_id = ae.comment_id
JOIN aspect_definitions adef ON ae.aspect_id = adef.id
GROUP BY tp.product_id, tp.name, adef.aspect_name
ORDER BY tp.product_id, mention_count DESC;
```

### 6.3 제품별 질문 빈도
```sql
-- 제품에 대한 질문 빈도
SELECT 
    tp.product_id,
    tp.name AS product_name,
    qc.category_name AS question_category,
    COUNT(*) AS question_count,
    COUNT(*) FILTER (WHERE pq.is_answered = FALSE) AS unanswered_count
FROM tech_products tp
JOIN videos v ON tp.product_id = v.product_id
JOIN raw_comments rc ON v.video_id = rc.video_id
JOIN product_questions pq ON rc.comment_id = pq.comment_id
LEFT JOIN question_categories qc ON pq.question_category_id = qc.id
GROUP BY tp.product_id, tp.name, qc.category_name
ORDER BY tp.product_id, question_count DESC;
```

---

## 7. 통합 뷰 (제품 중심)

### 7.1 제품별 종합 분석 뷰
```sql
CREATE OR REPLACE VIEW v_product_comprehensive_analysis AS
SELECT 
    tp.product_id,
    tp.name AS product_name,
    tp.brand,
    
    -- 비디오 통계
    COUNT(DISTINCT v.video_id) AS video_count,
    SUM(v.view_count) AS total_views,
    SUM(v.like_count) AS total_likes,
    SUM(v.comment_count) AS total_comments_from_youtube,
    
    -- 댓글 수집 통계
    COUNT(DISTINCT rc.comment_id) AS collected_comments,
    COUNT(DISTINCT CASE WHEN ad.final_action = 'ANALYZE' THEN rc.comment_id END) AS analyzed_comments,
    COUNT(DISTINCT CASE WHEN ad.final_action = 'EXCLUDE' THEN rc.comment_id END) AS excluded_comments,
    
    -- 감정 분석
    COUNT(DISTINCT CASE WHEN sa.sentiment = 'POSITIVE' THEN rc.comment_id END) AS positive_count,
    COUNT(DISTINCT CASE WHEN sa.sentiment = 'NEGATIVE' THEN rc.comment_id END) AS negative_count,
    ROUND(AVG(sa.sentiment_score), 4) AS avg_sentiment,
    
    -- Aspect 분석
    COUNT(DISTINCT ae.aspect_id) AS aspects_mentioned_count,
    
    -- 질문 분석
    COUNT(DISTINCT pq.comment_id) AS questions_count,
    
    -- 최근 업데이트
    MAX(rc.collected_at) AS last_comment_collected_at
FROM tech_products tp
LEFT JOIN videos v ON tp.product_id = v.product_id
LEFT JOIN raw_comments rc ON v.video_id = rc.video_id
LEFT JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
LEFT JOIN sentiment_analysis sa ON rc.comment_id = sa.comment_id
LEFT JOIN aspect_extractions ae ON rc.comment_id = ae.comment_id
LEFT JOIN product_questions pq ON rc.comment_id = pq.comment_id
GROUP BY tp.product_id, tp.name, tp.brand;

COMMENT ON VIEW v_product_comprehensive_analysis IS '제품별 종합 분석 (비디오, 댓글, 감정, aspect, 질문 통합)';
```

---

## 8. 마이그레이션 DDL (통합 버전)

### 8.1 순서
```sql
-- 1. 기존 테이블 확인 (이미 존재)
SELECT * FROM tech_products;
SELECT * FROM videos;

-- 2. ENUM 타입 생성
CREATE TYPE filter_status AS ENUM ('PASS', 'REJECT');
CREATE TYPE comment_label AS ENUM (...);
-- ... (전체 ENUM)

-- 3. Metadata 테이블 생성
CREATE TABLE filter_rules_versions (...);
CREATE TABLE classifier_versions (...);
CREATE TABLE aspect_definitions (...);
CREATE TABLE question_categories (...);

-- 4. Core 테이블 생성 (raw_comments부터)
CREATE TABLE raw_comments (
    ...
    video_id VARCHAR(64) NOT NULL,
    CONSTRAINT fk_video
        FOREIGN KEY (video_id)
        REFERENCES videos(video_id)  -- ← 기존 테이블과 연결
        ON DELETE CASCADE
);

-- 5. 나머지 Agent 테이블 생성
CREATE TABLE rule_filter_results (...);
CREATE TABLE llm_classifications (...);
CREATE TABLE agent_decisions (...);
-- ...

-- 6. 뷰 생성
CREATE OR REPLACE VIEW v_product_comprehensive_analysis AS ...;
```

---

## 9. 통합 후 데이터 흐름

```
1. 제품 등록
   tech_products 테이블에 제품 추가
   
2. 비디오 수집
   YouTube API → videos 테이블 저장
   
3. 댓글 수집
   YouTube API → raw_comments 테이블 저장
   (video_id FK로 videos와 연결)
   
4. 댓글 필터링 파이프라인
   raw_comments
      ↓
   rule_filter_results
      ↓
   llm_classifications
      ↓
   agent_decisions
      ↓
   sentiment_analysis / aspect_extractions / product_questions
   
5. 제품별 분석 조회
   v_product_comprehensive_analysis 뷰 쿼리
```

---

## 10. 기존 코드 수정 최소화

### 10.1 기존 코드 그대로 유지
```python
# app/models.py - 변경 없음
@dataclass
class Product:
    product_id: int
    name: str
    brand: str | None
    created_at: datetime

@dataclass
class Video:
    video_id: str
    product_id: int
    title: str
    # ...
```

### 10.2 새 모델 추가
```python
# comment_filtering_agent/models.py - 새로 추가
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class CommentLabel(str, Enum):
    PRODUCT_OPINION = "PRODUCT_OPINION"
    # ...

@dataclass
class RawComment:
    comment_id: str
    video_id: str  # videos.video_id 참조
    text_original: str
    author_name: str
    # ...

@dataclass
class AgentDecision:
    comment_id: str
    final_action: str
    # ...
```

### 10.3 Repository 분리
```python
# app/repositories.py - 기존 그대로
class ProductRepository:
    # 기존 코드 유지
    pass

class VideoRepository:
    # 기존 코드 유지
    pass

# comment_filtering_agent/repositories.py - 새로 추가
class CommentRepository:
    def insert_raw_comment(self, comment: RawComment):
        """raw_comments 테이블에 삽입"""
        pass
    
    def get_comments_by_video(self, video_id: str):
        """특정 비디오의 댓글 조회"""
        pass

class AgentDecisionRepository:
    def insert_decision(self, decision: AgentDecision):
        """agent_decisions 테이블에 삽입"""
        pass
```

---

## 11. 통합의 장점

### 11.1 데이터 일관성
✅ 기존 `tech_products`, `videos` 테이블 재사용
✅ FK 제약으로 데이터 무결성 보장
✅ 제품 삭제 시 관련 비디오/댓글 cascade 삭제

### 11.2 분석 유연성
✅ 제품별, 비디오별, 댓글별 모든 레벨 분석 가능
✅ `tech_products` → `videos` → `raw_comments` 조인으로 제품 중심 분석
✅ 단일 비디오 분석도 가능

### 11.3 기존 코드 호환성
✅ 기존 `ProductRepository`, `VideoRepository` 변경 없음
✅ 새 Agent 관련 코드는 별도 모듈로 분리
✅ 점진적 마이그레이션 가능

### 11.4 확장성
✅ 향후 새로운 분석 테이블 추가 쉬움
✅ 제품-비디오-댓글 계층 구조 명확
✅ 뷰를 통한 복잡한 집계 쿼리 캡슐화

---

## 12. 마이그레이션 체크리스트

- [ ] 1. 기존 DB 백업
- [ ] 2. ENUM 타입 생성 (PostgreSQL)
- [ ] 3. Metadata 테이블 생성 (aspect_definitions 등)
- [ ] 4. `raw_comments` 테이블 생성 (FK 포함)
- [ ] 5. Agent 파이프라인 테이블 생성
- [ ] 6. 분석 테이블 생성 (sentiment, aspect 등)
- [ ] 7. 추적 테이블 생성 (logs, queue)
- [ ] 8. 통합 뷰 생성 (v_product_comprehensive_analysis)
- [ ] 9. 초기 데이터 삽입 (aspect, categories)
- [ ] 10. 인덱스 생성 확인
- [ ] 11. FK 제약 테스트 (CASCADE 동작 확인)
- [ ] 12. 기존 코드 동작 확인

---

## 13. 통합 쿼리 예시

### 13.1 특정 제품의 전체 분석
```sql
SELECT * 
FROM v_product_comprehensive_analysis 
WHERE product_id = 1;
```

### 13.2 특정 비디오의 댓글 파이프라인 추적
```sql
SELECT 
    rc.comment_id,
    rc.text_original,
    rfr.filter_status,
    lc.label,
    lc.confidence,
    ad.final_action,
    sa.sentiment
FROM raw_comments rc
LEFT JOIN rule_filter_results rfr ON rc.comment_id = rfr.comment_id
LEFT JOIN llm_classifications lc ON rc.comment_id = lc.comment_id
LEFT JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
LEFT JOIN sentiment_analysis sa ON rc.comment_id = sa.comment_id
WHERE rc.video_id = 'VIDEO_ID_HERE'
ORDER BY rc.published_at DESC;
```

### 13.3 제품 간 비교
```sql
SELECT 
    product_name,
    brand,
    analyzed_comments,
    avg_sentiment,
    ROUND(positive_count::NUMERIC / NULLIF(analyzed_comments, 0) * 100, 2) AS positive_ratio
FROM v_product_comprehensive_analysis
WHERE analyzed_comments > 10
ORDER BY avg_sentiment DESC;
```

---

이 통합 설계로 기존 시스템을 건드리지 않고 새로운 Agent 시스템을 추가할 수 있습니다! 🚀
