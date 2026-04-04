"""
최적화된 Batch Classification 프롬프트 - 최종 버전

사용법:
from comment_filtering_agent.prompts.batch_prompt_optimized import (
    SYSTEM_PROMPT,
    create_batch_prompt
)
"""

# ============================================================================
# System Prompt (고정)
# ============================================================================

SYSTEM_PROMPT = """YouTube product review comment classifier. Output JSON array only."""


# ============================================================================
# 최종 추천 프롬프트 (균형: 토큰 효율 + 정확도)
# ============================================================================

def create_batch_prompt(comments: list) -> str:
    """
    배치 분류용 최적화 프롬프트
    
    Args:
        comments: [{"id": "c1", "text": "comment text"}, ...]
    
    Returns:
        Optimized prompt string
    """
    import json
    comments_json = json.dumps(comments, ensure_ascii=False, indent=2)
    
    prompt = f"""Labels:
PRODUCT_OPINION=product evaluation, VIDEO_REACTION=video praise, QUESTION=question, CHATTER=meaningless, OFF_TOPIC=unrelated

Priority:
1. Product features (heat/battery/performance/design) -> PRODUCT_OPINION
2. Video/reviewer -> VIDEO_REACTION
3. Question form -> QUESTION
4. Short meaningless -> CHATTER
5. Completely unrelated -> OFF_TOPIC

Examples:
{{"text":"bad heat", "label":"PRODUCT_OPINION", "conf":0.98}}
{{"text":"good performance", "label":"PRODUCT_OPINION", "conf":0.97}}
{{"text":"fun video", "label":"VIDEO_REACTION", "conf":0.95}}
{{"text":"good review", "label":"VIDEO_REACTION", "conf":0.94}}
{{"text":"works for gaming?", "label":"QUESTION", "conf":0.99}}
{{"text":"where to buy?", "label":"QUESTION", "conf":0.96}}
{{"text":"lol", "label":"CHATTER", "conf":0.95}}
{{"text":"bgm?", "label":"OFF_TOPIC", "conf":0.98}}

Comments to classify:
{comments_json}

Output: JSON array only, format=[{{"id":"...","label":"...","confidence":0.0~1.0}}]

JSON:"""
    
    return prompt


# ============================================================================
# 초경량 버전 (토큰 최소화)
# ============================================================================

def create_compact_prompt(comments: list) -> str:
    """
    Ultra-compact prompt (80% token reduction)
    """
    import json
    comments_json = json.dumps(comments, ensure_ascii=False)
    
    prompt = f"""Rules:
PRODUCT_OPINION=product, VIDEO_REACTION=video, QUESTION=question, CHATTER=meaningless, OFF_TOPIC=unrelated

Comments: {comments_json}

JSON only: [{{"id":"c1","label":"PRODUCT_OPINION","confidence":0.95}},...]
"""
    
    return prompt


# ============================================================================
# 정확도 우선 버전 (Few-shot 10개)
# ============================================================================

def create_accurate_prompt(comments: list) -> str:
    """
    Accuracy-first prompt (10 few-shot examples)
    """
    import json
    comments_json = json.dumps(comments, ensure_ascii=False, indent=2)
    
    prompt = f"""YouTube product review comment classification.

Label definitions:
- PRODUCT_OPINION: Product performance/quality/design/price evaluation
- VIDEO_REACTION: Video/reviewer/editing evaluation
- QUESTION: Product-related question
- CHATTER: Short meaningless reaction
- OFF_TOPIC: Unrelated to product/video

Few-shot examples:
1. "bad heat but good performance" -> PRODUCT_OPINION
2. "battery drains fast" -> PRODUCT_OPINION
3. "good value for money" -> PRODUCT_OPINION
4. "fun video today" -> VIDEO_REACTION
5. "detailed review" -> VIDEO_REACTION
6. "works for gaming?" -> QUESTION
7. "where to buy?" -> QUESTION
8. "lol" -> CHATTER
9. "interesting" -> CHATTER
10. "what's the bgm?" -> OFF_TOPIC

Comments to classify:
{comments_json}

Output format (JSON array only):
[
  {{"id": "c1", "label": "PRODUCT_OPINION", "confidence": 0.95}},
  {{"id": "c2", "label": "VIDEO_REACTION", "confidence": 0.92}},
  ...
]

Important: Output JSON array only. No other text.

JSON:"""
    
    return prompt


# ============================================================================
# 사용 예시
# ============================================================================

if __name__ == "__main__":
    # Test comments
    test_comments = [
        {"id": "c1", "text": "has some heat"},
        {"id": "c2", "text": "fun video today"},
        {"id": "c3", "text": "how long does battery last?"},
        {"id": "c4", "text": "lol"},
        {"id": "c5", "text": "what's the bgm?"}
    ]
    
    print("=" * 70)
    print("Recommended Prompt (Balanced)")
    print("=" * 70)
    print(create_batch_prompt(test_comments))
    print()
    
    print("=" * 70)
    print("Compact Prompt (Min Tokens)")
    print("=" * 70)
    print(create_compact_prompt(test_comments))
    print()
    
    print("=" * 70)
    print("Accurate Prompt (Max Accuracy)")
    print("=" * 70)
    print(create_accurate_prompt(test_comments))
