# testLocalvsAPI

댓글 분류기 backend 두 가지를 같은 댓글 셋으로 비교하는 도구.

| Backend | 모델 |
|---|---|
| **API** | GPT-4.1 (openai/gpt-4.1-2025-04-14) via RunYourAI |
| **Local** | KLUE-RoBERTa-large 3-class (자체 학습, test macro F1 0.917) |

## 빠른 시작

```bash
git clone https://github.com/moabom-official/testLocalvsAPI.git
cd testLocalvsAPI

# 의존성
pip install -r requirements.txt

# 환경변수
cp .env.example .env
# RUNYOURAI_API_KEY, YOUTUBE_API_KEY 채우기

# 학습된 모델 가중치 배포 (별도)
# → local_classifier/artifacts/3_labels/klue__roberta-large/model/best/

# 비교 실행
python -m scripts.benchmark.run_agent_comparison --product "갤럭시 S25"
```

자세한 사용법 / 모델 정보 / 트러블슈팅:

> **→ [scripts/benchmark/README.md](scripts/benchmark/README.md)**

## 리포 구조

```
testLocalvsAPI/
├── scripts/benchmark/
│   ├── run_agent_comparison.py   # ⭐ 제품명 입력 → 자동 비교
│   ├── compare_classifiers.py    # video_id 지정 비교
│   ├── agent_helpers.py          # fetch/preprocess/select (sync.py 소량 추출)
│   └── README.md                 # 상세 가이드
├── comment_filtering_agent/      # 7-step 댓글 필터 agent (운영 동일)
│   ├── classifiers/              # API 분류기 (OptimizedBatchClassifier)
│   ├── filters/                  # 규칙 필터
│   └── services/                 # YouTube 댓글 수집
├── local_classifier/             # KLUE-RoBERTa 학습 + 추론
│   ├── classifier.py             # 추론 wrapper + VR 키워드 매칭
│   ├── keywords.py               # PRODUCT_ASPECT_KEYWORDS
│   └── train.py / evaluate.py
├── requirements.txt
└── .env.example
```

## 운영 코드 의존성 0

비교 도구는 운영 본체 (FastAPI / DB / templates / video_selection_agent / regression 등)에 의존하지 않음. 단일 리포로 충분.

-  가 운영  의 필요 로직만 자체 복제
-  와  는 self-contained 패키지

> 운영 본체에 backend swap 적용은 [Moabom_Prototype 의 APIvsLOCAL 브랜치](https://github.com/moabom-official/Moabom_Prototype/tree/APIvsLOCAL) 참고.
