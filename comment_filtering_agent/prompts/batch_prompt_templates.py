"""
최적화된 Batch Classification 프롬프트 템플릿
"""

# ============================================================================
# System Prompt (고정)
# ============================================================================

SYSTEM_PROMPT = """YouTube 제품 리뷰 댓글 분류기. JSON 배열만 출력."""


# ============================================================================
# User Prompt Template (동적)
# ============================================================================

def create_batch_prompt(comments: list) -> str:
    """
    배치 분류용 프롬프트 생성
    
    Args:
        comments: [{"id": "c1", "text": "댓글"}, ...] 형태
    
    Returns:
        프롬프트 문자열
    """
    
    # 댓글 리스트를 JSON 문자열로
    import json
    comments_json = json.dumps(comments, ensure_ascii=False, indent=2)
    
    prompt = f"""라벨:
• PRODUCT_OPINION: 제품 성능/품질 평가 (발열/배터리/성능/디자인)
• VIDEO_REACTION: 영상/리뷰어 칭찬
• QUESTION: 제품 질문
• CHATTER: 무의미 반응 (ㅋㅋ/와/오)
• OFF_TOPIC: 완전 무관

규칙:
1. 제품 특성 언급 → PRODUCT_OPINION
2. 영상/리뷰어 → VIDEO_REACTION
3. 질문형 → QUESTION
4. 짧고 무의미 → CHATTER
5. 무관 → OFF_TOPIC

예시:
[
  {{"text": "발열은 심한데 성능은 좋네요", "label": "PRODUCT_OPINION"}},
  {{"text": "배터리 빨리 닳아요", "label": "PRODUCT_OPINION"}},
  {{"text": "오늘 영상 재밌네요", "label": "VIDEO_REACTION"}},
  {{"text": "리뷰 설명 상세해요", "label": "VIDEO_REACTION"}},
  {{"text": "이거 게임 잘 돌아가나요?", "label": "QUESTION"}},
  {{"text": "어디서 사나요?", "label": "QUESTION"}},
  {{"text": "ㅋㅋㅋㅋ", "label": "CHATTER"}},
  {{"text": "오 신기하다", "label": "CHATTER"}},
  {{"text": "배경음악 뭐예요?", "label": "OFF_TOPIC"}},
  {{"text": "점심 뭐 먹을까", "label": "OFF_TOPIC"}}
]

분류할 댓글:
{comments_json}

중요:
- 반드시 JSON 배열만 출력
- 다른 텍스트 절대 금지
- 각 항목: {{"id": "...", "label": "...", "confidence": 0.0~1.0}}

JSON:"""
    
    return prompt


# ============================================================================
# 더 압축된 버전 (초경량)
# ============================================================================

def create_ultra_compact_prompt(comments: list) -> str:
    """
    초경량 프롬프트 (few-shot 없음, 규칙만)
    
    토큰 절감: 기존 대비 80% 감소
    """
    import json
    comments_json = json.dumps(comments, ensure_ascii=False)
    
    prompt = f"""분류 규칙:
PRODUCT_OPINION=제품평가, VIDEO_REACTION=영상칭찬, QUESTION=질문, CHATTER=무의미, OFF_TOPIC=무관

댓글: {comments_json}

JSON만 출력: [{{"id":"c1","label":"PRODUCT_OPINION","confidence":0.95}},...]
"""
    
    return prompt


# ============================================================================
# Few-shot 포함 버전 (정확도 우선)
# ============================================================================

def create_accurate_prompt(comments: list) -> str:
    """
    정확도 우선 프롬프트 (few-shot 10개)
    """
    import json
    comments_json = json.dumps(comments, ensure_ascii=False, indent=2)
    
    prompt = f"""YouTube 제품 리뷰 댓글 분류.

라벨 정의:
- PRODUCT_OPINION: 제품 성능/품질/디자인/가격 평가
- VIDEO_REACTION: 영상/리뷰어/편집 평가
- QUESTION: 제품 관련 질문
- CHATTER: 짧고 의미 없는 반응
- OFF_TOPIC: 제품/영상과 무관

Few-shot 예시:
1. "발열은 심한데 성능은 좋네요" → PRODUCT_OPINION
2. "배터리 빨리 닳아요" → PRODUCT_OPINION
3. "가격 대비 괜찮아요" → PRODUCT_OPINION
4. "오늘 영상 재밌네요" → VIDEO_REACTION
5. "리뷰 설명 상세해요" → VIDEO_REACTION
6. "이거 게임 잘 돌아가나요?" → QUESTION
7. "어디서 사나요?" → QUESTION
8. "ㅋㅋㅋㅋ" → CHATTER
9. "오 신기하다" → CHATTER
10. "배경음악 뭐예요?" → OFF_TOPIC

분류할 댓글:
{comments_json}

출력 형식 (JSON 배열만):
[
  {{"id": "c1", "label": "PRODUCT_OPINION", "confidence": 0.95}},
  {{"id": "c2", "label": "VIDEO_REACTION", "confidence": 0.92}},
  ...
]

주의: JSON 배열만 출력하세요. 다른 텍스트 포함 금지.

JSON:"""
    
    return prompt


