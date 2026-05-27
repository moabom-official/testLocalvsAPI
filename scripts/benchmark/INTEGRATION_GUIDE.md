# 운영 통합 가이드 — 3-class 분류 결과 + 프롬프트 / Agent 룰

> **목적**: KLUE-RoBERTa 와 DeBERTa 의 final 학습 결과를 정리하고, 운영
> (`scripts/api/sync.py` → `comment_filtering_agent`) 에 통합할 때 변경이
> 필요한 프롬프트 / Agent decision 룰을 매우 구체적으로 명세.
>
> 비교 도구 사용법: [scripts/benchmark/README.md](./README.md) 참고.

---

## 1. Final 학습 결과 — 두 모델

### 1-1. 메타

| 항목 | **KLUE-RoBERTa-large** (production-ready) | DeBERTa-v3-base-korean (baseline) |
|---|---|---|
| 모델 ID | `klue/roberta-large` | `team-lucid/deberta-v3-base-korean` |
| 파라미터 | 340M | 180M |
| Tokenizer | BertTokenizer (KLUE) | SentencePiece |
| 학습 hyperparam | lr `1e-5`, 4 epoch, batch 32, bf16 | lr `2e-5`, 4 epoch, batch 32, bf16 |
| Class weighting | inverse frequency + per-example confidence | 동일 |
| Label smoothing | 0.05 | 0.05 |
| Best epoch | **2** (early plateau — 수렴 빠름) | **4** (still climbing — epoch 더 주면 ↑ 가능) |
| best val_macro_F1 | **0.8862** | 0.7485 |
| **test acc** | **0.9156** | 0.8447 |
| **test macro F1** | **0.9167** ⭐ | 0.8464 |

### 1-2. Per-class F1 (test, n=1114)

| 라벨 | RoBERTa-large | DeBERTa-base | Δ |
|---|---:|---:|---:|
| `PRODUCT_OPINION` (support 351) | **0.916** | 0.828 | +0.088 |
| `VIDEO_REACTION` (support 436) | **0.902** | 0.822 | +0.080 |
| `QUESTION` (support 327) | **0.932** | 0.889 | +0.043 |

### 1-3. RoBERTa 의 운영 등가 confusion (참고)

```
                pred_PO  pred_VR  pred_Q
true PO  (351)     327      20       4
true VR  (436)      28     379      29
true Q   (327)       8       5     314
```

- VR → PO 28건: 영상에서 제품 평가가 강하게 묻어나는 경우 (운영 영향 적음, ANALYZE 승격으로 회복)
- VR → Q 29건 / Q → VR 5건: 질문/응원 boundary
- 전체적으로 **VR-PO 양쪽 경계가 가장 큰 잠재 오차원** — 키워드 룰로 보완 가능

### 1-4. 운영 채택 권고

| 시나리오 | 추천 |
|---|---|
| **Production 분류기** | **RoBERTa-large** (test macro F1 0.917, 추론 ~50ms/배치) |
| 비교용 baseline | DeBERTa (학습 곡선이 느려서 4 epoch 부족. epoch 늘리면 0.86+ 가능) |
| 학습 시간 (A40 기준) | RoBERTa-large 12분 / DeBERTa-base 6분 |

---

## 2. 라벨 체계 변경 — 4-class → 3-class

### 2-1. 변경 요약

| 4-class (구 운영) | **3-class (Local 모델 출력)** | 변경 사유 |
|---|---|---|
| `PRODUCT_OPINION` | `PRODUCT_OPINION` | 그대로 |
| `VIDEO_REACTION` | **`VIDEO_REACTION` (확장)** | 아래 NOISE / CHATTER / OFF_TOPIC 흡수 |
| `QUESTION` | `QUESTION` | 그대로 |
| `NOISE` / `CHATTER` / `OFF_TOPIC` | → **`VIDEO_REACTION`** 으로 흡수 | 운영 액션이 모두 EXCLUDE 라 분리 가치 적음 |

### 2-2. legacy 라벨 자동 매핑

학습 데이터의 구 라벨이 들어와도 `local_classifier/config.py` 의
`LEGACY_LABEL_REMAP` 가 자동으로 처리:

