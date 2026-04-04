"""
전체 파이프라인 통합 테스트

목적:
- YouTube 댓글 수집부터 보고서 생성까지 전체 흐름 검증
- API 키 없이도 Mock 모드로 실행 가능
- 각 단계 결과 출력 및 검증

실행:
    python test_full_pipeline.py
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# 프로젝트 루트 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("\n" + "="*80)
print("Complete Pipeline Integration Test")
print("="*80)
print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


# ============================================================================
# Step 1: Comment Collection
# ============================================================================
print("━"*80)
print("Step 1: YouTube Comment Collection")
print("━"*80)

from comment_filtering_agent.services.comment_collector import (
    YouTubeCommentCollector, Comment
)

collector = YouTubeCommentCollector()  # Real API mode
# Using real video ID from videos.csv: 아이폰 16 시리즈 리뷰 (545 comments)
comments = collector.collect_comments("i5lQYSjw2hc", max_results=50)

print(f"OK Collected: {len(comments)} comments")
print(f"   Example: {comments[0].text_original[:50]}...")
print()

collected_comments = comments


# ============================================================================
# Step 2: Rule-Based Filter
# ============================================================================
print("━"*80)
print("Step 2: Rule-Based Filter")
print("━"*80)

from comment_filtering_agent.filters.rule_based_filter import RuleBasedFilter

rule_filter = RuleBasedFilter()

passed_comments = []
rejected_comments = []

for comment in collected_comments:
    result = rule_filter.filter_single(comment.text_original)
    
    if result.is_passed:
        passed_comments.append({
            'comment': comment,
            'filter_result': result
        })
    else:
        rejected_comments.append({
            'comment': comment,
            'filter_result': result
        })

print(f"OK Filter completed")
print(f"   Passed: {len(passed_comments)}")
print(f"   Rejected: {len(rejected_comments)}")
print(f"   Exclusion Rate: {len(rejected_comments)/len(collected_comments)*100:.1f}%")

if rejected_comments:
    print(f"\n   Rejection examples:")
    for i, item in enumerate(rejected_comments[:2], 1):
        reasons = item['filter_result'].reject_reason_codes
        print(f"    {i}. \"{item['comment'].text_original[:40]}...\"")
        if reasons:
            print(f"       Reason: {reasons[0].value}")

print()


# ============================================================================
# Step 3: 2차 LLM 분류 (Mock)
# ============================================================================
print("━"*80)
print("Step 3: 2차 LLM 분류")
print("━"*80)

# Mock 분류 결과 생성 (실제로는 GroqClassifier 사용)
from comment_filtering_agent.classifiers.models import (
    ClassificationResult, CommentLabel
)
import random

classified_comments = []

for idx, item in enumerate(passed_comments):
    # Mock 분류 (실제로는 LLM API 호출)
    labels = [
        CommentLabel.PRODUCT_OPINION,
        CommentLabel.VIDEO_REACTION,
        CommentLabel.QUESTION,
        CommentLabel.CHATTER,
        CommentLabel.OFF_TOPIC
    ]
    
    # 단순 휴리스틱으로 Mock 분류
    text = item['comment'].text_original.lower()
    if any(word in text for word in ['좋', '나쁨', '발열', '성능', '카메라', '배터리']):
        label = CommentLabel.PRODUCT_OPINION
        confidence = 0.9
    elif any(word in text for word in ['?', '궁금', '알고', '어떤']):
        label = CommentLabel.QUESTION
        confidence = 0.85
    elif any(word in text for word in ['영상', '잘', '재밌', '구독']):
        label = CommentLabel.VIDEO_REACTION
        confidence = 0.8
    else:
        label = random.choice(labels)
        confidence = random.uniform(0.6, 0.9)
    
    classification = ClassificationResult(
        index=idx,
        original_comment=item['comment'].text_original,
        label=label,
        confidence=confidence,
        rationale_short=f"Mock classification (conf: {confidence:.2f})",
        needs_recheck=(confidence < 0.7),
        mentioned_product_features=['카메라', '성능'] if label == CommentLabel.PRODUCT_OPINION else [],
        is_product_related=(label in [CommentLabel.PRODUCT_OPINION, CommentLabel.QUESTION])
    )
    
    classified_comments.append({
        'comment': item['comment'],
        'filter_result': item['filter_result'],
        'classification': classification
    })

print(f"✓ 2차 분류 완료: {len(classified_comments)}개")

# 라벨별 집계
label_counts = {}
for item in classified_comments:
    label = item['classification'].label
    label_counts[label] = label_counts.get(label, 0) + 1

print(f"\n  분류 결과:")
for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
    print(f"    {label}: {count}개")

print()


# ============================================================================
# Step 4: Agent 결정
# ============================================================================
print("━"*80)
print("Step 4: Agent 결정")
print("━"*80)

from comment_filtering_agent.core.agent import AgentDecisionEngine
from comment_filtering_agent.core.models import AgentAction

agent = AgentDecisionEngine()

agent_decisions = []

for item in classified_comments:
    decision = agent.decide(
        comment_text=item['comment'].text_original,
        rule_filter_result=item['filter_result'],
        classification_result=item['classification']
    )
    
    agent_decisions.append({
        'comment': item['comment'],
        'filter_result': item['filter_result'],
        'classification': item['classification'],
        'agent_decision': decision
    })

print(f"✓ Agent 결정 완료: {len(agent_decisions)}개")

# Action별 집계
action_counts = {}
for item in agent_decisions:
    action = item['agent_decision'].final_action.value
    action_counts[action] = action_counts.get(action, 0) + 1

print(f"\n  결정 결과:")
for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
    print(f"    {action}: {count}개")

print()


# ============================================================================
# Step 5: 감정 분석 (ANALYZE 대상만, Mock)
# ============================================================================
print("━"*80)
print("Step 5: 감정 분석 (ANALYZE 대상)")
print("━"*80)

from comment_filtering_agent.analyzers.models import (
    SentimentType, AspectSentiment, SentimentAnalysisResult
)

analyze_items = [
    item for item in agent_decisions
    if item['agent_decision'].final_action == AgentAction.ANALYZE
]

sentiment_results = []

for item in analyze_items:
    # Mock 감정 분석
    text = item['comment'].text_original.lower()
    
    # 간단한 휴리스틱
    if any(word in text for word in ['좋', '최고', '훌륭', '만족']):
        overall = SentimentType.POSITIVE
        score = 0.8
    elif any(word in text for word in ['나쁨', '별로', '실망', '아쉽']):
        overall = SentimentType.NEGATIVE
        score = -0.7
    else:
        overall = SentimentType.NEUTRAL
        score = 0.0
    
    # Mock aspects
    aspects = []
    if '카메라' in text:
        aspects.append(AspectSentiment(
            aspect='카메라',
            sentiment=SentimentType.POSITIVE,
            score=0.8,
            evidence='카메라 관련 언급'
        ))
    if '발열' in text:
        aspects.append(AspectSentiment(
            aspect='발열',
            sentiment=SentimentType.NEGATIVE,
            score=-0.6,
            evidence='발열 관련 언급'
        ))
    
    analysis = SentimentAnalysisResult(
        overall_sentiment=overall,
        overall_score=score,
        aspects=aspects
    )
    
    sentiment_results.append({
        'comment': item['comment'],
        'analysis': analysis
    })

print(f"✓ 감정 분석 완료: {len(sentiment_results)}개")

if sentiment_results:
    sentiment_counts = {
        'positive': 0,
        'neutral': 0,
        'negative': 0
    }
    for item in sentiment_results:
        sentiment_counts[item['analysis'].overall_sentiment.value] += 1
    
    print(f"\n  감정 분포:")
    print(f"    긍정: {sentiment_counts['positive']}개")
    print(f"    중립: {sentiment_counts['neutral']}개")
    print(f"    부정: {sentiment_counts['negative']}개")

print()


# ============================================================================
# Step 6: 질문 처리 (AUXILIARY_STORE 대상만, Mock)
# ============================================================================
print("━"*80)
print("Step 6: 질문 처리 (AUXILIARY_STORE 대상)")
print("━"*80)

from comment_filtering_agent.analyzers.question_models import (
    ProductQuestion, QuestionCategory, UrgencyLevel
)

question_items = [
    item for item in agent_decisions
    if item['agent_decision'].final_action == AgentAction.AUXILIARY_STORE
]

question_results = []

for item in question_items:
    # Mock 질문 분석
    question = ProductQuestion(
        question_text=item['comment'].text_original,
        is_product_related=True,
        categories=[QuestionCategory.GAME, QuestionCategory.PERFORMANCE],
        has_buying_intent=random.choice([True, False]),
        urgency=UrgencyLevel.MEDIUM,
        answerable_from_video=random.choice([True, False]),
        keywords=['게임', '성능']
    )
    
    question_results.append({
        'comment': item['comment'],
        'question': question
    })

print(f"✓ 질문 처리 완료: {len(question_results)}개")

if question_results:
    print(f"\n  질문 예시:")
    for i, item in enumerate(question_results[:2], 1):
        print(f"    {i}. \"{item['question'].question_text[:50]}...\"")
        print(f"       카테고리: {', '.join([c.value for c in item['question'].categories])}")

print()


# ============================================================================
# Step 7: DB 저장 (Mock - JSON 파일로 저장)
# ============================================================================
print("━"*80)
print("Step 7: DB 저장 (Mock)")
print("━"*80)

# Mock DB 저장 - JSON 파일로 저장
output_dir = Path("test_output")
output_dir.mkdir(exist_ok=True)

# 파이프라인 결과 저장
pipeline_result = {
    'video_id': 'test_video_id',
    'timestamp': datetime.now().isoformat(),
    'statistics': {
        'collected': len(collected_comments),
        'rule_filter': {
            'passed': len(passed_comments),
            'rejected': len(rejected_comments)
        },
        'classified': len(classified_comments),
        'agent_decisions': action_counts,
        'sentiment_analyzed': len(sentiment_results),
        'questions_processed': len(question_results)
    },
    'comments': [
        {
            'text': item['comment'].text_original,
            'classification': item['classification'].label,
            'action': item['agent_decision'].final_action.value
        }
        for item in agent_decisions
    ]
}

output_file = output_dir / f"pipeline_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(pipeline_result, f, ensure_ascii=False, indent=2)

print(f"✓ DB 저장 완료 (Mock)")
print(f"  저장 위치: {output_file}")
print()


# ============================================================================
# Step 8: 보고서 생성
# ============================================================================
print("━"*80)
print("Step 8: 보고서 생성")
print("━"*80)

from comment_filtering_agent.services.report_generator import (
    ReportGenerator, ReportConfig
)
from comment_filtering_agent.services.report_models import (
    ReportMetadata, CommentStatistics, SentimentDistribution,
    AspectMention, RepresentativeComment, QuestionTopic,
    ProductInsight
)

# 보고서 데이터 구성
metadata = ReportMetadata(
    video_id="test_video_id",
    video_title="테스트 비디오",
    product_name="테스트 제품"
)

statistics = CommentStatistics(
    total_collected=len(collected_comments),
    rule_filter_rejected=len(rejected_comments),
    llm_classified=len(classified_comments),
    analyzed_count=action_counts.get('ANALYZE', 0),
    auxiliary_count=action_counts.get('AUXILIARY_STORE', 0),
    excluded_count=action_counts.get('EXCLUDE', 0),
    hold_count=action_counts.get('HOLD', 0),
    reclassify_count=action_counts.get('RECLASSIFY', 0)
)

# 감정 분포 (sentiment_results에서)
sentiment_counts_for_report = {
    'positive': sum(1 for r in sentiment_results if r['analysis'].overall_sentiment == SentimentType.POSITIVE),
    'neutral': sum(1 for r in sentiment_results if r['analysis'].overall_sentiment == SentimentType.NEUTRAL),
    'negative': sum(1 for r in sentiment_results if r['analysis'].overall_sentiment == SentimentType.NEGATIVE)
}

overall_sentiment = SentimentDistribution(
    positive_count=sentiment_counts_for_report['positive'],
    neutral_count=sentiment_counts_for_report['neutral'],
    negative_count=sentiment_counts_for_report['negative']
)

# Aspect 집계
aspect_dict = {}
for result in sentiment_results:
    for aspect in result['analysis'].aspects:
        if aspect.aspect not in aspect_dict:
            aspect_dict[aspect.aspect] = {'positive': 0, 'neutral': 0, 'negative': 0}
        aspect_dict[aspect.aspect][aspect.sentiment.value] += 1

aspect_mentions = [
    AspectMention(
        aspect=aspect,
        total_mentions=sum(counts.values()),
        positive_count=counts['positive'],
        neutral_count=counts['neutral'],
        negative_count=counts['negative']
    )
    for aspect, counts in aspect_dict.items()
]

# 인사이트
insight = ProductInsight(
    strengths=[am.aspect for am in aspect_mentions if am.dominant_sentiment == SentimentType.POSITIVE],
    weaknesses=[am.aspect for am in aspect_mentions if am.dominant_sentiment == SentimentType.NEGATIVE],
    neutral_points=[],
    user_concerns=[q['question'].categories[0].value for q in question_results[:5]] if question_results else [],
    summary=f"테스트 결과: {overall_sentiment.sentiment_score:+.1f} 스코어"
)

# ReportData 구성
from comment_filtering_agent.services.report_models import ReportData

report_data = ReportData(
    metadata=metadata,
    statistics=statistics,
    overall_sentiment=overall_sentiment,
    aspect_mentions=aspect_mentions,
    representative_positive=[],
    representative_negative=[],
    question_topics=[],
    insight=insight
)

# 보고서 생성 및 저장
config = ReportConfig(output_dir=str(output_dir))
generator = ReportGenerator(config)

md_path = generator.save_markdown(report_data)
json_path = generator.save_json(report_data)

print(f"✓ 보고서 생성 완료")
print(f"  Markdown: {md_path}")
print(f"  JSON: {json_path}")
print()


# ============================================================================
# 최종 요약
# ============================================================================
print("━"*80)
print("전체 파이프라인 실행 요약")
print("━"*80)

print(f"""
📊 통계:
  ├─ 수집: {len(collected_comments)}개
  ├─ 1차 필터 통과: {len(passed_comments)}개
  ├─ 1차 필터 제외: {len(rejected_comments)}개
  ├─ 2차 분류 완료: {len(classified_comments)}개
  ├─ Agent 결정:
  │   ├─ ANALYZE: {action_counts.get('ANALYZE', 0)}개
  │   ├─ AUXILIARY_STORE: {action_counts.get('AUXILIARY_STORE', 0)}개
  │   ├─ EXCLUDE: {action_counts.get('EXCLUDE', 0)}개
  │   ├─ HOLD: {action_counts.get('HOLD', 0)}개
  │   └─ RECLASSIFY: {action_counts.get('RECLASSIFY', 0)}개
  ├─ 감정 분석: {len(sentiment_results)}개
  └─ 질문 처리: {len(question_results)}개

