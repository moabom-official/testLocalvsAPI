"""
1차 규칙 기반 필터 - 사용 예시

실제 프로젝트에서 사용하는 방법을 보여줍니다.
"""
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
from comment_filtering_agent.filters.models import RuleConfig, RejectReason


def example_basic_usage():
    """예시 1: 기본 사용법"""
    print("=" * 80)
    print("예시 1: 기본 사용법")
    print("=" * 80)
    
    # 필터 생성
    filter_engine = RuleBasedFilter()
    
    # 단일 댓글 필터링
    comment = "발열은 심한데 성능은 좋네요"
    result = filter_engine.filter_single(comment)
    
    print(f"원본: {result.original_text}")
    print(f"통과: {result.is_passed}")
    print(f"정제된 텍스트: {result.cleaned_text}")
    print(f"제외 사유: {result.reject_reason_codes}")
    print()


def example_batch_processing():
    """예시 2: 배치 처리"""
    print("=" * 80)
    print("예시 2: 배치 처리 (YouTube 댓글 수집 후)")
    print("=" * 80)
    
    # YouTube에서 수집한 댓글이라고 가정
    youtube_comments = [
        "발열은 심한데 성능은 좋네요. 게임도 잘 돌아가요.",
        "ㅋㅋㅋㅋㅋ",
        "이거 배터리 얼마나 가나요?",
        "잘 보고 갑니다",
        "가격이 좀 비싸긴 한데 품질은 좋네요",
        "http://bit.ly/sale 최저가!",
        "시발 이거 별로네",
        "😂😂😂😂😂",
    ]
    
    # 필터 생성 및 배치 처리
    filter_engine = RuleBasedFilter()
    results = filter_engine.filter_batch(youtube_comments)
    
    # 통과한 댓글만 추출
    passed_comments = [r for r in results if r.is_passed]
    rejected_comments = [r for r in results if not r.is_passed]
    
    print(f"총 댓글: {len(youtube_comments)}개")
    print(f"통과: {len(passed_comments)}개")
    print(f"제외: {len(rejected_comments)}개\n")
    
    print("통과한 댓글 (2차 LLM 분류로 전달):")
    for r in passed_comments:
        print(f"  ✓ {r.original_text}")
    
    print("\n제외된 댓글:")
    for r in rejected_comments:
        reasons = ", ".join(reason.value for reason in r.reject_reason_codes)
        print(f"  ✗ {r.original_text[:30]}... ({reasons})")
    
    print()


def example_database_integration():
    """예시 3: DB 연동 (PostgreSQL)"""
    print("=" * 80)
    print("예시 3: DB 연동 예시 (의사 코드)")
    print("=" * 80)
    
    print("""
# PostgreSQL 연동 예시 (psycopg2 사용)

import psycopg2
from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter

# DB 연결
conn = psycopg2.connect(
    host="localhost",
    database="youtube_analysis",
    user="postgres",
    password="password"
)
cursor = conn.cursor()

# 필터 생성
filter_engine = RuleBasedFilter()

# raw_comments 테이블에서 미처리 댓글 가져오기
cursor.execute('''
    SELECT comment_id, text_original
    FROM raw_comments
    WHERE comment_id NOT IN (
        SELECT comment_id FROM rule_filter_results
    )
    LIMIT 1000
''')

comments = cursor.fetchall()

# 배치 필터링
texts = [c[1] for c in comments]
results = filter_engine.filter_batch(texts)

# rule_filter_results 테이블에 저장
for (comment_id, _), result in zip(comments, results):
    cursor.execute('''
        INSERT INTO rule_filter_results (
            comment_id,
            filter_status,
            rejected_by_rule,
            reject_reason,
            rule_version_id,
            filter_metadata
        ) VALUES (%s, %s, %s, %s, %s, %s)
    ''', (
        comment_id,
        'PASS' if result.is_passed else 'REJECT',
        result.matched_rules[0] if result.matched_rules else None,
        ', '.join(r.value for r in result.reject_reason_codes),
        1,  # rule_version_id (filter_rules_versions 테이블 참조)
        psycopg2.extras.Json(result.metadata)
    ))

conn.commit()
cursor.close()
conn.close()
    """)
    print()


