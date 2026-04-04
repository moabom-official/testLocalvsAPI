"""
정확도 측정 방법 설명 문서

벤치마크에서 사용한 정확도 지표와 한계점
"""

print("="*70)
print("정확도 측정 방법 설명")
print("="*70)

print("""
현재 벤치마크에서 사용한 정확도 지표:

1. Label Agreement Rate (라벨 일치율)
   - 정의: Legacy와 Batch가 동일한 라벨을 준 댓글의 비율
   - 계산: (일치한 댓글 수) / (전체 댓글 수)
   - 예시: 10개 중 7개 일치 = 70%
   
   왜 사용했나?
   - Ground Truth(정답)가 없는 상황에서 사용 가능
   - 두 방법의 일관성(consistency)을 측정
   - 빠르게 계산 가능

   한계점:
   - 둘 다 틀릴 수도 있음 (일치한다고 정답은 아님)
   - 절대적 정확도가 아닌 상대적 일관성만 측정
   - 예: Legacy=CHATTER, Batch=CHATTER → 일치
         하지만 실제 정답은 PRODUCT_OPINION일 수 있음!

2. Confidence Score (신뢰도 점수)
   - 정의: LLM이 자신의 판단에 대해 얼마나 확신하는지
   - 범위: 0.0 ~ 1.0 (높을수록 확신)
   - 비교: Legacy 평균 vs Batch 평균
   
   왜 사용했나?
   - LLM의 확신도를 비교
   - 불확실한 댓글을 찾아낼 수 있음
   - 품질 지표로 활용 가능

   한계점:
   - Confidence가 높다고 정답은 아님 (과신할 수 있음)
   - Confidence calibration 문제
   - 예: Confidence 0.95로 틀릴 수도 있음

3. Label Distribution (라벨 분포)
   - 정의: 각 라벨별로 몇 개씩 분류했는지
   - 비교: Legacy vs Batch 분포 차이
   
   예시:
   Legacy: CHATTER=3, VIDEO_REACTION=5, OFF_TOPIC=1, PRODUCT_OPINION=1
   Batch:  CHATTER=5, VIDEO_REACTION=4, OFF_TOPIC=1, PRODUCT_OPINION=0
   
   왜 사용했나?
   - 분류 경향 파악 (한쪽이 특정 라벨에 편향되는지)
   - 극단적 차이 발견 가능
   
   한계점:
   - 분포가 다르다고 틀린 것은 아님
   - 데이터 특성에 따라 달라질 수 있음

=""")

print("\n" + "="*70)
print("현재 방법의 문제점")
print("="*70)

print("""
[문제 1] Ground Truth 없음
  → 실제 정답이 없어서 절대적 정확도를 모름
  → 둘 다 틀릴 가능성 존재

[문제 2] 상대 비교만 가능
  → Legacy가 정확하다는 보장 없음
  → Batch와 일치한다고 정확하다는 보장 없음

[문제 3] 애매한 댓글
  → "can confirm: he never gave us up"
     Legacy: VIDEO_REACTION
     Batch: CHATTER
     정답: ??? (사람도 판단 어려움)
""")

print("\n" + "="*70)
print("더 나은 정확도 측정 방법")
print("="*70)

print("""
1. Ground Truth 생성 (수동 라벨링)
   방법:
   - 사람이 직접 100개 댓글에 정답 라벨 부여
   - 여러 명이 라벨링 후 다수결
   - Inter-annotator agreement 계산
   
   장점:
   - 절대적 정확도 측정 가능
   - Precision, Recall, F1-score 계산
   
   단점:
   - 시간 많이 소요
   - 비용 발생
   - 애매한 케이스는 사람도 의견 다름

2. Confusion Matrix
   실제 정답이 있다면:
   
                 Predicted
           PO   Q   VR   CH   OT
   Actual
   PO     10   0    1    2    0
   Q       0   5    0    1    0
   VR      1   0   15    3    0
   CH      2   1    2   20    1
   OT      0   0    0    1    5
   
   이를 통해:
   - Precision: 정밀도 (예측한 것 중 맞은 비율)
   - Recall: 재현율 (실제 중 찾아낸 비율)
   - F1-score: 조화평균

3. Cross-validation
   방법:
   - 데이터를 여러 번 나눠서 테스트
   - 평균 성능 측정
   - 과적합 방지
   
   장점:
   - 더 신뢰할 수 있는 결과
   
   단점:
   - API 호출 많이 필요
   - 시간 많이 소요

4. Human Evaluation
   방법:
   - 불일치 케이스만 사람이 판단
   - 어느 쪽이 더 정확한지 평가
   
   장점:
   - 현실적인 타협안
   - 전체 라벨링보다 적은 노력
   
   단점:
   - 여전히 수동 작업 필요
""")

print("\n" + "="*70)
print("현재 벤치마크의 의미")
print("="*70)

print("""
현재 70% Label Agreement의 의미:

✅ 확실한 것:
  - 30%의 댓글은 두 방법이 다르게 분류함
  - Legacy와 Batch는 100% 동일하지 않음
  - 애매한 댓글에서 차이 발생

❓ 불확실한 것:
  - 어느 쪽이 더 정확한지 모름
  - 둘 다 틀렸을 가능성도 있음
  - 70%가 "좋은" 수치인지 판단 어려움

💡 실용적 해석:
  - Batch가 8배 빠르고 90% 비용 절감
  - 70% 일치는 "합리적" 수준
  - 완벽한 일치를 기대하기 어려움 (LLM의 특성)
  - 중요한 경우 불일치 케이스 검토 권장

🎯 결론:
  - 속도/비용 절감이 목적이면 Batch 사용 권장
  - 정확도가 최우선이면 수동 검증 병행
  - 70% 일치율은 실무에서 충분히 사용 가능
""")

print("\n" + "="*70)
print("권장 개선 방향")
print("="*70)

print("""
1. 소규모 Ground Truth 생성
   - 대표적인 100개 댓글만 수동 라벨링
   - 이를 기준으로 정확도 측정
   - 비용: 1~2시간 정도

2. Active Learning
   - Confidence 낮은 댓글만 사람이 확인
   - 점진적으로 정확도 향상
   
3. A/B Testing
   - 실제 서비스에 두 방법 병행 적용
   - 사용자 피드백으로 평가

4. 전문가 검토
   - 불일치 30% 케이스만 검토
   - 어느 쪽이 더 합리적인지 판단
""")

print("\n" + "="*70)
print("요약")
print("="*70)

print("""
현재 정확도 측정 방법:
  지표: Label Agreement Rate (70%)
  의미: Legacy vs Batch 일치율
  
한계:
  - 절대적 정확도 아님 (상대 비교)
  - Ground Truth 없음
  - 둘 다 틀릴 수 있음

왜 사용했나:
  - Ground Truth 없이 빠르게 비교 가능
  - 두 방법의 일관성 측정
  - 실무적으로 충분히 유용

개선 방향:
  - 100개 댓글 수동 라벨링 (Ground Truth)
  - Precision/Recall/F1 계산
  - 불일치 케이스 전문가 검토
""")

print("\n" + "="*70)
