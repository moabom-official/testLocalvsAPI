"""
LLM 호출 지점 분석 - 불필요한 호출이 있는지 확인
"""

print("="*70)
print("LLM 호출 지점 분석")
print("="*70)

print("\n[1단계] 1차 필터 (Rule-based Filter)")
print("   - LLM 호출: ❌ 없음")
print("   - 로직: 정규식, stopword, 패턴 매칭만 사용")
print("   - 비용: 0 토큰")

print("\n[2단계] 2차 분류 (LLM Classifier)")
print("   - LLM 호출: ✅ 있음 (classify_batch)")
print("   - 호출 조건: 1차 필터 통과한 댓글만")
print("   - 배치 크기: 10개씩")
print("   - 예상 호출 횟수: (통과 댓글 수 / 10)")
print("   - 비용: ~1,500 토큰/배치")

print("\n[3단계] Agent 결정 (AgentDecisionEngine)")
print("   - LLM 호출: ❌ 없음")
print("   - 로직: 분류 결과를 규칙 기반으로 판단")
print("   - RECLASSIFY 액션 시: ⚠️ 재분류 필요 (현재 미구현)")
print("   - 비용: 0 토큰")

print("\n[4단계] 감정 분석 (Sentiment Analyzer)")
print("   - LLM 호출: ✅ 있음 (analyze)")
print("   - 호출 조건: Agent가 ANALYZE로 판단한 댓글만")
print("   - 배치 처리: ❌ 없음 (개별 호출)")
print("   - 예상 호출 횟수: ANALYZE 액션 개수")
print("   - 비용: ~1,000 토큰/댓글")

print("\n[5단계] 질문 분석 (Question Processor)")
print("   - LLM 호출: ✅ 있음 (현재 미사용)")
print("   - 호출 조건: Agent가 AUXILIARY_STORE로 판단한 질문 댓글")
print("   - 비용: ~500 토큰/댓글")

print("\n[6단계] 보고서 생성")
print("   - LLM 호출: ❌ 없음")
print("   - 로직: DB 데이터 집계 및 템플릿 기반 생성")
print("   - 비용: 0 토큰")

print("\n" + "="*70)
print("잠재적 문제점")
print("="*70)

print("\n⚠️ 1. 감정 분석이 배치 처리되지 않음")
print("   - 현재: ANALYZE 댓글마다 개별 API 호출")
print("   - 개선: 10개씩 묶어서 배치 처리 가능")
print("   - 절감: 80% 토큰 절약")

print("\n⚠️ 2. RECLASSIFY 무한 루프 가능성")
print("   - Agent가 needs_recheck=true인 댓글을 RECLASSIFY로 판단")
print("   - 재분류 로직이 없으면 무한 루프 발생 가능")
print("   - 현재 상태: RECLASSIFY 액션 후 처리 미구현")

print("\n⚠️ 3. Question Processor 중복 호출 가능성")
print("   - 모든 QUESTION 라벨 댓글에 LLM 호출")
print("   - 간단한 질문도 LLM 분석 필요한지 검토 필요")

print("\n✅ 4. 현재 설정은 합리적")
print("   - 1차 필터: 빠른 규칙 기반 제외")
print("   - 2차 분류: 배치로 효율적 처리")
print("   - Agent: 규칙 기반 판단 (LLM 미사용)")
print("   - 감정 분석: 필요한 댓글만 분석")

print("\n" + "="*70)
print("토큰 소모 예상 (50개 댓글 기준)")
print("="*70)

print("\n시나리오: 1차 필터 50개 모두 통과")
print("   - 2차 분류: 5번 배치 호출 × 1,500 = 7,500 토큰")
print("   - Agent 결정: 0 토큰")
print("   - 감정 분석: 8개 ANALYZE × 1,000 = 8,000 토큰")
print("   - 총합: ~15,500 토큰 ✅")

print("\n시나리오: 1차 필터 30개만 통과")
print("   - 2차 분류: 3번 배치 호출 × 1,500 = 4,500 토큰")
print("   - Agent 결정: 0 토큰")
print("   - 감정 분석: 5개 ANALYZE × 1,000 = 5,000 토큰")
print("   - 총합: ~9,500 토큰 ✅✅")

print("\n" + "="*70)
print("권장사항")
print("="*70)

print("\n1. 감정 분석도 배치 처리 구현")
print("   - GroqAspectSentimentAnalyzer.analyze_batch() 추가")
print("   - 10개씩 묶어서 처리")
print("   - 예상 절감: 6,000 토큰 → 1,200 토큰")

print("\n2. RECLASSIFY 로직 명확히 정의")
print("   - 재분류 최대 1회로 제한")
print("   - 또는 HOLD로 변경하여 사람 검토")

print("\n3. 현재는 불필요한 호출 없음 ✅")
print("   - 모든 LLM 호출이 필요한 시점에만 발생")
print("   - 1차 필터가 효과적으로 작동")

print("\n" + "="*70)
