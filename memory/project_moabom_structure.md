---
name: Moabom Prototype - Project Structure
description: YouTube 기술 리뷰 수집/분석 FastAPI 앱 + Airflow DAG 구조 및 Agent 파이프라인 개요
type: project
---

## 프로젝트 개요
YouTube 기술 리뷰 영상의 댓글을 수집/필터링/감정분석하는 FastAPI 앱.


## 핵심 컴포넌트

### 진입점
- `main_youtube_tech_review.py`: FastAPI 앱 생성, DB init, 라우트 등록

### 라우터
- `scripts/api/products.py`: 상품 목록/생성/상세
- `scripts/api/videos.py`: 영상 상세, 리포트 생성, PDF 다운로드
- `scripts/api/sync.py`: YouTube 동기화 + Agent 기반 댓글 처리 (핵심)

### Agent 파이프라인 (`scripts/api/sync.py::process_comments_with_agent()`)
1. YouTubeCommentCollector.collect_comments()
2. _spark_preprocess_comments() — null제거, 중복제거, 플래그 생성
3. comments 테이블 upsert
4. RuleBasedFilter.filter_single()
5. _preprocess_candidate_pool() + _select_comments_multicriteria()
6. token budget trim
7. OptimizedBatchClassifier.classify_batch() — LLM 분류 (Groq)
8. agent.decide() — AgentAction 결정
9. ANALYZE면 GroqAspectSentimentAnalyzer.analyze_single() — 감정/aspect

### Agent 의사결정 (`comment_filtering_agent/core/agent.py::decide()`)
- PRODUCT_OPINION → 무조건 ANALYZE (확신도 무관, 저확신 플래그만)
- VIDEO_REACTION → 조건부 ANALYZE (min_product_features_for_analysis=2)
- QUESTION → AUXILIARY_STORE or EXCLUDE
- CHATTER → EXCLUDE or RECLASSIFY
- OFF_TOPIC → EXCLUDE

### LLM 호출
- 분류: `comment_filtering_agent/classifiers/optimized_batch_classifier.py::_classify_batch_llm()`
- 감정/Aspect: `comment_filtering_agent/analyzers/groq_analyzer.py::_call_llm()`
- 모델: GROQ_MODEL (default: llama-3.1-70b-versatile)

### DB 테이블
tech_products, videos, comments, comment_sentiments, rule_filter_results,
llm_classifications, agent_decisions, aspect_definitions, aspect_extractions,
video_transcripts, video_reports

## 미적용 TODO (2026-04-16 기준)
- AGENT_WORKERS / LLM_MAX_CONCURRENT / LLM_MAX_RETRIES / LLM_BACKOFF_BASE 환경변수
- excluded/hold/reclassify/auxiliary 분리 로그
- selected_post_llm 의미 명확화 (현재 analyzed와 동일)
- llm_gate.py 미존재 (429 특화 처리 미적용)

## Airflow DAG
- `dags/youtube_product_sync_dag.py`
- 스케줄: */30 * * * * (30분)
- FastAPI sync 경로와 DB 테이블 공유, 직접 호출 연동 없음
- **현재 미사용**: 구현만 되어있고 실제로 사용하지 않음. 제안/수정 시 dags 폴더는 고려 대상 제외.

**Why:** 이관용 분석 문서(md/CLAUDE_CODE_HANDOFF_ANALYSIS_20260416.md)에서 추출
**How to apply:** 구조/흐름 파악, 수정 제안 시 파이프라인 단계 고려