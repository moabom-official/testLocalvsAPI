"""
보고서 생성기 사용 예시
"""
import sys
from pathlib import Path
from datetime import datetime

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from comment_filtering_agent.services.report_generator import (
    ReportGenerator, ReportConfig
)
from comment_filtering_agent.services.report_models import (
    ReportData, ReportMetadata, CommentStatistics, SentimentDistribution,
    AspectMention, RepresentativeComment, QuestionTopic, ProductInsight,
    SentimentType
)


def example_1_basic_usage():
    """예시 1: 기본 사용법"""
    print("="*60)
    print("Example 1: Basic Usage")
    print("="*60)
    
    # Mock 파이프라인 결과
    pipeline_results = {
        'statistics': {
            'collected': 1247,
            'rule_filter': {'rejected': 423},
            'classified': 824,
            'agent_decisions': {
                'ANALYZE': 687,
                'AUXILIARY_STORE': 137,
                'EXCLUDE': 0,
                'HOLD': 0,
                'RECLASSIFY': 0
            }
        },
        'sentiments': [
            {'sentiment': 'positive'} for _ in range(412)
        ] + [
            {'sentiment': 'neutral'} for _ in range(189)
        ] + [
            {'sentiment': 'negative'} for _ in range(86)
        ],
        'aspects': [],
        'analyzed_comments': [],
        'questions': []
    }
    
    generator = ReportGenerator()
    
    report = generator.generate_report(
        video_id="abc123",
        pipeline_results=pipeline_results,
        video_title="갤럭시 S25 Ultra 리뷰",
        product_name="갤럭시 S25 Ultra"
    )
    
    print(f"Generated report for: {report.metadata.product_name}")
    print(f"Sentiment score: {report.overall_sentiment.sentiment_score:+.1f}")
    print(f"Analysis rate: {report.statistics.analysis_rate:.1f}%")
    print()


def example_2_custom_config():
    """예시 2: 커스텀 설정"""
    print("="*60)
    print("Example 2: Custom Config")
    print("="*60)
    
    config = ReportConfig(
        top_aspects_count=15,  # 상위 15개 항목
        representative_comments_count=10,  # 대표 댓글 10개
        min_aspect_mentions=3,  # 최소 3회 언급
        output_dir="custom_reports"
    )
    
    print(f"Top aspects: {config.top_aspects_count}")
    print(f"Representative comments: {config.representative_comments_count}")
    print(f"Min mentions: {config.min_aspect_mentions}")
    print(f"Output dir: {config.output_dir}")
    print()


def example_3_aspect_analysis():
    """예시 3: Aspect 분석"""
    print("="*60)
    print("Example 3: Aspect Analysis")
    print("="*60)
    
    aspects = [
        AspectMention("카메라", 247, 198, 32, 17),
        AspectMention("성능", 231, 187, 28, 16),
        AspectMention("발열", 156, 42, 37, 77),
        AspectMention("가격", 98, 23, 14, 61)
    ]
    
    print("Aspect Analysis:")
    print(f"{'항목':<10} {'언급':<6} {'긍정':<6} {'부정':<6} {'스코어':<8} {'감정'}")
    print("-" * 60)
    
    for aspect in aspects:
        score = aspect.sentiment_distribution.sentiment_score
        sentiment = aspect.dominant_sentiment.value
        
        print(
            f"{aspect.aspect:<10} "
            f"{aspect.total_mentions:<6} "
            f"{aspect.positive_count:<6} "
            f"{aspect.negative_count:<6} "
            f"{score:+6.0f}   "
            f"{sentiment}"
        )
    
    print()


def example_4_representative_comments():
    """예시 4: 대표 댓글 추출"""
    print("="*60)
    print("Example 4: Representative Comments")
    print("="*60)
    
    positive_comments = [
        RepresentativeComment(
            "c1",
            "카메라 진짜 미쳤네요. 야간 촬영 최고",
            SentimentType.POSITIVE,
            ["카메라"],
            342
        ),
        RepresentativeComment(
            "c2",
            "성능 체감됩니다. 끊김 없음",
            SentimentType.POSITIVE,
            ["성능"],
            231
        )
    ]
    
    negative_comments = [
        RepresentativeComment(
            "c3",
            "가격이 너무 비싸요",
            SentimentType.NEGATIVE,
            ["가격"],
            412
        ),
        RepresentativeComment(
            "c4",
            "게임 하면 발열 심함",
            SentimentType.NEGATIVE,
            ["발열"],
            267
        )
    ]
    
    print("Top Positive Comments:")
    for i, comment in enumerate(positive_comments, 1):
        print(f"{i}. {comment.text} (👍 {comment.like_count})")
    
    print("\nTop Negative Comments:")
    for i, comment in enumerate(negative_comments, 1):
        print(f"{i}. {comment.text} (👍 {comment.like_count})")
    
    print()