def example_custom_configuration():
    """예시 4: 커스텀 설정"""
    print("=" * 80)
    print("예시 4: 커스텀 설정 (제품별 다른 기준)")
    print("=" * 80)
    
    # 프리미엄 제품: 엄격한 필터
    premium_config = RuleConfig(
        min_length=10,
        max_emoji_ratio=0.3,
        version="1.0-premium"
    )
    
    # 일반 제품: 기본 필터
    standard_config = RuleConfig(
        min_length=5,
        max_emoji_ratio=0.7,
        version="1.0-standard"
    )
    
    premium_filter = RuleBasedFilter(config=premium_config)
    standard_filter = RuleBasedFilter(config=standard_config)
    
    test_comment = "좋네요😊"
    
    premium_result = premium_filter.filter_single(test_comment)
    standard_result = standard_filter.filter_single(test_comment)
    
    print(f"댓글: {test_comment}\n")
    print(f"프리미엄 필터 (엄격): {'통과' if premium_result.is_passed else '제외'}")
    print(f"  사유: {[r.value for r in premium_result.reject_reason_codes]}")
    print(f"\n일반 필터 (관대): {'통과' if standard_result.is_passed else '제외'}")
    print(f"  사유: {[r.value for r in standard_result.reject_reason_codes]}")
    print()


def example_statistics_tracking():
    """예시 5: 통계 추적"""
    print("=" * 80)
    print("예시 5: 필터링 통계 추적")
    print("=" * 80)
    
    filter_engine = RuleBasedFilter()
    
    # 샘플 댓글
    sample_comments = [
        "발열은 있지만 성능은 좋아요",
        "ㅋㅋㅋㅋㅋ",
        "배터리가 빨리 닳네요",
        "잘 보고 갑니다",
        "http://sale.com",
        "시발",
        "가격 대비 괜찮아요",
        "😂😂😂😂😂",
        "카메라 성능 좋네요",
        "1등!",
    ]
    
    results = filter_engine.filter_batch(sample_comments)
    
    # 제외 사유별 통계
    from collections import Counter
    
    all_reasons = []
    for r in results:
        if not r.is_passed:
            all_reasons.extend([reason.value for reason in r.reject_reason_codes])
    
    reason_counts = Counter(all_reasons)
    
    print(f"총 댓글: {len(results)}개")
    print(f"통과: {sum(1 for r in results if r.is_passed)}개")
    print(f"제외: {sum(1 for r in results if not r.is_passed)}개\n")
    
    print("제외 사유별 통계:")
    for reason, count in reason_counts.most_common():
        print(f"  - {reason}: {count}개")
    
    print()


def example_pipeline_integration():
    """예시 6: 전체 파이프라인 통합"""
    print("=" * 80)
    print("예시 6: 전체 파이프라인 통합")
    print("=" * 80)
    
    print("""
전체 파이프라인 흐름:

1. YouTube 댓글 수집
   ↓
2. 1차 규칙 필터 (RuleBasedFilter) ← 현재 단계
   ↓
3. 2차 LLM 분류 (LLMClassifier)
   ↓
4. Agent 결정 (CommentFilteringAgent)
   ↓
5. 분석 (SentimentAnalyzer, AspectExtractor)
   ↓
6. 보고서 생성

코드 예시:

from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
from comment_filtering_agent.classifiers.llm_classifier import LLMClassifier
from comment_filtering_agent.core.agent import CommentFilteringAgent

# 1. 1차 필터
rule_filter = RuleBasedFilter()
rule_results = rule_filter.filter_batch(raw_comments)

# 2. 통과한 댓글만 2차 분류로
passed_comments = [r.cleaned_text for r in rule_results if r.is_passed]

# 3. LLM 분류 (2차)
llm_classifier = LLMClassifier()
llm_results = llm_classifier.classify_batch(passed_comments)

# 4. Agent 최종 결정
agent = CommentFilteringAgent()
final_decisions = agent.decide_batch(rule_results, llm_results)

# 5. 분석 대상만 추출
analyze_comments = [
    d for d in final_decisions 
    if d.final_action == "ANALYZE"
]

# 6. 감정/항목 분석
# ...
    """)
    print()


def run_all_examples():
    """모든 예시 실행"""
    example_basic_usage()
    example_batch_processing()
    example_database_integration()
    example_custom_configuration()
    example_statistics_tracking()
    example_pipeline_integration()
    
    print("=" * 80)
    print("✓ 모든 예시 완료!")
    print("=" * 80)


if __name__ == "__main__":
    run_all_examples()
