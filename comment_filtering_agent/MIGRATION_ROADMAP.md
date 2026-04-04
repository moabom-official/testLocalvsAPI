# Few-shot → Fine-tuned Classifier 전환 로드맵

**프로젝트**: 댓글 분류 비용 최적화  
**목표**: 월간 운영 비용 75% 절감 (하이브리드) ~ 90% 절감 (완전 전환)  
**기간**: 12개월  

---

## 📅 타임라인 Overview

```
Month 0-3: Phase 0 (현재 운영)
  └─ Few-shot LLM 100%

Month 3-6: Phase 1 (데이터 준비)
  ├─ 라벨링 데이터 수집
  ├─ 수기 정제
  └─ Train/Valid/Test 분할

Month 6-9: Phase 2 (모델 개발)
  ├─ Fine-tuned 모델 학습
  ├─ 성능 평가
  └─ 하이브리드 시스템 구현

Month 9-12: Phase 3 (점진적 전환)
  ├─ A/B 테스트
  ├─ 카나리 배포
  └─ 완전 전환

Month 12+: Phase 4 (최적화)
  ├─ 성능 모니터링
  ├─ 주기적 재학습
  └─ 지속적 개선
```

---

## Phase 0: 현재 운영 (Month 0-3)

### 목표
- 시스템 안정화
- 데이터 수집
- 베이스라인 성능 측정

### Tasks

#### Week 1-4: 베이스라인 설정
- [ ] Few-shot 분류 성능 측정
  - 샘플 500개 수동 검증
  - 클래스별 정확도 측정
  - 엣지 케이스 수집
- [ ] 비용 모니터링 시작
  - 일별 API 호출 수 기록
  - 월별 비용 집계
- [ ] 성능 지표 대시보드 구축

**산출물**:
```
베이스라인 리포트:
- Overall Accuracy: 92%
- PRODUCT_OPINION F1: 0.94
- VIDEO_REACTION F1: 0.91
- QUESTION F1: 0.89
- CHATTER F1: 0.88
- OFF_TOPIC F1: 0.85
- 월간 비용: $487
- 처리량: 523,000 댓글/월
```

#### Week 5-12: 데이터 수집
- [ ] 다양한 제품 카테고리 댓글 수집
  - 스마트폰: 30%
  - 노트북: 25%
  - 태블릿: 20%
  - 웨어러블: 15%
  - 기타: 10%
- [ ] 엣지 케이스 별도 수집
- [ ] 분류 결과 + Confidence 저장

**산출물**:
- 수집된 댓글: ~50,000개
- Few-shot 자동 라벨: 50,000개
- DB에 저장 완료

---

## Phase 1: 데이터 준비 (Month 3-6)

### 목표
- 고품질 학습 데이터 10,000개 확보
- Train/Valid/Test 분할
- 라벨 정확도 95% 이상

### Tasks

#### Month 3: 1차 라벨링

**Week 1-2: 샘플링 전략**
```python
# 샘플링 코드
def stratified_sampling(comments, n=10000):
    """
    클래스 균형 고려 + 다양성 확보
    """
    samples = []
    
    # 각 클래스별 목표 개수
    target_per_class = {
        'PRODUCT_OPINION': 4000,
        'VIDEO_REACTION': 2000,
        'QUESTION': 1500,
        'CHATTER': 1500,
        'OFF_TOPIC': 1000
    }
    
    # Confidence 분포 고려
    for label, target in target_per_class.items():
        # High confidence (60%)
        high = filter_by_confidence(comments, label, min=0.8, max=1.0)
        samples.extend(random.sample(high, int(target * 0.6)))
        
        # Medium confidence (30%)
        medium = filter_by_confidence(comments, label, min=0.6, max=0.8)
        samples.extend(random.sample(medium, int(target * 0.3)))
        
        # Low confidence (10%)
        low = filter_by_confidence(comments, label, min=0.0, max=0.6)
        samples.extend(random.sample(low, int(target * 0.1)))
    
    return samples
```

- [ ] 50,000개 중 10,000개 선택
- [ ] 클래스 균형 확인
- [ ] Confidence 분포 확인

**Week 3-4: Few-shot으로 1차 라벨링**
- [ ] Groq API로 10,000개 재분류
- [ ] Rationale 포함 저장
- [ ] 비용: ~$10

**산출물**:
- `labeling_pool_v1.csv` (10,000 rows)

#### Month 4: 수기 정제

