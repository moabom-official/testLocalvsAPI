# 댓글 필터링 파이프라인 설계 문서

> 기준일: 2026-04-16  
> 대상 파일: `scripts/api/sync.py`  
> 목적: tech 제품 리뷰 YouTube 영상의 댓글에서 **제품 관련 의견**을 추출하여 감성/속성 분석에 활용

---

## 1. 파이프라인 전체 흐름

```
YouTube API
    │
    ▼
[Step 1] 댓글 수집 (최대 1,000개)
    │
    ▼
[Step 2] Spark 전처리 (null/공백 제거 + exact dedup + 메타 플래그 부착)
    │
    ▼
[Step 3] 1차 규칙 기반 필터 (hard gate — 노이즈 제거)
    │    ├── PASS → 후보군 (candidate_comments)
    │    └── REJECT → DB 기록만, 이후 처리 제외
    ▼
[Step 4] 후보군 점수화 + 상위 300개 컷 (_preprocess_candidate_pool)
    │
    ▼
[Step 5] 다중 기준 중복 선택 → 상위 20개 추출 (_select_comments_multicriteria)
    │
    ▼
[Step 5.5] 토큰 예산 트리밍 (video당 2,000 token budget)
    │
    ▼
[Step 6] LLM 배치 분류 (OptimizedBatchClassifier, batch_size=8)
    │
    ▼
[Step 7] Agent 최종 판단 + 감성/속성 분석 저장
    │
    ▼
DB 저장 (comment_sentiments, aspect_extractions)
```

**목표 통과율:**  
`1,000 수집 → ~300 1차 필터 통과 → 20 LLM 분류 → N개 최종 분석`

---

## 2. Step 2: Spark 전처리

### 역할
기술적 무효 데이터만 제거. 내용 기반 판단은 하지 않는다.

| 처리 | 조건 |
|------|------|
| null/공백 제거 | `text IS NULL` 또는 `trim(text) = ""` |
| exact dedup | `(video_id, author, text)` 3-tuple 기준 중복 제거 |
| 메타 플래그 부착 | `char_count`, `is_short`, `has_url`, `is_repetitive` (정보용, hard drop 아님) |

> Spark가 없으면 동일 로직을 Python fallback으로 실행한다.

---

## 3. Step 3: 1차 규칙 기반 필터 (Hard Gate)

### 설정값 (`RuleBasedFilter` + `RuleConfig`)

```python
RuleConfig(
    min_length=5,               # 기본값 유지
    max_emoji_ratio=0.7,        # 기본값 유지
    max_repeated_char_ratio=0.7, # 완화 (기본 0.5 → 0.7): ㅋㅋ 혼합 댓글 통과
    enable_url_check=False,     # 비활성화: URL 포함 댓글은 LLM이 판단
    enable_duplicate_check=False # 비활성화: Spark에서 이미 처리
)
```

### 필터 규칙 목록

| 규칙 코드 | 제외 조건 |
|----------|----------|
| `TOO_SHORT` | 텍스트 길이 < 5자 |
| `SPECIAL_CHARS_ONLY` | 특수문자만 있음 |
| `EMOJI_HEAVY` | 이모지 비율 > 70% |
| `LOW_INFORMATION` | 반복 문자 비율 > 70% (예: `ㅋㅋㅋㅋㅋㅋㅋ`) |
| `GREETING_ONLY` | 인사말만 있음 (잘 보고 갑니다, 감사합니다 등) |
| `REACTION_ONLY` | 반응어만 있음 (ㅋㅋ, 와, 대박 등) |
| `CREATOR_PRAISE_ONLY` | 유튜버 칭찬/구독 유도만 있음 |
| `PROMOTIONAL` | 광고·홍보 키워드 포함 |
| `ABUSIVE` | 욕설·비속어 포함 |

> `URL_SPAM`, `DUPLICATE_CANDIDATE` 규칙은 현재 비활성화

### Hard Gate 동작

