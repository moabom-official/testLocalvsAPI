# 통합 DB 구조 ERD

## 전체 테이블 관계도

```mermaid
erDiagram
    %% ========================================
    %% 기존 테이블 (EXISTING)
    %% ========================================
    
    tech_products ||--o{ videos : "has many"
    
    tech_products {
        int product_id PK
        varchar name
        varchar brand
        timestamp created_at
    }
    
    videos {
        varchar video_id PK
        int product_id FK
        varchar title
        text description
        timestamp published_at
        text thumbnail_url
        bigint view_count
        bigint like_count
        bigint comment_count
        timestamp created_at
    }
    
    %% ========================================
    %% 댓글 파이프라인 (CORE)
    %% ========================================
    
    videos ||--o{ raw_comments : "has many"
    raw_comments ||--o| raw_comments : "parent of"
    
    raw_comments {
        varchar comment_id PK
        varchar video_id FK
        varchar author_name
        varchar author_channel_id
        text text_original
        text text_display
        int like_count
        int reply_count
        timestamptz published_at
        timestamptz collected_at
        uuid collection_batch_id
        boolean is_reply
        varchar parent_comment_id FK
    }
    
    raw_comments ||--o| rule_filter_results : "filtered by"
    filter_rules_versions ||--o{ rule_filter_results : "version"
    
    rule_filter_results {
        bigint id PK
        varchar comment_id FK
        filter_status filter_status
        varchar rejected_by_rule
        text reject_reason
        int rule_version_id FK
        jsonb filter_metadata
        timestamptz filtered_at
    }
    
    raw_comments ||--o| llm_classifications : "classified by"
    classifier_versions ||--o{ llm_classifications : "version"
    
    llm_classifications {
        bigint id PK
        varchar comment_id FK
        comment_label label
        numeric confidence
        text reasoning
        classifier_type classifier_type
        int classifier_version_id FK
        varchar model_name
        varchar prompt_version
        varchar llm_provider
        int tokens_used
        int latency_ms
        jsonb classification_metadata
        timestamptz classified_at
    }
    
    raw_comments ||--o| agent_decisions : "decided by"
    rule_filter_results ||--o{ agent_decisions : "based on"
    llm_classifications ||--o{ agent_decisions : "based on"
    
    agent_decisions {
        bigint id PK
        varchar comment_id FK
        bigint rule_filter_result_id FK
        bigint llm_classification_id FK
        agent_action final_action
        varchar next_stage
        exclusion_reason exclusion_reason
        text exclusion_details
        boolean is_low_confidence
        boolean needs_human_review
        boolean needs_reclassification
        text decision_reasoning
        varchar agent_version
        numeric confidence_threshold
        jsonb decision_metadata
        timestamptz decided_at
    }
    
    %% ========================================
    %% 분석 결과 (ANALYSIS)
    %% ========================================
    
    raw_comments ||--o| sentiment_analysis : "analyzed"
    agent_decisions ||--o{ sentiment_analysis : "triggers"
    
    sentiment_analysis {
        bigint id PK
        varchar comment_id FK
        bigint agent_decision_id FK
        sentiment_type sentiment
        numeric sentiment_score
        numeric positive_score
        numeric neutral_score
        numeric negative_score
        varchar intensity
        varchar sentiment_model
        varchar model_version
        text analysis_reasoning
        timestamptz analyzed_at
    }
    
    raw_comments ||--o{ aspect_extractions : "has aspects"
    aspect_definitions ||--o{ aspect_extractions : "defines"
    
    aspect_extractions {
        bigint id PK
        varchar comment_id FK
        int aspect_id FK
        text mention_text
        text mention_context
        sentiment_type aspect_sentiment
        numeric aspect_sentiment_score
        numeric extraction_confidence
        varchar extraction_method
        timestamptz extracted_at
    }
    
    raw_comments ||--o| product_questions : "is question"
    agent_decisions ||--o{ product_questions : "triggers"
    question_categories ||--o{ product_questions : "categorizes"
    
    product_questions {
        bigint id PK
        varchar comment_id FK
        bigint agent_decision_id FK
        text question_text
        int question_category_id FK
        boolean is_product_related
        boolean is_answered
        int_array mentioned_aspects
        text_array question_keywords
        int priority
        timestamptz stored_at
    }
    
    %% ========================================
    %% 메타데이터 (METADATA)
    %% ========================================
    
    filter_rules_versions {
        int id PK
        varchar version_name UK
        text description
        jsonb rules_config
        boolean is_active
        timestamptz created_at
        timestamptz deprecated_at
    }
    
    classifier_versions {
        int id PK
        varchar version_name UK
        classifier_type classifier_type
        varchar model_name
        text prompt_template
        varchar model_path
        jsonb performance_metrics
        boolean is_active
        timestamptz created_at
        timestamptz deprecated_at
    }
    
    aspect_definitions {
        int id PK
        varchar aspect_name UK
        varchar aspect_name_en
        varchar category
        text description
        text_array keywords
        boolean is_active
        int display_order
        timestamptz created_at
        timestamptz updated_at
    }
    
    question_categories {
        int id PK
        varchar category_name UK
        varchar category_name_en
        text description
        boolean is_active
        timestamptz created_at
    }
    
    %% ========================================
    %% 추적/로그 (TRACKING)
    %% ========================================
    
    raw_comments ||--o{ excluded_comments_log : "excluded"
    agent_decisions ||--o{ excluded_comments_log : "triggers"
    
    excluded_comments_log {
        bigint id PK
        varchar comment_id FK
        bigint agent_decision_id FK
        exclusion_reason exclusion_reason
        varchar exclusion_stage
        text details
        varchar video_id
        comment_label original_label
        timestamptz excluded_at
    }
    
    raw_comments ||--o{ comment_processing_logs : "logged"
    
    comment_processing_logs {
        bigint id PK
        varchar comment_id FK
        processing_stage stage
        varchar status
        text error_message
        text error_stack
        int processing_time_ms
        timestamptz logged_at
    }
    
    raw_comments ||--o{ reclassification_queue : "queued"
    llm_classifications ||--o{ reclassification_queue : "original"
    llm_classifications ||--o{ reclassification_queue : "new"
    
    reclassification_queue {
        bigint id PK
        varchar comment_id FK
        bigint original_classification_id FK
        varchar reason
        int priority
        varchar status
        bigint new_classification_id FK
        timestamptz queued_at
        timestamptz processed_at
    }
```

