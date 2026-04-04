"""
보고서 생성기 테스트
"""
import sys
from pathlib import Path

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


def test_sentiment_distribution():
    """감정 분포 계산 테스트"""
    print("="*60)
    print("Test 1: Sentiment Distribution")
    print("="*60)
    
    dist = SentimentDistribution(
        positive_count=412,
        neutral_count=189,
        negative_count=86
    )
    
    print(f"Total: {dist.total}")
    print(f"Positive Ratio: {dist.positive_ratio:.1f}%")
    print(f"Neutral Ratio: {dist.neutral_ratio:.1f}%")
    print(f"Negative Ratio: {dist.negative_ratio:.1f}%")
    print(f"Sentiment Score: {dist.sentiment_score:+.1f}")
    
    assert dist.total == 687
    assert abs(dist.positive_ratio - 60.0) < 0.1
    assert abs(dist.sentiment_score - 47.45) < 0.1
    print("✓ PASSED\n")


def test_aspect_mention():
    """Aspect 언급 테스트"""
    print("="*60)
    print("Test 2: Aspect Mention")
    print("="*60)
    
    aspect = AspectMention(
        aspect="발열",
        total_mentions=156,
        positive_count=42,
        neutral_count=37,
        negative_count=77
    )
    
    print(f"Aspect: {aspect.aspect}")
    print(f"Total Mentions: {aspect.total_mentions}")
    print(f"Dominant Sentiment: {aspect.dominant_sentiment.value}")
    print(f"Score: {aspect.sentiment_distribution.sentiment_score:+.1f}")
    
    assert aspect.dominant_sentiment == SentimentType.NEGATIVE
    assert aspect.sentiment_distribution.sentiment_score < 0
    print("✓ PASSED\n")


def test_comment_statistics():
    """댓글 통계 테스트"""
    print("="*60)
    print("Test 3: Comment Statistics")
    print("="*60)
    
    stats = CommentStatistics(
        total_collected=1247,
        rule_filter_rejected=423,
        llm_classified=824,
        analyzed_count=687,
        auxiliary_count=137,
        excluded_count=0,
        hold_count=0,
        reclassify_count=0
    )
    
    print(f"Total Collected: {stats.total_collected}")
    print(f"Analyzed: {stats.analyzed_count}")
    print(f"Exclusion Rate: {stats.exclusion_rate:.1f}%")
    print(f"Analysis Rate: {stats.analysis_rate:.1f}%")
    
    assert stats.exclusion_rate > 30
    assert stats.analysis_rate > 50
    print("✓ PASSED\n")


def test_report_data_to_dict():
    """ReportData JSON 변환 테스트"""
    print("="*60)
    print("Test 4: ReportData to Dict")
    print("="*60)
    
    from datetime import datetime
    
    metadata = ReportMetadata(
        video_id="test123",
        video_title="Test Video",
        product_name="Test Product"
    )
    
    statistics = CommentStatistics(
        total_collected=100,
        rule_filter_rejected=30,
        llm_classified=70,
        analyzed_count=60,
        auxiliary_count=10,
        excluded_count=0,
        hold_count=0,
        reclassify_count=0
    )
    
    sentiment = SentimentDistribution(
        positive_count=40,
        neutral_count=15,
        negative_count=5
    )
    
    aspects = [
        AspectMention("카메라", 25, 20, 3, 2),
        AspectMention("성능", 20, 18, 1, 1)
    ]
    
    insight = ProductInsight(
        strengths=["카메라", "성능"],
        weaknesses=["가격"],
        neutral_points=[],
        user_concerns=["게임"],
        summary="Good product"
    )
    
    report = ReportData(
        metadata=metadata,
        statistics=statistics,
        overall_sentiment=sentiment,
        aspect_mentions=aspects,
        representative_positive=[],
        representative_negative=[],
        question_topics=[],
        insight=insight
    )
    
    data_dict = report.to_dict()
    
    print(f"Video ID: {data_dict['metadata']['video_id']}")
    print(f"Sentiment Score: {data_dict['overall_sentiment']['sentiment_score']}")
    print(f"Aspect Count: {len(data_dict['aspect_analysis'])}")
    
    assert data_dict['metadata']['video_id'] == 'test123'
    assert data_dict['overall_sentiment']['sentiment_score'] > 0
    print("✓ PASSED\n")


