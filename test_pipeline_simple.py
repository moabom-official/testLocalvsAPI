"""
전체 파이프라인 통합 테스트 (간단 버전)

실행: python test_pipeline_simple.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("="*60)
print("FULL PIPELINE TEST")
print("="*60)

try:
    # Step 1: Collect (REAL API)
    print("\n[1/5] Collecting comments from REAL YouTube API...")
    from comment_filtering_agent.services.comment_collector import YouTubeCommentCollector
    collector = YouTubeCommentCollector()
    # Real video: 아이폰 16 시리즈 리뷰 (545 comments)
    comments = collector.collect_comments("i5lQYSjw2hc", max_results=50)
    print(f"      OK - {len(comments)} comments collected (REAL)")
    print(f"      Example: {comments[0].text_original[:50]}...")
    
    # Step 2: Rule Filter
    print("\n[2/5] Rule-based filtering...")
    from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
    rule_filter = RuleBasedFilter()
    filter_results = [rule_filter.filter_single(c.text_original) for c in comments]
    passed = [c for c, r in zip(comments, filter_results) if r.is_passed]
    print(f"      OK - {len(passed)}/{len(comments)} passed")
    
    # Step 3: LLM Classify (Mock)
    print("\n[3/5] LLM classification (Mock)...")
    from comment_filtering_agent.classifiers.models import (
        ClassificationResult, CommentLabel
    )
    classifications = []
    for i, c in enumerate(passed):
        cls = ClassificationResult(
            index=i,
            original_comment=c.text_original,
            label=CommentLabel.PRODUCT_OPINION,
            confidence=0.9,
            rationale_short="Mock classification",
            needs_recheck=False,
            mentioned_product_features=["camera"],
            is_product_related=True
        )
        classifications.append(cls)
    print(f"      OK - {len(classifications)} classified")
    
    # Step 4: Agent Decision
    print("\n[4/5] Agent decision...")
    from comment_filtering_agent.core.agent import AgentDecisionEngine
    from comment_filtering_agent.filters.models import FilterResult
    agent = AgentDecisionEngine()
    decisions = []
    for i, (c, cls) in enumerate(zip(passed, classifications)):
        fr = FilterResult(
            index=i,
            original_text=c.text_original,
            cleaned_text=c.text_original,
            is_passed=True
        )
        decision = agent.decide(c.text_original, fr, cls)
        decisions.append(decision)
    print(f"      OK - {len(decisions)} decisions")
    
    # Step 5: Report
    print("\n[5/5] Generating report...")
    from comment_filtering_agent.services.report_models import (
        ReportData, ReportMetadata, CommentStatistics,
        SentimentDistribution, ProductInsight
    )
    report = ReportData(
        metadata=ReportMetadata(video_id="test"),
        statistics=CommentStatistics(
            total_collected=len(comments),
            rule_filter_rejected=len(comments)-len(passed),
            llm_classified=len(classifications),
            analyzed_count=len(decisions),
            auxiliary_count=0,
            excluded_count=0,
            hold_count=0,
            reclassify_count=0
        ),
        overall_sentiment=SentimentDistribution(
            positive_count=len(decisions),
            neutral_count=0,
            negative_count=0
        ),
        aspect_mentions=[],
        representative_positive=[],
        representative_negative=[],
        question_topics=[],
        insight=ProductInsight(
            strengths=[],
            weaknesses=[],
            neutral_points=[],
            user_concerns=[],
            summary="Test pipeline complete"
        )
    )
    print(f"      OK - Sentiment score: {report.overall_sentiment.sentiment_score:+.1f}")
    
    # Success
    print("\n" + "="*60)
    print("SUCCESS: ALL 5 STEPS COMPLETED")
    print("="*60)
    print("\nPipeline Flow:")
    print(f"  Collect -> Filter -> Classify -> Agent -> Report")
    print(f"  {len(comments)} -> {len(passed)} -> {len(classifications)} -> {len(decisions)} -> Done")
    print("\nStatus: WORKING")
    
except Exception as e:
    print(f"\n ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
