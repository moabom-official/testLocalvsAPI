# Claude Code 이관용 코드베이스 분석 문서 (2026-04-16)

## 1) 전체 파일 구조
**현재 상태: 적용됨**

### 디렉토리 트리 (실행/분석 관련 파일 중심)
```text
Moabom_Prototype/
├─ main_youtube_tech_review.py
├─ Dockerfile
├─ docker-compose.yml
├─ requirements-airflow.txt
├─ .env
├─ dags/
│  └─ youtube_product_sync_dag.py
├─ scripts/
│  ├─ main_youtube_tech_review.py
│  ├─ config.py
│  ├─ api/
│  │  ├─ products.py
│  │  ├─ videos.py
│  │  └─ sync.py
│  ├─ database/
│  │  ├─ connection.py
│  │  ├─ queries.py
│  │  └─ schema.py
│  ├─ youtube/
│  │  ├─ video_service.py
│  │  ├─ comment_service.py
│  │  └─ transcript_service.py
│  ├─ analysis/
│  │  ├─ product_filter.py
│  │  ├─ sentiment.py
│  │  └─ confidence_weights.py
│  ├─ reports/
│  │  ├─ transcript_report.py
│  │  ├─ comment_report.py
│  │  ├─ integrated_report.py
│  │  └─ pdf_generator.py
│  └─ utils/
│     ├─ prompt_manager.py
│     └─ markdown_renderer.py
├─ comment_filtering_agent/
│  ├─ core/
│  │  ├─ agent.py
│  │  └─ models.py
│  ├─ filters/
│  │  ├─ rule_based_filter.py
│  │  └─ models.py
│  ├─ classifiers/
│  │  ├─ base_classifier.py
│  │  ├─ groq_classifier.py
│  │  ├─ optimized_batch_classifier.py
│  │  ├─ async_batch_classifier.py
│  │  ├─ prompt_builder.py
│  │  └─ models.py
│  ├─ analyzers/
│  │  ├─ base_analyzer.py
│  │  ├─ groq_analyzer.py
│  │  ├─ question_processor.py
│  │  ├─ question_models.py
│  │  └─ models.py
│  ├─ services/
│  │  ├─ comment_collector.py
│  │  ├─ pipeline_orchestrator.py
│  │  ├─ report_generator.py
│  │  └─ report_models.py
│  ├─ cache/classification_cache.py
│  ├─ prompts/
│  │  ├─ batch_prompt_templates.py
│  │  └─ batch_prompt_optimized.py
│  └─ data/
│     ├─ profanity_list.txt
│     └─ reaction_patterns.json
├─ templates/
│  ├─ products.html
│  ├─ product_detail.html
│  └─ video_detail.html
├─ services/analysis/
│  ├─ analysis_pipeline_service.py
│  ├─ comment_filter_service.py
│  ├─ summarization_service.py
│  ├─ report_service.py
│  └─ airflow_analysis_runner.py
└─ app/
   ├─ app_factory.py
   ├─ config.py
   ├─ database.py
   ├─ repositories.py
   ├─ services.py
   ├─ templates.py
   ├─ models.py
   └─ schemas.py
```

### 주요 파일 한 줄 역할
- `main_youtube_tech_review.py`: 현재 FastAPI 실제 진입점(앱 생성, DB init, 라우트 등록).  
- `scripts/api/products.py`: 상품 목록/생성/상세 페이지 라우트.  
- `scripts/api/videos.py`: 영상 상세 페이지, 리포트 생성/표시, PDF 다운로드 라우트.  
- `scripts/api/sync.py`: YouTube 동기화 + Agent 기반 댓글 처리 파이프라인 핵심.  
- `scripts/database/schema.py`: 앱 시작 시 DB 스키마/마이그레이션 생성.  
- `comment_filtering_agent/core/agent.py`: 규칙필터+LLM 분류를 최종 액션으로 결정.  
- `comment_filtering_agent/core/models.py`: AgentAction/정책/결정 DTO 정의.  
- `comment_filtering_agent/classifiers/optimized_batch_classifier.py`: 배치 LLM 분류(캐시/재시도/내부 병렬).  
- `comment_filtering_agent/analyzers/groq_analyzer.py`: Groq 기반 감정/Aspect 분석 LLM 어댑터.  
- `dags/youtube_product_sync_dag.py`: Airflow 주기 동기화 파이프라인.

---

## 2) 코드 연결 흐름
**현재 상태: 적용됨**