```python
LEGACY_LABEL_REMAP = {
    "CHATTER":   "VIDEO_REACTION",
    "OFF_TOPIC": "VIDEO_REACTION",
    "NOISE":     "VIDEO_REACTION",
}
```

→ 운영 sync.py 가 학습된 모델을 부르면 라벨 출력은 무조건 `PO`/`VR`/`Q` 3종.

### 2-3. 운영 코드 / DB 영향

**변경 없음** — 운영 4-class enum 그대로 유지하고 분류기 출력만 3-class.
agent decision engine 은 4-class label 받는데 NOISE 가 안 들어오니 자연히
NOISE 분기 미사용. DB 마이그레이션 불필요.

---

## 3. 운영 프롬프트 — 3-class 로 갈아끼우기

### 3-1. 현재 프롬프트 위치

`comment_filtering_agent/prompts/batch_prompt_optimized.py` 의
`create_batch_prompt()` (또는 `create_compact_prompt`, `create_accurate_prompt`)

### 3-2. 변경 권장 — 3-class 명시적 프롬프트

> **중요**: API 분류기 (`OptimizedBatchClassifier`) 는 GPT-4.1 에 직접 프롬프트
> 전송. 프롬프트가 여전히 5-class (CHATTER / OFF_TOPIC 포함) 라 GPT-4.1 이
> 가끔 그 라벨로 출력 → `LEGACY_LABEL_REMAP` 으로 자동 합쳐지지만 토큰 낭비.
> 운영 통일 위해 3-class 프롬프트로 바꿔 GPT-4.1 출력 자체를 3-class 로.

#### 권장 새 프롬프트 (replace `create_batch_prompt`)

```python
SYSTEM_PROMPT = """YouTube 한국어 제품 리뷰 댓글 3-class 분류기.
출력은 JSON 배열만. 다른 텍스트 절대 금지."""


def create_batch_prompt(comments: list) -> str:
    """3-class 균형 프롬프트 — token-efficient + 정확도.

    출력 라벨:
      PRODUCT_OPINION : 제품 자체에 대한 의견·평가
      VIDEO_REACTION  : 영상/리뷰어/잡담/무관 댓글 (NOISE/OFF_TOPIC 흡수)
      QUESTION        : 제품 관련 질문
    """
    import json
    comments_json = json.dumps(comments, ensure_ascii=False, indent=2)

    prompt = f\"\"\"라벨 (3-class):
PRODUCT_OPINION = 제품 평가 (발열/배터리/성능/디자인/가격/카메라/품질 등 제품 속성에 대한 의견)
VIDEO_REACTION  = 그 외 (영상·리뷰어 칭찬, 단순 반응, 잡담, 광고, 제품 무관 내용 — 모두 여기로)
QUESTION        = 제품 관련 질문 (성능/구매/기능/호환/사용법 등)

우선순위 (위에서부터 검사):
1. 제품 속성 단어가 포함되고 평가·의견 표현이면 → PRODUCT_OPINION
2. 의문문 (?, "나요?", "어떻게", "얼마") 이고 제품 관련이면 → QUESTION
3. 그 외 모두 → VIDEO_REACTION

규칙:
- 단순 반응 ("ㅋㅋㅋ", "와", "대박") → VIDEO_REACTION
- 영상 칭찬 ("편집 깔끔", "설명 좋다") → VIDEO_REACTION
- 배경음악/썸네일 질문 → VIDEO_REACTION (제품 관련 X)
- 제품 모델명 + 평가어 ("S25 발열 심하네요") → PRODUCT_OPINION
- 영상 자체 질문 ("다음 영상 언제?") → VIDEO_REACTION

Few-shot:
{{"text": "발열 심한데 성능 좋네요", "label": "PRODUCT_OPINION"}}
{{"text": "배터리 너무 빨리 닳아요", "label": "PRODUCT_OPINION"}}
{{"text": "가격 대비 괜찮은 듯", "label": "PRODUCT_OPINION"}}
{{"text": "이거 게임 잘 돌아가나요?", "label": "QUESTION"}}
{{"text": "어디서 사면 싸요?", "label": "QUESTION"}}
{{"text": "이거랑 아이폰 중 뭐가 나음?", "label": "QUESTION"}}
{{"text": "영상 잘 만드셨네요 다음 기대됩니다", "label": "VIDEO_REACTION"}}
{{"text": "리뷰어님 목소리 좋네요", "label": "VIDEO_REACTION"}}
{{"text": "ㅋㅋㅋㅋ 신기", "label": "VIDEO_REACTION"}}
{{"text": "배경음악 제목이 뭔가요?", "label": "VIDEO_REACTION"}}
{{"text": "오늘 점심 뭐 먹지", "label": "VIDEO_REACTION"}}

분류할 댓글 (각각 같은 id 그대로 라벨 부여):
{{comments_json}}

출력: JSON 배열만. 형식 = [{{"id":"<원본 id>","label":"<3 중 하나>","confidence":0.0~1.0,"mentioned_product_features":["<댓글에 나온 제품 속성 단어>",...]}},...]

JSON:\"\"\"

    return prompt
```

