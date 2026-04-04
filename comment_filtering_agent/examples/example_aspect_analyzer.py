"""
감정 및 항목(Aspect) 분석 - 사용 예시
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from comment_filtering_agent.analyzers.groq_analyzer import create_analyzer


def example_1_basic():
    """예시 1: 기본 사용법"""
    print("\n" + "=" * 60)
    print("예시 1: 기본 사용법")
    print("=" * 60)
    
    # 분석기 생성
    analyzer = create_analyzer()
    
    # 댓글 분석
    comment = "발열은 심한데 성능은 좋네요"
    result = analyzer.analyze_single(comment)
    
    print(f"\n댓글: {comment}")
    print(f"전체 감정: {result.overall_sentiment.value} (점수: {result.overall_score})")
    print(f"강도: {result.overall_intensity.value}")
    print(f"이유: {result.overall_reasoning}")
    print(f"\n항목별 감정 ({len(result.aspects)}개):")
    
    for aspect in result.aspects:
        print(f"  • {aspect.aspect}: {aspect.sentiment.value} (점수: {aspect.score})")
        if aspect.mention_text:
            print(f"    언급: '{aspect.mention_text}'")
        if aspect.reasoning:
            print(f"    이유: {aspect.reasoning}")


def example_2_batch():
    """예시 2: 여러 댓글 일괄 분석"""
    print("\n" + "=" * 60)
    print("예시 2: 여러 댓글 일괄 분석")
    print("=" * 60)
    
    analyzer = create_analyzer()
    
    comments = [
        "가격 대비 성능 정말 좋아요",
        "배터리가 빨리 닳아서 아쉽네요",
        "디자인도 예쁘고 성능도 좋고 최고예요",
        "발열이 없지는 않지만 괜찮은 수준이에요"
    ]
    
    results = analyzer.analyze_batch(comments)
    
    for i, result in enumerate(results, 1):
        print(f"\n[{i}] {result.original_comment}")
        print(f"    감정: {result.overall_sentiment.value} ({result.overall_score})")
        print(f"    항목: {', '.join([asp.aspect for asp in result.aspects]) if result.aspects else '없음'}")


def example_3_statistics():
    """예시 3: 통계 분석"""
    print("\n" + "=" * 60)
    print("예시 3: 통계 분석")
    print("=" * 60)
    
    analyzer = create_analyzer()
    
    comments = [
        "발열은 심한데 성능은 좋네요",
        "배터리가 빨리 닳아요. 너무 아쉽네요",
        "가격 대비 정말 만족스럽습니다",
        "디자인도 예쁘고 성능도 좋아요",
        "전반적으로 좋지만 가격이 비싸요",
        "성능은 좋은데 배터리가 빨리 닳아요",
        "발열이 조금 있지만 괜찮아요",
        "화면도 선명하고 카메라도 좋네요"
    ]
    
    results = analyzer.analyze_batch(comments)
    stats = analyzer.get_statistics(results)
    
    print(f"\n총 댓글 수: {stats['total_comments']}개")
    print(f"평균 점수: {stats['average_score']}")
    
    print(f"\n감정 분포:")
    dist = stats['overall_sentiment_distribution']
    print(f"  긍정: {dist['positive']}개 ({dist['positive_pct']}%)")
    print(f"  중립: {dist['neutral']}개 ({dist['neutral_pct']}%)")
    print(f"  부정: {dist['negative']}개 ({dist['negative_pct']}%)")
    
    print(f"\n추출된 항목:")
    print(f"  총 항목 수: {stats['total_aspects_extracted']}개")
    print(f"  고유 항목 수: {stats['unique_aspects']}개")
    
    print(f"\n자주 언급된 항목 TOP 5:")
    for aspect, count in stats['top_aspects'][:5]:
        print(f"  {count}회 - {aspect}")
        if aspect in stats['aspect_sentiments']:
            sent = stats['aspect_sentiments'][aspect]
            print(f"         (긍정: {sent['POSITIVE']}, 중립: {sent['NEUTRAL']}, 부정: {sent['NEGATIVE']})")


def example_4_custom_config():
    """예시 4: 커스텀 설정"""
    print("\n" + "=" * 60)
    print("예시 4: 커스텀 설정")
    print("=" * 60)
    
    from comment_filtering_agent.analyzers.models import AnalyzerConfig
    from comment_filtering_agent.analyzers.groq_analyzer import GroqAspectSentimentAnalyzer
    
    # 커스텀 설정
    config = AnalyzerConfig(
        model_name="llama-3.3-70b-versatile",
        temperature=0.2,  # 더 다양한 응답
        max_tokens=1500,
        extract_mention_text=True,
        extract_reasoning=True
    )
    
    analyzer = GroqAspectSentimentAnalyzer(config=config)
    
    comment = "가격만 빼면 정말 완벽한 제품이에요"
    result = analyzer.analyze_single(comment)
    
    print(f"\n댓글: {comment}")
    print(f"전체 감정: {result.overall_sentiment.value} ({result.overall_score})")
    print(f"설정: temperature={config.temperature}, max_tokens={config.max_tokens}")
    
    for aspect in result.aspects:
        print(f"\n  항목: {aspect.aspect}")
        print(f"  감정: {aspect.sentiment.value} ({aspect.score})")
        print(f"  강도: {aspect.intensity.value}")
        if aspect.mention_text:
            print(f"  언급: {aspect.mention_text}")
        if aspect.reasoning:
            print(f"  이유: {aspect.reasoning}")


def example_5_json_output():
    """예시 5: JSON 출력"""
    print("\n" + "=" * 60)
    print("예시 5: JSON 출력")
    print("=" * 60)
    
    import json
    
    analyzer = create_analyzer()
    
    comment = "디자인도 예쁘고 성능도 좋고 배터리도 오래가요"
    result = analyzer.analyze_single(comment)
    
    # JSON으로 변환
    result_dict = result.to_dict()
    
    print(f"\n댓글: {comment}")
    print("\nJSON 출력:")
    print(json.dumps(result_dict, ensure_ascii=False, indent=2))


def example_6_edge_cases():
    """예시 6: 엣지 케이스 처리"""
    print("\n" + "=" * 60)
    print("예시 6: 엣지 케이스 처리")
    print("=" * 60)
    
    analyzer = create_analyzer()
    
    edge_cases = [
        ("부정어 반전", "배터리가 나쁘지 않네요"),
        ("반어법", "발열 때문에 겨울용으로 딱이네요 ㅋㅋ"),
        ("비교 표현", "전 모델보다 발열이 많이 개선됐어요"),
        ("조건부 평가", "가격만 빼면 완벽해요"),
        ("질문+평가", "성능은 좋은데 배터리가 빨리 닳는데 정상인가요?")
    ]
    
    for label, comment in edge_cases:
        result = analyzer.analyze_single(comment)
        print(f"\n[{label}]")
        print(f"댓글: {comment}")
        print(f"감정: {result.overall_sentiment.value} ({result.overall_score})")
        if result.aspects:
            print(f"항목:")
            for asp in result.aspects:
                print(f"  • {asp.aspect}: {asp.sentiment.value} ({asp.score})")


def example_7_integration():
    """예시 7: Agent와 통합"""
    print("\n" + "=" * 60)
    print("예시 7: Agent와 통합")
    print("=" * 60)
    
    from comment_filtering_agent.core.models import AgentAction
    
    # 가정: Agent가 ANALYZE 결정을 내린 댓글들
    analyze_comments = [
        "발열은 심한데 성능은 좋네요",
        "가격 대비 만족스럽습니다",
        "디자인도 예쁘고 성능도 좋아요"
    ]
    
    analyzer = create_analyzer()
    
    print("\n[Agent가 ANALYZE로 판정한 댓글 분석]")
    
    results = analyzer.analyze_batch(analyze_comments)
    
    for result in results:
        print(f"\n댓글: {result.original_comment}")
        print(f"감정: {result.overall_sentiment.value} ({result.overall_score})")
        
        if result.aspects:
            print("추출된 항목:")
            for asp in result.aspects:
                print(f"  • {asp.aspect} ({asp.aspect_category}): {asp.sentiment.value}")
        
        # DB 저장 시뮬레이션
        print("→ sentiment_analysis 테이블 저장")
        if result.aspects:
            print("→ aspect_extractions 테이블 저장")


def main():
    """메인 함수"""
    print("\n" + "=" * 60)
    print("감정 및 항목 분석 - 사용 예시")
    print("=" * 60)
    
    # API 키 확인
    if not os.getenv("GROQ_API_KEY"):
        print("\n⚠ GROQ_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("예시를 실행하려면 API 키를 설정하세요:")
        print('  export GROQ_API_KEY="your-api-key"  # Linux/Mac')
        print('  set GROQ_API_KEY=your-api-key       # Windows')
        return
    
    try:
        example_1_basic()
        example_2_batch()
        example_3_statistics()
        example_4_custom_config()
        example_5_json_output()
        example_6_edge_cases()
        example_7_integration()
        
        print("\n" + "=" * 60)
        print("모든 예시 실행 완료!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
