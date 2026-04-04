"""
감정 및 항목(Aspect) 분석 - 테스트
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from comment_filtering_agent.analyzers.models import (
    SentimentType,
    IntensityType,
    AnalyzerConfig
)
from comment_filtering_agent.analyzers.groq_analyzer import (
    GroqAspectSentimentAnalyzer,
    create_analyzer
)


def test_models():
    """데이터 모델 테스트"""
    print("=" * 60)
    print("TEST 1: Data Models")
    print("=" * 60)
    
    # SentimentType
    assert SentimentType.POSITIVE.value == "POSITIVE"
    assert SentimentType.NEUTRAL.value == "NEUTRAL"
    assert SentimentType.NEGATIVE.value == "NEGATIVE"
    
    # IntensityType
    assert IntensityType.STRONG.value == "STRONG"
    assert IntensityType.MODERATE.value == "MODERATE"
    assert IntensityType.WEAK.value == "WEAK"
    
    # AnalyzerConfig
    config = AnalyzerConfig()
    assert config.model_name == "llama-3.3-70b-versatile"
    assert config.temperature == 0.1
    assert "발열" in config.predefined_aspects
    assert "성능" in config.predefined_aspects
    
    print("✓ All model tests passed\n")


def test_analyzer_initialization():
    """분석기 초기화 테스트"""
    print("=" * 60)
    print("TEST 2: Analyzer Initialization")
    print("=" * 60)
    
    # API 키 확인
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("✗ GROQ_API_KEY not set. Skipping API tests.")
        return None
    
    # 분석기 생성
    analyzer = create_analyzer(api_key=api_key)
    
    assert analyzer is not None
    assert analyzer.config is not None
    assert analyzer.system_prompt is not None
    assert len(analyzer.system_prompt) > 0
    assert analyzer.user_prompt_template is not None
    
    print(f"✓ Analyzer created")
    print(f"  Model: {analyzer.config.model_name}")
    print(f"  System prompt length: {len(analyzer.system_prompt)} chars")
    print(f"  User prompt template length: {len(analyzer.user_prompt_template)} chars\n")
    
    return analyzer


def test_single_aspect_positive(analyzer):
    """단일 항목 긍정 테스트"""
    if not analyzer:
        return
    
    print("=" * 60)
    print("TEST 3: Single Aspect - Positive")
    print("=" * 60)
    
    comment = "가격 대비 성능 정말 좋아요"
    
    result = analyzer.analyze_single(comment, index=0)
    
    print(f"Comment: {comment}")
    print(f"Overall Sentiment: {result.overall_sentiment.value} ({result.overall_score})")
    print(f"Overall Intensity: {result.overall_intensity.value}")
    print(f"Total Aspects: {len(result.aspects)}")
    
    for aspect in result.aspects:
        print(f"  - {aspect.aspect}: {aspect.sentiment.value} ({aspect.score})")
        if aspect.mention_text:
            print(f"    Mention: {aspect.mention_text}")
    
    # 검증
    assert result.overall_sentiment == SentimentType.POSITIVE
    assert result.overall_score > 0.5
    assert len(result.aspects) >= 1
    
    print("✓ Test passed\n")


def test_mixed_sentiment(analyzer):
    """혼재 감정 테스트"""
    if not analyzer:
        return
    
    print("=" * 60)
    print("TEST 4: Mixed Sentiment")
    print("=" * 60)
    
    comment = "발열은 심한데 성능은 좋네요"
    
    result = analyzer.analyze_single(comment, index=0)
    
    print(f"Comment: {comment}")
    print(f"Overall Sentiment: {result.overall_sentiment.value} ({result.overall_score})")
    print(f"Overall Reasoning: {result.overall_reasoning}")
    print(f"Total Aspects: {len(result.aspects)}")
    
    for aspect in result.aspects:
        print(f"  - {aspect.aspect}: {aspect.sentiment.value} ({aspect.score})")
        if aspect.reasoning:
            print(f"    Reasoning: {aspect.reasoning}")
    
    # 검증
    assert len(result.aspects) >= 2
    
    # 발열은 부정, 성능은 긍정이어야 함
    aspects_dict = {asp.aspect: asp for asp in result.aspects}
    if "발열" in aspects_dict:
        assert aspects_dict["발열"].sentiment == SentimentType.NEGATIVE
    if "성능" in aspects_dict:
        assert aspects_dict["성능"].sentiment == SentimentType.POSITIVE
    
    print("✓ Test passed\n")


def test_negation(analyzer):
    """부정어 테스트"""
    if not analyzer:
        return
    
    print("=" * 60)
    print("TEST 5: Negation Expression")
    print("=" * 60)
    
    comment = "배터리가 나쁘지 않네요"
    
    result = analyzer.analyze_single(comment, index=0)
    
    print(f"Comment: {comment}")
    print(f"Overall Sentiment: {result.overall_sentiment.value} ({result.overall_score})")
    print(f"Total Aspects: {len(result.aspects)}")
    
    for aspect in result.aspects:
        print(f"  - {aspect.aspect}: {aspect.sentiment.value} ({aspect.score})")
        print(f"    Intensity: {aspect.intensity.value}")
    
    # 검증: "나쁘지 않다" = 약한 긍정
    assert result.overall_sentiment in [SentimentType.POSITIVE, SentimentType.NEUTRAL]
    assert len(result.aspects) >= 1
    
    print("✓ Test passed\n")


def test_batch_analysis(analyzer):
    """배치 분석 테스트"""
    if not analyzer:
        return
    
    print("=" * 60)
    print("TEST 6: Batch Analysis")
    print("=" * 60)
    
    comments = [
        "발열은 심한데 성능은 좋네요",
        "배터리가 빨리 닳아요",
        "가격 대비 만족스럽습니다",
        "디자인도 예쁘고 성능도 좋아요"
    ]
    
    results = analyzer.analyze_batch(comments)
    
    assert len(results) == len(comments)
    
    for i, result in enumerate(results):
        print(f"\n[{i+1}] {result.original_comment}")
        print(f"    Sentiment: {result.overall_sentiment.value} ({result.overall_score})")
        print(f"    Aspects: {len(result.aspects)}")
    
    print("\n✓ Test passed\n")


def test_statistics(analyzer):
    """통계 테스트"""
    if not analyzer:
        return
    
    print("=" * 60)
    print("TEST 7: Statistics")
    print("=" * 60)
    
    comments = [
        "발열은 심한데 성능은 좋네요",
        "배터리가 빨리 닳아요",
        "가격 대비 만족스럽습니다",
        "디자인도 예쁘고 성능도 좋아요",
        "전반적으로 만족합니다"
    ]
    
    results = analyzer.analyze_batch(comments)
    stats = analyzer.get_statistics(results)
    
    print(f"Total Comments: {stats['total_comments']}")
    print(f"Average Score: {stats['average_score']}")
    print(f"\nSentiment Distribution:")
    dist = stats['overall_sentiment_distribution']
    print(f"  Positive: {dist['positive']} ({dist['positive_pct']}%)")
    print(f"  Neutral: {dist['neutral']} ({dist['neutral_pct']}%)")
    print(f"  Negative: {dist['negative']} ({dist['negative_pct']}%)")
    
    print(f"\nTotal Aspects Extracted: {stats['total_aspects_extracted']}")
    print(f"Unique Aspects: {stats['unique_aspects']}")
    
    print(f"\nTop Aspects:")
    for aspect, count in stats['top_aspects'][:5]:
        print(f"  - {aspect}: {count}")
    
    if stats['average_latency_ms']:
        print(f"\nAverage Latency: {stats['average_latency_ms']} ms")
    
    print("\n✓ Test passed\n")


def main():
    """메인 테스트 실행"""
    print("\n" + "=" * 60)
    print("ASPECT SENTIMENT ANALYZER TESTS")
    print("=" * 60 + "\n")
    
    # 1. 모델 테스트
    test_models()
    
    # 2. 분석기 초기화
    analyzer = test_analyzer_initialization()
    
    if not analyzer:
        print("⚠ Skipping API-dependent tests (no API key)")
        return
    
    # 3. 단일 항목 긍정
    test_single_aspect_positive(analyzer)
    
    # 4. 혼재 감정
    test_mixed_sentiment(analyzer)
    
    # 5. 부정어
    test_negation(analyzer)
    
    # 6. 배치 분석
    test_batch_analysis(analyzer)
    
    # 7. 통계
    test_statistics(analyzer)
    
    print("=" * 60)
    print("ALL TESTS COMPLETED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