### 3-3. `mentioned_product_features` 출력 명시 — 매우 중요

GPT-4.1 출력에 `mentioned_product_features` 키를 포함시켜야 운영 agent 의
VR → ANALYZE 승격 룰이 작동. **빈 배열 `[]` 이라도 키는 반드시 출력**하도록
프롬프트에 강제.

> Local 분류기는 `local_classifier/classifier.py` 가 후처리로 자체 키워드
> 매칭. API 는 프롬프트에 명시 안 하면 LLM 이 빠뜨리는 경우 있음.

---

## 4. Agent Decision Engine — VR 분기 룰

### 4-1. 운영 코드 위치

`comment_filtering_agent/core/agent.py:_handle_video_reaction()`

### 4-2. 변경 후 룰 (정확한 의사 코드)

```python
def _handle_video_reaction(comment_text, classification_result):
    """3-class 통합 후의 VR 처리 — NOISE 흡수 댓글 가려내기."""

    features = classification_result.mentioned_product_features or []
    n = len(features)

    # === 룰 1: 제품 키워드 2개 이상 → ANALYZE 승격 ===
    # 예: "발열 심한데 화면도 어두워" → features=[발열, 화면] → 사실상 PO
    # GPT-4.1 이 라벨링 실수했거나, 칭찬 + 제품 언급 혼합 댓글 회복
    if n >= 2:
        return Decision(action="ANALYZE",
                        reason=f"VR + features×{n} → 제품 평가로 승격",
                        promoted_from="VIDEO_REACTION")

    # === 룰 2: 제품 키워드 1개 + 길이 충분 → 약 승격 (선택) ===
    # 예: "배터리 좀 더 좋았으면" (단일 키워드인데 명확한 의견)
    # 현재 운영은 1개에선 승격 X, 그대로 EXCLUDE. 보수적 룰.

    # === 룰 3: 키워드 0개 → EXCLUDE ===
    # 잡담 / 영상 칭찬 / 광고 / 단순 반응 등
    return Decision(action="EXCLUDE",
                    reason="VR with no product features",
                    exclusion_reason="VIDEO_REACTION")
```

### 4-3. 임계값 결정 근거

| 임계값 | precision (잡힌 게 진짜 PO?) | recall (놓친 PO 회수) | 결정 |
|---|---|---|---|
| ≥ 1 (관대) | 0.65 정도 (false positive 많음) | 높음 | **비추** — VR-PO 경계 흐려져 ABSA 입력 품질 ↓ |
| **≥ 2** (현재) | **0.85+ 추정** | 중간 | **★ 운영 default** |
| ≥ 3 (보수) | 0.95+ | 낮음 (놓치는 PO 다수) | 정확도 최우선 시나리오만 |

운영 데이터 분포 가정 시 **2개**가 sweet spot. 추후 ABSA 입력 품질 모니터링
하면서 ±1 조정 가능.

### 4-4. `PRODUCT_ASPECT_KEYWORDS` 단일 진실 출처

키워드 리스트는 두 곳에서 사용:

| 사용처 | 위치 |
|---|---|
| 운영 (API 분류기 후처리 + sync.py 의 multi-criteria) | `scripts/api/sync.py:155` |
| Local 분류기 후처리 (VR 키워드 매칭) | `local_classifier/keywords.py` |

**둘이 같은 값을 유지해야 backend 간 동등 비교 가능**. 현재 37개 키워드,
9개 카테고리 (성능 / 배터리 / 화면 / 디자인 / 카메라 / 가격 / SW / 내구성 / 음향).