### 엔트리포인트 → 라우터 등록
```text
main_youtube_tech_review.py
  ├─ startup_event() -> init_db()                          [scripts/database/schema.py]
  ├─ register_product_routes(app)                          [scripts/api/products.py]
  ├─ register_video_routes(app)                            [scripts/api/videos.py]
  └─ register_sync_routes(app)                             [scripts/api/sync.py]
```

### Route별 호출 흐름
1. `/products` 계열 (`scripts/api/products.py`)
   - `list_products()` -> `query_all("SELECT * FROM tech_products...")`
   - `create_product()` -> `execute_insert(...)` -> `query_one(...)`
   - `product_detail()` -> `query_one(product)` + `query_all(videos)`

2. `/products/{product_id}/videos/{video_id}` 계열 (`scripts/api/videos.py`)
   - `video_detail()`
     - 댓글 조회: `comments + agent_decisions + comment_sentiments` 조인 쿼리
     - 자막 없으면 `fetch_video_transcript(video_id)` 호출 후 `video_transcripts` upsert
     - `generate_and_save_all_reports(video_id, product_name)` 호출
       - 내부: `build_transcript_report` + `build_comment_sentiment_report` + `build_integrated_analysis_report`
       - 결과를 `video_reports` upsert
   - PDF 라우트 3종: `video_reports`에서 report text 읽고 `render_report_pdf()`

3. `/products/{product_id}/sync` (`scripts/api/sync.py`)
   - 기존 데이터 삭제(해당 product): `comment_sentiments -> comments -> video_transcripts -> video_reports -> videos`
   - `fetch_product_videos(product_name)`로 영상 수집/저장
   - 각 video마다 `process_comments_with_agent(video_id, product_name)` 실행
   - Agent 실패 시 fallback(`fetch_video_comments` + 키워드 기반 단순 sentiment 저장)

---

## 3) Agent 처리 파이프라인 (핵심)
**현재 상태: 적용됨**

### A. `scripts/api/sync.py` - `process_comments_with_agent()` 내부 흐름
```text
process_comments_with_agent(video_id, product_name)
  1) YouTubeCommentCollector.collect_comments()
  2) _spark_preprocess_comments()
     - null/blank 제거
     - dropDuplicates(video_id, author, text)
     - text_cleaned=trim(text), char_count/is_short/has_url/is_repetitive
  3) comments 테이블 upsert
  4) RuleBasedFilter.filter_single() 실행 + rule_filter_results upsert
  5) _preprocess_candidate_pool() (점수 기반 pool 축소)
  6) _select_comments_multicriteria() (소스별 top + overlap 우선)
  7) token budget trim
  8) classifier.classify_batch([...])  <-- LLM 분류
  9) 각 결과에 대해
     - llm_classifications upsert
     - agent.decide(...) -> agent_decisions upsert
     - final_action==ANALYZE 이면 sentiment_analyzer.analyze_single()  <-- LLM 감정/aspect
       -> comment_sentiments upsert(analysis_weight 포함)
       -> aspect_extractions insert
```

### B. LLM 호출 위치
- 분류 LLM:
  - `scripts/api/sync.py` -> `OptimizedBatchClassifier.classify_batch()` 호출
  - 실제 API 호출: `comment_filtering_agent/classifiers/optimized_batch_classifier.py::_classify_batch_llm()`
  - 호출 메서드: `self.client.chat.completions.create(...)`
- 감정/Aspect LLM:
  - `scripts/api/sync.py` -> `GroqAspectSentimentAnalyzer.analyze_single()` 호출
  - 실제 API 호출: `comment_filtering_agent/analyzers/groq_analyzer.py::_call_llm()`
  - 호출 메서드: `self.client.chat.completions.create(...)`

### C. `comment_filtering_agent/core/agent.py` - `decide()` 분기 로직
- 공통 우선순위
  1. `filter_result.is_passed=False` -> `EXCLUDE(RULE_FILTERED)`
  2. `classification_result is None` -> `HOLD(needs_human_review=True)`
  3. label별 핸들러 분기

- `PRODUCT_OPINION`
  - 현재: **확신도 무관 ANALYZE**
  - 저확신/재확인 필요는 제외가 아니라 플래그 처리
  - 플래그: `is_low_confidence`, `needs_human_review`

- `QUESTION`
  - `exclude_all_questions=True`면 EXCLUDE
  - 아니면 제품 관련 질문은 `AUXILIARY_STORE`, 비관련 질문은 `EXCLUDE(OFF_TOPIC_QUESTION)`

- `VIDEO_REACTION`
  - `allow_video_reaction_with_features=True`이고
  - `mentioned_features >= min_product_features_for_analysis`면 `ANALYZE`
  - 아니면 `EXCLUDE(VIDEO_REACTION)`

