-- ================================================
-- 댓글 필터링 Agent Database Schema
-- PostgreSQL 14+
-- ================================================

-- ================================================
-- 1. ENUMS & CUSTOM TYPES
-- ================================================

CREATE TYPE filter_status AS ENUM ('PASS', 'REJECT');

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

CREATE TYPE agent_action AS ENUM (
    'ANALYZE',
    'AUXILIARY_STORE',
    'EXCLUDE',
    'HOLD',
    'RECLASSIFY'
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

CREATE TYPE sentiment_type AS ENUM ('POSITIVE', 'NEUTRAL', 'NEGATIVE');

CREATE TYPE processing_stage AS ENUM (
    'COLLECTED',
    'RULE_FILTERED',
    'LLM_CLASSIFIED',
    'AGENT_DECIDED',
    'ANALYZED',
    'COMPLETED',
    'FAILED'
);

-- ================================================
-- 2. METADATA TABLES (생성 우선순위: 먼저)
-- ================================================

-- 2.1 필터 규칙 버전 관리
CREATE TABLE filter_rules_versions (
    id SERIAL PRIMARY KEY,
    version_name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    rules_config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deprecated_at TIMESTAMPTZ
);

-- 2.2 분류기 버전 관리
CREATE TABLE classifier_versions (
    id SERIAL PRIMARY KEY,
    version_name VARCHAR(50) NOT NULL UNIQUE,
    classifier_type classifier_type NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    prompt_template TEXT,
    model_path VARCHAR(500),
    performance_metrics JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deprecated_at TIMESTAMPTZ
);

-- 2.3 Aspect 정의
CREATE TABLE aspect_definitions (
    id SERIAL PRIMARY KEY,
    aspect_name VARCHAR(100) NOT NULL UNIQUE,
    aspect_name_en VARCHAR(100),
    category VARCHAR(50),
    description TEXT,
    keywords TEXT[],
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

-- 2.4 질문 카테고리
CREATE TABLE question_categories (
    id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    category_name_en VARCHAR(100),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ================================================
-- 3. CORE TABLES
-- ================================================

-- 3.1 원본 댓글
CREATE TABLE raw_comments (
    comment_id VARCHAR(255) PRIMARY KEY,
    video_id VARCHAR(255) NOT NULL,
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
    
    CONSTRAINT fk_parent_comment 
        FOREIGN KEY (parent_comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE SET NULL
);

CREATE INDEX idx_raw_comments_video_id ON raw_comments(video_id);
CREATE INDEX idx_raw_comments_published_at ON raw_comments(published_at DESC);
CREATE INDEX idx_raw_comments_collected_at ON raw_comments(collected_at DESC);
CREATE INDEX idx_raw_comments_batch_id ON raw_comments(collection_batch_id);

CREATE UNIQUE INDEX uk_raw_comments_dedup 
    ON raw_comments(video_id, author_channel_id, text_original, published_at)
    WHERE parent_comment_id IS NULL;

COMMENT ON TABLE raw_comments IS '원본 댓글 저장 (재처리의 기준점)';

-- 3.2 규칙 필터 결과
CREATE TABLE rule_filter_results (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL,
    filter_status filter_status NOT NULL,
    rejected_by_rule VARCHAR(100),
    reject_reason TEXT,
    rule_version_id INTEGER,
    filter_metadata JSONB,
    filtered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_comment_rule_filter 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_rule_version
        FOREIGN KEY (rule_version_id)
        REFERENCES filter_rules_versions(id)
        ON DELETE SET NULL
);

CREATE INDEX idx_rule_filter_comment_id ON rule_filter_results(comment_id);
CREATE INDEX idx_rule_filter_status ON rule_filter_results(filter_status);
CREATE INDEX idx_rule_filter_rejected_by ON rule_filter_results(rejected_by_rule);
CREATE INDEX idx_rule_filter_version ON rule_filter_results(rule_version_id);

CREATE UNIQUE INDEX uk_one_filter_result_per_comment 
    ON rule_filter_results(comment_id, rule_version_id);

COMMENT ON TABLE rule_filter_results IS '1차 규칙 필터 결과';

-- 3.3 LLM 분류 결과
CREATE TABLE llm_classifications (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL,
    label comment_label NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL,
    reasoning TEXT,
    classifier_type classifier_type NOT NULL,
    classifier_version_id INTEGER,
    model_name VARCHAR(100),
    prompt_version VARCHAR(50),
    llm_provider VARCHAR(50),
    tokens_used INTEGER,
    latency_ms INTEGER,
    classification_metadata JSONB,
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
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

CREATE INDEX idx_classification_comment_id ON llm_classifications(comment_id);
CREATE INDEX idx_classification_label ON llm_classifications(label);
CREATE INDEX idx_classification_confidence ON llm_classifications(confidence);
CREATE INDEX idx_classification_classifier_type ON llm_classifications(classifier_type);
CREATE INDEX idx_classification_version ON llm_classifications(classifier_version_id);
CREATE INDEX idx_classification_label_confidence 
    ON llm_classifications(label, confidence DESC);

CREATE UNIQUE INDEX uk_one_classification_per_comment 
    ON llm_classifications(comment_id, classifier_version_id);

COMMENT ON TABLE llm_classifications IS '2차 LLM 분류 결과';

-- 3.4 Agent 최종 결정
CREATE TABLE agent_decisions (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL,
    rule_filter_result_id BIGINT,
    llm_classification_id BIGINT,
    final_action agent_action NOT NULL,
    next_stage VARCHAR(100),
    exclusion_reason exclusion_reason,
    exclusion_details TEXT,
    is_low_confidence BOOLEAN DEFAULT FALSE,
    needs_human_review BOOLEAN DEFAULT FALSE,
    needs_reclassification BOOLEAN DEFAULT FALSE,
    decision_reasoning TEXT,
    agent_version VARCHAR(50),
    confidence_threshold NUMERIC(3, 2),
    decision_metadata JSONB,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
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

CREATE INDEX idx_agent_comment_id ON agent_decisions(comment_id);
CREATE INDEX idx_agent_action ON agent_decisions(final_action);
CREATE INDEX idx_agent_exclusion_reason ON agent_decisions(exclusion_reason);
CREATE INDEX idx_agent_low_confidence ON agent_decisions(is_low_confidence) 
    WHERE is_low_confidence = TRUE;
CREATE INDEX idx_agent_needs_review ON agent_decisions(needs_human_review) 
    WHERE needs_human_review = TRUE;
CREATE INDEX idx_agent_action_decided 
    ON agent_decisions(final_action, decided_at DESC);

CREATE UNIQUE INDEX uk_one_decision_per_comment 
    ON agent_decisions(comment_id, agent_version);

COMMENT ON TABLE agent_decisions IS 'Agent 최종 판단 결과';

-- ================================================
-- 4. ANALYSIS TABLES
-- ================================================

-- 4.1 감정 분석
CREATE TABLE sentiment_analysis (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL UNIQUE,
    agent_decision_id BIGINT NOT NULL,
    sentiment sentiment_type NOT NULL,
    sentiment_score NUMERIC(5, 4) NOT NULL,
    positive_score NUMERIC(5, 4),
    neutral_score NUMERIC(5, 4),
    negative_score NUMERIC(5, 4),
    intensity VARCHAR(20),
    sentiment_model VARCHAR(100),
    model_version VARCHAR(50),
    analysis_reasoning TEXT,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
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

CREATE INDEX idx_sentiment_comment_id ON sentiment_analysis(comment_id);
CREATE INDEX idx_sentiment_type ON sentiment_analysis(sentiment);
CREATE INDEX idx_sentiment_score ON sentiment_analysis(sentiment_score DESC);

COMMENT ON TABLE sentiment_analysis IS '감정 분석 결과';

-- 4.2 Aspect 추출
CREATE TABLE aspect_extractions (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL,
    aspect_id INTEGER NOT NULL,
    mention_text TEXT,
    mention_context TEXT,
    aspect_sentiment sentiment_type,
    aspect_sentiment_score NUMERIC(5, 4),
    extraction_confidence NUMERIC(5, 4),
    extraction_method VARCHAR(50),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_comment_aspect 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_aspect_definition
        FOREIGN KEY (aspect_id)
        REFERENCES aspect_definitions(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_aspect_comment_id ON aspect_extractions(comment_id);
CREATE INDEX idx_aspect_id ON aspect_extractions(aspect_id);
CREATE INDEX idx_aspect_sentiment ON aspect_extractions(aspect_sentiment);
CREATE INDEX idx_aspect_comment_aspect 
    ON aspect_extractions(comment_id, aspect_id);

CREATE UNIQUE INDEX uk_one_aspect_per_comment 
    ON aspect_extractions(comment_id, aspect_id);

COMMENT ON TABLE aspect_extractions IS 'Aspect 추출 결과 (정규화)';

-- 4.3 제품 질문
CREATE TABLE product_questions (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL UNIQUE,
    agent_decision_id BIGINT NOT NULL,
    question_text TEXT NOT NULL,
    question_category_id INTEGER,
    is_product_related BOOLEAN DEFAULT TRUE,
    is_answered BOOLEAN DEFAULT FALSE,
    mentioned_aspects INTEGER[],
    question_keywords TEXT[],
    priority INTEGER DEFAULT 0,
    stored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
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

CREATE INDEX idx_question_comment_id ON product_questions(comment_id);
CREATE INDEX idx_question_category ON product_questions(question_category_id);
CREATE INDEX idx_question_answered ON product_questions(is_answered) 
    WHERE is_answered = FALSE;
CREATE INDEX idx_question_priority ON product_questions(priority DESC);

COMMENT ON TABLE product_questions IS '제품 질문 댓글';

-- ================================================
-- 5. TRACKING TABLES
-- ================================================

-- 5.1 제외 댓글 로그
CREATE TABLE excluded_comments_log (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL,
    agent_decision_id BIGINT NOT NULL,
    exclusion_reason exclusion_reason NOT NULL,
    exclusion_stage VARCHAR(50),
    details TEXT,
    video_id VARCHAR(255),
    original_label comment_label,
    excluded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_comment_excluded 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_agent_decision_excluded
        FOREIGN KEY (agent_decision_id)
        REFERENCES agent_decisions(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_excluded_reason ON excluded_comments_log(exclusion_reason);
CREATE INDEX idx_excluded_stage ON excluded_comments_log(exclusion_stage);
CREATE INDEX idx_excluded_video ON excluded_comments_log(video_id);
CREATE INDEX idx_excluded_at ON excluded_comments_log(excluded_at DESC);

COMMENT ON TABLE excluded_comments_log IS '제외 댓글 추적';

-- 5.2 댓글 처리 로그
CREATE TABLE comment_processing_logs (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL,
    stage processing_stage NOT NULL,
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    error_stack TEXT,
    processing_time_ms INTEGER,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_comment_log 
        FOREIGN KEY (comment_id) 
        REFERENCES raw_comments(comment_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_processing_comment_id ON comment_processing_logs(comment_id);
CREATE INDEX idx_processing_stage ON comment_processing_logs(stage);
CREATE INDEX idx_processing_status ON comment_processing_logs(status);
CREATE INDEX idx_processing_failed ON comment_processing_logs(stage, status) 
    WHERE status = 'FAILED';

COMMENT ON TABLE comment_processing_logs IS '댓글 처리 이력 추적';

-- 5.3 재분류 대기열
CREATE TABLE reclassification_queue (
    id BIGSERIAL PRIMARY KEY,
    comment_id VARCHAR(255) NOT NULL,
    original_classification_id BIGINT,
    reason VARCHAR(100) NOT NULL,
    priority INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'PENDING',
    new_classification_id BIGINT,
    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
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

CREATE INDEX idx_reclass_status ON reclassification_queue(status) 
    WHERE status = 'PENDING';
CREATE INDEX idx_reclass_priority ON reclassification_queue(priority DESC, queued_at);

COMMENT ON TABLE reclassification_queue IS '재분류 대기열';

-- ================================================
-- 6. VIEWS (집계 및 분석용)
-- ================================================

-- 6.1 제품별 감정 집계
CREATE OR REPLACE VIEW v_product_sentiment_summary AS
SELECT 
    rc.video_id,
    COUNT(*) AS total_analyzed_comments,
    COUNT(*) FILTER (WHERE sa.sentiment = 'POSITIVE') AS positive_count,
    COUNT(*) FILTER (WHERE sa.sentiment = 'NEUTRAL') AS neutral_count,
    COUNT(*) FILTER (WHERE sa.sentiment = 'NEGATIVE') AS negative_count,
    ROUND(AVG(sa.sentiment_score), 4) AS avg_sentiment_score,
    ROUND(
        COUNT(*) FILTER (WHERE sa.sentiment = 'POSITIVE')::NUMERIC / NULLIF(COUNT(*), 0) * 100, 
        2
    ) AS positive_ratio
FROM raw_comments rc
JOIN agent_decisions ad ON rc.comment_id = ad.comment_id
JOIN sentiment_analysis sa ON rc.comment_id = sa.comment_id
WHERE ad.final_action = 'ANALYZE'
GROUP BY rc.video_id;

COMMENT ON VIEW v_product_sentiment_summary IS '제품별 감정 분석 집계';

-- 6.2 Aspect별 분석 집계
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

COMMENT ON VIEW v_aspect_analysis_summary IS 'Aspect별 분석 집계';

-- 6.3 질문 빈도 집계
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

COMMENT ON VIEW v_question_frequency IS '질문 빈도 집계';

-- 6.4 필터 성능 모니터링
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
        COUNT(*) FILTER (WHERE rfr.filter_status = 'REJECT')::NUMERIC / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS reject_ratio
FROM rule_filter_results rfr
LEFT JOIN filter_rules_versions frv ON rfr.rule_version_id = frv.id
GROUP BY DATE_TRUNC('day', rfr.filtered_at), frv.version_name
ORDER BY filter_date DESC;

COMMENT ON VIEW v_filter_performance IS '필터 성능 모니터링';

-- ================================================
-- 7. INITIAL DATA (초기 데이터)
-- ================================================

-- Aspect 정의 초기 데이터
INSERT INTO aspect_definitions (aspect_name, aspect_name_en, category, keywords, display_order) VALUES
    ('발열', 'heating', 'hardware', ARRAY['발열', '뜨겁', '열', '온도', 'hot', 'heat'], 1),
    ('성능', 'performance', 'hardware', ARRAY['성능', '속도', '빠르', '느리', 'performance', 'speed'], 2),
    ('배터리', 'battery', 'hardware', ARRAY['배터리', '충전', '전력', 'battery', 'power'], 3),
    ('카메라', 'camera', 'hardware', ARRAY['카메라', '사진', '화질', 'camera', 'photo'], 4),
    ('디스플레이', 'display', 'hardware', ARRAY['화면', '디스플레이', '밝기', 'display', 'screen'], 5),
    ('소음', 'noise', 'hardware', ARRAY['소음', '소리', '시끄러', 'noise', 'sound'], 6),
    ('디자인', 'design', 'design', ARRAY['디자인', '외관', '예쁘', 'design', 'looks'], 7),
    ('가격', 'price', 'price', ARRAY['가격', '비싸', '저렴', '가성비', 'price', 'cost'], 8)
ON CONFLICT (aspect_name) DO NOTHING;

-- 질문 카테고리 초기 데이터
INSERT INTO question_categories (category_name, category_name_en, description) VALUES
    ('성능문의', 'performance_inquiry', '제품 성능에 대한 질문'),
    ('호환성', 'compatibility', '다른 제품과의 호환성 질문'),
    ('가격문의', 'price_inquiry', '가격 및 구매처 관련 질문'),
    ('사용법', 'usage', '제품 사용 방법 질문'),
    ('비교', 'comparison', '다른 제품과의 비교 질문'),
    ('기타', 'others', '기타 질문')
ON CONFLICT (category_name) DO NOTHING;

-- 기본 규칙 버전
INSERT INTO filter_rules_versions (version_name, description, rules_config) VALUES
    ('v1.0', '초기 규칙 필터', '{
        "min_length": 5,
        "max_emoji_ratio": 0.8,
        "block_urls": true,
        "profanity_check": true
    }'::jsonb)
ON CONFLICT (version_name) DO NOTHING;

-- 기본 분류기 버전
INSERT INTO classifier_versions (
    version_name, 
    classifier_type, 
    model_name, 
    prompt_template
) VALUES
    (
        'few-shot-v1', 
        'FEW_SHOT', 
        'llama-3.1-70b-versatile',
        '당신은 YouTube 제품 리뷰 댓글을 분류하는 전문가입니다...'
    )
ON CONFLICT (version_name) DO NOTHING;

-- ================================================
-- 8. FUNCTIONS & TRIGGERS (선택)
-- ================================================

-- 자동으로 updated_at 갱신
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_aspect_definitions_updated_at
    BEFORE UPDATE ON aspect_definitions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ================================================
-- END OF SCHEMA
-- ================================================
