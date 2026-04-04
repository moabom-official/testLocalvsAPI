# 댓글 필터링 Agent 폴더 구조

## 📁 전체 구조

```
Moabom_Prototype/
├── comment_filtering_agent/           # [NEW] 댓글 필터링 Agent 독립 모듈
│   │
│   ├── core/                          # 핵심 Agent 로직
│   │   ├── __init__.py
│   │   ├── agent.py                   # CommentFilteringAgent 메인 클래스
│   │   ├── decision.py                # AgentDecision 데이터 클래스
│   │   └── pipeline.py                # 전체 파이프라인 오케스트레이터
│   │
│   ├── filters/                       # 1차 규칙 기반 필터
│   │   ├── __init__.py
│   │   ├── rule_based_filter.py      # RuleBasedFilter 메인 클래스
│   │   ├── length_filter.py          # 길이 체크 필터
│   │   ├── emoji_filter.py           # 이모지 전용 댓글 필터
│   │   ├── pattern_filter.py         # 반응 패턴 필터 ("1등", "ㅋㅋㅋ")
│   │   ├── url_filter.py             # URL/광고 필터
│   │   └── profanity_filter.py       # 욕설 필터
│   │
│   ├── classifiers/                   # 2차 LLM 기반 분류기
│   │   ├── __init__.py
│   │   ├── base_classifier.py        # LLMClassifier 추상 인터페이스
│   │   ├── few_shot_classifier.py    # Few-shot 구현체 (현재)
│   │   ├── finetuned_classifier.py   # Fine-tuned 모델 구현체 (향후)
│   │   └── models.py                 # CommentLabel, ClassificationResult
│   │
│   ├── utils/                         # 유틸리티
│   │   ├── __init__.py
│   │   ├── spam_detector.py          # 스팸/중복 탐지
│   │   ├── text_processor.py         # 텍스트 전처리
│   │   ├── cache_manager.py          # 분류 결과 캐싱
│   │   └── logger.py                 # 로깅 유틸
│   │
│   ├── prompts/                       # LLM 프롬프트 템플릿
│   │   ├── few_shot_base.txt         # 기본 few-shot 프롬프트
│   │   ├── few_shot_ko.txt           # 한국어 프롬프트
│   │   └── recheck_prompt.txt        # 재판단용 프롬프트
│   │
│   ├── data/                          # 데이터 파일
│   │   ├── stopwords_ko.txt          # 한국어 불용어 사전
│   │   ├── profanity_list.txt        # 욕설 사전
│   │   └── reaction_patterns.json    # 반응 패턴 정의
│   │
│   ├── tests/                         # 테스트
│   │   ├── __init__.py
│   │   ├── test_rule_filter.py       # 규칙 필터 테스트
│   │   ├── test_classifier.py        # 분류기 테스트
│   │   ├── test_agent.py             # Agent 통합 테스트
│   │   └── fixtures/                 # 테스트 데이터
│   │       └── sample_comments.json
│   │
│   ├── __init__.py                    # 패키지 초기화
│   ├── README.md                      # Agent 사용 가이드
│   └── config.py                      # Agent 설정
│
├── app/                               # 기존 FastAPI 앱
├── services/                          # 기존 서비스
├── llm/                               # 기존 LLM 클라이언트
└── main.py
```

---

## 📦 모듈별 역할

### 1. `core/` - 핵심 로직
Agent의 메인 비즈니스 로직이 들어있는 곳입니다.

```
core/
├── agent.py         → CommentFilteringAgent 클래스 (3차 판단 로직)
├── decision.py      → AgentDecision 데이터 클래스
└── pipeline.py      → 전체 파이프라인 오케스트레이션
```

**주요 클래스**:
- `CommentFilteringAgent`: 1차 필터 + 2차 분류 결과를 종합해서 최종 결정
- `AgentDecision`: 판단 결과를 담는 데이터 클래스
- `FilteringPipeline`: 전체 흐름을 관리하는 파이프라인

---

### 2. `filters/` - 1차 규칙 필터
빠르고 가벼운 패턴 기반 필터입니다.

```
filters/
├── rule_based_filter.py   → 메인 필터 (규칙들을 통합)
├── length_filter.py       → 길이 체크 (< 5자 제외)
├── emoji_filter.py        → 이모지만 있는 댓글 제외
├── pattern_filter.py      → 반응 패턴 ("1등", "ㅋㅋㅋ")
├── url_filter.py          → URL 포함 댓글 제외
└── profanity_filter.py    → 욕설 탐지
```

**설계 원칙**:
- 각 필터는 독립적으로 동작
- 규칙 추가/제거가 쉬움
- LLM 호출 전에 최대한 걸러내기

---

### 3. `classifiers/` - 2차 LLM 분류기
LLM을 활용한 지능형 분류기입니다.

```
classifiers/
├── base_classifier.py      → LLMClassifier 추상 인터페이스
├── few_shot_classifier.py  → Few-shot 구현체 (Groq API)
├── finetuned_classifier.py → Fine-tuned 모델 구현체 (향후)
└── models.py              → CommentLabel, ClassificationResult
```

**확장 전략**:
- 추상 인터페이스로 구현체 교체 가능
- Few-shot → Fine-tuned 쉽게 전환

---

### 4. `utils/` - 유틸리티
공통으로 사용되는 유틸리티입니다.