```python
if filter_result.is_passed:
    # 후보군에 추가 → 이후 단계 진행
    candidate_comments.append(...)
else:
    # rule_filter_results 테이블에만 REJECT 기록, 이후 단계 완전 제외
    stats["rule_rejected"] += 1
```

---

## 4. Step 4: 후보군 점수화 및 상위 300개 컷

### 함수: `_preprocess_candidate_pool()`

규칙 필터를 통과한 댓글들에 점수를 부여하고, 상위 `PREPROCESS_CANDIDATE_MAX=300`개를 LLM 전 단계로 전달한다.

---

### 4-1. 점수 산정 공식

```
score = (keyword_score × 4.0) + (length_score × 2.0) + (normalized_eng × 1.0)
```

최대 점수: `4.0 + 2.0 + 1.0 = 7.0`

#### 구성 요소별 계산

| 구성 요소 | 공식 | 범위 | 가중치 |
|----------|------|------|------|
| `keyword_score` | `min(keyword_hits / 3.0, 1.0)` | 0 ~ 1 | × 4.0 |
| `length_score` | `min(len(text), 140) / 140.0` | 0 ~ 1 | × 2.0 |
| `normalized_eng` | `engagement / max_engagement` | 0 ~ 1 | × 1.0 |

여기서:
- `keyword_hits` = 텍스트에서 발견된 ABSA 키워드 수 (포화 기준: 3개)
- `engagement` = `like_count + 0.7 × reply_count`
- `max_engagement` = 현재 후보군 전체 중 최대 engagement 값

#### 가중치 설계 근거

```
제품 키워드 신호 (4.0)
  ↑ 가장 중요: 제품 관련 의견인지 여부를 직접 판별

텍스트 길이 (2.0)
  ↑ 길수록 단순 감탄이 아닌 구체적 의견일 가능성 높음

참여도 정규화 (1.0)
  ↑ 보조 신호: 커뮤니티 관심도 반영, 단독 지배 방지를 위해 정규화
```

> **참여도 정규화 이유**: 원본 like_count는 0~수만 범위로 다른 점수를 압도한다.  
> 배치 내 최댓값 대비 상대값으로 변환해 0~1로 스케일링.

---

### 4-2. ABSA 기반 제품 속성 키워드

**이론적 근거**: SemEval-2014 Task 4 (Aspect-Based Sentiment Analysis)에서 정의한 소비자 전자제품 표준 속성 카테고리를 기반으로 선정. 감정어(좋다/나쁘다/추천 등)는 의도적으로 제외 — 영상 자체에 대한 반응과 구분 불가.

```python
PRODUCT_ASPECT_KEYWORDS = [
    # 성능/처리 (Performance)
    "성능", "속도", "처리", "발열", "온도", "쿨링",          # 6개

    # 배터리 (Battery)
    "배터리", "충전", "배터리수명", "전력",                   # 4개

    # 디스플레이 (Display)
    "화면", "디스플레이", "해상도", "밝기",                   # 4개

    # 디자인/외형 (Design)
    "디자인", "무게", "크기", "마감", "색상", "두께",          # 6개

    # 카메라 (Camera)
    "카메라", "화질", "사진",                                 # 3개

    # 가격/가성비 (Price)
    "가격", "가성비", "성가비",                               # 3개

    # 소프트웨어/UI (Software)
    "소프트웨어", "앱", "업데이트", "버그",                    # 4개

    # 내구성/서비스 (Quality & Service)
    "내구성", "AS", "서비스", "품질",                         # 4개

    # 음향 (Audio)
    "소리", "음질", "스피커",                                 # 3개
]
# 총 37개 + 제품명 토큰 (동적 추가)
```

**제품명 토큰 동적 추가**: `_keyword_hit_count()`에서 제품명을 토큰화하여 키워드 목록에 합산. 예: "갤럭시 S24" → `["갤럭시", "s24"]`

---

## 5. Step 5: 다중 기준 중복 선택 (Multi-criteria Overlap)

### 함수: `_select_comments_multicriteria()`