def example_5_question_topics():
    """예시 5: 질문 주제 분석"""
    print("="*60)
    print("Example 5: Question Topics")
    print("="*60)
    
    topics = [
        QuestionTopic("게임", 87, [
            "원신 최고옵 돌아가나요?",
            "롤 모바일 120fps 되나요?",
            "배그 발열 어떤가요?"
        ]),
        QuestionTopic("가격", 52, [
            "공시지원금 포함 얼마예요?",
            "중고가 잘 유지되나요?"
        ]),
        QuestionTopic("카메라", 43, [
            "아이폰이랑 비교하면?",
            "망원 줌 몇 배까지?"
        ])
    ]
    
    print("Top Question Topics:")
    for topic in topics:
        print(f"\n{topic.category} ({topic.count}개 질문):")
        for example in topic.examples:
            print(f"  - {example}")
    
    print()


def example_6_insight_generation():
    """예시 6: 인사이트 생성"""
    print("="*60)
    print("Example 6: Insight Generation")
    print("="*60)
    
    insight = ProductInsight(
        strengths=[
            "카메라 (198개 긍정)",
            "성능 (187개 긍정)",
            "디스플레이 (156개 긍정)"
        ],
        weaknesses=[
            "가격 (61개 부정)",
            "발열 (77개 부정)",
            "소음 (24개 부정)"
        ],
        neutral_points=[
            "배터리 (의견 분분)"
        ],
        user_concerns=[
            "게임 (87개 질문)",
            "가격 (52개 질문)",
            "카메라 (43개 질문)"
        ],
        summary="전반적으로 긍정적인 반응. 주요 강점은 카메라. 주요 약점은 가격. 사용자들은 특히 게임에 관심."
    )
    
    print("Product Insight:")
    print(f"\nSummary: {insight.summary}")
    
    print("\nStrengths:")
    for s in insight.strengths:
        print(f"  ✅ {s}")
    
    print("\nWeaknesses:")
    for w in insight.weaknesses:
        print(f"  ❌ {w}")
    
    print("\nUser Concerns:")
    for c in insight.user_concerns:
        print(f"  🤔 {c}")
    
    print()


def example_7_save_reports():
    """예시 7: 보고서 저장"""
    print("="*60)
    print("Example 7: Save Reports")
    print("="*60)
    
    # Mock 보고서 데이터
    report = ReportData(
        metadata=ReportMetadata(
            video_id="abc123",
            video_title="갤럭시 S25 Ultra 리뷰",
            product_name="갤럭시 S25 Ultra"
        ),
        statistics=CommentStatistics(
            total_collected=1247,
            rule_filter_rejected=423,
            llm_classified=824,
            analyzed_count=687,
            auxiliary_count=137,
            excluded_count=0,
            hold_count=0,
            reclassify_count=0
        ),
        overall_sentiment=SentimentDistribution(412, 189, 86),
        aspect_mentions=[],
        representative_positive=[],
        representative_negative=[],
        question_topics=[],
        insight=ProductInsight([], [], [], [], "Good product")
    )
    
    generator = ReportGenerator()
    
    # Markdown 저장
    md_path = generator.save_markdown(report)
    print(f"Markdown saved: {md_path}")
    
    # JSON 저장
    json_path = generator.save_json(report)
    print(f"JSON saved: {json_path}")
    
    print()


def example_8_json_export():
    """예시 8: JSON 내보내기"""
    print("="*60)
    print("Example 8: JSON Export")
    print("="*60)
    
    report = ReportData(
        metadata=ReportMetadata(
            video_id="abc123",
            product_name="Test Product"
        ),
        statistics=CommentStatistics(
            total_collected=100,
            rule_filter_rejected=30,
            llm_classified=70,
            analyzed_count=60,
            auxiliary_count=10,
            excluded_count=0,
            hold_count=0,
            reclassify_count=0
        ),
        overall_sentiment=SentimentDistribution(40, 15, 5),
        aspect_mentions=[
            AspectMention("카메라", 25, 20, 3, 2)
        ],
        representative_positive=[],
        representative_negative=[],
        question_topics=[],
        insight=ProductInsight(["카메라"], ["가격"], [], [], "Good")
    )
    
    # Dictionary로 변환
    data_dict = report.to_dict()
    
    print("Exported JSON structure:")
    print(f"  - video_id: {data_dict['metadata']['video_id']}")
    print(f"  - sentiment_score: {data_dict['overall_sentiment']['sentiment_score']}")
    print(f"  - aspect_count: {len(data_dict['aspect_analysis'])}")
    print(f"  - strengths: {data_dict['insight']['strengths']}")
    
    # JSON 문자열로 변환
    json_str = report.to_json()
    print(f"\nJSON string length: {len(json_str)} chars")
    print()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("REPORT GENERATOR EXAMPLES")
    print("="*60 + "\n")
    
    example_1_basic_usage()
    example_2_custom_config()
    example_3_aspect_analysis()
    example_4_representative_comments()
    example_5_question_topics()
    example_6_insight_generation()
    example_7_save_reports()
    example_8_json_export()
    
    print("="*60)
    print("ALL EXAMPLES COMPLETED")
    print("="*60)