**Week 1-2: 라벨링 도구 준비**
```python
# 간단한 라벨링 UI
import streamlit as st

def labeling_ui():
    st.title("댓글 라벨 검증")
    
    comment = load_next_comment()
    
    st.write(f"댓글: {comment.text}")
    st.write(f"LLM 예측: {comment.predicted_label} (conf: {comment.confidence})")
    st.write(f"Rationale: {comment.rationale}")
    
    correct = st.radio("라벨이 맞습니까?", ["맞음", "틀림", "애매함"])
    
    if correct == "틀림":
        new_label = st.selectbox("올바른 라벨", LABELS)
        save_correction(comment.id, new_label)
    elif correct == "애매함":
        flag_for_discussion(comment.id)
    else:
        confirm_label(comment.id)
```

- [ ] Streamlit 기반 라벨링 도구 구축
- [ ] 작업 가이드라인 문서화

**Week 3-4: 집중 정제 (2-3명 투입)**

작업 우선순위:
1. Low confidence (< 0.6): 1,000개
2. Medium confidence (0.6-0.8): 3,000개
3. High confidence 샘플링 (0.8+): 500개

- [ ] Day 1-3: 경계 사례 집중 검토
- [ ] Day 4-6: 불일치 사례 토론
- [ ] Day 7-10: 전체 재검증
- [ ] Day 11-12: 최종 확인

**산출물**:
- `labeling_final_v1.csv` (10,000 rows, 95%+ accuracy)
- `edge_cases.md` (애매한 사례 정리)

#### Month 5: Train/Valid/Test 분할

**Week 1: Stratified Split**
```python
from sklearn.model_selection import train_test_split

# 70% train, 15% valid, 15% test
train, temp = train_test_split(
    data, test_size=0.3, stratify=data['label'], random_state=42
)
valid, test = train_test_split(
    temp, test_size=0.5, stratify=temp['label'], random_state=42
)

print(f"Train: {len(train)}")  # 7,000
print(f"Valid: {len(valid)}")  # 1,500
print(f"Test: {len(test)}")    # 1,500
```

- [ ] Stratified split 실행
- [ ] 클래스 분포 확인
- [ ] 데이터 누수 검증

**Week 2-4: 데이터 증강 (선택)**
```python
# Back-translation으로 증강
def augment_with_backtranslation(text):
    # ko → en → ko
    en = translate(text, "ko", "en")
    augmented = translate(en, "en", "ko")
    return augmented

# Train set을 2배로
train_augmented = train + [augment(x) for x in train]
```

- [ ] Back-translation 증강 (선택)
- [ ] 증강 데이터 품질 검증

**산출물**:
- `train.csv` (7,000 rows)
- `valid.csv` (1,500 rows)
- `test.csv` (1,500 rows)

---

## Phase 2: 모델 개발 (Month 6-9)

### 목표
- Fine-tuned 모델 학습
- F1 ≥ 0.85 달성
- 하이브리드 시스템 구현

### Tasks

#### Month 6: 베이스라인 모델 학습

**Week 1: 환경 설정**
```bash
# GPU 환경 준비
pip install transformers torch datasets accelerate

# 모델 다운로드
huggingface-cli login
huggingface-cli download monologg/kobert
```

- [ ] GPU 서버 준비 (AWS p3.2xlarge or GCP T4)
- [ ] 학습 환경 구축

**Week 2-3: KoBERT Fine-tuning**
```python
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer
)

# 모델 로드
model = AutoModelForSequenceClassification.from_pretrained(
    "monologg/kobert",
    num_labels=5,
    id2label={0: "PRODUCT_OPINION", 1: "VIDEO_REACTION", ...},
    label2id={"PRODUCT_OPINION": 0, ...}
)

# 학습 설정
training_args = TrainingArguments(
    output_dir="./kobert-comment-classifier",
    num_train_epochs=5,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=32,
    learning_rate=2e-5,
    weight_decay=0.01,
    evaluation_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1",
)

# 학습
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=valid_dataset,
    compute_metrics=compute_metrics
)

trainer.train()
```

- [ ] 학습 실행 (2-4시간)
- [ ] Validation set 평가
- [ ] Hyperparameter tuning

**Week 4: 성능 평가**
```python
# Test set 평가
results = trainer.evaluate(test_dataset)

print(f"Overall F1: {results['f1']:.3f}")
print(f"PRODUCT_OPINION F1: {results['f1_product']:.3f}")
print(f"VIDEO_REACTION F1: {results['f1_video']:.3f}")
...
```

**목표 성능**:
- Overall F1 ≥ 0.85
- PRODUCT_OPINION F1 ≥ 0.88 (가장 중요!)
- 다른 클래스 F1 ≥ 0.80

**산출물**:
- `kobert-comment-classifier-v1/` (모델 체크포인트)
- `evaluation_report_v1.md`

#### Month 7: 모델 최적화

**Week 1-2: 에러 분석**
```python
# 오분류 사례 분석
errors = []
for sample in test_set:
    pred = model.predict(sample.text)
    if pred != sample.label:
        errors.append({
            'text': sample.text,
            'true': sample.label,
            'pred': pred,
            'confidence': pred.confidence
        })

# 패턴 파악
analyze_error_patterns(errors)
```

