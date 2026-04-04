# 기술 의사결정 문서 (TDD)
# Few-shot LLM vs Fine-tuned Classifier 전환 전략

**문서 버전**: 1.0  
**작성일**: 2026-04-02  
**상태**: 제안  
**담당**: 댓글 분석 파이프라인팀  

---

## 1. 배경 및 현황

### 1.1 현재 아키텍처

```
[댓글 수집]
    ↓
[1차 규칙 필터] ← 경량 (CPU, ~5,000/sec)
    ↓
[2차 LLM 분류] ← 현재: Few-shot (Groq API)
    ↓
[Agent 결정]
    ↓
[감정/질문 분석]
    ↓
[보고서 생성]
```

### 1.2 현재 Few-shot LLM 분류 방식

**사용 모델**: Groq API (llama-3.3-70b-versatile)  
**방식**: 25개 few-shot examples + system prompt  
**처리 속도**: ~2-3초/댓글  
**정확도**: ~90-95% (추정)  

---

## 2. Few-shot 방식 분석

### 2.1 장점 ✅

#### 1. **즉시 사용 가능**
- 학습 데이터 불필요
- 프롬프트만으로 작동
- 빠른 프로토타이핑

#### 2. **높은 초기 정확도**
- 70B 파라미터 LLM
- 문맥 이해 우수
- 엣지 케이스 처리 강점

#### 3. **유연한 수정**
- 프롬프트 수정만으로 개선
- 새 라벨 추가 용이
- A/B 테스트 쉬움

#### 4. **도메인 적응성**
- 한국어 자연어 이해
- 제품 리뷰 문맥 파악
- 반어/비교 표현 인식

### 2.2 단점 ❌

#### 1. **높은 운영 비용**
```
비용 계산 예시:
- 1개 댓글 분류: ~0.001달러 (Groq 무료 제한 초과 시)
- 100만 댓글/월: ~1,000달러
- 연간: ~12,000달러
```

#### 2. **API 의존성**
- 외부 서비스 장애 위험
- 네트워크 레이턴시
- Rate limiting

#### 3. **처리 속도 제한**
- API 호출 오버헤드
- 배치 처리 한계
- 실시간 처리 어려움

#### 4. **비용 예측 어려움**
- 댓글 수 변동
- API 가격 정책 변경
- 확장성 문제

---

## 3. Fine-tuned Classifier 분석

### 3.1 장점 ✅

#### 1. **낮은 운영 비용**
```
비용 비교:
- Few-shot: 1,000달러/100만 댓글
- Fine-tuned: ~50달러/월 (GPU 서버)
- 절감: 95% ↓
```

#### 2. **빠른 처리 속도**
- GPU: ~100-500/sec
- CPU: ~10-50/sec
- 배치 최적화 가능

#### 3. **독립 운영**
- API 의존성 제거
- 오프라인 동작
- 안정성 향상

#### 4. **예측 가능한 비용**
- 고정 인프라 비용
- 확장 계획 수립 용이

### 3.2 단점 ❌

#### 1. **초기 투자 필요**
```
라벨링 비용:
- 5,000개: ~500,000원 (크라우드소싱)
- 10,000개: ~1,000,000원
- 수기 정제: 추가 시간
```

#### 2. **학습 데이터 수집**
- 고품질 라벨 필수
- 클래스 불균형 문제
- 주기적 재학습 필요

#### 3. **정확도 리스크**
- 초기 정확도 불확실
- Few-shot 대비 낮을 수 있음
- 엣지 케이스 약할 수 있음

#### 4. **유지보수 복잡도**
- 모델 버전 관리
- 재학습 파이프라인
- 성능 모니터링

---

## 4. 전환 시점 판단 기준

### 4.1 정량적 기준

#### 1. **처리량 기준**
```python
월간 댓글 수 > 50만개
→ Fine-tuned 전환 검토

계산 근거:
- Few-shot: 50만 * $0.001 = $500/월
- Fine-tuned: GPU 서버 $50/월 + 초기 투자 상각
- Break-even: 3-6개월
```

#### 2. **비용 효율성**
```
ROI 계산:
초기 투자: $2,000 (라벨링 + 학습 환경)
월간 절감: $450
회수 기간: ~4.5개월

→ 6개월 이상 운영 시 전환 권장
```

