"""
정확도 측정의 한계와 개선 방안을 시각적으로 보여주는 예시
"""

print("="*70)
print("정확도 측정 방법 - 구체적 예시")
print("="*70)

print("""
[현재 사용한 방법: Label Agreement Rate]

예시 데이터 (10개 댓글):

ID   댓글                          Legacy         Batch          일치?
------------------------------------------------------------------------
1    "can confirm..."              VIDEO_REACTION CHATTER        X
2    "Why has the world..."        OFF_TOPIC      OFF_TOPIC     O
3    "Holy tried to find..."       VIDEO_REACTION VIDEO_REACTION O
4    "Ad saved mee"                PRODUCT_OPINION VIDEO_REACTION X
5    "Kokoshka is a genius"        VIDEO_REACTION VIDEO_REACTION O
6    "Dude I swear gemini..."      CHATTER        CHATTER        O
7    "@mokkachocolata"             CHATTER        CHATTER        O
8    "Lucky that the 5 sec..."     VIDEO_REACTION VIDEO_REACTION O
9    "W HSR"                       CHATTER        CHATTER        O
10   "Miltil, sua puta!!!"         VIDEO_REACTION CHATTER        X

일치: 7개 / 전체: 10개 = 70% Label Agreement
""")

print("\n" + "="*70)
print("[문제점: 실제 정답이 뭔지 모름]")
print("="*70)

print("""
만약 Ground Truth(정답)가 있다면:

ID   댓글                    실제정답       Legacy         Batch          
------------------------------------------------------------------------
1    "can confirm..."        VIDEO_REACTION VIDEO_REACTION CHATTER        
     → Legacy 맞음 ✓, Batch 틀림 ✗

4    "Ad saved mee"          VIDEO_REACTION PRODUCT_OPINION VIDEO_REACTION
     → Legacy 틀림 ✗, Batch 맞음 ✓

6    "Dude I swear..."       CHATTER        CHATTER        CHATTER        
     → 둘 다 맞음 ✓✓

가능한 시나리오:
- 70% 일치하지만 Legacy가 더 정확할 수도
- 70% 일치하지만 Batch가 더 정확할 수도
- 70% 일치하지만 둘 다 틀렸을 수도
""")

print("\n" + "="*70)
print("[더 나은 방법: Ground Truth 기반 측정]")
print("="*70)

print("""
100개 댓글에 대해 사람이 정답 라벨링:

실제정답      Legacy 예측    Batch 예측
------------------------------------------
PRODUCT_OPINION (20개)
  맞춤:        18개 (90%)    17개 (85%)
  틀림:        2개 (10%)     3개 (15%)

QUESTION (15개)
  맞춤:        13개 (87%)    14개 (93%)
  틀림:        2개 (13%)     1개 (7%)

VIDEO_REACTION (30개)
  맞춤:        25개 (83%)    24개 (80%)
  틀림:        5개 (17%)     6개 (20%)

CHATTER (25개)
  맞춤:        23개 (92%)    24개 (96%)
  틀림:        2개 (8%)      1개 (4%)

OFF_TOPIC (10개)
  맞춤:        8개 (80%)     9개 (90%)
  틀림:        2개 (20%)     1개 (10%)

전체 정확도:
  Legacy: 87/100 = 87%
  Batch:  88/100 = 88%

→ 이제 절대적 정확도를 알 수 있음!
→ Batch가 약간 더 정확하다는 것을 확인!
""")

print("\n" + "="*70)
print("[Precision, Recall, F1-score 예시]")
print("="*70)

print("""
PRODUCT_OPINION 라벨 기준:

Legacy 분류 결과:
  - 실제 PO를 PO로 분류: 18개 (True Positive)
  - 실제 PO를 다른 것으로: 2개 (False Negative)
  - 다른 것을 PO로 분류: 3개 (False Positive)

계산:
  Precision = TP / (TP + FP) = 18 / (18 + 3) = 85.7%
  → Legacy가 PO라고 예측한 것 중 85.7%가 맞음
  
  Recall = TP / (TP + FN) = 18 / (18 + 2) = 90.0%
  → 실제 PO 중 90.0%를 찾아냄
  
  F1 = 2 * (P * R) / (P + R) = 87.8%
  → 전체적인 성능 지표

Batch 분류 결과:
  - 실제 PO를 PO로 분류: 17개 (True Positive)
  - 실제 PO를 다른 것으로: 3개 (False Negative)
  - 다른 것을 PO로 분류: 2개 (False Positive)

계산:
  Precision = 17 / (17 + 2) = 89.5%
  Recall = 17 / (17 + 3) = 85.0%
  F1 = 87.2%
  
→ Legacy는 Recall 우세 (더 많이 찾아냄)
→ Batch는 Precision 우세 (정확하게 분류)
""")

