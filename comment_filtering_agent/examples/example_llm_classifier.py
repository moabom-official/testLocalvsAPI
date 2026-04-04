"""
LLM 댓글 분류기 - 사용 예시

Groq API를 사용한 실제 분류 예시
주의: 실행하려면 GROQ_API_KEY 환경변수 설정 필요
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from comment_filtering_agent.classifiers.groq_classifier import GroqClassifier, create_groq_classifier
from comment_filtering_agent.classifiers.models import ClassificationConfig


def example_basic_usage():
    """예시 1: 기본 사용법"""
    print("=" * 80)
    print("예시 1: 기본 사용법")
    print("=" * 80)
    
    print("""
# Groq 분류기 생성
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier

classifier = create_groq_classifier(
    api_key="your_groq_api_key",  # 또는 환경변수 GROQ_API_KEY 설정
    model="llama-3.3-70b-versatile",
    temperature=0.1
)

# 단일 댓글 분류
comment = "발열은 심한데 성능은 좋네요"
result = classifier.classify_single(
    comment=comment,
    product_name="갤럭시 S25",
    product_category="스마트폰"
)

print(f"라벨: {result.label.value}")
print(f"확신도: {result.confidence}")
print(f"이유: {result.rationale_short}")
print(f"제품 특성: {result.mentioned_product_features}")
    """)
    print()


def example_batch_processing():
    """예시 2: 배치 처리"""
    print("=" * 80)
    print("예시 2: 배치 처리")
    print("=" * 80)
    
    print("""
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier

classifier = create_groq_classifier()

# 1차 필터 통과한 댓글들
comments = [
    "발열은 심한데 성능은 좋네요. 게임도 잘 돌아가요.",
    "배터리가 생각보다 빨리 닳네요",
    "오늘 영상 재밌네요",
    "이거 게임도 잘 돌아가나요?",
    "가격 대비 성능 괜찮은 것 같아요"
]

# 배치 분류
results = classifier.classify_batch(
    comments=comments,
    product_name="MacBook Pro",
    product_category="노트북"
)

# 라벨별 분류
from collections import Counter
label_counts = Counter(r.label.value for r in results)

print(f"총 {len(results)}개 댓글")
for label, count in label_counts.items():
    print(f"  - {label}: {count}개")

# PRODUCT_OPINION만 추출 (감정 분석 대상)
product_opinions = [r for r in results if r.should_analyze]
print(f"\\n감정 분석 대상: {len(product_opinions)}개")
    """)
    print()


def example_database_integration():
    """예시 3: DB 연동"""
    print("=" * 80)
    print("예시 3: DB 연동 (PostgreSQL)")
    print("=" * 80)
    
    print("""
import psycopg2
from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier

conn = psycopg2.connect(...)
cursor = conn.cursor()

# 1단계: 1차 필터 통과한 댓글 가져오기
cursor.execute('''
    SELECT rfr.id, rc.comment_id, rc.text_original
    FROM raw_comments rc
    JOIN rule_filter_results rfr ON rc.comment_id = rfr.comment_id
    WHERE rfr.filter_status = 'PASS'
    AND rc.comment_id NOT IN (
        SELECT comment_id FROM llm_classifications
    )
    LIMIT 100
''')

comments_data = cursor.fetchall()

# 2단계: LLM 분류
classifier = create_groq_classifier()
texts = [c[2] for c in comments_data]
results = classifier.classify_batch(texts, product_name="iPhone 15")

