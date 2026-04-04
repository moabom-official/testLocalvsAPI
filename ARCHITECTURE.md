# 🏗️ 시스템 아키텍처

## 전체 시스템 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    사용자 (Web Browser)                          │
│                   http://localhost:9000                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   FastAPI App   │
                    │ (포트 9000)      │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼─────┐      ┌──────▼──────┐    ┌───────▼────────┐
   │  웹 라우트 │      │ 데이터 처리 │    │   API 엔드포인트│
   │           │      │             │    │                │
   ├───────────┤      ├─────────────┤    ├────────────────┤
   │ /products │      │YouTube 페치 │    │/api/ai-status  │
   │ /product/ │      │댓글 분석    │    │                │
   │   detail  │      │감정 분석    │    └────────────────┘
   │ /sync     │      │             │
   └───────────┘      └─────────────┘
        │                    │
        └────────┬───────────┘
                 │
        ┌────────▼─────────┐
        │  PostgreSQL DB   │
        │  (localhost:5432)│
        │                  │
        ├──────────────────┤
        │ tech_products    │
        │ videos           │
        │ comments         │
        │ comment_sentiments│
        │ video_transcripts│
        │ video_reports    │
        └──────────────────┘
```

---

## 🌐 외부 API & AI 서비스 통합

```
┌──────────────────────────────────────────────────────────────┐
│                    YouTube Product Analysis                   │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 1️⃣  데이터 수집 (Data Collection)                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│         │                                                      │
│         ├─ YouTube Data API v3 (Google)                      │
│         │  └─ 비디오 검색 & 메타데이터                        │
│         │                                                      │
│         └─ YouTube Comments API                              │
│            └─ 댓글 수집                                       │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 2️⃣  AI 분석 (AI Analysis)                              │ │
│  └─────────────────────────────────────────────────────────┘ │
│         │                                                      │
│         ├─ Groq API (Llama 3.1) - 온디맨드                 │
│         │  └─ 트랜스크립트 분석                               │
│         │  └─ 댓글 감정 분석                                  │
│         │                                                      │
│         └─ 규칙 기반 분석 (Rule-based) - 기본                │
│            ├─ 제품 관련성 필터링                              │
│            └─ 감정 분석 (Positive/Negative/Neutral)         │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 3️⃣  Airflow 자동화 (선택사항)                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│         │                                                      │
│         └─ Airflow DAG (30분 주기)                           │
│            ├─ comment_filter_batch (새)                      │
│            ├─ summarize_transcripts_batch (새)               │
│            └─ generate_product_report_batch (새)             │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔄 기능별 AI/API 사용 흐름

### **기능 1: 제품 생성**
```
사용자 입력
    ↓
[FastAPI] POST /products
    ↓
[DB] tech_products 저장
    ↓
응답 (제품 ID 반환)

❌ API 사용 안 함
```

---

### **기능 2: YouTube 동기화**
```
사용자: "Sync Videos from YouTube" 클릭
    ↓
[FastAPI] POST /products/{id}/sync
    ↓
┌─────────────────────────────────────┐
│ 🔗 YouTube Data API v3 (Google)     │ ← 필수
│ ├─ videos.list (검색)                │
│ └─ videos.get (상세정보)              │
└─────────────────────────────────────┘
    ↓
[DB] videos 테이블 저장
    ↓
┌─────────────────────────────────────┐
│ 🔗 YouTube Comments API             │ ← 필수
│ └─ commentThreads.list               │
└─────────────────────────────────────┘
    ↓
[DB] comments 테이블 저장
    ↓
┌─────────────────────────────────────┐
│ 🤖 규칙 기반 분석 (내장)              │ ← 자동
│ ├─ is_product_related()              │
│ └─ analyze_sentiment()               │
└─────────────────────────────────────┘
    ↓
[DB] comment_sentiments 저장
    ↓
✅ 동기화 완료
```

---

### **기능 3: 비디오 상세 조회**
```
사용자: 비디오 제목 클릭
    ↓
[FastAPI] GET /products/{pid}/videos/{vid}
    ↓
[DB] 댓글 & 감정 데이터 조회
    ↓
┌─────────────────────────────────────┐
│ 🔗 YouTube Transcript API           │ ← 온디맨드
│ └─ YouTubeTranscriptApi.get_transcript
└─────────────────────────────────────┘
    ↓
[DB] video_transcripts 저장
    ↓
┌─────────────────────────────────────┐
│ 🤖 Groq API (Llama 3.1) - 무료    │ ← 추천
│ ├─ 트랜스크립트 분석                  │
│ └─ 댓글 감정 리포트                   │
└─────────────────────────────────────┘
    ↓
[DB] video_reports 저장
    ↓
📊 분석 결과 표시 (HTML 렌더링)
```