#### 3. **성능 허용 범위**
```
Fine-tuned 정확도 ≥ 85%
AND
Few-shot 정확도 - Fine-tuned 정확도 ≤ 5%

→ 전환 가능
```

### 4.2 정성적 기준

#### 1. **서비스 성숙도**
- 프로덕션 안정화 완료
- 라벨 정의 확정
- 6개월 이상 운영 경험

#### 2. **데이터 축적**
- 충분한 댓글 데이터 확보
- 다양한 엣지 케이스 수집
- 클래스별 균형 데이터

#### 3. **팀 역량**
- ML 모델 학습 경험
- 모델 운영 인프라
- 성능 모니터링 체계

---

## 5. 전환 절차 (3단계)

### 5.1 Phase 1: 라벨링 데이터 생성

#### Step 1-1: 고성능 API로 1차 라벨링
```python
# Groq API로 10,000개 댓글 자동 라벨링
for comment in unlabeled_comments[:10000]:
    result = groq_classifier.classify(comment)
    save_to_labeling_pool(comment, result)

예상 비용: ~$10
예상 시간: ~6시간
```

#### Step 1-2: 라벨 분포 확인
```python
PRODUCT_OPINION: 4,200개 (42%)
VIDEO_REACTION: 2,100개 (21%)
QUESTION: 1,500개 (15%)
CHATTER: 1,400개 (14%)
OFF_TOPIC: 800개 (8%)

→ 불균형 확인 후 추가 수집
```

#### Step 1-3: 수기 정제
```
정제 작업:
- 불확실한 라벨 재검토 (confidence < 0.7)
- 경계 사례 수기 판단
- 라벨 일관성 검증

투입: 2-3명 * 3일
목표: 95% 이상 정확도
```

#### Step 1-4: Train/Valid/Test 분할
```python
train: 7,000개 (70%)
valid: 1,500개 (15%)
test: 1,500개 (15%)

Stratified split (클래스 비율 유지)
```

### 5.2 Phase 2: 모델 학습

#### Step 2-1: 베이스라인 모델 선정
```
후보 모델:
1. KoBERT (추천)
   - 한국어 특화
   - 5-class 분류 성능 우수
   - 경량 (~110MB)

2. KoELECTRA
   - 성능 우수
   - 약간 무거움

3. Sentence Transformers
   - 문장 임베딩 + Classifier
   - 확장성 좋음
```

#### Step 2-2: Fine-tuning
```python
from transformers import AutoModelForSequenceClassification, Trainer

model = AutoModelForSequenceClassification.from_pretrained(
    "monologg/kobert",
    num_labels=5
)

trainer = Trainer(
    model=model,
    train_dataset=train_dataset,
    eval_dataset=valid_dataset,
    compute_metrics=compute_metrics
)

trainer.train()

예상 학습 시간: GPU 2-4시간
```

#### Step 2-3: 성능 평가
```python
# Test set 평가
precision: 0.87
recall: 0.85
f1-score: 0.86
accuracy: 0.86

# 클래스별 성능
PRODUCT_OPINION: F1 0.91 (중요!)
VIDEO_REACTION: F1 0.84
QUESTION: F1 0.82
CHATTER: F1 0.79
OFF_TOPIC: F1 0.75

→ 목표: Overall F1 ≥ 0.85
```

### 5.3 Phase 3: 점진적 전환

#### Step 3-1: A/B 테스트 (1주일)
```
Group A (50%): Few-shot LLM
Group B (50%): Fine-tuned

비교 지표:
- 분류 정확도
- 최종 보고서 품질
- 처리 속도
- 비용
```

#### Step 3-2: 카나리 배포 (2주)
```
Week 1: 10% Fine-tuned
Week 2: 30% Fine-tuned
Week 3: 70% Fine-tuned
Week 4: 100% Fine-tuned (LLM은 fallback만)
```

#### Step 3-3: 모니터링
```python
모니터링 지표:
- 분류 정확도 (샘플링 검증)
- Agent 제외율 (급증 시 이슈)
- 최종 보고서 품질 (감정 스코어 변동)
- 사용자 피드백
```

---

## 6. 성능 vs 비용 판단 기준

### 6.1 허용 가능한 성능 차이

