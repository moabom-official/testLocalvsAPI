# -*- coding: utf-8 -*-
"""
Full Pipeline Test with Real YouTube API and Groq LLM
"""
import sys
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv

# Load .env file first (override existing environment variables)
load_dotenv(override=True)

sys.path.insert(0, str(Path(__file__).parent))

print("\n" + "="*80)
print("FULL PIPELINE TEST - REAL YOUTUBE API + GROQ LLM")
print("="*80)
print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Check API keys
youtube_key = os.getenv('YOUTUBE_API_KEY')
groq_key = os.getenv('GROQ_API_KEY')
print(f"YouTube API: {'SET' if youtube_key else 'NOT SET'}")
print(f"Groq API:    {'SET' if groq_key else 'NOT SET'}")
print()

# Import all
from comment_filtering_agent.services.comment_collector import YouTubeCommentCollector
from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter
from comment_filtering_agent.classifiers.groq_classifier import GroqClassifier as GroqCommentClassifier
from comment_filtering_agent.core.agent import AgentDecisionEngine
from comment_filtering_agent.analyzers.groq_analyzer import GroqAspectSentimentAnalyzer

# Step 1: Collect
print("[1/6] Collecting from YouTube API...")
collector = YouTubeCommentCollector()
comments = collector.collect_comments("i5lQYSjw2hc", max_results=50)
print(f"      Collected: {len(comments)} comments")

# Step 2: Rule Filter
print("\n[2/6] Rule-based filtering...")
rule_filter = RuleBasedFilter()
passed_comments = []
rejected_count = 0
for c in comments:
    result = rule_filter.filter_single(c.text_original)
    if result.is_passed:
        passed_comments.append({'comment': c, 'filter_result': result})
    else:
        rejected_count += 1
print(f"      Passed: {len(passed_comments)}/{len(comments)}")
print(f"      Rejected: {rejected_count} ({rejected_count/len(comments)*100:.1f}%)")

# Step 3: LLM Classification (REAL GROQ - BATCH MODE)
print("\n[3/6] LLM classification (REAL GROQ - BATCH)...")
if groq_key:
    classifier = GroqCommentClassifier()
    classified_comments = []
    batch_size = 10
    
    total = len(passed_comments)
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_items = passed_comments[batch_start:batch_end]
        batch_comments = [item['comment'].text_original for item in batch_items]
        
        print(f"      Batch {batch_start//batch_size + 1}/{(total + batch_size - 1)//batch_size} ({batch_start+1}-{batch_end}/{total})...")
        
        # 배치 분류
        batch_results = classifier.classify_batch(batch_comments, start_index=batch_start)
        
        # 결과 저장
        for i, result in enumerate(batch_results):
            classified_comments.append({
                'comment': batch_items[i]['comment'],
                'filter_result': batch_items[i]['filter_result'],
                'classification': result
            })
    
    print(f"      Classified: {len(classified_comments)} (REAL LLM - BATCH)")
    
    # Label distribution
    label_counts = {}
    for item in classified_comments:
        label = item['classification'].label.value
        label_counts[label] = label_counts.get(label, 0) + 1
    print(f"      Distribution:")
    for label, count in sorted(label_counts.items(), key=lambda x: -x[1])[:3]:
        print(f"        {label}: {count}")
else:
    print("      ERROR: Groq API key not set!")
    sys.exit(1)

# Step 4: Agent Decision
print("\n[4/6] Agent decision engine...")
agent = AgentDecisionEngine()
agent_decisions = []

for item in classified_comments:
    decision = agent.decide(
        item['comment'].text_original,
        item['filter_result'],
        item['classification']
    )
    agent_decisions.append({
        'comment': item['comment'],
        'filter_result': item['filter_result'],
        'classification': item['classification'],
        'decision': decision
    })

print(f"      Decisions: {len(agent_decisions)}")

# Action distribution
action_counts = {}
for item in agent_decisions:
    action = item['decision'].final_action.value
    action_counts[action] = action_counts.get(action, 0) + 1
print(f"      Actions:")
for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
    print(f"        {action}: {count}")

# Step 5: Sentiment Analysis (REAL GROQ)
print("\n[5/6] Sentiment analysis (REAL GROQ)...")
analyze_items = [item for item in agent_decisions 
                 if item['decision'].final_action.value == 'ANALYZE']

if groq_key and analyze_items:
    analyzer = GroqAspectSentimentAnalyzer()
    sentiment_results = []
    
    for idx, item in enumerate(analyze_items):
        print(f"      Analyzing {idx+1}/{len(analyze_items)}...", end='\r')
        result = analyzer.analyze(item['comment'].text_original)
        sentiment_results.append(result)
    
    print(f"      Analyzed: {len(sentiment_results)} comments (REAL LLM)")
    
    # Show sentiment distribution
    sentiment_counts = {'positive': 0, 'neutral': 0, 'negative': 0}
    for result in sentiment_results:
        sentiment_counts[result.overall_sentiment.value] += 1
    print(f"      Sentiment:")
    for sent, count in sentiment_counts.items():
        if count > 0:
            print(f"        {sent}: {count}")
else:
    print(f"      Analyzed: 0 comments (no ANALYZE actions or no Groq key)")

# Step 6: Report
print("\n[6/6] Generating report...")
from comment_filtering_agent.services.report_models import (
    ReportData, ReportMetadata, CommentStatistics,
    SentimentDistribution, ProductInsight
)

report = ReportData(
    metadata=ReportMetadata(video_id="i5lQYSjw2hc"),
    statistics=CommentStatistics(
        total_collected=len(comments),
        rule_filter_rejected=rejected_count,
        llm_classified=len(classified_comments),
        analyzed_count=len(analyze_items),
        auxiliary_count=action_counts.get('AUXILIARY_STORE', 0),
        excluded_count=action_counts.get('EXCLUDE', 0),
        hold_count=action_counts.get('HOLD', 0),
        reclassify_count=action_counts.get('RECLASSIFY', 0)
    ),
    overall_sentiment=SentimentDistribution(
        positive_count=sentiment_counts.get('positive', 0) if analyze_items else 0,
        neutral_count=sentiment_counts.get('neutral', 0) if analyze_items else 0,
        negative_count=sentiment_counts.get('negative', 0) if analyze_items else 0
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
        summary="Real pipeline with Groq LLM completed successfully"
    )
)

print(f"      Report generated")
print(f"      Sentiment score: {report.overall_sentiment.sentiment_score:+.1f}")

# Final Summary
print("\n" + "="*80)
print("PIPELINE COMPLETED SUCCESSFULLY")
print("="*80)
print(f"\nFlow:")
print(f"  Collect:  {len(comments)}")
print(f"  Filter:   {len(passed_comments)} (rejected {rejected_count})")
print(f"  Classify: {len(classified_comments)} (REAL GROQ LLM)")
print(f"  Agent:    {len(agent_decisions)}")
print(f"  Analyze:  {len(analyze_items)} (REAL GROQ LLM)")
print(f"  Report:   Generated")
print(f"\nFinal: {len(comments)} -> {len(passed_comments)} -> {len(classified_comments)} -> {len(agent_decisions)} -> {len(analyze_items)}")
print("\nStatus: SUCCESS with REAL LLM")