- `CHATTER`
  - `needs_recheck=True && confidence < reclassify_priority_high_confidence_threshold`면 `RECLASSIFY`
  - 그 외 `EXCLUDE(CHATTER)`

- `OFF_TOPIC`
  - `EXCLUDE(OFF_TOPIC)`

### D. confidence 관련 enum/상수/설정 정의 위치
- 액션/사유 enum: `comment_filtering_agent/core/models.py`
  - `AgentAction`, `ExclusionReason`
- 정책 threshold: `AgentPolicyConfig` (`core/models.py`)
  - `high/medium/low_confidence_threshold`
  - `reclassify_priority_high_confidence_threshold`
  - `hold_below_confidence`
- 분류기 confidence 설정: `comment_filtering_agent/classifiers/models.py`
  - `low_confidence_threshold`, `high_confidence_threshold`, `max_retries`, `retry_delay`
- 저확신 가중치: `scripts/analysis/confidence_weights.py`
  - `CONFIDENCE_WEIGHTS` + `LOW_CONFIDENCE_WARNING_THRESHOLD`

### E. `comment_filtering_agent/core/models.py` 설정값 확인
- `allow_video_reaction_with_features = True`
- `min_product_features_for_analysis = 2`

### F. `groq_analyzer.py` / `groq_classifier.py` 호출 방식
- `groq_analyzer.py`: `Groq` 클라이언트 생성 후 `chat.completions.create(response_format={"type":"json_object"})`
- `groq_classifier.py`: `Groq` 클라이언트 생성 후 `chat.completions.create(response_format={"type":"json_object"})`

---

## 4) DB 테이블 구조
**현재 상태: 적용됨**

### 스키마 생성 소스
- FastAPI startup: `init_db()` (`scripts/database/schema.py`)
- Airflow DAG: `ensure_schema()` (`dags/youtube_product_sync_dag.py`) - 일부 중복/축약 스키마

### 테이블 목록(앱 스키마 기준)
- `tech_products`, `videos`, `comments`, `comment_sentiments`
- `rule_filter_results`, `llm_classifications`, `agent_decisions`
- `aspect_definitions`, `aspect_extractions`
- `video_transcripts`, `video_reports`

### 주요 write 시점
1. `scripts/api/sync.py::sync_product_videos()`
   - product 단위 초기화 삭제
2. `scripts/api/sync.py::process_comments_with_agent()`
   - `comments` (수집/전처리 후)
   - `rule_filter_results` (1차 필터 직후)
   - `llm_classifications` (LLM 분류 직후)
   - `agent_decisions` (agent.decide 직후)
   - `comment_sentiments`, `aspect_extractions` (ANALYZE 분기)
3. `scripts/api/videos.py::video_detail()`
   - 자막 미존재 시 `video_transcripts` upsert
4. `scripts/reports/integrated_report.py::upsert_video_report()`
   - `video_reports` upsert
5. `dags/youtube_product_sync_dag.py`
   - `videos`, `comments`, `comment_sentiments` insert/upsert

---

## 5) 2026-04-16 변경사항 반영 여부 점검
**현재 상태: 부분 적용**

### Agent 정책 튜닝
- `PRODUCT_OPINION 무조건 ANALYZE`: **적용됨**
  - 근거: `core/agent.py`의 `_handle_product_opinion()`
- 저확신/needs_recheck 플래그 처리(`needs_human_review`, `is_low_confidence`): **적용됨**
- `VIDEO_REACTION allow + min_features=2`: **적용됨**
  - 근거: `core/models.py` 기본값 + `core/agent.py::_handle_video_reaction()`
- 분기 정책 상태:
  - PRODUCT_OPINION: ANALYZE
  - VIDEO_REACTION: ANALYZE or EXCLUDE(조건부)
  - QUESTION: AUXILIARY_STORE or EXCLUDE
  - CHATTER: EXCLUDE or RECLASSIFY
  - OFF_TOPIC: EXCLUDE
  - HOLD: 분류결과 없음 시 사용

### Spark 전처리
- null/빈값 제거: **적용됨**
- `dropDuplicates(["video_id","author","text"])`: **적용됨**
- `text_cleaned` trim-only: **적용됨**
- `is_short/has_url/is_repetitive/char_count` 플래그: **적용됨**
- 위치: `scripts/api/sync.py::_spark_preprocess_comments()`

### Agent 병렬화
- `ThreadPoolExecutor` 사용: **부분 적용**
  - `process_comments_with_agent()` 자체 loop는 직렬
  - 내부 분류기(`optimized_batch_classifier.py`)에서 배치 병렬 수행