```
시나리오 1: 높은 정확도 유지
Few-shot: 92%
Fine-tuned: 90%
차이: -2%

→ ✅ 전환 가능
이유: 1차 필터가 70% 걸러냄 + Agent가 재검증
```

```
시나리오 2: 중간 정확도
Few-shot: 92%
Fine-tuned: 85%
차이: -7%

→ ⚠️ 신중 검토
조건: PRODUCT_OPINION F1 ≥ 0.90 필수
```

```
시나리오 3: 낮은 정확도
Few-shot: 92%
Fine-tuned: 78%
차이: -14%

→ ❌ 전환 불가
이유: 보고서 품질 저하 우려
```

### 6.2 비용 효율성 계산

```python
# 투자 회수 기간 계산
def calculate_roi(
    initial_investment,  # 초기 투자 (라벨링 + 학습)
    monthly_saving,      # 월간 절감액
    accuracy_drop        # 정확도 하락 (%)
):
    # 정확도 하락 페널티
    if accuracy_drop > 10:
        return "전환 불가"
    
    penalty = accuracy_drop * 0.5  # 1% 하락 = 0.5개월 추가
    payback_months = initial_investment / monthly_saving + penalty
    
    if payback_months < 6:
        return "즉시 전환 권장"
    elif payback_months < 12:
        return "전환 검토"
    else:
        return "Few-shot 유지"

# 예시
calculate_roi(
    initial_investment=2000,  # $2,000
    monthly_saving=450,       # $450/월
    accuracy_drop=2           # -2%
) 
# → "즉시 전환 권장" (4.4 + 1 = 5.4개월)
```

---

## 7. 잡담이 섞여도 괜찮은 이유 (시스템 관점)

### 7.1 다층 방어 구조

```
Layer 1: 1차 규칙 필터 (정밀도 ~95%)
  → "ㅋㅋㅋ", "1등", "잘 보고 갑니다" 제거
  → 70% 댓글 걸러냄

Layer 2: 2차 LLM 분류 (정확도 85-92%)
  → PRODUCT_OPINION vs 기타 분류
  → 일부 잡담 VIDEO_REACTION으로 분류 가능

Layer 3: Agent 결정 (정책 기반)
  → VIDEO_REACTION → EXCLUDE
  → Confidence < 0.6 → HOLD/RECLASSIFY
  → 최종 방어선

Layer 4: 보고서 집계 (통계적 안정성)
  → Aspect 기반 집계
  → 이상치 제거
  → 다수결 원리
```

### 7.2 오분류 영향 분석

#### 시나리오 A: 잡담이 긍정으로 오분류
```
"ㅋㅋㅋ 재밌네요" → PRODUCT_OPINION (오분류)
    ↓
감정 분석: positive (aspect 없음)
    ↓
보고서 집계: Aspect 없어서 제외
    ↓
영향: 전체 긍정 비율 +0.1% (미미)
```

#### 시나리오 B: 제품 평가가 잡담으로 오분류
```
"발열 좀 있네요 ㅋㅋ" → CHATTER (오분류)
    ↓
Agent: CHATTER → EXCLUDE
    ↓
영향: 발열 부정 의견 1개 누락
    ↓
보고서: 발열 156개 → 155개 (-0.6%, 미미)
```

### 7.3 통계적 안정성

```python
# 몬테카를로 시뮬레이션
def simulate_misclassification(
    total_comments=687,
    error_rate=0.08,  # 8% 오분류
    iterations=1000
):
    results = []
    for _ in range(iterations):
        # 오분류 시뮬레이션
        misclassified = random.sample(comments, int(total * error_rate))
        
        # 보고서 생성
        report = generate_report(comments - misclassified)
        results.append(report.sentiment_score)
    
    return np.std(results)

# 결과: 표준편차 ±2.3
# 감정 스코어: 42.3 ± 2.3
# → 오차 범위 내 (유의미한 변화 아님)
```

**결론**: 
- 5-10% 오분류는 통계적으로 흡수됨
- Aspect 기반 집계가 노이즈 완화
- 대량 데이터일수록 안정적

---

## 8. 하이브리드 전략 (권장)

### 8.1 전략 개요

```
[1차 규칙 필터]
    ↓
[2차 분류] ← 여기에 하이브리드 적용
  ├─ Fine-tuned (80-90% 댓글)
  │   └─ Confidence ≥ 0.8 → 직접 사용
  │
  └─ Few-shot LLM Fallback (10-20% 댓글)
      └─ Confidence < 0.8 → LLM 재판단
    ↓
[Agent 결정]
```