---

### **기능 4: AI 상태 조회 (신규)**
```
외부 시스템: API 요청
    ↓
[FastAPI] GET /api/ai-analysis-status
    ↓
┌─────────────────────────────────────┐
│ 🔄 Airflow DAG 상태 확인            │ ← 연동 준비
│ ├─ comment_filter_batch              │
│ ├─ summarize_transcripts_batch       │
│ └─ generate_product_report_batch     │
└─────────────────────────────────────┘
    ↓
JSON 응답 (AI task 상태)
```

---

## 📡 API 목록 및 사용 현황

### **외부 API (외부 서비스)**

| API | 제공자 | 용도 | 사용 여부 | 비용 | 필수 |
|-----|--------|------|---------|------|------|
| **YouTube Data API v3** | Google | 비디오/댓글 조회 | ✅ 필수 | 무료* | ✅ |
| **YouTube Transcript API** | Google | 자막 수집 | ✅ 선택 | 무료 | ❌ |
| **Groq API** | Groq | AI 분석 (무료) | ✅ 권장 | 무료 | ❌ |

*무료이지만 quota 제한 있음

---

### **내부 API (자체 구현)**

| 엔드포인트 | 메서드 | 기능 | 인증 | 상태 |
|-----------|--------|------|------|------|
| `/` | GET | 홈 페이지 리다이렉트 | ❌ | ✅ |
| `/products` | GET | 제품 목록 | ❌ | ✅ |
| `/products` | POST | 제품 생성 | ❌ | ✅ |
| `/products/{id}` | GET | 제품 상세 | ❌ | ✅ |
| `/products/{id}/sync` | POST | YouTube 동기화 | ❌ | ✅ |
| `/products/{id}/videos/{vid}` | GET | 비디오 상세 | ❌ | ✅ |
| `/products/{id}/videos/{vid}/rewrite-transcript-report` | POST | 트랜스크립트 리포트 재생성 | ❌ | ✅ |
| `/products/{id}/videos/{vid}/rewrite-comment-report` | POST | 댓글 리포트 재생성 | ❌ | ✅ |
| `/products/{id}/videos/{vid}/transcript-report.pdf` | GET | PDF 다운로드 | ❌ | ✅ |
| **`/api/ai-analysis-status`** | GET | **AI task 상태** | ❌ | ✅ **NEW** |

---

## 🤖 AI/분석 엔진

### **1️⃣ 규칙 기반 분석 (Rule-based)**
```python
# 내장 함수 - 항상 사용
def is_product_related(text, product_name):
    # 키워드 매칭으로 제품 관련성 판정
    keywords = ["price", "spec", "battery", "performance", ...]
    return product_name.lower() in text.lower() or \
           any(kw in text.lower() for kw in keywords)

def analyze_sentiment(text):
    # 긍정/부정/중립 판정
    positive_words = ["good", "love", "great", ...]
    negative_words = ["bad", "hate", "poor", ...]
    # 단순 카운팅으로 판정
    return ("positive" | "negative" | "neutral", confidence)
```

**특징**:
- ✅ 비용 무료
- ✅ 실시간 분석
- ✅ 한국어 미지원 (영어만)

---

### **2️⃣ Groq Llama (무료!)**
```python
# 온디맨드 분석 - 사용자가 비디오 상세 조회할 때
client = anthropic.Anthropic(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# 트랜스크립트 분석
transcript_report = client.messages.create(
    model="llama-3.1-70b-versatile",
    max_tokens=2048,
    messages=[{
        "role": "user",
        "content": f"Analyze this transcript...\n{transcript_text}"
    }]
)

# 댓글 감정 분석
comment_report = client.messages.create(
    model="llama-3.1-70b-versatile",
    max_tokens=1024,
    messages=[{
        "role": "user", 
        "content": f"Analyze these comments sentiment...\n{comments}"
    }]
)
```