def test_report_generator_mock():
    """보고서 생성기 Mock 테스트"""
    print("="*60)
    print("Test 5: Report Generator (Mock Data)")
    print("="*60)
    
    # Mock 파이프라인 결과
    mock_results = {
        'statistics': {
            'collected': 100,
            'rule_filter': {'rejected': 30},
            'classified': 70,
            'agent_decisions': {
                'ANALYZE': 60,
                'AUXILIARY_STORE': 10,
                'EXCLUDE': 0,
                'HOLD': 0,
                'RECLASSIFY': 0
            }
        },
        'sentiments': [
            {'sentiment': 'positive'} for _ in range(40)
        ] + [
            {'sentiment': 'neutral'} for _ in range(15)
        ] + [
            {'sentiment': 'negative'} for _ in range(5)
        ],
        'aspects': [
            {'aspect': '카메라', 'sentiment': 'positive'} for _ in range(20)
        ] + [
            {'aspect': '성능', 'sentiment': 'positive'} for _ in range(18)
        ] + [
            {'aspect': '발열', 'sentiment': 'negative'} for _ in range(10)
        ],
        'analyzed_comments': [
            {
                'comment_id': 'c1',
                'text': '카메라 진짜 좋네요',
                'overall_sentiment': 'positive',
                'aspects': ['카메라'],
                'like_count': 100
            },
            {
                'comment_id': 'c2',
                'text': '발열이 심합니다',
                'overall_sentiment': 'negative',
                'aspects': ['발열'],
                'like_count': 50
            }
        ],
        'questions': [
            {'categories': ['게임'], 'question_text': '게임 돌아가나요?'},
            {'categories': ['게임'], 'question_text': '롤 되나요?'},
            {'categories': ['가격'], 'question_text': '가격 얼마예요?'}
        ]
    }
    
    config = ReportConfig(
        top_aspects_count=5,
        representative_comments_count=3
    )
    
    generator = ReportGenerator(config)
    
    report = generator.generate_report(
        video_id="test123",
        pipeline_results=mock_results,
        video_title="Test Video",
        product_name="Test Product"
    )
    
    print(f"Video ID: {report.metadata.video_id}")
    print(f"Total Collected: {report.statistics.total_collected}")
    print(f"Sentiment Score: {report.overall_sentiment.sentiment_score:+.1f}")
    print(f"Aspects Count: {len(report.aspect_mentions)}")
    print(f"Top Aspect: {report.aspect_mentions[0].aspect if report.aspect_mentions else 'None'}")
    
    assert report.metadata.video_id == 'test123'
    assert report.statistics.total_collected == 100
    assert report.overall_sentiment.sentiment_score > 0
    print("✓ PASSED\n")


def test_markdown_generation():
    """Markdown 생성 테스트"""
    print("="*60)
    print("Test 6: Markdown Generation")
    print("="*60)
    
    from datetime import datetime
    
    # 간단한 보고서 데이터
    report = ReportData(
        metadata=ReportMetadata(
            video_id="test123",
            video_title="Test Video",
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
        representative_positive=[
            RepresentativeComment("c1", "좋아요", SentimentType.POSITIVE, ["카메라"], 10)
        ],
        representative_negative=[],
        question_topics=[
            QuestionTopic("게임", 5, ["게임 되나요?"])
        ],
        insight=ProductInsight(
            strengths=["카메라"],
            weaknesses=["가격"],
            neutral_points=[],
            user_concerns=["게임"],
            summary="Good"
        )
    )
    
    generator = ReportGenerator()
    markdown = generator._generate_markdown(report)
    
    print(f"Markdown Length: {len(markdown)} chars")
    print("\n--- Preview ---")
    print(markdown[:300])
    print("...")
    
    assert "제품 리뷰 댓글 분석 보고서" in markdown
    assert "test123" in markdown
    assert "카메라" in markdown
    print("✓ PASSED\n")


def test_save_reports():
    """보고서 저장 테스트"""
    print("="*60)
    print("Test 7: Save Reports")
    print("="*60)
    
    from datetime import datetime
    import tempfile
    import json
    
    # 임시 디렉토리
    temp_dir = Path(tempfile.mkdtemp())
    
    report = ReportData(
        metadata=ReportMetadata(
            video_id="test123",
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
        aspect_mentions=[],
        representative_positive=[],
        representative_negative=[],
        question_topics=[],
        insight=ProductInsight([], [], [], [], "Test")
    )
    
    config = ReportConfig(output_dir=str(temp_dir))
    generator = ReportGenerator(config)
    
    # Markdown 저장
    md_path = generator.save_markdown(report)
    print(f"Markdown saved: {md_path}")
    assert md_path.exists()
    
    # JSON 저장
    json_path = generator.save_json(report)
    print(f"JSON saved: {json_path}")
    assert json_path.exists()
    
    # JSON 검증
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    assert data['metadata']['video_id'] == 'test123'
    print("✓ PASSED\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("REPORT GENERATOR TEST SUITE")
    print("="*60 + "\n")
    
    test_sentiment_distribution()
    test_aspect_mention()
    test_comment_statistics()
    test_report_data_to_dict()
    test_report_generator_mock()
    test_markdown_generation()
    test_save_reports()
    
    print("="*60)
    print("ALL TESTS PASSED ✓")
    print("="*60)
