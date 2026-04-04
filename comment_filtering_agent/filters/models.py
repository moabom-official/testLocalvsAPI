"""
1차 규칙 기반 필터 - 데이터 모델
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RejectReason(str, Enum):
    """필터 제외 사유 코드"""
    TOO_SHORT = "TOO_SHORT"                     # 글자 수 너무 짧음
    EMOJI_HEAVY = "EMOJI_HEAVY"                 # 이모지만 많음
    LOW_INFORMATION = "LOW_INFORMATION"         # 정보량 낮음 (반복 문자)
    GREETING_ONLY = "GREETING_ONLY"             # 인사만 있음
    REACTION_ONLY = "REACTION_ONLY"             # 반응만 있음 (ㅋㅋㅋ, 와)
    URL_SPAM = "URL_SPAM"                       # URL 포함 (광고성)
    PROMOTIONAL = "PROMOTIONAL"                 # 홍보성
    CREATOR_PRAISE_ONLY = "CREATOR_PRAISE_ONLY" # 유튜버 칭찬만
    ABUSIVE = "ABUSIVE"                         # 욕설/비속어
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE" # 중복 의심
    SPECIAL_CHARS_ONLY = "SPECIAL_CHARS_ONLY"   # 특수문자만


@dataclass
class FilterResult:
    """필터링 결과"""
    index: int                                  # 댓글 인덱스
    original_text: str                          # 원본 텍스트
    cleaned_text: str                           # 정제된 텍스트
    is_passed: bool                             # 통과 여부
    reject_reason_codes: List[RejectReason] = field(default_factory=list)
    matched_rules: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # 추가 정보
    
    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "index": self.index,
            "original_text": self.original_text,
            "cleaned_text": self.cleaned_text,
            "is_passed": self.is_passed,
            "reject_reason_codes": [r.value for r in self.reject_reason_codes],
            "matched_rules": self.matched_rules,
            "metadata": self.metadata
        }


@dataclass
class RuleConfig:
    """규칙 설정"""
    min_length: int = 5                         # 최소 글자 수
    max_emoji_ratio: float = 0.7                # 최대 이모지 비율
    min_information_ratio: float = 0.3          # 최소 정보량 비율
    max_repeated_char_ratio: float = 0.5        # 최대 반복 문자 비율
    enable_profanity_check: bool = True         # 욕설 체크 활성화
    enable_url_check: bool = True               # URL 체크 활성화
    enable_duplicate_check: bool = True         # 중복 체크 활성화
    
    # 버전 관리
    version: str = "1.0"
    description: str = "기본 규칙 필터"