**특징**:
- ✅ 비용: 무료 (완전!)
- ✅ 속도: 초고속 (0.5-1초)
- ✅ 품질: 우수 (GPT-4 수준)
- ⚠️ 한국어: 80% 수준

---

### **3️⃣ Airflow 자동화 (신규)**
```
매 30분마다 자동 실행:

1. comment_filter_batch()
   └─ 모든 댓글 필터링 & 통계

2. summarize_transcripts_batch()
   └─ 모든 트랜스크립트 요약

3. generate_product_report_batch()
   └─ 제품별 종합 리포트 생성

4. publish_sync_report()
   └─ 최종 리포트 발행
```

**특징**:
- 🔄 예약 실행 (일정 주기)
- 📊 배치 처리
- ⚙️ 워크플로우 관리

---

## 🗄️ 데이터 흐름

```
사용자 입력
    ↓
FastAPI (main_youtube_analysis.py)
    ├─ 웹 라우트 처리
    ├─ 데이터 검증
    └─ 비즈니스 로직
        ↓
    ┌───────────────────────────────────┐
    │ 외부 API 호출                       │
    ├───────────────────────────────────┤
    │ ✅ YouTube Data API (필수)         │
    │ ✅ YouTube Transcript API (선택)   │
    │ ✅ Groq API (무료!)               │
    │ ✅ Airflow (선택)                  │
    └───────────────────────────────────┘
        ↓
    PostgreSQL Database
    ├─ tech_products (제품 정보)
    ├─ videos (비디오)
    ├─ comments (댓글)
    ├─ comment_sentiments (감정 분석)
    ├─ video_transcripts (자막)
    └─ video_reports (분석 리포트)
        ↓
    HTML 렌더링 (Jinja2 템플릿)
        ↓
    사용자 브라우저 (웹 페이지)
```

---

## 📊 기능 요약표

| 기능 | 사용 API | AI 모델 | 위치 | 필수/선택 |
|------|---------|--------|------|----------|
| **제품 관리** | - | - | 웹 | 필수 |
| **YouTube 검색** | YouTube Data API v3 | - | 웹 | 필수 |
| **댓글 수집** | YouTube Comments API | - | 웹 | 필수 |
| **댓글 필터링** | - | Rule-based | 웹/DAG | 필수 |
| **감정 분석** | - | Rule-based | 웹/DAG | 필수 |
| **자막 수집** | YouTube Transcript API | - | 웹 | 선택 |
| **고급 분석** | Groq API | Llama 3.1 70B | 웹 | 선택 |
| **자동화** | Airflow | Rule-based | DAG | 선택 |

---

## 🎯 사용 시나리오별 흐름

### **시나리오 1: 기본 사용 (최소 설정)**
```
필요: YouTube API Key만
      
사용자 → 제품 생성 → 동기화 → 기본 분석 (규칙 기반) ✅
```

### **시나리오 2: Groq Llama AI 사용**
```
필요: YouTube API Key + Groq API Key (무료!)
      
사용자 → 제품 생성 → 동기화 → 기본 분석 → 
         비디오 상세 → Groq AI 분석 (초고속 + 무료) ✅
```

### **시나리오 3: 자동화 배치**
```
필요: Airflow + 모든 API Key
      
Airflow 스케줄러 → (매 30분마다)
    ├─ 모든 제품 동기화
    ├─ 필터링 & 분석 (규칙 기반)
    ├─ 리포트 생성
    └─ 결과 저장 ✅
```

---

## 🔐 API 키 설정

```bash
# .env 파일
DATABASE_URL=postgresql://user:pass@localhost/techdb
YOUTUBE_API_KEY=your_youtube_key_here         # ✅ 필수
GROQ_API_KEY=your_groq_key_here               # ✅ 권장 (무료!)
GROQ_MODEL=llama-3.1-70b-versatile            # ✅ Llama 모델
```

---

## 🚀 배포 구성

```
개발 (Development):
├─ FastAPI 단독 실행
├─ YouTube API만 필요
└─ 규칙 기반 분석만 사용

프로덕션 (Production):
├─ FastAPI + PostgreSQL
├─ YouTube API + Groq API (권장, 무료)
└─ Airflow 자동화 (선택)

Docker:
├─ FastAPI 컨테이너
├─ PostgreSQL 컨테이너
└─ Airflow 컨테이너 (선택)
```

---

**이 구조로 최소 비용에 최대 기능을 제공합니다!** 🎉