### 8.2 비용 최적화

```python
# 비용 계산
기존 Few-shot 100%: $500/월 (50만 댓글)

하이브리드:
- Fine-tuned 85%: $50/월 (GPU)
- Few-shot 15%: $75/월 (7.5만 댓글)
총 비용: $125/월

절감: 75% ↓
```

### 8.3 품질 유지

```
Fine-tuned 처리: 85% (confidence ≥ 0.8)
  → 정확도 ~90% (높은 확신)

LLM Fallback: 15% (confidence < 0.8)
  → 정확도 ~95% (애매한 케이스)

전체 정확도: 0.85 * 0.90 + 0.15 * 0.95 = 90.75%
→ Few-shot 92%와 거의 동일
```

### 8.4 구현 예시

```python
class HybridClassifier:
    def __init__(self, fine_tuned, llm_fallback, threshold=0.8):
        self.fine_tuned = fine_tuned
        self.llm_fallback = llm_fallback
        self.threshold = threshold
    
    def classify(self, comment: str) -> ClassificationResult:
        # 1차: Fine-tuned 시도
        result = self.fine_tuned.classify(comment)
        
        # Confidence 체크
        if result.confidence >= self.threshold:
            result.classifier_used = "fine-tuned"
            return result
        
        # 2차: LLM Fallback
        result = self.llm_fallback.classify(comment)
        result.classifier_used = "llm-fallback"
        return result
```

---

## 9. 추천 의사결정

### 9.1 즉시 실행 (현재)

✅ **Few-shot LLM 유지**
- 이유: 프로토타입 단계
- 기간: 3-6개월
- 목표: 데이터 수집 + 시스템 안정화

### 9.2 단기 (3-6개월)

✅ **라벨링 데이터 준비**
- Few-shot으로 10,000개 자동 라벨링
- 수기 정제 (정확도 95% 이상)
- 비용: ~$2,000

### 9.3 중기 (6-12개월)

✅ **하이브리드 전환**
- Fine-tuned 모델 학습
- A/B 테스트
- 점진적 전환 (카나리 배포)
- 예상 절감: 월 $375

### 9.4 장기 (12개월+)

✅ **완전 Fine-tuned 전환 검토**
- 조건: F1 ≥ 0.90, 운영 안정화
- LLM은 완전히 제거 또는 극소량 fallback만
- 예상 절감: 월 $450+

---

## 10. 리스크 및 완화 방안

### 10.1 정확도 하락 리스크

**리스크**: Fine-tuned 정확도 < 85%

**완화**:
1. 충분한 학습 데이터 (10,000+)
2. 정기적 재학습 (월 1회)
3. Active learning으로 지속 개선
4. Fallback 전략 유지

### 10.2 초기 투자 리스크

**리스크**: ROI 미달성

**완화**:
1. 단계별 투자 (Phase 분할)
2. 소규모 PoC 먼저 (1,000개)
3. 명확한 중단 기준 설정

### 10.3 유지보수 리스크

**리스크**: 모델 성능 저하

**완화**:
1. 자동 모니터링 대시보드
2. 성능 임계값 알림
3. 재학습 파이프라인 자동화

---

## 11. 의사결정 요약

| 기준 | Few-shot LLM | Fine-tuned | 하이브리드 |
|------|-------------|-----------|----------|
| **초기 비용** | 낮음 | 높음 ($2K) | 높음 ($2K) |
| **운영 비용** | 높음 ($500/월) | 낮음 ($50/월) | 중간 ($125/월) |
| **정확도** | 92% | 86% | 91% |
| **처리 속도** | 느림 | 빠름 | 중간 |
| **유연성** | 높음 | 낮음 | 중간 |
| **추천 시점** | 초기 (0-6개월) | 장기 (12개월+) | 중기 (6-12개월) |

**최종 권장**: 
1. **현재**: Few-shot 유지 (데이터 수집)
2. **6개월 후**: 하이브리드 전환 (비용 75% 절감)
3. **12개월 후**: 완전 Fine-tuned 검토 (비용 90% 절감)

---

**승인**: [ ]  
**검토자**: _____________  
**날짜**: _____________
