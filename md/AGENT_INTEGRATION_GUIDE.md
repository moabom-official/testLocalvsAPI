# Agent 연동 매뉴얼

> 작성일: 2026-04-24  
> 대상: 영상 선정 Agent / 댓글 필터링 Agent / 보고서 작성 Agent 팀원

---

## 전체 파이프라인 흐름

```
[사용자 요청]
    │  POST /products/{product_id}/sync
    ▼
┌──────────────────────────────┐
│   1. 영상 선정 Agent          │  → product_name → YouTube 검색 → video_id 목록 반환
│   (팀원 A)                   │
└──────────────────────────────┘
    │  입력: product_name (str)
    │  출력: List[video_id]
    ▼
┌──────────────────────────────┐
│   2. 댓글 필터링 Agent        │  → video_id별 댓글 수집·필터·분류·감성분석 → DB 저장
│   (나: MeDeoDuck)            │
└──────────────────────────────┘
    │  입력: video_id (str), product_name (str)
    │  출력: stats dict + DB 테이블 5개에 결과 저장
    ▼
┌──────────────────────────────┐
│   3. 보고서 작성 Agent        │  → DB에서 결과 읽어 보고서 생성
│   (팀원 B)                   │
└──────────────────────────────┘
    │  입력: product_id (int) 또는 video_id 목록
    │  출력: 보고서 (PDF / Markdown / HTML 등)
```

---

## Agent 1. 영상 선정 Agent — 인터페이스 명세

### 팀원 A에게 요청하는 것

아래 함수 시그니처를 맞춰서 구현해주세요:

```python
def select_videos(product_name: str, max_results: int = 5) -> list[dict]:
    """
    제품명으로 YouTube 영상을 선정하여 반환.
    
    Returns:
        [
            {
                "video_id": "dQw4w9WgXcQ",        # YouTube video ID (필수)
                "title": "갤럭시 S25 리뷰",        # 영상 제목 (필수)
                "channel_title": "테크채널",        # 채널명 (선택)
                "published_at": "2025-01-15T...",  # 게시일 ISO 형식 (선택)
                "view_count": 1500000,             # 조회수 (선택)
                "like_count": 30000,               # 좋아요 수 (선택)
                "comment_count": 2000,             # 댓글 수 (선택)
                "description": "...",              # 설명 (선택)
                "thumbnail_url": "https://...",    # 썸네일 URL (선택)
            },
            ...
        ]
    """
```

### 현재 코드에서 연결 위치

`scripts/api/sync.py` → `register_sync_routes()` 내부:

```python
# 현재 코드 (단순 YouTube 검색)
videos = fetch_product_videos(product["name"], max_results=5)

# 교체할 코드 (영상 선정 Agent 연결)
from <팀원A_모듈> import select_videos
videos = select_videos(product["name"], max_results=5)
```

반환값의 key 이름만 위 명세와 맞으면 그대로 연결됩니다.

---

## Agent 2. 댓글 필터링 Agent — 현재 인터페이스

### 진입 함수

```python
# scripts/api/sync.py
def process_comments_with_agent(video_id: str, product_name: str) -> dict:
    """
    Returns:
        {
            "collected": int,        # 수집된 댓글 수
            "rule_passed": int,      # 규칙 필터 통과 수
            "rule_rejected": int,    # 규칙 필터 탈락 수
            "selected_pre_llm": int, # LLM 분류 전 선발 수
            "selected_post_llm": int,# LLM → Agent ANALYZE 판정 수
            "analyzed": int,         # 감성 분석 완료 수
            "excluded": int,         # 제외 수
            "errors": int            # 오류 수
        }
    """
```

### DB 출력 테이블 (보고서 팀원 B가 읽는 테이블)

| 테이블 | 핵심 컬럼 | 설명 |
|--------|-----------|------|
| `comments` | `comment_id, video_id, text_raw` | 원본 댓글 |
| `rule_filter_results` | `comment_id, filter_status` | PASS/REJECT |
| `llm_classifications` | `comment_id, predicted_label, confidence_score` | LLM 분류 결과 |
| `agent_decisions` | `comment_id, final_action` | ANALYZE/EXCLUDE 등 |
| `comment_sentiments` | `comment_id, sentiment_label, sentiment_score` | **최종 감성 결과** |
| `aspect_extractions` | `comment_id, aspect_name, aspect_sentiment` | 항목별 감성 |

### 최종 필터링된 댓글 조회 쿼리

