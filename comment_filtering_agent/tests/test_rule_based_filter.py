"""
1차 규칙 기반 필터 - 테스트 코드
"""
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
from comment_filtering_agent.filters.models import RuleConfig, RejectReason


def test_basic_filtering():
    """기본 필터링 테스트"""
    print("=" * 80)
    print("테스트 1: 기본 필터링")
    print("=" * 80)
    
    filter_engine = RuleBasedFilter()
    
    # 테스트 댓글 샘플
    test_comments = [
        # 통과해야 하는 댓글
        "발열은 심한데 성능은 정말 좋네요. 게임도 잘 돌아가고 배터리도 오래가요.",
        "이거 실제로 써보니까 생각보다 소음이 커요. 밤에 쓰기엔 좀 그래요.",
        "가격 대비 성능이 괜찮은 것 같아요. 다만 발열 관리가 아쉽네요.",
        "이 제품 게임할 때 프레임 드랍 있나요? 구매 고민 중입니다.",
        
        # 제외되어야 하는 댓글
        "ㅋㅋㅋㅋㅋㅋㅋ",                           # REACTION_ONLY
        "잘 보고 갑니다",                            # GREETING_ONLY
        "1등!",                                      # REACTION_ONLY
        "오늘도 영상 잘봤어요 구독했습니다",         # CREATOR_PRAISE_ONLY
        "😂😂😂😂😂",                               # EMOJI_HEAVY
        "ㅋ",                                        # TOO_SHORT
        "http://bit.ly/sale 최저가 할인",           # URL_SPAM
        "시발 이거 개별로네",                        # ABUSIVE
        "!!!!!!",                                    # SPECIAL_CHARS_ONLY
        "ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ",        # LOW_INFORMATION
    ]
    
    results = filter_engine.filter_batch(test_comments)
    
    # 결과 출력
    for result in results:
        print(f"\n[{result.index}] {result.original_text[:50]}")
        print(f"  ✓ 통과: {result.is_passed}")
        if not result.is_passed:
            print(f"  ✗ 제외 사유: {[r.value for r in result.reject_reason_codes]}")
            print(f"  ✗ 매칭 규칙: {result.matched_rules}")
        if result.metadata:
            print(f"  📊 메타데이터: {result.metadata}")
    
    # 통계
    passed = sum(1 for r in results if r.is_passed)
    rejected = len(results) - passed
    print(f"\n{'=' * 80}")
    print(f"총 {len(results)}개 댓글 중 통과: {passed}개, 제외: {rejected}개")
    print(f"{'=' * 80}\n")


def test_korean_patterns():
    """한국어 패턴 테스트"""
    print("=" * 80)
    print("테스트 2: 한국어 특수 패턴")
    print("=" * 80)
    
    filter_engine = RuleBasedFilter()
    
    korean_comments = [
        "ㅋㅋㅋㅋㅋㅋ",
        "ㅎㅎㅎ재미있네요",
        "ㅠㅠㅠㅠ아쉬워요",
        "와 대박",
        "오 이거 좋은데요?",
        "헐 진짜요?",
        "잘 보고 갑니다 감사합니다",
        "구독하고갑니다",
        "1빠!",
        "ㅊㅊ",
    ]
    
    results = filter_engine.filter_batch(korean_comments)
    
    for result in results:
        status = "✓ 통과" if result.is_passed else "✗ 제외"
        reasons = f" ({', '.join(r.value for r in result.reject_reason_codes)})" if not result.is_passed else ""
        print(f"{status}: {result.original_text}{reasons}")
    
    print()


def test_product_review_comments():
    """제품 리뷰 댓글 테스트 (통과해야 함)"""
    print("=" * 80)
    print("테스트 3: 제품 리뷰 댓글 (모두 통과해야 함)")
    print("=" * 80)
    
    filter_engine = RuleBasedFilter()
    
    review_comments = [
        "발열 관리가 아쉽지만 전반적인 성능은 만족스럽습니다.",
        "배터리가 생각보다 빨리 닳네요. 하루 종일 쓰기엔 부족해요.",
        "카메라 성능은 좋은데 야간 촬영이 조금 아쉽습니다.",
        "가격 대비 성능은 괜찮아요. 근데 소음이 좀 있어요.",
        "디자인은 예쁜데 무게가 좀 무겁네요. 들고 다니기 힘들어요.",
        "화면이 정말 선명하고 좋아요! 다만 밝기 조절이 좀 민감해요.",
        "충전이 빠른 건 좋은데 발열이 심해서 걱정됩니다.",
        "소프트웨어 최적화가 잘 되어있어서 게임이 부드럽게 돌아가요.",
    ]
    
    results = filter_engine.filter_batch(review_comments)
    
    all_passed = all(r.is_passed for r in results)
    
    for result in results:
        status = "✓" if result.is_passed else "✗"
        print(f"{status} {result.original_text}")
        if not result.is_passed:
            print(f"  경고: 제품 리뷰가 제외됨! {result.reject_reason_codes}")
    
    print(f"\n{'=' * 80}")
    if all_passed:
        print("✓ 성공: 모든 제품 리뷰 댓글이 통과했습니다!")
    else:
        print("✗ 실패: 일부 제품 리뷰 댓글이 제외되었습니다.")
    print(f"{'=' * 80}\n")