- [ ] 오분류 사례 100개 분석
- [ ] 패턴 파악 (짧은 문장, 반어, 비교 등)
- [ ] 추가 학습 데이터 수집 계획

**Week 3-4: 재학습**
```python
# 어려운 샘플 추가 수집
hard_negatives = collect_hard_samples(errors)

# 기존 train에 추가
train_v2 = train + hard_negatives

# 재학습
trainer.train()
```

- [ ] Hard negative mining
- [ ] 재학습
- [ ] 성능 재평가

**산출물**:
- `kobert-comment-classifier-v2/`
- `error_analysis_v1.md`

#### Month 8: 하이브리드 시스템 구현

**Week 1-2: 인터페이스 구현**
```python
# classifiers/hybrid_classifier.py
class HybridClassifier(BaseClassifier):
    def __init__(
        self,
        fine_tuned: FineTunedClassifier,
        llm_fallback: GroqClassifier,
        threshold: float = 0.8
    ):
        self.fine_tuned = fine_tuned
        self.llm_fallback = llm_fallback
        self.threshold = threshold
        self.stats = {"fine_tuned": 0, "llm": 0}
    
    def classify(self, comment: str) -> ClassificationResult:
        # 1차: Fine-tuned
        result = self.fine_tuned.classify(comment)
        
        if result.confidence >= self.threshold:
            self.stats["fine_tuned"] += 1
            result.classifier_used = "fine-tuned"
            return result
        
        # 2차: LLM Fallback
        result = self.llm_fallback.classify(comment)
        self.stats["llm"] += 1
        result.classifier_used = "llm-fallback"
        return result
```

- [ ] HybridClassifier 구현
- [ ] Pipeline 통합
- [ ] 로깅 추가

**Week 3-4: 성능 검증**
- [ ] Test set으로 하이브리드 평가
- [ ] Threshold 최적화 (0.7, 0.75, 0.8, 0.85)
- [ ] 비용/성능 트레이드오프 분석

**산출물**:
- `classifiers/hybrid_classifier.py`
- `hybrid_performance_report.md`

#### Month 9: A/B 테스트 준비

**Week 1-2: 인프라 구축**
```python
# A/B 테스트 라우팅
class ABTestRouter:
    def __init__(self, variant_a, variant_b, split=0.5):
        self.variant_a = variant_a
        self.variant_b = variant_b
        self.split = split
    
    def classify(self, comment: str, video_id: str) -> ClassificationResult:
        # video_id 기반 일관된 라우팅
        if hash(video_id) % 100 < self.split * 100:
            return self.variant_a.classify(comment)
        else:
            return self.variant_b.classify(comment)
```

- [ ] A/B 테스트 라우터 구현
- [ ] 메트릭 수집 인프라
- [ ] 대시보드 구축

**Week 3-4: Dry-run**
- [ ] 소규모 트래픽 (1%) 테스트
- [ ] 버그 수정
- [ ] 모니터링 검증

**산출물**:
- A/B 테스트 준비 완료

---

## Phase 3: 점진적 전환 (Month 9-12)

### 목표
- 하이브리드 시스템 프로덕션 배포
- 비용 75% 절감
- 품질 유지

### Tasks

#### Month 9: A/B 테스트

**Week 1-2: 50/50 Split**
```
Group A (50%): Few-shot LLM
Group B (50%): Hybrid (Fine-tuned + LLM Fallback)

비교 지표:
- 분류 정확도 (샘플 검증)
- Agent 제외율
- 보고서 품질 (감정 스코어)
- 처리 속도
- 비용
```

- [ ] A/B 테스트 시작
- [ ] 일별 메트릭 수집
- [ ] 이상 징후 모니터링

**Week 3-4: 결과 분석**
```python
# A/B 테스트 결과
results = {
    'variant_a': {
        'accuracy': 0.92,
        'avg_latency': 2.3,
        'cost_per_1k': 1.0,
        'sentiment_score_mean': 42.1,
        'sentiment_score_std': 3.2
    },
    'variant_b': {
        'accuracy': 0.91,
        'avg_latency': 0.8,
        'cost_per_1k': 0.25,
        'sentiment_score_mean': 41.8,
        'sentiment_score_std': 3.4
    }
}

# 통계적 유의성 검정
p_value = ttest(variant_a_scores, variant_b_scores)
# p > 0.05 → 유의미한 차이 없음 → 전환 가능
```

- [ ] 통계 분석
- [ ] 전환 Go/No-go 결정

**의사결정 기준**:
```
✅ 전환 조건:
1. Accuracy 차이 < 2%
2. 보고서 품질 유의미한 차이 없음 (p > 0.05)
3. 비용 절감 > 70%
4. 레이턴시 개선

❌ 중단 조건:
1. Accuracy 하락 > 5%
2. 보고서 품질 악화 (p < 0.01)
3. 심각한 버그
```

