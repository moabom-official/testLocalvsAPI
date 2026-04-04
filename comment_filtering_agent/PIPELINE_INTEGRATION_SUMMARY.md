# 댓글 분석 파이프라인 - 전체 통합

## ✅ 구현 완료

전체 댓글 분석 파이프라인이 **하나의 서비스로 통합**되었습니다!

---

## 📦 생성된 파일 (3개)

### 1. **Comment Collector**
- `services/comment_collector.py` (7.3 KB)
  - YouTubeCommentCollector 클래스
  - YouTube Data API v3 연동
  - Mock 데이터 모드 지원
  - Comment 데이터 모델

### 2. **Pipeline Orchestrator**
- `services/pipeline_orchestrator.py` (13.9 KB)
  - CommentAnalysisPipeline 클래스
  - 전체 파이프라인 조율
  - 6단계 순차 실행
  - 통계 및 에러 추적

### 3. **Pipeline Runner**
- `pipeline_runner.py` (2.5 KB)
  - CLI 실행 스크립트
  - 인자 파싱
  - 환경 변수 설정
  - 결과 저장

### 4. **Architecture 문서**
- `PIPELINE_ARCHITECTURE.md` (11.4 KB)
  - 전체 구조도
  - 클래스 다이어그램
  - 예외 처리 전략
  - 로깅 전략

---

## 🎯 파이프라인 흐름

```
[1. 댓글 수집]
   YouTubeCommentCollector
   → raw_comments
        ↓
[2. 1차 규칙 필터]
   RuleBasedFilter
   → PASS/REJECT
        ↓
[3. 2차 LLM 분류]
   GroqClassifier
   → 5개 라벨
        ↓
[4. Agent 결정]
   AgentDecisionEngine
   → ANALYZE/AUXILIARY/EXCLUDE/HOLD/RECLASSIFY
        ↓
[5a. 감정 분석]        [5b. 질문 처리]
   (ANALYZE)              (AUXILIARY_STORE)
   AspectSentimentAnalyzer  ProductQuestionProcessor
        ↓                       ↓
[6. 보고서 생성]
   ReportGenerator (향후)
```

---

## 🚀 사용법

### 기본 실행
```bash
# 환경 변수 설정
export YOUTUBE_API_KEY="your-youtube-api-key"
export GROQ_API_KEY="your-groq-api-key"

# 파이프라인 실행
python pipeline_runner.py --video-id VIDEO_ID
```

### 옵션 포함 실행
```bash
python pipeline_runner.py \
  --video-id abc123xyz \
  --max-comments 200 \
  --batch-size 50 \
  --log-level DEBUG \
  --output results/video_abc123xyz.json
```

### Python 코드에서 직접 실행
```python
from comment_filtering_agent.services.pipeline_orchestrator import (
    CommentAnalysisPipeline,
    PipelineConfig
)

# 설정
config = PipelineConfig(
    youtube_api_key="your-key",
    groq_api_key="your-key",
    max_comments=100
)

# 실행
pipeline = CommentAnalysisPipeline(config)
result = pipeline.run("VIDEO_ID")

# 결과 확인
print(f"수집: {result.collected_count}개")
print(f"분석: {result.sentiment_analyzed_count}개")
print(f"질문: {result.questions_processed_count}개")
```

---

## 📊 실행 결과 예시

```
============================================================
Pipeline started: video_id=abc123
============================================================
[Stage 1] Collecting comments...
Collected 10 comments
[Stage 2] Rule-based filtering...
Passed: 7, Rejected: 3
[Stage 3] LLM classification...
Classified 7 comments
[Stage 4] Agent decision making...
ANALYZE: 5, AUXILIARY: 2, EXCLUDE: 0, HOLD: 0, RECLASSIFY: 0
[Stage 5a] Analyzing sentiment for 5 comments...
Analyzed 5 comments
[Stage 5b] Processing 2 questions...
Processed 2 questions
============================================================
Pipeline completed successfully
============================================================

============================================================
PIPELINE SUMMARY
============================================================
Video ID: abc123
Duration: 12.34s

Collected: 10
Rule Filter: Passed=7, Rejected=3
Classified: 7
Agent Decisions:
  - ANALYZE: 5
  - AUXILIARY_STORE: 2
  - EXCLUDE: 0
  - HOLD: 0
  - RECLASSIFY: 0
Sentiment Analyzed: 5
Questions Processed: 2
============================================================
```