def test_duplicate_detection():
    """중복 댓글 탐지 테스트"""
    print("=" * 80)
    print("테스트 4: 중복 댓글 탐지")
    print("=" * 80)
    
    filter_engine = RuleBasedFilter()
    
    duplicate_comments = [
        "이 제품 정말 좋아요",
        "이 제품 정말 좋아요",  # 중복
        "이제품정말좋아요",      # 공백만 다름 (중복)
        "이 제품 정말 좋네요",   # 약간 다름 (중복 아님)
    ]
    
    results = filter_engine.filter_batch(duplicate_comments)
    
    for result in results:
        status = "✓ 통과" if result.is_passed else "✗ 제외"
        reasons = ""
        if RejectReason.DUPLICATE_CANDIDATE in result.reject_reason_codes:
            reasons = " (중복 감지)"
        print(f"{status}: {result.original_text}{reasons}")
    
    print()


def test_custom_config():
    """커스텀 설정 테스트"""
    print("=" * 80)
    print("테스트 5: 커스텀 설정")
    print("=" * 80)
    
    # 엄격한 설정
    strict_config = RuleConfig(
        min_length=10,              # 최소 10글자
        max_emoji_ratio=0.3,        # 이모지 30% 이하
        max_repeated_char_ratio=0.3, # 반복 30% 이하
        version="1.0-strict"
    )
    
    strict_filter = RuleBasedFilter(config=strict_config)
    
    test_comments = [
        "좋아요",          # TOO_SHORT (10글자 미만)
        "이거 좋네요😊😊",  # EMOJI_HEAVY (엄격한 기준)
        "ㅋㅋㅋ 재미있어요",  # LOW_INFORMATION (반복 많음)
    ]
    
    results = strict_filter.filter_batch(test_comments)
    
    print(f"설정: {strict_config.version}")
    print(f"  - 최소 길이: {strict_config.min_length}글자")
    print(f"  - 최대 이모지 비율: {strict_config.max_emoji_ratio}")
    print(f"  - 최대 반복 문자 비율: {strict_config.max_repeated_char_ratio}\n")
    
    for result in results:
        status = "✓ 통과" if result.is_passed else "✗ 제외"
        reasons = f" ({', '.join(r.value for r in result.reject_reason_codes)})" if not result.is_passed else ""
        print(f"{status}: {result.original_text}{reasons}")
    
    print()


def test_filter_stats():
    """필터 통계 테스트"""
    print("=" * 80)
    print("테스트 6: 필터 통계")
    print("=" * 80)
    
    filter_engine = RuleBasedFilter()
    
    stats = filter_engine.get_stats()
    print(f"버전: {stats['version']}")
    print(f"설명: {stats['description']}")
    print(f"총 규칙 수: {stats['total_rules']}")
    print(f"욕설 사전 단어 수: {stats['profanity_words_count']}")
    print(f"중복 캐시 크기: {stats['duplicate_cache_size']}")
    print(f"\n설정:")
    for key, value in stats['config'].items():
        print(f"  - {key}: {value}")
    
    print()


def test_to_dict():
    """딕셔너리 변환 테스트"""
    print("=" * 80)
    print("테스트 7: JSON 출력 (DB 저장용)")
    print("=" * 80)
    
    filter_engine = RuleBasedFilter()
    
    test_comment = "발열은 있지만 성능은 훌륭합니다."
    result = filter_engine.filter_single(test_comment)
    
    result_dict = result.to_dict()
    
    print("FilterResult → Dict 변환:")
    import json
    print(json.dumps(result_dict, ensure_ascii=False, indent=2))
    
    print()


def run_all_tests():
    """모든 테스트 실행"""
    test_basic_filtering()
    test_korean_patterns()
    test_product_review_comments()
    test_duplicate_detection()
    test_custom_config()
    test_filter_stats()
    test_to_dict()
    
    print("=" * 80)
    print("✓ 모든 테스트 완료!")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