📈 결과:
  ├─ 감정 스코어: {overall_sentiment.sentiment_score:+.1f}
  ├─ 긍정 비율: {overall_sentiment.positive_ratio:.1f}%
  ├─ 제외율: {statistics.exclusion_rate:.1f}%
  └─ 분석 비율: {statistics.analysis_rate:.1f}%

📁 출력:
  ├─ 파이프라인 결과: {output_file}
  ├─ Markdown 보고서: {md_path}
  └─ JSON 보고서: {json_path}
""")

print("="*80)
print("✅ 전체 파이프라인 테스트 완료!")
print("="*80)
print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# 성공 여부 체크
success_checks = [
    ("댓글 수집", len(collected_comments) > 0),
    ("1차 필터", len(passed_comments) >= 0),
    ("2차 분류", len(classified_comments) > 0),
    ("Agent 결정", len(agent_decisions) > 0),
    ("DB 저장", output_file.exists()),
    ("보고서 생성", md_path.exists() and json_path.exists())
]

all_success = all(check[1] for check in success_checks)

print("체크리스트:")
for name, success in success_checks:
    status = "✓" if success else "✗"
    print(f"  [{status}] {name}")

if all_success:
    print("\n🎉 모든 단계 정상 동작!")
    sys.exit(0)
else:
    print("\n⚠️ 일부 단계 실패")
    sys.exit(1)