---

## 데이터 흐름도 (Flow Diagram)

```mermaid
flowchart TB
    subgraph EXISTING["🔵 기존 테이블"]
        TP[tech_products]
        V[videos]
    end
    
    subgraph CORE["🟢 댓글 파이프라인"]
        RC[raw_comments]
        RFR[rule_filter_results]
        LC[llm_classifications]
        AD[agent_decisions]
    end
    
    subgraph ANALYSIS["🟡 분석 결과"]
        SA[sentiment_analysis]
        AE[aspect_extractions]
        PQ[product_questions]
    end
    
    subgraph METADATA["🟣 메타데이터"]
        FRV[filter_rules_versions]
        CV[classifier_versions]
        ADEF[aspect_definitions]
        QC[question_categories]
    end
    
    subgraph TRACKING["🟠 추적/로그"]
        ECL[excluded_comments_log]
        CPL[comment_processing_logs]
        RQ[reclassification_queue]
    end
    
    %% 기존 테이블 관계
    TP -->|1:N| V
    
    %% 댓글 파이프라인
    V -->|1:N| RC
    RC --> RFR
    RFR --> AD
    RC --> LC
    LC --> AD
    
    %% 메타데이터 연결
    FRV -.->|version| RFR
    CV -.->|version| LC
    
    %% 분석 결과
    AD -->|ANALYZE| SA
    AD -->|ANALYZE| AE
    AD -->|AUXILIARY| PQ
    AD -->|EXCLUDE| ECL
    
    %% 메타데이터 연결
    ADEF -.->|defines| AE
    QC -.->|categorizes| PQ
    
    %% 추적
    RC -.->|logs| CPL
    RC -.->|requeue| RQ
    
    style EXISTING fill:#e3f2fd
    style CORE fill:#e8f5e9
    style ANALYSIS fill:#fff9c4
    style METADATA fill:#f3e5f5
    style TRACKING fill:#ffe0b2
```

---

## 계층 구조도 (Hierarchy)

