# 분류기 비교 도구 (API vs Local)

댓글 분류기 backend 두 가지를 같은 댓글 셋으로 비교하는 CLI.

| Backend | 모델 | 위치 |
|---|---|---|
| **API** | GPT-4.1 (RunYourAI 게이트웨이) | 외부 API |
| **Local** | KLUE-RoBERTa-large 3-class | 자체 학습 + 호스팅 |

운영 댓글 파이프라인의 분류 단계만 두 번 (각 backend) 돌려서 결과를 비교.
DB 에 쓰지 않음 (read-only).

---

## 1. 사전 준비

### 1-1. 의존성 설치

```bash
pip install -r requirements.txt              # 운영 코드 의존성
pip install -r local_classifier/requirements.txt  # Local 모델 추가 의존성
```

### 1-2. 환경변수

`.env.example` 복사 후 채우기 (또는 `export` 직접):

```bash
cp .env.example .env
# 편집해서 키 값 채우기
```

| 변수 | 필수 | 용도 |
|---|---|---|
| `RUNYOURAI_API_KEY` | ★ | API 분류기 호출 |
| `RUNYOURAI_BASE_URL` | (default 있음) | `https://api.runyour.ai/v1` |
| `RUNYOURAI_MODEL` | (default 있음) | `openai/gpt-4.1-2025-04-14` |
| `YOUTUBE_API_KEY` | ★ | YouTube 댓글 fetch + 영상 검색 |
| `DATABASE_URL` | ★ (dummy OK) | `scripts.api.sync` 임포트 시점 검사. 실제 DB 쓰지 않음. `postgresql://dummy@dummy/dummy` 도 통과. |

### 1-3. 학습된 Local 모델 가중치 배포

Local backend 만 쓸 경우 모델 가중치 (~1.3GB) 가 필요. **git 에 포함되지 않음**.

```
local_classifier/artifacts/3_labels/klue__roberta-large/model/best/
├── model.safetensors      (~1.3 GB) ★
├── config.json
├── tokenizer.json
├── tokenizer_config.json
├── vocab.txt
├── special_tokens_map.json
└── training_config.json
```

학습한 머신에서 운영으로 옮기는 예:
```bash
# 학습 머신 → 운영 머신
scp -r user@trainer:/PATH/local_classifier/artifacts/3_labels \
       ./local_classifier/artifacts/
# 검증
ls -lh local_classifier/artifacts/3_labels/klue__roberta-large/model/best/
```

> API 만 비교할 거면 (`--skip-local`) 가중치 불필요.

---

## 2. 가장 빠른 사용법

### 제품명만으로 자동 검색 + 비교 ⭐

```bash
python -m scripts.benchmark.run_agent_comparison --product "갤럭시 S25"
```

흐름:
1. YouTube 에서 `<제품명> 리뷰` 검색 (KR, 조회수 순) → 인기 영상 1개 자동 선택
2. `comment_filtering_agent` 의 fetch + rule filter + Multi-Criteria 선정 (default 20 댓글)
3. API / Local 분류기에 같은 댓글 셋 입력
4. 콘솔에 댓글별 결과 + 일치 여부 출력
5. `scripts/benchmark/results/<product>_<timestamp>.json` 저장

옵션:

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--product TEXT` | (interactive 입력) | 제품명 |
| `--top-k N` | 20 | 분류기에 넣을 댓글 최대 개수 |
| `--skip-api` | - | API 건너뜀 (Local 만) |
| `--skip-local` | - | Local 건너뜀 (API 만) |
| `--output PATH` | 자동 | JSON 결과 저장 경로 |

### Interactive 모드

```bash
python -m scripts.benchmark.run_agent_comparison
> 제품명을 입력하세요: 갤럭시 S25
```

### 특정 video_id 로 비교 (검색 단계 skip)

```bash
python -m scripts.benchmark.compare_classifiers \
    --video-id UQt_EMkUdbs \
    --product-name "갤럭시 S25" \
    --max-comments 100 \
    --output result.json
```

---

## 3. 출력 해석

### 콘솔 출력 예

```
[1] YouTube 검색 — '갤럭시 S25'
  ★ 갤럭시 S25 7일 사용기 — 진짜 솔직 후기
    channel    : ITSub잇섭
    view_count : 850,000
    comments   : 1,234

[ 1]  좋아요  234  · 답글  12
     발열이 심한데 성능은 진짜 좋네요 게임할 때 손이 뜨거워서…
     API   : PRODUCT_OPINION    (conf=0.952)
     Local : PRODUCT_OPINION    (conf=0.937)
     일치  : ✓  (운영 3-class 기준)

[ 2]  좋아요   87  · 답글   3
     영상 잘 만드셨네요 다음 영상도 기대됩니다
     API   : VIDEO_REACTION     (conf=0.891)
     Local : VIDEO_REACTION     (conf=0.902)
     일치  : ✓

[ 3]  좋아요   56
     ㅋㅋㅋㅋㅋ 신기하다
     API   : NOISE              (conf=0.945)
     Local : VIDEO_REACTION     (conf=0.612)
     일치  : ✓  ← NOISE → VR 흡수 후 동일 (운영 동등)

...

요약:
  API   분포 : {'PRODUCT_OPINION': 11, 'VIDEO_REACTION': 5, 'NOISE': 3, 'QUESTION': 1}
  API   시간 : 8.34s  (2.40 cmt/s)
  API   비용 추정 (GPT-4.1) : $0.0028
  Local 분포 : {'PRODUCT_OPINION': 11, 'VIDEO_REACTION': 8, 'QUESTION': 1}
  Local 시간 : 0.42s  (47.62 cmt/s)

  >> speedup (Local vs API) : 19.86x
  >> 일치율 (3-class 운영)  : 95.0%