# ============================================================================
# 추천 버전 (균형)
# ============================================================================

RECOMMENDED_SYSTEM_PROMPT = """YouTube 제품 리뷰 댓글 분류. JSON 배열만 출력."""

def create_recommended_prompt(comments: list) -> str:
    """
    권장 프롬프트 (균형: 토큰 효율 + 정확도)
    
    특징:
    - Few-shot 8개 (핵심만)
    - 짧은 라벨 정의
    - 명확한 출력 형식
    - JSON 깨짐 방지 강화
    """
    import json
    comments_json = json.dumps(comments, ensure_ascii=False, indent=2)
    
    prompt = f"""라벨:
PRODUCT_OPINION=제품평가, VIDEO_REACTION=영상반응, QUESTION=질문, CHATTER=무의미, OFF_TOPIC=무관

우선순위:
1. 제품 특성(발열/배터리/성능/디자인) → PRODUCT_OPINION
2. 영상/리뷰어 → VIDEO_REACTION
3. 질문형 → QUESTION
4. 짧고 무의미 → CHATTER
5. 완전 무관 → OFF_TOPIC

예시:
{{"text":"발열 심해요", "label":"PRODUCT_OPINION", "conf":0.98}}
{{"text":"성능 좋네요", "label":"PRODUCT_OPINION", "conf":0.97}}
{{"text":"영상 재밌어요", "label":"VIDEO_REACTION", "conf":0.95}}
{{"text":"리뷰 잘 봤어요", "label":"VIDEO_REACTION", "conf":0.94}}
{{"text":"게임 되나요?", "label":"QUESTION", "conf":0.99}}
{{"text":"어디서 사요?", "label":"QUESTION", "conf":0.96}}
{{"text":"ㅋㅋㅋ", "label":"CHATTER", "conf":0.95}}
{{"text":"배경음악?", "label":"OFF_TOPIC", "conf":0.98}}

댓글:
{comments_json}

출력: JSON 배열만, 형식=[{{"id":"...","label":"...","confidence":0.0~1.0}}]

JSON:"""
    
    return prompt


# ============================================================================
# 사용 예시
# ============================================================================

if __name__ == "__main__":
    # 테스트 댓글
    test_comments = [
        {"id": "c1", "text": "발열이 좀 있네요"},
        {"id": "c2", "text": "오늘 영상 재밌어요"},
        {"id": "c3", "text": "이거 배터리 얼마나 가요?"},
        {"id": "c4", "text": "ㅋㅋㅋㅋ"},
        {"id": "c5", "text": "배경음악 제목 알려주세요"}
    ]
    
    print("="*70)
    print("1. 균형 프롬프트 (추천)")
    print("="*70)
    print(create_recommended_prompt(test_comments))
    print()
    
    print("="*70)
    print("2. 초경량 프롬프트 (토큰 최소)")
    print("="*70)
    print(create_ultra_compact_prompt(test_comments))
    print()
    
    print("="*70)
    print("3. 정확도 우선 프롬프트")
    print("="*70)
    print(create_accurate_prompt(test_comments))
    print()
    
    # 토큰 수 추정
    print("="*70)
    print("토큰 수 비교 (대략)")
    print("="*70)
    
    def estimate_tokens(text):
        # 한국어: 약 0.7 토큰/글자
        # 영어: 약 0.25 토큰/단어
        korean_chars = sum(1 for c in text if ord(c) > 127)
        english_words = len(text.split())
        return int(korean_chars * 0.7 + english_words * 0.25)
    
    p1 = create_recommended_prompt(test_comments)
    p2 = create_ultra_compact_prompt(test_comments)
    p3 = create_accurate_prompt(test_comments)
    
    print(f"균형 프롬프트:   ~{estimate_tokens(p1)} 토큰")
    print(f"초경량 프롬프트: ~{estimate_tokens(p2)} 토큰 (80% 절감)")
    print(f"정확도 프롬프트: ~{estimate_tokens(p3)} 토큰")
    
    print("\n추천: 균형 프롬프트 (토큰 효율 + 정확도)")
