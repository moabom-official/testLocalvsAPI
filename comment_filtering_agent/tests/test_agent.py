"""
댓글 필터링 Agent - 테스트 코드

10개 이상의 테스트 케이스로 Agent 의사결정 로직 검증
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from comment_filtering_agent.core.agent import AgentDecisionEngine
from comment_filtering_agent.core.models import AgentPolicyConfig, AgentAction
from comment_filtering_agent.filters.models import FilterResult, RejectReason
from comment_filtering_agent.classifiers.models import ClassificationResult, CommentLabel, ClassifierType


def create_mock_filter_pass() -> FilterResult:
    """1차 필터 PASS 결과 생성"""
    return FilterResult(
        index=0,
        original_text="테스트 댓글",
        cleaned_text="테스트 댓글",
        is_passed=True,
        reject_reason_codes=[],
        matched_rules=[],
        metadata={}
    )


def create_mock_filter_reject(reason: RejectReason) -> FilterResult:
    """1차 필터 REJECT 결과 생성"""
    return FilterResult(
        index=0,
        original_text="테스트 댓글",
        cleaned_text="테스트 댓글",
        is_passed=False,
        reject_reason_codes=[reason],
        matched_rules=["test_rule"],
        metadata={}
    )


def create_mock_classification(
    label: CommentLabel,
    confidence: float = 0.95,
    needs_recheck: bool = False,
    is_product_related: bool = True,
    mentioned_features: list = None
) -> ClassificationResult:
    """2차 분류 결과 생성"""
    return ClassificationResult(
        index=0,
        original_comment="테스트 댓글",
        label=label,
        confidence=confidence,
        rationale_short="테스트 분류",
        needs_recheck=needs_recheck,
        mentioned_product_features=mentioned_features or [],
        is_product_related=is_product_related,
        classifier_type=ClassifierType.FEW_SHOT,
        model_name="test-model"
    )


def test_case_1():
    """테스트 1: 1차 필터 REJECT → EXCLUDE"""
    print("=" * 80)
    print("테스트 1: 1차 필터 REJECT → EXCLUDE")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "ㅋㅋㅋㅋㅋㅋㅋ"
    filter_result = create_mock_filter_reject(RejectReason.REACTION_ONLY)
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=None  # 1차 필터 실패 시 2차 분류 안 함
    )
    
    print(f"댓글: {comment}")
    print(f"1차 필터: REJECT ({filter_result.reject_reason_codes})")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"제외 사유: {decision.exclusion_reason.value if decision.exclusion_reason else None}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.EXCLUDE
    assert decision.exclusion_reason.value == "RULE_FILTERED"
    print("✓ 테스트 통과\n")


def test_case_2():
    """테스트 2: PRODUCT_OPINION + 고확신 → ANALYZE"""
    print("=" * 80)
    print("테스트 2: PRODUCT_OPINION + 고확신 → ANALYZE")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "발열은 심한데 성능은 좋네요"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.PRODUCT_OPINION,
        confidence=0.95,
        mentioned_features=["발열", "성능"]
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}, 확신도: {classification_result.confidence}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"감정 분석: {decision.should_run_sentiment}")
    print(f"항목 분석: {decision.should_run_aspect_analysis}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.ANALYZE
    assert decision.should_run_sentiment == True
    assert decision.should_run_aspect_analysis == True
    print("✓ 테스트 통과\n")


def test_case_3():
    """테스트 3: PRODUCT_OPINION + 저확신 → HOLD"""
    print("=" * 80)
    print("테스트 3: PRODUCT_OPINION + 저확신 → HOLD")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "음... 글쎄요"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.PRODUCT_OPINION,
        confidence=0.45  # VERY_LOW
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}, 확신도: {classification_result.confidence}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"저확신: {decision.is_low_confidence}")
    print(f"수동 검토: {decision.needs_human_review}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.HOLD
    assert decision.is_low_confidence == True
    assert decision.needs_human_review == True
    print("✓ 테스트 통과\n")


def test_case_4():
    """테스트 4: QUESTION + 제품 관련 → AUXILIARY_STORE"""
    print("=" * 80)
    print("테스트 4: QUESTION + 제품 관련 → AUXILIARY_STORE")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "이거 게임도 잘 돌아가나요?"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.QUESTION,
        confidence=0.98,
        is_product_related=True,
        mentioned_features=["게임"]
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}, 제품 관련: {classification_result.is_product_related}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"질문 저장: {decision.should_store_as_question}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.AUXILIARY_STORE
    assert decision.should_store_as_question == True
    print("✓ 테스트 통과\n")


def test_case_5():
    """테스트 5: QUESTION + 제품 무관 → EXCLUDE"""
    print("=" * 80)
    print("테스트 5: QUESTION + 제품 무관 → EXCLUDE")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "배경음악 제목 뭔가요?"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.QUESTION,
        confidence=0.99,
        is_product_related=False
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}, 제품 관련: {classification_result.is_product_related}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"제외 사유: {decision.exclusion_reason.value}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.EXCLUDE
    assert decision.exclusion_reason.value == "OFF_TOPIC_QUESTION"
    print("✓ 테스트 통과\n")


def test_case_6():
    """테스트 6: VIDEO_REACTION → EXCLUDE"""
    print("=" * 80)
    print("테스트 6: VIDEO_REACTION → EXCLUDE")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "오늘 영상 재밌네요"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.VIDEO_REACTION,
        confidence=0.97
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"제외 사유: {decision.exclusion_reason.value}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.EXCLUDE
    assert decision.exclusion_reason.value == "VIDEO_REACTION"
    print("✓ 테스트 통과\n")


def test_case_7():
    """테스트 7: CHATTER → EXCLUDE"""
    print("=" * 80)
    print("테스트 7: CHATTER → EXCLUDE")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "오 신기하다"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.CHATTER,
        confidence=0.93
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"제외 사유: {decision.exclusion_reason.value}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.EXCLUDE
    assert decision.exclusion_reason.value == "CHATTER"
    print("✓ 테스트 통과\n")


def test_case_8():
    """테스트 8: OFF_TOPIC → EXCLUDE"""
    print("=" * 80)
    print("테스트 8: OFF_TOPIC → EXCLUDE")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "오늘 날씨 좋네요"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.OFF_TOPIC,
        confidence=0.99,
        is_product_related=False
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"제외 사유: {decision.exclusion_reason.value}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.EXCLUDE
    assert decision.exclusion_reason.value == "OFF_TOPIC"
    print("✓ 테스트 통과\n")


def test_case_9():
    """테스트 9: needs_recheck=True → RECLASSIFY"""
    print("=" * 80)
    print("테스트 9: needs_recheck=True → RECLASSIFY")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "좋네요"  # 애매한 댓글
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.PRODUCT_OPINION,
        confidence=0.65,
        needs_recheck=True
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}, needs_recheck: {classification_result.needs_recheck}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"LLM 재확인: {decision.should_send_llm_recheck}")
    print(f"재분류 필요: {decision.needs_reclassification}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.RECLASSIFY
    assert decision.should_send_llm_recheck == True
    assert decision.needs_reclassification == True
    print("✓ 테스트 통과\n")


def test_case_10():
    """테스트 10: LLM 실패 → HOLD"""
    print("=" * 80)
    print("테스트 10: LLM 실패 → HOLD")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "테스트 댓글"
    filter_result = create_mock_filter_pass()
    classification_result = None  # LLM 실패
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"1차 필터: PASS")
    print(f"2차 분류: 실패")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"수동 검토: {decision.needs_human_review}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.HOLD
    assert decision.needs_human_review == True
    print("✓ 테스트 통과\n")


def test_case_11():
    """테스트 11: CHATTER + 낮은 확신 + needs_recheck → RECLASSIFY"""
    print("=" * 80)
    print("테스트 11: CHATTER + 낮은 확신 + needs_recheck → RECLASSIFY")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comment = "뭐지?"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.CHATTER,
        confidence=0.60,  # 낮은 확신
        needs_recheck=True
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"2차 분류: {classification_result.label.value}, 확신도: {classification_result.confidence}")
    print(f"needs_recheck: {classification_result.needs_recheck}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"이유: {decision.final_reason}")
    
    assert decision.final_action == AgentAction.RECLASSIFY
    print("✓ 테스트 통과\n")


def test_case_12():
    """테스트 12: 커스텀 정책 - exclude_all_questions=True"""
    print("=" * 80)
    print("테스트 12: 커스텀 정책 - 모든 질문 제외")
    print("=" * 80)
    
    # 커스텀 정책: 모든 질문 제외
    policy = AgentPolicyConfig(
        exclude_all_questions=True
    )
    agent = AgentDecisionEngine(policy_config=policy)
    
    comment = "이거 배터리 얼마나 가나요?"
    filter_result = create_mock_filter_pass()
    classification_result = create_mock_classification(
        label=CommentLabel.QUESTION,
        confidence=0.98,
        is_product_related=True
    )
    
    decision = agent.decide(
        comment=comment,
        filter_result=filter_result,
        classification_result=classification_result
    )
    
    print(f"댓글: {comment}")
    print(f"정책: exclude_all_questions = True")
    print(f"2차 분류: {classification_result.label.value}, 제품 관련: {classification_result.is_product_related}")
    print(f"최종 액션: {decision.final_action.value}")
    print(f"제외 사유: {decision.exclusion_reason.value if decision.exclusion_reason else None}")
    print(f"이유: {decision.final_reason}")
    
    # 정책에 의해 제품 관련 질문도 EXCLUDE
    assert decision.final_action == AgentAction.EXCLUDE
    print("✓ 테스트 통과\n")


def test_case_13():
    """테스트 13: 배치 처리"""
    print("=" * 80)
    print("테스트 13: 배치 처리")
    print("=" * 80)
    
    agent = AgentDecisionEngine()
    
    comments = [
        "발열은 심한데 성능은 좋네요",
        "ㅋㅋㅋㅋㅋㅋㅋ",
        "이거 게임도 잘 돌아가나요?",
        "오늘 영상 재밌네요"
    ]
    
    filter_results = [
        create_mock_filter_pass(),
        create_mock_filter_reject(RejectReason.REACTION_ONLY),
        create_mock_filter_pass(),
        create_mock_filter_pass()
    ]
    
    classification_results = [
        create_mock_classification(CommentLabel.PRODUCT_OPINION, 0.95),
        None,  # 1차 필터 실패로 2차 분류 안 함
        create_mock_classification(CommentLabel.QUESTION, 0.98, is_product_related=True),
        create_mock_classification(CommentLabel.VIDEO_REACTION, 0.97)
    ]
    
    decisions = agent.decide_batch(
        comments=comments,
        filter_results=filter_results,
        classification_results=classification_results
    )
    
    print(f"배치 크기: {len(comments)}개")
    print("\n결과:")
    for i, (comment, decision) in enumerate(zip(comments, decisions)):
        print(f"\n{i+1}. {comment}")
        print(f"   액션: {decision.final_action.value}")
    
    assert len(decisions) == len(comments)
    assert decisions[0].final_action == AgentAction.ANALYZE
    assert decisions[1].final_action == AgentAction.EXCLUDE
    assert decisions[2].final_action == AgentAction.AUXILIARY_STORE
    assert decisions[3].final_action == AgentAction.EXCLUDE
    print("\n✓ 테스트 통과\n")


def run_all_tests():
    """모든 테스트 실행"""
    test_case_1()    # 1차 필터 REJECT
    test_case_2()    # PRODUCT_OPINION + 고확신
    test_case_3()    # PRODUCT_OPINION + 저확신
    test_case_4()    # QUESTION + 제품 관련
    test_case_5()    # QUESTION + 제품 무관
    test_case_6()    # VIDEO_REACTION
    test_case_7()    # CHATTER
    test_case_8()    # OFF_TOPIC
    test_case_9()    # needs_recheck
    test_case_10()   # LLM 실패
    test_case_11()   # CHATTER + 낮은 확신
    test_case_12()   # 커스텀 정책
    test_case_13()   # 배치 처리
    
    print("=" * 80)
    print("✓ 모든 테스트 통과! (13개)")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
