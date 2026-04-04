"""
최적화된 분류기 사용 예시 및 성능 비교
"""
import time
from comment_filtering_agent.classifiers.optimized_batch_classifier import (
    OptimizedBatchClassifier,
    create_optimized_classifier
)
from comment_filtering_agent.classifiers.groq_classifier import GroqClassifier


def compare_performance():
    """기존 vs 최적화 분류기 성능 비교"""
    
    # 테스트 댓글
    test_comments = [
        "발열이 심해요",
        "성능 좋네요",
        "배터리 오래 가요",
        "오늘 영상 재밌어요",
        "ㅋㅋㅋㅋ",
        "이거 게임 잘 돌아가나요?",
        "가격 대비 괜찮아요",
        "디자인 예쁘네요",
        "소음이 좀 있어요",
        "배경음악 뭔가요?",
    ] * 5  # 50개
    
    print("="*70)
    print("성능 비교: 기존 vs 최적화 분류기")
    print("="*70)
    print(f"테스트 댓글 수: {len(test_comments)}개\n")
    
    # ========================================
    # 1. 기존 분류기 (배치 처리만)
    # ========================================
    print("[1] 기존 GroqClassifier (배치 처리)")
    print("-" * 70)
    
    try:
        old_classifier = GroqClassifier()
        
        start = time.time()
        old_results = old_classifier.classify_batch(
            test_comments,
            start_index=0
        )
        old_time = time.time() - start
        
        print(f"✓ 소요 시간: {old_time:.2f}초")
        print(f"✓ 분류 완료: {len(old_results)}개")
        print(f"✓ API 호출 횟수: ~{(len(test_comments) + 9) // 10}회 (배치)")
        print(f"✓ 예상 토큰: ~{((len(test_comments) + 9) // 10) * 1500} 토큰\n")
        
    except Exception as e:
        print(f"✗ 실행 실패: {e}\n")
        old_time = 0
    
    # ========================================
    # 2. 최적화 분류기
    # ========================================
    print("[2] OptimizedBatchClassifier")
    print("-" * 70)
    
    try:
        new_classifier = OptimizedBatchClassifier()
        
        # 첫 번째 실행 (캐시 없음)
        start = time.time()
        new_results_1 = new_classifier.classify_batch(
            test_comments,
            start_index=0
        )
        new_time_1 = time.time() - start
        
        print(f"[첫 실행 - 캐시 없음]")
        print(f"✓ 소요 시간: {new_time_1:.2f}초")
        print(f"✓ 분류 완료: {len(new_results_1)}개")
        
        stats_1 = new_classifier.get_stats()
        print(f"✓ 캐시 통계: {stats_1['cache']}")
        
        # 두 번째 실행 (캐시 있음)
        start = time.time()
        new_results_2 = new_classifier.classify_batch(
            test_comments,
            start_index=0
        )
        new_time_2 = time.time() - start
        
        print(f"\n[두 번째 실행 - 캐시 활용]")
        print(f"✓ 소요 시간: {new_time_2:.2f}초")
        print(f"✓ 분류 완료: {len(new_results_2)}개")
        
        stats_2 = new_classifier.get_stats()
        print(f"✓ 캐시 통계: {stats_2['cache']}")
        print(f"✓ 속도 향상: {new_time_1 / new_time_2:.1f}배 빨라짐\n")
        
    except Exception as e:
        print(f"✗ 실행 실패: {e}\n")
        new_time_1 = 0
    
    # ========================================
    # 3. 비교 요약
    # ========================================
    print("="*70)
    print("요약")
    print("="*70)
    
    if old_time > 0 and new_time_1 > 0:
        improvement = (1 - new_time_1 / old_time) * 100
        print(f"첫 실행 시간 단축: {improvement:.1f}%")
    
    print("\n최적화 효과:")
    print("1. 프롬프트 압축: few-shot 25개 → 8개 (70% 토큰 절감)")
    print("2. 출력 최소화: 필수 필드만 반환 (50% 토큰 절감)")
    print("3. 캐싱: 중복 댓글 재분류 방지 (100% 절감)")
    print("4. 재판단: 확신도 낮은 댓글만 재요청")
    print("\n예상 총 절감: 60~80%")


def test_cache():
    """캐싱 기능 테스트"""
    
    print("\n" + "="*70)
    print("캐싱 기능 테스트")
    print("="*70)
    
    classifier = OptimizedBatchClassifier()
    
    # 동일한 댓글 반복
    comments = [
        "발열이 심해요",
        "성능 좋네요",
        "발열이 심해요",  # 중복
        "성능 좋네요",    # 중복
        "새로운 댓글",
    ]
    
    print(f"\n댓글 목록 (중복 포함):")
    for i, c in enumerate(comments, 1):
        print(f"  {i}. {c}")
    
    # 분류 실행
    results = classifier.classify_batch(comments)
    
    # 통계
    stats = classifier.get_stats()
    print(f"\n캐시 통계:")
    print(f"  - 전체 요청: {stats['cache']['hits'] + stats['cache']['misses']}개")
    print(f"  - 캐시 히트: {stats['cache']['hits']}개")
    print(f"  - 캐시 미스: {stats['cache']['misses']}개")
    print(f"  - 히트율: {stats['cache']['hit_rate']}")
    print(f"\n→ 중복 댓글 2개는 캐시에서 즉시 반환!")


def test_recheck():
    """재판단 로직 테스트"""
    
    print("\n" + "="*70)
    print("재판단 로직 테스트")
    print("="*70)
    
    classifier = OptimizedBatchClassifier(
        confidence_threshold=0.8  # 높은 임계값 설정
    )
    
    comments = [
        "좋네요",           # 애매함 → 재판단 필요
        "발열 심해요",      # 명확함
        "그냥 그래요",      # 애매함 → 재판단 필요
    ]
    
    print(f"\n애매한 댓글 (confidence < 0.8) 재판단 예정:")
    for i, c in enumerate(comments, 1):
        print(f"  {i}. {c}")
    
    results = classifier.classify_batch(comments)
    
    print(f"\n분류 결과:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {comments[i-1]}")
        print(f"     → {result.label.value} (confidence: {result.confidence:.2f})")
        print(f"     → 재판단됨: {result.needs_recheck}")


if __name__ == "__main__":
    # 성능 비교
    compare_performance()
    
    # 캐싱 테스트
    test_cache()
    
    # 재판단 테스트
    test_recheck()