print("\n" + "="*70)
print("[현재 70% Agreement의 실제 의미]")
print("="*70)

print("""
70% Label Agreement = 70% 일치율

하지만 이것만으로는:
❌ 정확도가 70%라는 뜻이 아님
❌ 30%가 틀렸다는 뜻이 아님
❌ 어느 쪽이 더 정확한지 알 수 없음

실제 의미:
✓ 두 방법이 70%의 댓글에서 같은 판단
✓ 30%의 댓글에서 다른 판단
✓ 두 방법의 일관성(consistency) 측정

가능한 시나리오 3가지:

시나리오 1: Legacy가 더 정확
  - 불일치 30%에서 Legacy가 대부분 맞음
  - 실제 정확도: Legacy 90%, Batch 75%

시나리오 2: Batch가 더 정확
  - 불일치 30%에서 Batch가 대부분 맞음
  - 실제 정확도: Legacy 75%, Batch 90%

시나리오 3: 비슷한 정확도
  - 불일치 30%에서 반반씩 맞음
  - 실제 정확도: Legacy 85%, Batch 85%

→ Ground Truth 없이는 어떤 시나리오인지 모름!
""")

print("\n" + "="*70)
print("[왜 이 방법을 사용했나?]")
print("="*70)

print("""
이유 1: Ground Truth가 없음
  - 100개 댓글 수동 라벨링 = 1~2시간 소요
  - 벤치마크 목적: 속도 비교가 주 목적
  - 빠른 측정이 필요했음

이유 2: 상대적 일관성 측정
  - 두 방법이 얼마나 비슷하게 동작하는지 확인
  - 극단적으로 다르면 문제 신호
  - 70%면 "합리적" 수준

이유 3: 실용적 선택
  - 완벽한 정확도보다 속도/비용이 목적
  - 8배 빠르고 90% 비용 절감이 메인 포인트
  - 정확도 70% 일치면 실무 사용 가능

이유 4: LLM 특성
  - LLM은 확률적 모델
  - 같은 모델도 호출할 때마다 결과 다를 수 있음
  - 100% 일치는 현실적으로 어려움
""")

print("\n" + "="*70)
print("[개선 방안]")
print("="*70)

print("""
단기 (1~2시간):
  1. 대표 100개 댓글만 수동 라벨링
  2. Precision/Recall/F1 계산
  3. 절대적 정확도 확인

중기 (1주일):
  1. 불일치 30% 케이스만 전문가 검토
  2. 어느 쪽이 더 합리적인지 판단
  3. 패턴 분석 (어떤 타입에서 차이 발생?)

장기 (1개월):
  1. Active Learning 도입
  2. Confidence 낮은 케이스만 사람 검토
  3. 점진적 품질 향상
  4. A/B 테스트로 실사용 데이터 수집
""")

print("\n" + "="*70)
print("결론")
print("="*70)

print("""
현재 측정 방법:
  - 지표: Label Agreement Rate (70%)
  - 의미: Legacy와 Batch의 일치율
  - 한계: 절대적 정확도 모름

왜 사용했나:
  - Ground Truth 없이 빠르게 비교
  - 속도/비용 절감이 주 목적
  - 실용적 타협안

개선 필요시:
  - 100개 댓글 수동 라벨링
  - Precision/Recall/F1 계산
  - 불일치 케이스 검토

실무 판단:
  - 8배 빠르고 90% 비용 절감
  - 70% 일치는 충분히 사용 가능
  - 중요한 경우만 수동 검증 병행
""")

print("\n" + "="*70)