```
utils/
├── spam_detector.py     → 스팸/중복 탐지 (Levenshtein 거리)
├── text_processor.py    → 텍스트 전처리 (정규화, 클리닝)
├── cache_manager.py     → Redis/메모리 캐싱
└── logger.py           → 구조화된 로깅
```

---

### 5. `prompts/` - 프롬프트 템플릿
LLM에 전달할 프롬프트를 저장합니다.

```
prompts/
├── few_shot_base.txt    → 기본 few-shot 프롬프트
├── few_shot_ko.txt      → 한국어 최적화 프롬프트
└── recheck_prompt.txt   → 재판단용 프롬프트
```

---

### 6. `data/` - 데이터 파일
규칙 기반 필터에서 사용할 사전 데이터입니다.

```
data/
├── stopwords_ko.txt         → 한국어 불용어 ("등", "님", "요")
├── profanity_list.txt       → 욕설 사전
└── reaction_patterns.json   → 반응 패턴 정의
```

---

### 7. `tests/` - 테스트
유닛/통합 테스트입니다.

```
tests/
├── test_rule_filter.py      → 규칙 필터 테스트
├── test_classifier.py       → 분류기 테스트
├── test_agent.py            → Agent 통합 테스트
└── fixtures/
    └── sample_comments.json → 테스트용 댓글 샘플
```

---

## 🔄 데이터 흐름

```
[댓글 입력]
    ↓
┌─────────────────────────────────┐
│ pipeline.py                     │
│ FilteringPipeline.process()     │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ filters/rule_based_filter.py    │ ← 1차 필터
│ - length_filter                 │
│ - emoji_filter                  │
│ - pattern_filter                │
│ - url_filter                    │
└─────────────────────────────────┘
    ↓ passed_comments
┌─────────────────────────────────┐
│ classifiers/few_shot_classifier │ ← 2차 분류
│ - LLM API 호출                  │
│ - 5개 라벨 분류                 │
└─────────────────────────────────┘
    ↓ classifications
┌─────────────────────────────────┐
│ core/agent.py                   │ ← 3차 판단
│ CommentFilteringAgent           │
│ - 욕설 체크                     │
│ - 스팸 체크                     │
│ - 신뢰도 검증                   │
│ - 라벨별 라우팅                 │
└─────────────────────────────────┘
    ↓
[AgentDecision 리스트]
    ↓
[DB 저장 / 다음 단계]
```

---

## 🚀 사용 예시

```python
# main.py 또는 FastAPI 엔드포인트에서

from comment_filtering_agent.core.pipeline import FilteringPipeline
from comment_filtering_agent.core.agent import CommentFilteringAgent
from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
from comment_filtering_agent.classifiers.few_shot_classifier import FewShotClassifier
from comment_filtering_agent.utils.spam_detector import SpamDetector
from llm.groq_client import GroqClient

# 초기화
llm_client = GroqClient()
classifier = FewShotClassifier(
    llm_client=llm_client,
    prompt_path="comment_filtering_agent/prompts/few_shot_ko.txt"
)

agent = CommentFilteringAgent(
    rule_filter=RuleBasedFilter(),
    classifier=classifier,
    spam_detector=SpamDetector(),
    confidence_threshold=0.6
)

pipeline = FilteringPipeline(agent=agent)

# 댓글 필터링 실행
comments = [
    "발열은 심한데 성능은 좋네요",
    "ㅋㅋㅋㅋㅋ",
    "오늘 영상 재밌네요",
]

decisions = pipeline.process(comments)

# 결과 확인
for decision in decisions:
    print(f"댓글: {decision.text}")
    print(f"라벨: {decision.label}")
    print(f"액션: {decision.action}")
    print(f"다음 단계: {decision.next_stage}")
    print("---")
```

---

## 🔧 설정 파일

`comment_filtering_agent/config.py`:

```python
from dataclasses import dataclass

@dataclass
class AgentConfig:
    # 필터 설정
    min_length: int = 5
    max_emoji_ratio: float = 0.8
    
    # 분류기 설정
    confidence_threshold: float = 0.6
    recheck_threshold: float = 0.7
    
    # LLM 설정
    llm_provider: str = "groq"
    model_name: str = "llama-3.1-70b-versatile"
    
    # 캐싱
    enable_cache: bool = True
    cache_ttl: int = 3600  # 1시간
    
    # 로깅
    log_level: str = "INFO"
```

---

## 📝 독립 모듈의 장점

1. **명확한 책임 분리**: Agent 관련 코드가 한 곳에 모여있음
2. **재사용성**: 다른 프로젝트에서도 쉽게 가져다 쓸 수 있음
3. **테스트 용이**: 독립적인 테스트 실행 가능
4. **유지보수성**: 변경 사항이 다른 모듈에 영향을 미치지 않음
5. **확장성**: 새로운 필터/분류기 추가가 쉬움

---

## 🎯 다음 단계

1. **구현 순서**:
   ```
   1) filters/rule_based_filter.py
   2) classifiers/base_classifier.py
   3) classifiers/few_shot_classifier.py
   4) core/agent.py
   5) core/pipeline.py
   ```

2. **통합**:
   - `app/services.py`에서 `FilteringPipeline` 사용
   - FastAPI 엔드포인트 추가
   - 기존 `CommentFilterService`와 병행 운영

3. **테스트**:
   - 단위 테스트 작성
   - 실제 댓글 100개로 정확도 검증
   - 성능 벤치마크