300개 후보 중 20개를 선발. 단일 기준 편향을 방지하기 위해 6가지 정렬 기준을 동시에 적용하고, **여러 기준에 중복 등장한 댓글을 우선 선택**한다.

#### 6가지 소스 그룹 (각 상위 30개)

| 소스 | 기준 |
|------|------|
| `like` | 좋아요 수 내림차순 |
| `many` | 답글 수 내림차순 |
| `long` | 텍스트 길이 내림차순 |
| `new` | 최신순 |
| `old` | 오래된순 |
| `random` | 무작위 샘플링 |

#### 선택 로직

```
1) hit_count 계산: 댓글이 몇 개의 소스 그룹에 등장했는지

2) Primary pool: hit_count >= 2 (2개 이상 기준에서 상위 30위 안)
   → hit_count, like_count, reply_count, text_length 순으로 정렬
   → 최대 20개까지 선택

3) Primary pool이 20개 미만이면 Secondary pool (hit_count == 1)로 보충
   → 보충 점수: normalized_like + normalized_reply + keyword_hits
   → 부족한 수만큼 추가

4) 총 MAX_LLM_COMMENTS=20개 확정
```

---

## 6. Step 5.5: 토큰 예산 트리밍

- 영상당 토큰 예산: `TOKEN_BUDGET_PER_VIDEO = 2,000`
- 예상 토큰: `max(10, len(comment_text) // 3)` (글자 수의 약 1/3)
- 예산 초과 시 점수 낮은 댓글부터 제거 (hit_count → secondary_score → likes → replies 기준)

---

## 7. Step 6: LLM 배치 분류

- 모델: Groq API (`OptimizedBatchClassifier`)
- 배치 크기: 8개
- 신뢰도 임계값: 0.75
- 출력: `predicted_label`, `confidence_score`, `rationale_short`

---

## 8. Step 7: Agent 최종 판단

### 판단 우선순위

```
1. filter_result.is_passed == False → EXCLUDE(RULE_FILTERED)  ← 안전망 (실제로는 Step 3에서 이미 차단)
2. 분류 신뢰도 < 0.75 → ANALYZE with low_confidence_flag
3. 제품 관련 댓글로 분류 → ANALYZE
4. 그 외 → EXCLUDE
```

### ANALYZE 선택 시

- `GroqAspectSentimentAnalyzer` (llama-3.3-70b-versatile)로 감성 분석 실행
- DB 저장: `comment_sentiments`, `aspect_extractions`

---

## 9. 최종 퍼널 요약

| 단계 | 출력 수 | 기준 |
|------|--------|------|
| 수집 | ~1,000 | YouTube API |
| Spark dedup | ~950+ | null/공백/exact중복 제거 |
| 규칙 필터 PASS | ~300 | 노이즈 (인사/반응/홍보) 제거 |
| 점수화 상위 컷 | ≤300 | keyword×4 + length×2 + eng×1 |
| 다중기준 선발 | ≤20 | 중복 등장 우선, 소스 다양성 보장 |
| 토큰 예산 트리밍 | ≤20 | 2,000 token/video |
| LLM 분류 후 최종 | N | Agent ANALYZE 판정 |

---

## 10. 설계 결정 요약

| 결정 | 이유 |
|------|------|
| 규칙 필터 Hard gate | 소프트 필터는 실질적 효과 없음 — 모든 댓글이 LLM으로 넘어가 노이즈 그대로 |
| 참여도 정규화 | raw like 수는 0~수만으로 keyword/length 신호를 압도 |
| 키워드 포화 기준 3개 | 1개면 우연 매칭 가능, 3개 이상이면 명확한 제품 의견으로 해석 가능 |
| 감정어 키워드 제외 | "좋다/최고/추천"은 영상 반응 댓글과 구별 불가, ABSA 속성어만 사용 |
| 중복 선택 전략 | 단일 기준(좋아요 순) 편향 방지, 시간대/길이/반응 다양성 확보 |