- `llm_gate.py` 존재: **미적용** (파일 없음)
- 429 retry/backoff:
  - Agent 분류 경로에서 429 특화 처리: **미적용** (일반 예외 재시도만)
  - transcript 수집(`transcript_service.py`)에는 429 backoff **적용됨**

---

## 6) 미적용/미구현 항목(TODO) 점검
**현재 상태: 부분 적용**

- `analysis_weight` 컬럼(comment_sentiments): **적용됨**
  - 스키마/마이그레이션 존재, 저장 로직 존재
- `is_low_confidence 비율 모니터링 로그`: **적용됨**
  - `process_comments_with_agent()` 종료부 비율 로그 출력
- `excluded/hold/reclassify/auxiliary 분리 로그`: **미적용**
  - 현재 집계는 `analyzed/excluded/errors` 중심
- `selected_post_llm 의미 명확화`: **미적용**
  - 현재 `selected_post_llm = analyzed`로 동일값 대입

---

## 7) 설정값 정리
**현재 상태: 확인필요**

### 코드에서 확인된 설정
- `PORT`: `scripts/config.py` + `main_youtube_tech_review.py`
- `DATABASE_URL`: `scripts/config.py`, DAG fallback 있음
- `YOUTUBE_API_KEY`: `scripts/config.py`
- `GROQ_API_KEY`: `scripts/config.py`
- `GROQ_MODEL`: `scripts/config.py` (default: `llama-3.1-70b-versatile`)

### 요청 항목별 상태
- `AGENT_WORKERS`: **미적용** (코드 참조 없음)
- `LLM_MAX_CONCURRENT`: **미적용** (코드 참조 없음)
- `LLM_MAX_RETRIES`: **미적용** (환경변수 참조 없음)
- `LLM_BACKOFF_BASE`: **미적용** (환경변수 참조 없음)

### `.env` 상태
- `.env` 파일 존재, `DATABASE_URL/YOUTUBE_API_KEY/GROQ_API_KEY/GROQ_MODEL` 키 존재.
- 민감정보가 실제 값으로 저장되어 있음(문서에는 값 비노출).

---

## 8) Airflow DAG 분석
**현재 상태: 적용됨**

### 대상 파일
- `dags/youtube_product_sync_dag.py`

### 스케줄/구성
- DAG ID: `youtube_product_sync_pipeline`
- 스케줄: `*/30 * * * *` (30분 주기)
- 핵심 task
  1. `ensure_schema`
  2. `extract_products_to_sync`
  3. `fetch_and_upsert_videos_for_product` (expand)
  4. `flatten_video_units`
  5. `fetch_process_and_store_comments` (expand)
  6. `comment_filter_batch`
  7. `summarize_transcripts_batch`
  8. `generate_product_report_batch`
  9. `publish_sync_report`

### 의존관계
```text
ensure_schema -> extract_products_to_sync
extract_products_to_sync -> fetch_and_upsert_videos_for_product.expand -> flatten_video_units
flatten_video_units -> fetch_process_and_store_comments.expand
fetch_process_and_store_comments.expand -> [comment_filter_batch, summarize_transcripts_batch, generate_product_report_batch]
[comment_filter_batch, summarize_transcripts_batch, generate_product_report_batch] -> publish_sync_report
```

### FastAPI 메인 경로와의 관계
- 직접 호출 연동 없음.
- FastAPI `/products/{product_id}/sync`는 별도 동기화 경로(`scripts/api/sync.py`)를 사용.
- DAG와 FastAPI는 **같은 DB 테이블군**(`videos/comments/comment_sentiments` 등)을 공유하는 병렬 경로.

---

## 부록: 핵심 확인 포인트(라인)
**현재 상태: 적용됨**

- 엔트리포인트/라우터 등록: `main_youtube_tech_review.py` (등록부)  
- Agent 메인 파이프라인: `scripts/api/sync.py` (`_spark_preprocess_comments`, `process_comments_with_agent`, `register_sync_routes`)  
- Agent 의사결정: `comment_filtering_agent/core/agent.py::decide()` 및 `_handle_*`  
- 정책/모델: `comment_filtering_agent/core/models.py`  
- LLM 분류 호출: `comment_filtering_agent/classifiers/optimized_batch_classifier.py::_classify_batch_llm()`  
- LLM 감정 호출: `comment_filtering_agent/analyzers/groq_analyzer.py::_call_llm()`  
- DB 스키마: `scripts/database/schema.py`  
- DAG: `dags/youtube_product_sync_dag.py`
