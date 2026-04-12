# Comments Filtering Agent 실행 과정 수정 내역 (0412, 0411 스펙 정렬판)

## 개요
`Comments_Filtering_Token_Optimization_0411.md`의 핵심인  
**다중 기준 추출 + 중복(hit_count) 우선 선별** 구조로 `scripts/api/sync.py`를 재수정함.

---

## 1) 이번에 실제로 바꾼 내용

### A. 전처리
- `_normalize_comment_text`
- `_deduplicate_comments`

정규화 + 중복 제거만 수행하고, 하드 필터링은 하지 않음.

### B. 소프트 필터 로깅 유지
- `RuleBasedFilter` 결과는 `rule_filter_results`에 저장
- 실행 흐름은 PASS로 유지 (제거 기준 아님)

### C. 0411 방식의 다중 기준 후보 추출 도입
신규 함수:
- `_select_comments_multicriteria(comment_items, product_name)`
- `_keyword_hit_count(comment_text, product_name)`
- `_normalize_feature(...)`
- `_to_timestamp(...)`

기준 소스:
- `like` (좋아요 상위)
- `many` (답글 상위)
- `long` (길이 상위)
- `new` (최신)
- `old` (오래된)
- `random` (랜덤)

### D. hit_count 기반 1차/2차 선별
1차:
- `hit_count >= 2` 우선 선발

2차(부족분 보충):
- `hit_count == 1` 대상에서 `secondary_score` 계산
- `secondary_score = normalized_like + normalized_reply + keyword_hit_count`
- 정렬: `secondary_score DESC`, `길이 DESC`

### E. 토큰 예산 적용
- `MAX_LLM_COMMENTS = 20`
- `MAX_COMMENT_CHARS = 140`
- `TOKEN_BUDGET_PER_VIDEO = 2000`
- 영상 예산 초과 시 낮은 우선순위부터 제거

### F. 배치 상수 정합성 수정
- classifier 생성 시 `batch_size=CLASSIFICATION_BATCH_SIZE`로 변경 (기존 하드코딩 10 제거)

---

## 2) 수정 후 파이프라인

```text
[Collect]
  YouTube 댓글 수집(최대 100)
      ↓
[Preprocess]
  normalize + dedup
      ↓
[Persist + Soft Filter Log]
  comments 저장
  rule_filter_results 저장(PASS 흐름)
      ↓
[Multi-Criteria Candidate Extraction]
  like / many / long / new / old / random
      ↓
[Overlap Counting]
  comment별 hit_count, sources 집계
      ↓
[Primary Selection]
  hit_count >= 2 우선 선택
      ↓
[Secondary Fill]
  hit_count == 1 에서 secondary_score 기반 보충
      ↓
[Token Budget]
  개수/길이/영상 예산 제한 적용
      ↓
[LLM Classification]
  OptimizedBatchClassifier.classify_batch
      ↓
[Agent Decision]
  ANALYZE / EXCLUDE
      ↓
[Aspect/Sentiment]
  ANALYZE 대상만 추가 분석
      ↓
[DB 저장 + 기존 보고서/UI 연계]
```

---

## 3) 수정 파일
- `scripts/api/sync.py`

핵심 변경:
- 기존 단일 가중치 점수 방식 제거
- 다중 기준 + 중복 기반 선별로 교체
- batch size 상수 실제 반영