변경 시 양쪽 파일 같이 수정.

---

## 5. 댓글 우선순위 — 어떤 댓글을 먼저 / 적게 보낼지

LLM 호출 비용 / quota 가 한정적이므로 **모든 댓글을 분류기에 보내지
않음**. `sync.py` 의 `_select_comments_multicriteria` 가 영상별 fetch 한
1,000 댓글에서 **상위 20개만** 선별하여 분류기에 입력.

### 5-1. 선별 흐름 (운영 sync.py 기준)

```
1,000 댓글 fetch (YouTube API)
    ↓
Preprocess (null/blank 제거 + 정확한 중복 제거)
    ↓ ~600 댓글
Rule filter (1차 PASS/REJECT)
    ↓ ~400 댓글 (PASS)
Multi-Criteria 선정 (6 기준)  ← 핵심
    ↓
상위 20개 (MAX_LLM_COMMENTS)
    ↓
분류기 (3-class API 또는 Local)
```

### 5-2. Multi-Criteria 6 기준

각 기준별 Top 30 (`TOP_PER_SOURCE`) 추출 후 hit_count 누적:

| 기준 (key) | 의도 | 정렬 키 |
|---|---|---|
| `like` | 호응 많음 | (`like_count`, `reply_count`) desc |
| `many` | 토론 많음 | (`reply_count`, `like_count`) desc |
| `long` | 정보량 많음 | `len(comment_text)` desc |
| `new` | 최신 의견 | `published_ts` desc |
| `old` | 초기 인상 | `published_ts` asc |
| `random` | 다양성 확보 | random sample |

→ 각 댓글의 `hit_count` (몇 개 기준에 잡혔는지) 산출.

### 5-3. 우선순위 알고리즘

```
primary  = {hit_count >= 2 인 댓글}    ← 다수 기준 통과 = 강한 신호
secondary = {hit_count == 1 인 댓글}

if primary >= 20:
    → primary 만으로 채움
    정렬: (hit_count, like, reply, length) desc
else:
    1차 primary 전부 (hit_count >= 2)
    + 2차 secondary 부족분 = 20 - len(primary)
       secondary 정렬: (secondary_score, length) desc
       secondary_score = normalize(like) + normalize(reply) + keyword_hit_count
       ← 키워드 매칭 많을수록 우선 (제품 평가 가능성 ↑)
```

### 5-4. **운영에서 우선적으로 인식되는 댓글 (요약)**

1. **다수 기준 동시 충족** (like 많고 답글 많고 길고 새로운 댓글) — 가장 강한 신호
2. **좋아요 + 답글 + 제품 키워드** 가 모두 높은 댓글
3. **단순 반응 / 짧은 댓글** ("ㅋㅋ") 은 long 기준 미충족 + 보통 like 도 낮아 자연 탈락
4. **광고 / spam** 은 rule filter 1차에서 REJECT — 분류기까지 안 옴

### 5-5. 단일 댓글 인식 가능성 매트릭스

| 댓글 유형 | rule pass? | multi-criteria 진입? | 분류기 라벨 | 최종 액션 |
|---|---|---|---|---|
| "발열 심한데 성능은 진짜 좋네요 그리고 화면도 마음에 듭니다" (long + 키워드 3개) | ✅ | ✅ (long + 키워드) | **PO** | ANALYZE |
| "발열 심해요" (짧지만 키워드) | ✅ | △ (random 운만) | **PO** | ANALYZE |
| "ㅋㅋㅋ 진짜네" (단순 반응) | △ (REJECT 가능성) | ✗ | **VR** | EXCLUDE |
| "다음 영상 언제 나와요?" (영상 질문) | ✅ | △ | **VR** (Q 아님) | EXCLUDE |
| "이 영상 발열 진짜 진짜 심하네요 ㄷㄷ + 배터리 별로 + 가격은 좀 비싸" (long + 키워드 3개) | ✅ | ✅ (long + like) | **PO** 또는 **VR 승격** | ANALYZE |
| "https://광고링크.com" (광고) | ✗ | - | - | RULE_REJECT |
| "리뷰어님 머리 잘랐어요?" (사적 언급) | ✅ | △ | **VR** (키워드 0) | EXCLUDE |