```sql
-- 보고서 작성 시 이 쿼리로 최종 댓글을 가져오세요
SELECT 
    c.comment_id,
    c.text_raw,
    c.like_count,
    cs.sentiment_label,      -- 'positive' / 'neutral' / 'negative'
    cs.sentiment_score,      -- -1.0 ~ +1.0
    cs.analysis_weight
FROM comments c
JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
JOIN videos v ON c.video_id = v.video_id
WHERE v.product_id = %(product_id)s
ORDER BY cs.sentiment_score DESC;
```

```sql
-- 항목별 감성 조회 (ABSA)
SELECT
    ae.aspect_name,          -- '배터리', '발열', '성능' 등
    ae.aspect_sentiment,     -- 'POSITIVE' / 'NEUTRAL' / 'NEGATIVE'
    ae.aspect_sentiment_score,
    c.text_raw
FROM aspect_extractions ae
JOIN comments c ON ae.comment_id = c.comment_id
JOIN videos v ON c.video_id = v.video_id
WHERE v.product_id = %(product_id)s;
```

---

## Agent 3. 보고서 작성 Agent — 인터페이스 명세

### 팀원 B에게 요청하는 것

```python
def generate_report(product_id: int, db_url: str) -> dict:
    """
    DB에서 감성 분석 결과를 읽어 보고서를 생성.
    
    Args:
        product_id: tech_products 테이블의 product_id
        db_url: DATABASE_URL (scripts/config.py 에서 가져올 것)
    
    Returns:
        {
            "report_path": "/path/to/report.pdf",  # 생성된 파일 경로
            "summary": {
                "positive_ratio": 0.62,
                "negative_ratio": 0.21,
                "neutral_ratio": 0.17,
                "top_aspects": ["배터리", "발열", "성능"],
            }
        }
    """
```

### 현재 코드에서 연결 위치

`scripts/api/sync.py` → `sync_product_videos()` 마지막 부분에 추가:

```python
# 댓글 처리 완료 후 보고서 생성
from <팀원B_모듈> import generate_report
report = generate_report(product_id=product_id, db_url=DATABASE_URL)
print(f"[SYNC] Report generated: {report['report_path']}")
```

---

## 연결 코드 전체 예시

```python
# scripts/api/sync.py 의 sync_product_videos 함수 최종 구조

async def sync_product_videos(product_id: int, data: dict = None):
    product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))

    # --- Agent 1: 영상 선정 ---
    from <팀원A_모듈> import select_videos
    videos = select_videos(product["name"], max_results=5)

    # 영상 메타데이터 DB INSERT (기존 코드 유지)
    inserted_videos = []
    for video in videos:
        execute_update("INSERT INTO videos ...", (...))
        inserted_videos.append(video)

    # --- Agent 2: 댓글 필터링 (병렬) ---
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(process_comments_with_agent, v["video_id"], product["name"]): v["video_id"]
            for v in inserted_videos
        }
        for future in as_completed(futures):
            comment_stats = future.result()

    # --- Agent 3: 보고서 작성 ---
    from <팀원B_모듈> import generate_report
    report = generate_report(product_id=product_id, db_url=DATABASE_URL)

    return {"status": "success", "report": report}
```

---

## 공유 환경 설정 (.env)

팀원 모두 동일한 `.env` 파일 사용 (Git에 올리지 말 것):

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/techdb
YOUTUBE_API_KEY=...
GROQ_API_KEY=...
```

`scripts/config.py`에서 import:

```python
from scripts.config import DATABASE_URL, YOUTUBE_API_KEY, GROQ_API_KEY
```

---

## 체크리스트

### 팀원 A (영상 선정 Agent)
- [ ] `select_videos(product_name, max_results)` 함수 구현
- [ ] 반환값 `video_id` 키 포함 확인
- [ ] `sync.py`에서 `fetch_product_videos` 호출 부분 교체

### 나 (댓글 필터링 Agent) — 이미 완료
- [x] `process_comments_with_agent(video_id, product_name)` 구현
- [x] DB 6개 테이블에 결과 저장
- [x] 병렬 처리 (ThreadPoolExecutor)

### 팀원 B (보고서 작성 Agent)
- [ ] `generate_report(product_id, db_url)` 함수 구현
- [ ] `comment_sentiments`, `aspect_extractions` 테이블 조회
- [ ] `sync.py` 마지막 단계에 보고서 생성 호출 추가