```

### JSON 결과 구조

```json
{
  "product_name": "갤럭시 S25",
  "generated_at": "2026-05-27T16:30:00",
  "video": {"video_id": "...", "title": "...", "view_count": 850000, ...},
  "summary": {
    "n_comments": 20,
    "api_elapsed_s": 8.34,
    "local_elapsed_s": 0.42,
    "speedup_local_vs_api": 19.86,
    "agreement_3class": 0.95,
    "api_cost_usd_est": 0.0028,
    "api_label_dist": {...},
    "local_label_dist": {...}
  },
  "comments": [
    {
      "rank": 1,
      "text": "발열이 심한데 성능은 진짜 좋네요…",
      "like_count": 234,
      "api_label": "PRODUCT_OPINION",
      "api_confidence": 0.952,
      "api_3class": "PRODUCT_OPINION",
      "local_label": "PRODUCT_OPINION",
      "local_confidence": 0.937,
      "local_3class": "PRODUCT_OPINION",
      "agree_3class": true
    },
    ...
  ]
}
```

### 핵심 지표

| 지표 | 의미 | 운영 의사결정 |
|---|---|---|
| **`agreement_3class`** | NOISE/CHATTER/OFF_TOPIC → VR 흡수 후 일치율 | **>90% 면 운영 swap 가능** |
| `raw_4class_agreement` | NOISE 별개 비교 (참고용) | - |
| `speedup_local_vs_api` | 같은 환경 가정 시 속도 비교 | 환경 다르면 unfair, 참고만 |
| `api_cost_usd_est` | GPT-4.1 추정 비용 | Local 전환 시 절감 가능 |

---

## 4. 환경 분리 시나리오 (API 노트북 / Local 서버)

운영 서버가 외부 API 차단됐을 때:

| 메트릭 | 직접 비교 가능? |
|---|---|
| label / confidence | ✅ 환경 무관, 분류 결정적 |
| 일치율 | ✅ |
| 비용 추정 | ✅ 토큰 수 기반 |
| **wall clock time** | ❌ 환경 차이로 unfair |

→ 분류 정확도만 비교하고 시간은 별도 합산. 운영 결정엔 충분.

---

## 5. 운영 swap (별도 — 비교 도구 아님)

비교 결과가 만족스러우면 운영 `main.py` 도 swap 가능:

```bash
# Local 분류기로 운영
CLASSIFIER_BACKEND=local python main.py

# API 분류기 (default)
python main.py
```

`scripts/api/sync.py:process_comments_with_agent` 가 환경변수 보고 분류기 인스턴스 결정. ABSA / agent decision / DB 저장 등 나머지 흐름은 그대로.

---

## 6. 트러블슈팅

### `Warning: Batch classification failed: 401 Unauthorized`
→ `RUNYOURAI_API_KEY` 누락 / 만료. `.env` 또는 export 확인.

### `Warning: Batch classification failed: Connection error`
→ 서버 외부망 차단 가능성. 진단:
```bash
python -c "import socket; print(socket.gethostbyname('api.runyour.ai'))"
```
DNS 실패면 방화벽 / proxy 확인. 회사망 proxy 사용 시:
```bash
export HTTPS_PROXY=http://<실제-proxy-host>:<실제-포트>
```
**placeholder `<...>` 그대로 두지 말 것** — `nonnumeric port: port` 에러 발생.

### `FileNotFoundError: model not found at .../best`
→ Local 모델 가중치 미배포. § 1-3 참고. 또는 `--skip-local` 로 API 만.

### `KeyError: 'comment_text'` 등 데이터 키 에러
→ sync.py 스키마 변경 시 발생 가능. issue 제기.

### YouTube `403 quotaExceeded`
→ 일일 quota 10K 초과. 다음 날 또는 새 API 키.

---

## 7. 관련 파일

| 파일 | 역할 |
|---|---|
| `scripts/benchmark/run_agent_comparison.py` | 제품명 → 검색 → 비교 (사용자 추천) |
| `scripts/benchmark/compare_classifiers.py` | video_id → 비교 (저수준) |
| `scripts/api/sync.py` | `CLASSIFIER_BACKEND` 환경변수 swap |
| `local_classifier/classifier.py` | Local 분류기 wrapper + VR 키워드 매칭 |
| `local_classifier/keywords.py` | `PRODUCT_ASPECT_KEYWORDS` (sync.py 와 동기) |
| `local_classifier/config.py` | 3-class 라벨 / 모델 경로 |

---

## 8. 학습 머신에서 모델 학습 / 평가

본 리포의 `local_classifier/` 폴더는 추론만 아니라 학습 전체 파이프라인도 포함.
가중치 자체는 `.gitignore` 처리 — 학습은 별도 실행 후 결과를 운영으로 옮김.

```bash
# 1. 학습 데이터 준비 (운영 라벨 export 기반)
python -m local_classifier.prepare_dataset

# 2. 학습 (default: klue/roberta-large, 4 epoch, lr 1e-5)
python -m local_classifier.train

# 3. 평가
python -m local_classifier.evaluate

# 4. 모델 비교 (여러 backbone 실험 시)
python -m local_classifier.compare_models
```

산출물 위치: `local_classifier/artifacts/<LABEL_SCHEME>/<MODEL_SLUG>/`

자세한 학습 가이드는 `local_classifier/README.md` 참고.