**산출물**:
- `ab_test_report_month9.md`
- 전환 의사결정

#### Month 10-11: 카나리 배포

**Week 1-2 (10% Hybrid)**
- [ ] 10% 트래픽 Hybrid로 전환
- [ ] 모니터링 강화
- [ ] 이슈 대응

**Week 3-4 (30% Hybrid)**
- [ ] 30% 트래픽 전환
- [ ] 비용 절감 확인
- [ ] 성능 안정성 검증

**Week 5-6 (70% Hybrid)**
- [ ] 70% 트래픽 전환
- [ ] 주간 리뷰
- [ ] Fine-tuning 조정

**Week 7-8 (100% Hybrid)**
- [ ] 완전 전환
- [ ] Few-shot은 Fallback만
- [ ] 최종 비용 확인

**모니터링 지표**:
```python
metrics = {
    'hybrid_ratio': 0.85,  # 85% Fine-tuned 처리
    'llm_fallback_ratio': 0.15,  # 15% LLM
    'monthly_cost': 125,  # $125/월 (vs $500)
    'cost_saving': 0.75,  # 75% 절감
    'accuracy': 0.91,  # 91%
    'product_opinion_f1': 0.90  # 90%
}
```

**산출물**:
- `canary_deployment_report.md`
- 완전 전환 완료

#### Month 12: 안정화

**Week 1-2: 성능 최적화**
- [ ] 추론 속도 최적화 (ONNX 변환)
- [ ] 배치 처리 최적화
- [ ] 메모리 사용량 최적화

**Week 3-4: 재학습 파이프라인**
```python
# 자동 재학습 스크립트
def monthly_retraining():
    # 1. 최근 1개월 데이터 수집
    new_data = collect_recent_comments(days=30)
    
    # 2. Confidence 낮은 것 샘플링
    low_conf = filter(lambda x: x.confidence < 0.7, new_data)
    
    # 3. 수기 라벨링 (소량)
    labeled = manual_labeling(low_conf[:500])
    
    # 4. 기존 train set에 추가
    train_updated = train + labeled
    
    # 5. 재학습
    model_new = retrain(train_updated)
    
    # 6. 성능 평가
    if model_new.f1 > model_current.f1:
        deploy(model_new)
```

- [ ] 재학습 파이프라인 자동화
- [ ] 성능 모니터링 대시보드
- [ ] Alert 설정

**산출물**:
- `retraining_pipeline.py`
- `monitoring_dashboard/`

---

## Phase 4: 지속적 개선 (Month 12+)

### 장기 운영 계획

#### 월간 루틴
- [ ] 성능 모니터링 (매주)
- [ ] 재학습 (매월)
- [ ] 비용 리뷰 (매월)
- [ ] 에러 분석 (분기)

#### 개선 활동
- [ ] Active learning으로 어려운 샘플 지속 수집
- [ ] 새로운 제품 카테고리 추가 시 데이터 보강
- [ ] 모델 업그레이드 (KoBERT → RoBERTa 등)
- [ ] 멀티태스크 학습 (분류 + 감정 + Aspect 동시)

---

## 📊 마일스톤 요약

| Month | 마일스톤 | 산출물 | 비용 |
|-------|---------|--------|------|
| 0-3 | 베이스라인 측정 | 베이스라인 리포트 | $1,500 |
| 3-6 | 라벨링 완료 | 10K 라벨 데이터 | $1,500 |
| 6-9 | 모델 개발 | Fine-tuned 모델 v2 | $2,000 |
| 9 | A/B 테스트 | A/B 테스트 리포트 | $600 |
| 10-11 | 카나리 배포 | 완전 전환 | $400 |
| 12+ | 운영 | 재학습 파이프라인 | $125/월 |

**총 초기 투자**: ~$6,000  
**월간 절감**: $375  
**회수 기간**: 16개월  
**1년 후 누적 절감**: ~$1,500  
**2년 후 누적 절감**: ~$6,000 (Break-even)  

---

## 🎯 성공 기준

### 필수 조건 (Must-have)
- [ ] Fine-tuned F1 ≥ 0.85
- [ ] PRODUCT_OPINION F1 ≥ 0.88
- [ ] 비용 절감 ≥ 70%
- [ ] 보고서 품질 유지 (통계적 유의미한 차이 없음)

### 선택 조건 (Nice-to-have)
- [ ] Fine-tuned F1 ≥ 0.88
- [ ] 비용 절감 ≥ 80%
- [ ] 처리 속도 3배 향상
- [ ] 재학습 파이프라인 완전 자동화

---

**프로젝트 오너**: _____________  
**검토**: _____________  
**승인**: _____________  
**시작일**: _____________