---

## 📈 출력 JSON 예시

```json
{
  "video_id": "abc123",
  "start_time": "2026-04-02T09:00:00",
  "end_time": "2026-04-02T09:00:12",
  "duration_seconds": 12.34,
  "statistics": {
    "collected": 10,
    "rule_filter": {
      "passed": 7,
      "rejected": 3
    },
    "classified": 7,
    "agent_decisions": {
      "ANALYZE": 5,
      "AUXILIARY_STORE": 2,
      "EXCLUDE": 0,
      "HOLD": 0,
      "RECLASSIFY": 0
    },
    "analysis": {
      "sentiment_analyzed": 5,
      "questions_processed": 2
    }
  },
  "errors": []
}
```

---

## ⚙️ 주요 특징

### 1. 모듈화
- 각 단계가 독립적인 클래스
- 단계별로 교체/수정 가능
- 테스트 용이

### 2. 에러 처리
```python
try:
    result = stage_process(data)
except APIError:
    logger.error("API 에러")
    # 재시도 또는 스킵
except Exception as e:
    logger.error(f"예상치 못한 에러: {e}")
    # 안전하게 종료
```

### 3. 재시도 로직
```python
for attempt in range(max_retries):
    try:
        return api_call()
    except:
        if attempt == max_retries - 1:
            raise
        time.sleep(retry_delay)
```

### 4. 로깅
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
```

---

## 🔄 재처리 전략

### 1. 전체 재실행
```bash
python pipeline_runner.py --video-id VIDEO_ID
```

### 2. 단계별 재실행 (향후)
```python
pipeline.run_from_stage(video_id, start_stage='classification')
```

### 3. 실패 아이템만 (향후)
```python
failed_items = db.get_failed_items(video_id)
pipeline.reprocess_batch(failed_items)
```

---

## 🎨 Airflow 통합 예시

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def run_pipeline(**context):
    from comment_filtering_agent.services.pipeline_orchestrator import (
        CommentAnalysisPipeline, PipelineConfig
    )
    
    video_id = context['dag_run'].conf.get('video_id')
    
    config = PipelineConfig()
    pipeline = CommentAnalysisPipeline(config)
    result = pipeline.run(video_id)
    
    return result.to_dict()

with DAG(
    'comment_analysis_pipeline',
    start_date=datetime(2026, 1, 1),
    schedule_interval='@daily'
) as dag:
    
    run_task = PythonOperator(
        task_id='run_comment_pipeline',
        python_callable=run_pipeline,
        provide_context=True
    )
```

---

## 📝 완료 체크리스트

- [x] Comment Collector (YouTube API)
- [x] Pipeline Orchestrator (전체 조율)
- [x] 6단계 파이프라인 통합
  - [x] 1. 댓글 수집
  - [x] 2. 1차 규칙 필터
  - [x] 3. 2차 LLM 분류
  - [x] 4. Agent 결정
  - [x] 5a. 감정 분석
  - [x] 5b. 질문 처리
- [x] 에러 처리
- [x] 로깅
- [x] 통계 추적
- [x] CLI 실행 스크립트
- [x] Architecture 문서
- [ ] DB 저장 (DBService) - 다음 단계
- [ ] 보고서 생성 (ReportGenerator) - 다음 단계

---

## 🎉 요약

**전체 파이프라인 통합 완료!**

- ✅ 6단계 파이프라인 구현
- ✅ Service Layer 구조
- ✅ CLI 실행 가능
- ✅ 에러 처리 및 로깅
- ✅ Mock 모드 지원 (API 없어도 테스트 가능)
- ✅ Airflow 호환 설계
- ✅ 재처리 가능 구조

**실행 방법**:
```bash
# Mock 모드 (API 키 없이)
python pipeline_runner.py --video-id test123

# 실제 API 사용
export YOUTUBE_API_KEY="your-key"
export GROQ_API_KEY="your-key"
python pipeline_runner.py --video-id abc123 --max-comments 50
```

---

**남은 작업**:
1. DB Service (PostgreSQL 저장)
2. Report Generator (보고서 생성)
3. 배치 처리 최적화
