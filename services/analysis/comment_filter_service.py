from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


class CommentClass(str, Enum):
    PRODUCT_OPINION = "PRODUCT_OPINION"
    PRODUCT_QUESTION = "PRODUCT_QUESTION"
    VIDEO_REACTION = "VIDEO_REACTION"
    CHATTER_MEME = "CHATTER_MEME"
    OFF_TOPIC = "OFF_TOPIC"


@dataclass(frozen=True)
class CommentFilterResult:
    index: int
    text: str
    comment_class: CommentClass
    include_in_analysis: bool
    reason: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "class": self.comment_class.value,
            "include_in_analysis": self.include_in_analysis,
            "reason": self.reason,
            "confidence": self.confidence,
        }


ClassifierFn = Callable[[str], Tuple[CommentClass, float, str]]


class CommentFilterService:
    """
    Rule-first comment classifier.

    - Current: keyword and pattern based classification
    - Future: pass an LLM-backed `classifier` to replace `_rule_based_classify`
    """

    PRODUCT_KEYWORDS = {
        "제품",
        "상품",
        "모델",
        "성능",
        "가격",
        "가성비",
        "배터리",
        "화질",
        "음질",
        "내구성",
        "추천",
        "비추천",
        "구매",
        "샀",
        "쓰고",
        "사용",
        "후기",
        "리뷰",
        "장점",
        "단점",
    }

    VIDEO_REACTION_KEYWORDS = {
        "영상",
        "편집",
        "연출",
        "브금",
        "자막",
        "썸네일",
        "유튜버",
        "채널",
        "업로드",
        "좋아요",
        "구독",
    }

    CHATTER_MEME_KEYWORDS = {
        "ㅋㅋ",
        "ㅎㅎ",
        "lol",
        "lmao",
        "밈",
        "드립",
        "웃기",
        "개웃",
        "미쳤다",
    }

    OFF_TOPIC_KEYWORDS = {
        "정치",
        "종교",
        "축구",
        "야구",
        "주식",
        "코인",
        "날씨",
        "숙제",
        "시험",
    }

    QUESTION_TOKENS = {"?", "어때", "어떤가", "괜찮", "추천", "비교", "살까", "좋나요"}

    def __init__(self, classifier: Optional[ClassifierFn] = None) -> None:
        self._classifier = classifier or self._rule_based_classify

    def filter_comments(self, comments: Sequence[Any]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for idx, item in enumerate(comments):
            text = self._extract_text(item)
            if not text:
                result = CommentFilterResult(
                    index=idx,
                    text="",
                    comment_class=CommentClass.OFF_TOPIC,
                    include_in_analysis=False,
                    reason="empty_comment",
                    confidence=1.0,
                )
                results.append(result.to_dict())
                continue

            comment_class, confidence, reason = self._classifier(text)
            include = self._should_include(comment_class)

            result = CommentFilterResult(
                index=idx,
                text=text,
                comment_class=comment_class,
                include_in_analysis=include,
                reason=reason,
                confidence=confidence,
            )
            results.append(result.to_dict())

        return results

    def _extract_text(self, item: Any) -> str:
        if isinstance(item, str):
            return item.strip()

        if isinstance(item, dict):
            for key in ("text", "text_raw", "comment", "content"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _rule_based_classify(self, text: str) -> Tuple[CommentClass, float, str]:
        lowered = text.lower().strip()

        product_hits = self._count_hits(lowered, self.PRODUCT_KEYWORDS)
        video_hits = self._count_hits(lowered, self.VIDEO_REACTION_KEYWORDS)
        meme_hits = self._count_hits(lowered, self.CHATTER_MEME_KEYWORDS)
        offtopic_hits = self._count_hits(lowered, self.OFF_TOPIC_KEYWORDS)
        question_hits = self._count_hits(lowered, self.QUESTION_TOKENS)

        if offtopic_hits > 0 and product_hits == 0:
            return (CommentClass.OFF_TOPIC, 0.86, "offtopic_keywords")

        if product_hits > 0 and ("?" in lowered or question_hits > 0):
            return (CommentClass.PRODUCT_QUESTION, 0.9, "product_question_pattern")

        if product_hits > 0:
            return (CommentClass.PRODUCT_OPINION, 0.88, "product_keywords")

        if video_hits > 0:
            return (CommentClass.VIDEO_REACTION, 0.82, "video_reaction_keywords")

        # Very short laughter-only comments are typically chatter/noise.
        if meme_hits > 0 or self._is_short_chatter(lowered):
            return (CommentClass.CHATTER_MEME, 0.8, "meme_or_short_chatter")

        return (CommentClass.OFF_TOPIC, 0.65, "default_fallback")

    def _should_include(self, comment_class: CommentClass) -> bool:
        return comment_class in {
            CommentClass.PRODUCT_OPINION,
            CommentClass.PRODUCT_QUESTION,
        }

    @staticmethod
    def _count_hits(text: str, keywords: Iterable[str]) -> int:
        return sum(1 for kw in keywords if kw in text)

    @staticmethod
    def _is_short_chatter(text: str) -> bool:
        compact = text.replace(" ", "")
        if len(compact) <= 6 and any(token in compact for token in ("ㅋㅋ", "ㅎㅎ", "wow", "헉")):
            return True
        return False