```mermaid
graph TD
    subgraph L1["레벨 1: 제품"]
        TP[tech_products<br/>product_id, name, brand]
    end
    
    subgraph L2["레벨 2: 비디오"]
        V[videos<br/>video_id, title, view_count]
    end
    
    subgraph L3["레벨 3: 원본 댓글"]
        RC[raw_comments<br/>comment_id, text_original]
    end
    
    subgraph L4["레벨 4: 필터링"]
        RFR[rule_filter_results<br/>PASS/REJECT]
        LC[llm_classifications<br/>5개 라벨 분류]
    end
    
    subgraph L5["레벨 5: Agent 결정"]
        AD[agent_decisions<br/>ANALYZE/EXCLUDE/HOLD]
    end
    
    subgraph L6A["레벨 6A: 분석 (ANALYZE)"]
        SA[sentiment_analysis<br/>긍정/부정/중립]
        AE[aspect_extractions<br/>발열/성능/배터리 등]
    end
    
    subgraph L6B["레벨 6B: 질문 (AUXILIARY)"]
        PQ[product_questions<br/>제품 관련 질문]
    end
    
    subgraph L6C["레벨 6C: 제외 (EXCLUDE)"]
        ECL[excluded_comments_log<br/>제외 사유 추적]
    end
    
    TP --> V
    V --> RC
    RC --> RFR
    RC --> LC
    RFR --> AD
    LC --> AD
    AD -->|ANALYZE| SA
    AD -->|ANALYZE| AE
    AD -->|AUXILIARY| PQ
    AD -->|EXCLUDE| ECL
    
    style TP fill:#1976d2,color:#fff
    style V fill:#388e3c,color:#fff
    style RC fill:#fbc02d,color:#000
    style RFR fill:#f57c00,color:#fff
    style LC fill:#f57c00,color:#fff
    style AD fill:#d32f2f,color:#fff
    style SA fill:#7b1fa2,color:#fff
    style AE fill:#7b1fa2,color:#fff
    style PQ fill:#0288d1,color:#fff
    style ECL fill:#616161,color:#fff
```

---

## 제품별 분석 조인 경로

```mermaid
flowchart LR
    subgraph Query["제품별 감정 분석 쿼리"]
        direction TB
        Q1[tech_products]
        Q2[JOIN videos]
        Q3[JOIN raw_comments]
        Q4[JOIN agent_decisions]
        Q5[JOIN sentiment_analysis]
        
        Q1 --> Q2
        Q2 --> Q3
        Q3 --> Q4
        Q4 --> Q5
    end
    
    Result[["제품별 긍정/부정 비율<br/>평균 감정 점수<br/>분석 댓글 수"]]
    
    Query --> Result
    
    style Q1 fill:#e3f2fd
    style Q2 fill:#c8e6c9
    style Q3 fill:#fff9c4
    style Q4 fill:#ffccbc
    style Q5 fill:#f3e5f5
    style Result fill:#ffeb3b,stroke:#f57f17,stroke-width:3px
```

---

## 테이블별 색상 범례

| 색상 | 카테고리 | 테이블 |
|------|----------|--------|
| 🔵 **파란색** | 기존 테이블 | tech_products, videos |
| 🟢 **초록색** | 댓글 파이프라인 | raw_comments, rule_filter_results, llm_classifications, agent_decisions |
| 🟡 **노란색** | 분석 결과 | sentiment_analysis, aspect_extractions, product_questions |
| 🟣 **보라색** | 메타데이터 | aspect_definitions, question_categories, filter_rules_versions, classifier_versions |
| 🟠 **주황색** | 추적/로그 | excluded_comments_log, comment_processing_logs, reclassification_queue |

---

## 주요 관계 요약

### 1:N 관계
- `tech_products` (1) ↔ `videos` (N)
- `videos` (1) ↔ `raw_comments` (N)
- `raw_comments` (1) ↔ `rule_filter_results` (1)
- `raw_comments` (1) ↔ `llm_classifications` (1)
- `raw_comments` (1) ↔ `agent_decisions` (1)
- `raw_comments` (1) ↔ `aspect_extractions` (N)

### 버전 관리
- `filter_rules_versions` → `rule_filter_results`
- `classifier_versions` → `llm_classifications`

### 정의 참조
- `aspect_definitions` → `aspect_extractions`
- `question_categories` → `product_questions`

### 추적
- `agent_decisions` → `sentiment_analysis` (1:1)
- `agent_decisions` → `product_questions` (1:1)
- `agent_decisions` → `excluded_comments_log` (1:N)

---

## 전체 테이블 개수

| 카테고리 | 개수 | 테이블 목록 |
|---------|------|------------|
| **기존** | 2 | tech_products, videos |
| **Core** | 4 | raw_comments, rule_filter_results, llm_classifications, agent_decisions |
| **Analysis** | 3 | sentiment_analysis, aspect_extractions, product_questions |
| **Metadata** | 4 | aspect_definitions, question_categories, filter_rules_versions, classifier_versions |
| **Tracking** | 3 | excluded_comments_log, comment_processing_logs, reclassification_queue |
| **뷰** | 4 | v_product_comprehensive_analysis, v_video_sentiment_summary, v_aspect_analysis_by_product, v_filter_performance |
| **합계** | **16 테이블 + 4 뷰** | **총 20개** |