---

## 6. 운영 통합 체크리스트

코드 swap 전 확인:

- [ ] `local_classifier/artifacts/3_labels/klue__roberta-large/model/best/` 배포 완료 (1.3 GB)
- [ ] `comment_filtering_agent/prompts/batch_prompt_optimized.py` 의 `create_batch_prompt` 3-class 로 갱신
- [ ] GPT-4.1 출력에 `mentioned_product_features` 필드 강제 (프롬프트 + 응답 파서)
- [ ] `scripts/api/sync.py` 의 `CLASSIFIER_BACKEND` 환경변수 동작 검증 (`api` / `local`)
- [ ] `_handle_video_reaction` 의 features ≥ 2 → ANALYZE 룰 확인 (이미 운영 코드에 존재)
- [ ] `PRODUCT_ASPECT_KEYWORDS` 두 파일 (sync.py + keywords.py) 동기 확인
- [ ] DB enum `comment_label` 은 4-class 유지 — NOISE 값은 legacy 표시만 (CHECK 제약 풀어두기)
- [ ] 회귀 테스트: 같은 video 로 swap 전/후 ANALYZE 비율 비교 — ±10% 이내면 안전

---

## 7. 운영 후 모니터링 지표

| 지표 | 측정 위치 | 정상 범위 (기대) |
|---|---|---|
| 분류기 평균 latency | OptimizedBatchClassifier / LocalRobertaClassifier stats | API ~400ms / 20건, Local ~30ms / 20건 |
| VR → ANALYZE 승격 비율 | agent decision 로그 | 5~15% (VR 중에) |
| 분류기 confidence 분포 | per-comment 로그 | mean > 0.85, p10 > 0.65 |
| 운영 일치율 (API vs Local) | 주기적 sample 비교 | > 90% (운영 3-class 기준) |
| GPT-4.1 호출 비용 | 월 합계 | swap 전 / 후 비교 |

이상 발생 시:
- 승격 비율 급증 (>25%) → 키워드 매칭 너무 관대, 임계값 ≥3 으로 조정 검토
- confidence 평균 ↓ → 새 도메인 댓글 유입, 학습 데이터 추가 마이닝 후 재학습
- 일치율 < 85% → API 프롬프트 / Local 모델 중 하나가 drift, 재정렬 필요

---

## 8. 학습 재현 — 모델 새로 학습 시

```bash
# 데이터 준비 (운영 라벨 jsonl 6,375건 기반)
python -m local_classifier.prepare_dataset

# RoBERTa-large 3-class (현재 production 모델)
BASE_MODEL=klue/roberta-large LABEL_SCHEME=3_labels \
  LEARNING_RATE=1e-5 NUM_EPOCHS=4 \
  python -m local_classifier.train
python -m local_classifier.evaluate

# DeBERTa-v3-base 3-class (비교 baseline)
BASE_MODEL=team-lucid/deberta-v3-base-korean LABEL_SCHEME=3_labels \
  LEARNING_RATE=2e-5 NUM_EPOCHS=4 \
  python -m local_classifier.train
BASE_MODEL=team-lucid/deberta-v3-base-korean LABEL_SCHEME=3_labels \
  python -m local_classifier.evaluate

# 두 모델 결과 비교
python -m local_classifier.compare_models
```

산출물 위치 (모두 `.gitignore` 처리):
```
local_classifier/artifacts/3_labels/
├── klue__roberta-large/{model,logs}/
└── team-lucid__deberta-v3-base-korean/{model,logs}/
```

---

## 9. 요약 (한 줄)

- **production 모델**: KLUE-RoBERTa-large 3-class, test macro F1 **0.917**, acc 0.916
- **운영 swap**: `CLASSIFIER_BACKEND=local` 환경변수 한 줄
- **프롬프트 변경**: `batch_prompt_optimized.py` 의 라벨 정의 + few-shot 3-class 로
- **Agent VR 룰**: features ≥ 2 → ANALYZE 승격 (기존 코드 그대로, NOISE 흡수해도 자동 동작)
- **우선 인식 댓글**: 좋아요 + 답글 + 제품 키워드 + 길이 가 같이 큰 댓글
