"""
제품 질문 처리 - 사용 예시
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from comment_filtering_agent.analyzers.question_processor import create_processor


def example_1_basic():
    """예시 1: 기본 사용법"""
    print("\n" + "=" * 60)
    print("예시 1: 기본 사용법")
    print("=" * 60)
    
    # 프로세서 생성
    processor = create_processor()
    
    # 질문 댓글 처리
    comment = "이거 게임 돌아가나요? 배그 할 수 있을까요?"
    question = processor.process_single(comment)
    
    if question:
        print(f"\n댓글: {comment}")
        print(f"질문 텍스트: {question.question_text}")
        print(f"제품 관련: {question.is_product_related}")
        print(f"주 카테고리: {question.primary_category.value}")
        print(f"모든 카테고리: {[cat.value for cat in question.categories]}")
        print(f"구매 의도: {question.has_buying_intent}")
        print(f"긴급도: {question.urgency.value if question.urgency else 'N/A'}")
        print(f"영상 답변 가능: {question.answerable_from_video}")
        print(f"키워드: {question.keywords}")
    else:
        print("제품 무관 질문으로 필터링됨")


def example_2_buying_intent():
    """예시 2: 구매 의도가 강한 질문"""
    print("\n" + "=" * 60)
    print("예시 2: 구매 의도가 강한 질문")
    print("=" * 60)
    
    processor = create_processor()
    
    questions_with_intent = [
        "지금 구매하려는데 발열이 심한가요?",
        "가격대비 괜찮을까요? 살까 고민 중이에요",
        "삼성 vs 애플 중 어느걸 사야할까요?"
    ]
    
    for comment in questions_with_intent:
        question = processor.process_single(comment)
        if question:
            print(f"\n댓글: {comment}")
            print(f"  구매 의도: {'✓' if question.has_buying_intent else '✗'}")
            print(f"  긴급도: {question.urgency.value if question.urgency else 'N/A'}")
            print(f"  카테고리: {question.primary_category.value}")


def example_3_batch_processing():
    """예시 3: 여러 질문 일괄 처리"""
    print("\n" + "=" * 60)
    print("예시 3: 여러 질문 일괄 처리")
    print("=" * 60)
    
    processor = create_processor()
    
    comments = [
        "이거 게임 돌아가나요?",
        "배터리 오래가나요?",
        "배경음악 제목 뭔가요?",  # 제품 무관
        "가격이 얼마인가요?",
        "맥북에서 사용 가능한가요?"
    ]
    
    questions = processor.process_batch(comments)
    
    print(f"\n총 댓글: {len(comments)}개")
    print(f"제품 관련 질문: {len(questions)}개")
    
    for i, question in enumerate(questions, 1):
        print(f"\n[{i}] {question.original_comment}")
        print(f"    카테고리: {question.primary_category.value}")
        print(f"    제품 관련: {'✓' if question.is_product_related else '✗'}")


def example_4_statistics():
    """예시 4: 질문 통계 분석"""
    print("\n" + "=" * 60)
    print("예시 4: 질문 통계 분석")
    print("=" * 60)
    
    processor = create_processor()
    
    comments = [
        "이거 게임 돌아가나요?",
        "발열 심한가요?",
        "배터리 오래가나요?",
        "지금 살까 고민 중인데 추천하시나요?",
        "가격이 얼마인가요?",
        "아이폰 vs 갤럭시 어느게 좋나요?",
        "맥북에서 호환되나요?",
        "카메라 화질은 어떤가요?"
    ]
    
    questions = processor.process_batch(comments)
    stats = processor.get_statistics(questions)
    
    print(f"\n총 질문: {stats['total_questions']}개")
    print(f"제품 관련: {stats['product_related']}개 ({stats['product_related_pct']}%)")
    print(f"구매 의도: {stats['buying_intent']}개 ({stats['buying_intent_pct']}%)")
    print(f"영상 답변 가능: {stats['answerable_from_video']}개 ({stats['answerable_pct']}%)")
    
    print(f"\n긴급도 분포:")
    for level, count in stats['urgency_distribution'].items():
        if count > 0:
            print(f"  {level}: {count}개")
    
    print(f"\n카테고리 분포 (TOP 5):")
    for category, count in stats['top_categories']:
        print(f"  {category}: {count}개")


def example_5_json_output():
    """예시 5: JSON 출력"""
    print("\n" + "=" * 60)
    print("예시 5: JSON 출력")
    print("=" * 60)
    
    import json
    
    processor = create_processor()
    
    comment = "살까 고민 중인데 발열이 심한가요?"
    question = processor.process_single(comment)
    
    if question:
        print(f"\n댓글: {comment}")
        print("\nJSON 출력:")
        print(json.dumps(question.to_dict(), ensure_ascii=False, indent=2))


def example_6_faq_generation():
    """예시 6: FAQ 생성 시뮬레이션"""
    print("\n" + "=" * 60)
    print("예시 6: FAQ 생성을 위한 질문 수집")
    print("=" * 60)
    
    processor = create_processor()
    
    # 실제 댓글 시뮬레이션
    comments = [
        "이거 게임 돌아가나요?",
        "게임 할 수 있나요?",
        "배그 돌아가나요?",
        "발열 심한가요?",
        "뜨거운가요?",
        "배터리 오래가나요?",
        "충전 빨리 되나요?",
        "가격이 얼마인가요?",
        "할인하나요?"
    ]
    
    questions = processor.process_batch(comments)
    
    # 카테고리별 질문 그룹화
    from collections import defaultdict
    category_questions = defaultdict(list)
    
    for question in questions:
        category_questions[question.primary_category.value].append(
            question.question_text
        )
    
    print("\n[FAQ 생성 시뮬레이션]")
    print("카테고리별 자주 묻는 질문:")
    
    for category, q_list in category_questions.items():
        print(f"\n## {category} ({len(q_list)}건)")
        for q in q_list[:3]:  # 상위 3개만
            print(f"  Q: {q}")


def example_7_integration():
    """예시 7: Agent와 통합"""
    print("\n" + "=" * 60)
    print("예시 7: Agent와 통합")
    print("=" * 60)
    
    from comment_filtering_agent.core.models import AgentAction
    
    # 가정: Agent가 AUXILIARY_STORE 결정을 내린 QUESTION 댓글들
    auxiliary_comments = [
        "이거 게임 돌아가나요?",
        "배터리 오래가나요?",
        "가격대비 괜찮을까요?"
    ]
    
    processor = create_processor()
    
    print("\n[Agent가 AUXILIARY_STORE로 판정한 QUESTION 댓글 처리]")
    
    questions = processor.process_batch(auxiliary_comments)
    
    for question in questions:
        print(f"\n댓글: {question.original_comment}")
        print(f"카테고리: {question.primary_category.value}")
        print(f"구매 의도: {'있음' if question.has_buying_intent else '없음'}")
        
        # DB 저장 시뮬레이션
        if question.is_product_related:
            print("→ product_questions 테이블 저장")
            print(f"  - question_category: {question.primary_category.value}")
            print(f"  - has_buying_intent: {question.has_buying_intent}")
            print(f"  - keywords: {question.keywords}")


def example_8_priority_questions():
    """예시 8: 우선순위 질문 추출"""
    print("\n" + "=" * 60)
    print("예시 8: 우선순위 질문 추출 (긴급/구매의도)")
    print("=" * 60)
    
    processor = create_processor()
    
    comments = [
        "게임 돌아가나요?",  # 일반 질문
        "지금 구매하려는데 발열 어떤가요?",  # 긴급
        "살까 고민 중인데 추천하시나요?",  # 구매 의도
        "화면 밝기는 어떤가요?",  # 일반 질문
        "오늘 사려고 하는데 배터리 괜찮나요?"  # 긴급
    ]
    
    questions = processor.process_batch(comments)
    
    # 우선순위 질문 필터링
    priority_questions = [
        q for q in questions
        if q.has_buying_intent and q.urgency == "HIGH"
    ]
    
    print("\n[높은 우선순위 질문 (긴급 + 구매의도)]")
    for question in priority_questions:
        print(f"\n✓ {question.original_comment}")
        print(f"  카테고리: {question.primary_category.value}")
        print(f"  긴급도: {question.urgency.value if question.urgency else 'N/A'}")


def main():
    """메인 함수"""
    print("\n" + "=" * 60)
    print("제품 질문 처리 - 사용 예시")
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
        example_2_buying_intent()
        example_3_batch_processing()
        example_4_statistics()
        example_5_json_output()
        example_6_faq_generation()
        example_7_integration()
        example_8_priority_questions()
        
        print("\n" + "=" * 60)
        print("모든 예시 실행 완료!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