# 3단계: llm_classifications 테이블에 저장
for (rule_filter_result_id, comment_id, _), result in zip(comments_data, results):
    cursor.execute('''
        INSERT INTO llm_classifications (
            comment_id,
            label,
            confidence,
            reasoning,
            classifier_type,
            classifier_version_id,
            model_name,
            prompt_version,
            llm_provider,
            tokens_used,
            latency_ms,
            classification_metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        comment_id,
        result.label.value,
        result.confidence,
        result.rationale_short,
        result.classifier_type.value,
        1,  # classifier_version_id
        result.model_name,
        result.prompt_version,
        result.llm_provider,
        result.tokens_used,
        result.latency_ms,
        psycopg2.extras.Json({
            "needs_recheck": result.needs_recheck,
            "mentioned_product_features": result.mentioned_product_features,
            "is_product_related": result.is_product_related
        })
    ))

conn.commit()
    """)
    print()


def example_low_confidence_handling():
    """예시 4: 저확신 댓글 처리"""
    print("=" * 80)
    print("예시 4: 저확신 댓글 처리")
    print("=" * 80)
    
    print("""
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier

classifier = create_groq_classifier()
results = classifier.classify_batch(comments)

# 저확신 댓글 추출
low_confidence_results = [
    r for r in results 
    if r.is_low_confidence or r.needs_recheck
]

print(f"저확신 댓글: {len(low_confidence_results)}개")

for result in low_confidence_results:
    print(f"\\n댓글: {result.original_comment}")
    print(f"  라벨: {result.label.value}")
    print(f"  확신도: {result.confidence}")
    print(f"  재확인 필요: {result.needs_recheck}")
    print(f"  → Agent가 재판단할 예정")

# reclassification_queue 테이블에 추가
for result in low_confidence_results:
    cursor.execute('''
        INSERT INTO reclassification_queue (
            comment_id,
            original_classification_id,
            reason,
            priority,
            status
        ) VALUES (%s, %s, %s, %s, %s)
    ''', (
        result.comment_id,
        result.classification_id,
        f"Low confidence ({result.confidence})",
        1,  # high priority
        'PENDING'
    ))
    """)
    print()


def example_label_filtering():
    """예시 5: 라벨별 처리"""
    print("=" * 80)
    print("예시 5: 라벨별 처리 전략")
    print("=" * 80)
    
    print("""
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier
from comment_filtering_agent.classifiers.models import CommentLabel

classifier = create_groq_classifier()
results = classifier.classify_batch(comments)

# 라벨별 그룹화
from collections import defaultdict
grouped = defaultdict(list)

for result in results:
    grouped[result.label].append(result)

# 처리 전략
print("라벨별 처리:")

# 1. PRODUCT_OPINION → 감정/항목 분석
product_opinions = grouped[CommentLabel.PRODUCT_OPINION]
print(f"\\n1. PRODUCT_OPINION ({len(product_opinions)}개)")
print("   → 감정 분석 (SentimentAnalyzer)")
print("   → 항목 추출 (AspectExtractor)")

# 2. VIDEO_REACTION → 제외
video_reactions = grouped[CommentLabel.VIDEO_REACTION]
print(f"\\n2. VIDEO_REACTION ({len(video_reactions)}개)")
print("   → excluded_comments_log 저장 (exclusion_reason: VIDEO_REACTION)")

# 3. QUESTION → 보조 데이터 저장
questions = grouped[CommentLabel.QUESTION]
print(f"\\n3. QUESTION ({len(questions)}개)")
print("   → product_questions 테이블 저장")
print("   → FAQ 생성에 활용")

# 4. CHATTER → 제외
chatters = grouped[CommentLabel.CHATTER]
print(f"\\n4. CHATTER ({len(chatters)}개)")
print("   → excluded_comments_log 저장 (exclusion_reason: CHATTER)")

# 5. OFF_TOPIC → 제외
off_topics = grouped[CommentLabel.OFF_TOPIC]
print(f"\\n5. OFF_TOPIC ({len(off_topics)}개)")
print("   → excluded_comments_log 저장 (exclusion_reason: OFF_TOPIC)")
    """)
    print()


def example_statistics():
    """예시 6: 통계 추적"""
    print("=" * 80)
    print("예시 6: 분류 통계 추적")
    print("=" * 80)
    
    print("""
from comment_filtering_agent.classifiers.groq_classifier import create_groq_classifier
from collections import Counter
import statistics

classifier = create_groq_classifier()
results = classifier.classify_batch(comments)

# 라벨 분포
label_counts = Counter(r.label.value for r in results)
print("라벨 분포:")
for label, count in label_counts.most_common():
    percentage = count / len(results) * 100
    print(f"  - {label}: {count}개 ({percentage:.1f}%)")

# 확신도 통계
confidences = [r.confidence for r in results]
print(f"\\n확신도 통계:")
print(f"  - 평균: {statistics.mean(confidences):.2f}")
print(f"  - 중앙값: {statistics.median(confidences):.2f}")
print(f"  - 최소: {min(confidences):.2f}")
print(f"  - 최대: {max(confidences):.2f}")

# 저확신 비율
low_confidence_count = sum(1 for r in results if r.is_low_confidence)
print(f"\\n저확신 댓글: {low_confidence_count}개 ({low_confidence_count/len(results)*100:.1f}%)")

# 제품 특성 언급 빈도
from itertools import chain
all_features = list(chain(*[r.mentioned_product_features for r in results]))
feature_counts = Counter(all_features)
print(f"\\n제품 특성 언급 빈도 (Top 5):")
for feature, count in feature_counts.most_common(5):
    print(f"  - {feature}: {count}회")

# 레이턴시 통계
latencies = [r.latency_ms for r in results if r.latency_ms]
if latencies:
    print(f"\\n레이턴시 통계:")
    print(f"  - 평균: {statistics.mean(latencies):.0f}ms")
    print(f"  - 중앙값: {statistics.median(latencies):.0f}ms")
    """)
    print()


def example_custom_config():
    """예시 7: 커스텀 설정"""
    print("=" * 80)
    print("예시 7: 커스텀 설정 (프리미엄 vs 일반)")
    print("=" * 80)
    
    print("""
from comment_filtering_agent.classifiers.groq_classifier import GroqClassifier
from comment_filtering_agent.classifiers.models import ClassificationConfig

# 프리미엄 제품: 높은 정확도 (예시 포함)
premium_config = ClassificationConfig(
    model_name="llama-3.3-70b-versatile",
    temperature=0.0,
    include_examples=True,
    max_retries=5
)
premium_classifier = GroqClassifier(config=premium_config)

# 일반 제품: 빠른 처리 (예시 없음)
standard_config = ClassificationConfig(
    model_name="llama-3.1-8b-instant",
    temperature=0.2,
    include_examples=False,
    max_retries=2
)
standard_classifier = GroqClassifier(config=standard_config)

# 사용
premium_result = premium_classifier.classify_single("성능 좋아요")
standard_result = standard_classifier.classify_single("성능 좋아요")

print(f"프리미엄 확신도: {premium_result.confidence}")
print(f"일반 확신도: {standard_result.confidence}")
    """)
    print()


def run_all_examples():
    """모든 예시 실행"""
    example_basic_usage()
    example_batch_processing()
    example_database_integration()
    example_low_confidence_handling()
    example_label_filtering()
    example_statistics()
    example_custom_config()
    
    print("=" * 80)
    print("✓ 모든 예시 완료!")
    print("=" * 80)
    print("\n참고: 실제 API 호출은 GROQ_API_KEY 환경변수 설정 후 가능합니다.")


if __name__ == "__main__":
    run_all_examples()
