"""
LLM 댓글 분류기 - 테스트 코드 (Mock)

실제 API 호출 없이 프롬프트와 로직을 테스트합니다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from comment_filtering_agent.classifiers.prompt_builder import ClassificationPromptBuilder
from comment_filtering_agent.classifiers.models import ClassificationConfig, CommentLabel


def test_prompt_builder():
    """프롬프트 빌더 테스트"""
    print("=" * 80)
    print("테스트 1: 프롬프트 빌더")
    print("=" * 80)
    
    builder = ClassificationPromptBuilder()
    
    test_comments = [
        "발열은 심한데 성능은 좋네요",
        "오늘 영상 재밌네요",
        "이거 게임도 잘 돌아가나요?",
        "ㅋㅋㅋㅋㅋ",
        "배경음악 제목 뭔가요?"
    ]
    
    for comment in test_comments:
        print(f"\n댓글: {comment}")
        
        # 단일 프롬프트
        prompt = builder.build_single_prompt(
            comment=comment,
            product_name="갤럭시 S25",
            product_category="스마트폰",
            include_examples=False  # 예시 제외하고 테스트
        )
        
        print(f"  프롬프트 길이: {len(prompt)} 글자")
        print(f"  첫 150자: {prompt[:150]}...")
    
    print()


def test_message_format():
    """메시지 형식 테스트"""
    print("=" * 80)
    print("테스트 2: Chat API 메시지 형식")
    print("=" * 80)
    
    builder = ClassificationPromptBuilder()
    
    comment = "배터리가 생각보다 빨리 닳네요"
    
    messages = builder.build_messages(
        comment=comment,
        product_name="MacBook Pro",
        product_category="노트북",
        include_examples=True
    )
    
    print(f"메시지 개수: {len(messages)}\n")
    
    for i, msg in enumerate(messages):
        print(f"메시지 {i+1}:")
        print(f"  Role: {msg['role']}")
        print(f"  Content 길이: {len(msg['content'])} 글자")
        if msg['role'] == 'user':
            print(f"  Content:\n{msg['content']}")
        print()


def test_json_schema():
    """JSON 스키마 테스트"""
    print("=" * 80)
    print("테스트 3: JSON 스키마 검증")
    print("=" * 80)
    
    builder = ClassificationPromptBuilder()
    
    # 유효한 응답
    valid_responses = [
        {
            "label": "PRODUCT_OPINION",
            "confidence": 0.95,
            "rationale_short": "제품의 발열과 성능에 대한 평가",
            "needs_recheck": False,
            "mentioned_product_features": ["발열", "성능"],
            "is_product_related": True
        },
        {
            "label": "QUESTION",
            "confidence": 0.98,
            "rationale_short": "제품 성능에 대한 질문",
            "needs_recheck": False,
            "mentioned_product_features": ["게임"],
            "is_product_related": True
        }
    ]
    
    # 유효하지 않은 응답
    invalid_responses = [
        {
            "label": "INVALID_LABEL",  # 잘못된 라벨
            "confidence": 0.95,
            "rationale_short": "test",
            "needs_recheck": False,
            "mentioned_product_features": [],
            "is_product_related": True
        },
        {
            "label": "PRODUCT_OPINION",
            "confidence": 1.5,  # 범위 초과
            "rationale_short": "test",
            "needs_recheck": False,
            "mentioned_product_features": [],
            "is_product_related": True
        },
        {
            "label": "PRODUCT_OPINION",
            # confidence 누락
            "rationale_short": "test",
            "needs_recheck": False,
            "mentioned_product_features": [],
            "is_product_related": True
        }
    ]
    
    print("유효한 응답 검증:")
    for i, resp in enumerate(valid_responses):
        is_valid = builder.validate_response(resp)
        print(f"  응답 {i+1}: {'✓ 유효' if is_valid else '✗ 무효'}")
    
    print("\n유효하지 않은 응답 검증:")
    for i, resp in enumerate(invalid_responses):
        is_valid = builder.validate_response(resp)
        print(f"  응답 {i+1}: {'✓ 유효' if is_valid else '✗ 무효 (예상됨)'}")
    
    print()


def test_label_definitions():
    """라벨 정의 테스트"""
    print("=" * 80)
    print("테스트 4: 라벨 정의 및 예시")
    print("=" * 80)
    
    examples_by_label = {
        "PRODUCT_OPINION": [
            "발열은 심한데 성능은 좋네요",
            "배터리가 빨리 닳아요",
            "가격 대비 성능 괜찮아요"
        ],
        "VIDEO_REACTION": [
            "오늘 영상 재밌네요",
            "리뷰 설명이 좋아요",
            "편집 깔끔하네요"
        ],
        "QUESTION": [
            "이거 게임도 잘 돌아가나요?",
            "배터리 몇 시간 가나요?",
            "어디서 사나요?"
        ],
        "CHATTER": [
            "ㅋㅋㅋㅋㅋ",
            "오 신기하다",
            "대박"
        ],
        "OFF_TOPIC": [
            "배경음악 제목 뭔가요?",
            "오늘 날씨 좋네요",
            "점심 뭐 먹을까"
        ]
    }
    
    for label, examples in examples_by_label.items():
        print(f"\n{label}:")
        for ex in examples:
            print(f"  - {ex}")
    
    print()


def test_boundary_cases():
    """경계 케이스 테스트"""
    print("=" * 80)
    print("테스트 5: 경계 케이스 (애매한 댓글)")
    print("=" * 80)
    
    boundary_cases = [
        {
            "comment": "좋네요",
            "challenge": "제품인지 영상인지 불명확"
        },
        {
            "comment": "이 영상 덕분에 제품 이해했어요",
            "challenge": "VIDEO_REACTION vs PRODUCT_OPINION"
        },
        {
            "comment": "실제로 써보니 발열이 영상보다 더 심해요",
            "challenge": "PRODUCT_OPINION (직접 경험)"
        },
        {
            "comment": "리뷰 보니까 발열이 심한가봐요",
            "challenge": "VIDEO_REACTION (영상에서 본 내용)"
        }
    ]
    
    for case in boundary_cases:
        print(f"\n댓글: {case['comment']}")
        print(f"  도전 과제: {case['challenge']}")
    
    print()


def test_prompt_with_examples():
    """예시 포함 프롬프트 테스트"""
    print("=" * 80)
    print("테스트 6: Few-shot 예시 포함 프롬프트")
    print("=" * 80)
    
    builder = ClassificationPromptBuilder()
    
    comment = "카메라 성능은 좋은데 야간 촬영이 아쉬워요"
    
    # 예시 없는 프롬프트
    prompt_no_examples = builder.build_single_prompt(
        comment=comment,
        include_examples=False
    )
    
    # 예시 포함 프롬프트
    prompt_with_examples = builder.build_single_prompt(
        comment=comment,
        include_examples=True
    )
    
    print(f"예시 없는 프롬프트: {len(prompt_no_examples)} 글자")
    print(f"예시 포함 프롬프트: {len(prompt_with_examples)} 글자")
    print(f"차이: {len(prompt_with_examples) - len(prompt_no_examples)} 글자")
    print()
    
    # 예시 개수에 따른 차이
    print("Few-shot 예시 효과:")
    print(f"  - 예시 없음: {len(prompt_no_examples)} 글자")
    print(f"  - 예시 포함: {len(prompt_with_examples)} 글자")
    print(f"  - 예시 비중: {(len(prompt_with_examples) - len(prompt_no_examples)) / len(prompt_with_examples) * 100:.1f}%")
    print()


def test_config():
    """설정 테스트"""
    print("=" * 80)
    print("테스트 7: 분류기 설정")
    print("=" * 80)
    
    # 기본 설정
    default_config = ClassificationConfig()
    print("기본 설정:")
    print(f"  - 모델: {default_config.model_name}")
    print(f"  - Temperature: {default_config.temperature}")
    print(f"  - Max tokens: {default_config.max_tokens}")
    print(f"  - 예시 포함: {default_config.include_examples}")
    print(f"  - 재시도: {default_config.max_retries}")
    print()
    
    # 커스텀 설정
    custom_config = ClassificationConfig(
        model_name="llama-3.3-70b-versatile",
        temperature=0.0,
        max_tokens=300,
        include_examples=False,
        max_retries=5
    )
    print("커스텀 설정:")
    print(f"  - 모델: {custom_config.model_name}")
    print(f"  - Temperature: {custom_config.temperature}")
    print(f"  - Max tokens: {custom_config.max_tokens}")
    print(f"  - 예시 포함: {custom_config.include_examples}")
    print(f"  - 재시도: {custom_config.max_retries}")
    print()


def run_all_tests():
    """모든 테스트 실행"""
    test_prompt_builder()
    test_message_format()
    test_json_schema()
    test_label_definitions()
    test_boundary_cases()
    test_prompt_with_examples()
    test_config()
    
    print("=" * 80)
    print("✓ 모든 테스트 완료!")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
