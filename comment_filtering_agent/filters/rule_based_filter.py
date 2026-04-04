"""
1차 규칙 기반 필터 - 메인 클래스

가볍고 빠른 패턴 기반 필터링
- 정규식 사용
- Stopword 사전 활용
- 단순 룰 기반
- Explainable (reason code 제공)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Set, Optional, Callable
from difflib import SequenceMatcher

try:
    import emoji
    EMOJI_AVAILABLE = True
except ImportError:
    EMOJI_AVAILABLE = False
    print("Warning: emoji package not installed. Emoji filtering will be basic.")

from comment_filtering_agent.filters.models import (
    FilterResult, 
    RejectReason, 
    RuleConfig
)


class RuleBasedFilter:
    """
    규칙 기반 1차 필터
    
    특징:
    - 빠른 패턴 매칭
    - Explainable (사유 제공)
    - 규칙 추가/수정 쉬움
    - 애매한 댓글은 통과 (2차 분류로 넘김)
    """
    
    def __init__(
        self, 
        config: Optional[RuleConfig] = None,
        data_dir: Optional[Path] = None
    ):
        self.config = config or RuleConfig()
        self.data_dir = data_dir or Path(__file__).parent.parent / "data"
        
        # 욕설 사전 로드
        self.profanity_words = self._load_profanity_list()
        
        # 반응 패턴 로드
        self.reaction_patterns = self._load_reaction_patterns()
        
        # 중복 체크용 (메모리 캐시)
        self._seen_texts: Set[str] = set()
        
        # 규칙 함수 등록 (순서 중요 - 빠른 체크부터)
        self.rules: List[Callable] = [
            self._check_length,
            self._check_special_chars_only,
            self._check_emoji_heavy,
            self._check_repeated_chars,
            self._check_url,
            self._check_profanity,
            self._check_greeting_only,
            self._check_reaction_only,
            self._check_first_comment,
            self._check_creator_praise_only,
            self._check_promotional,
        ]
        
        if self.config.enable_duplicate_check:
            self.rules.append(self._check_duplicate)
    
    def _load_profanity_list(self) -> Set[str]:
        """욕설 사전 로드"""
        profanity_file = self.data_dir / "profanity_list.txt"
        if not profanity_file.exists():
            print(f"Warning: {profanity_file} not found. Using empty profanity list.")
            return set()
        
        profanity = set()
        with open(profanity_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    profanity.add(line)
        return profanity
    
    def _load_reaction_patterns(self) -> dict:
        """반응 패턴 로드"""
        patterns_file = self.data_dir / "reaction_patterns.json"
        if not patterns_file.exists():
            print(f"Warning: {patterns_file} not found. Using empty patterns.")
            return {}
        
        with open(patterns_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def filter_batch(self, texts: List[str]) -> List[FilterResult]:
        """
        배치 필터링
        
        Args:
            texts: 댓글 텍스트 리스트
            
        Returns:
            FilterResult 리스트
        """
        results = []
        for idx, text in enumerate(texts):
            result = self.filter_single(text, idx)
            results.append(result)
        return results
    
    def filter_single(self, text: str, index: int = 0) -> FilterResult:
        """
        단일 댓글 필터링
        
        Args:
            text: 댓글 텍스트
            index: 댓글 인덱스
            
        Returns:
            FilterResult
        """
        # 텍스트 정제
        cleaned = self._clean_text(text)
        
        # 필터 결과 초기화
        result = FilterResult(
            index=index,
            original_text=text,
            cleaned_text=cleaned,
            is_passed=True,
            reject_reason_codes=[],
            matched_rules=[],
            metadata={}
        )
        
        # 각 규칙 적용
        for rule_func in self.rules:
            rule_name = rule_func.__name__.replace("_check_", "")
            reject_reason = rule_func(cleaned, result.metadata)
            
            if reject_reason:
                result.reject_reason_codes.append(reject_reason)
                result.matched_rules.append(rule_name)
        
        # 최종 판단 (하나라도 걸리면 reject)
        if result.reject_reason_codes:
            result.is_passed = False
        
        return result
    
    def _clean_text(self, text: str) -> str:
        """
        텍스트 정제 (기본적인 정규화만)
        
        - 공백 정규화
        - 줄바꿈 제거
        """
        if not text:
            return ""
        
        # 연속 공백 제거
        cleaned = re.sub(r'\s+', ' ', text)
        # 앞뒤 공백 제거
        cleaned = cleaned.strip()
        
        return cleaned
    
    # ========================================
    # 규칙 함수들 (개별 체크)
    # ========================================
    
    def _check_length(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """글자 수 체크"""
        # 공백 제거한 실제 글자 수
        text_no_space = text.replace(" ", "")
        metadata["length"] = len(text_no_space)
        
        if len(text_no_space) < self.config.min_length:
            return RejectReason.TOO_SHORT
        return None
    
    def _check_special_chars_only(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """특수문자만 있는지 체크"""
        # 문자, 숫자 제거
        only_special = re.sub(r'[a-zA-Z0-9가-힣\s]', '', text)
        
        if len(only_special) > 0 and len(only_special) == len(text.replace(" ", "")):
            return RejectReason.SPECIAL_CHARS_ONLY
        return None
    
    def _check_emoji_heavy(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """이모지 비율 체크"""
        if not EMOJI_AVAILABLE:
            # emoji 패키지 없으면 기본 유니코드 범위 체크
            emoji_pattern = re.compile(
                "["
                "\U0001F600-\U0001F64F"  # emoticons
                "\U0001F300-\U0001F5FF"  # symbols & pictographs
                "\U0001F680-\U0001F6FF"  # transport & map symbols
                "\U0001F1E0-\U0001F1FF"  # flags
                "]+", 
                flags=re.UNICODE
            )
            text_no_emoji = emoji_pattern.sub('', text)
        else:
            text_no_emoji = emoji.replace_emoji(text, '')
        
        text_length = len(text.replace(" ", ""))
        emoji_count = text_length - len(text_no_emoji.replace(" ", ""))
        
        metadata["emoji_count"] = emoji_count
        
        if text_length > 0:
            emoji_ratio = emoji_count / text_length
            metadata["emoji_ratio"] = emoji_ratio
            
            if emoji_ratio > self.config.max_emoji_ratio:
                return RejectReason.EMOJI_HEAVY
        
        return None
    
    def _check_repeated_chars(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """반복 문자 체크 (ㅋㅋㅋㅋㅋㅋㅋ 등)"""
        # 3개 이상 연속 반복 문자 찾기
        repeated_pattern = re.compile(r'(.)\1{2,}')
        repeated_matches = repeated_pattern.findall(text)
        
        if repeated_matches:
            repeated_chars = sum(len(match) * 2 for match in repeated_matches)
            text_length = len(text.replace(" ", ""))
            
            if text_length > 0:
                repeated_ratio = repeated_chars / text_length
                metadata["repeated_char_ratio"] = repeated_ratio
                
                if repeated_ratio > self.config.max_repeated_char_ratio:
                    return RejectReason.LOW_INFORMATION
        
        return None
    
    def _check_url(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """URL 포함 체크"""
        if not self.config.enable_url_check:
            return None
        
        # URL 패턴
        url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            r'|(?:www\.)[a-zA-Z0-9-]+\.[a-zA-Z]{2,}'
            r'|[a-zA-Z0-9-]+\.(?:com|net|org|co\.kr|kr)'
        )
        
        if url_pattern.search(text):
            metadata["contains_url"] = True
            return RejectReason.URL_SPAM
        
        return None
    
    def _check_profanity(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """욕설/비속어 체크"""
        if not self.config.enable_profanity_check:
            return None
        
        text_lower = text.lower()
        
        # 사전 기반 체크
        for profanity in self.profanity_words:
            if profanity in text_lower:
                metadata["profanity_detected"] = profanity
                return RejectReason.ABUSIVE
        
        # 변형 욕설 패턴 (자음 분리 등)
        # 예: ㅅㅂ, ㅆㅂ, ㅂㅅ 등
        profanity_patterns = [
            r'[ㅅㅆ][\s]*[ㅂ]',
            r'[ㅂ][\s]*[ㅅ]',
            r'[ㅈ][\s]*[ㄹ]',
        ]
        
        for pattern in profanity_patterns:
            if re.search(pattern, text):
                metadata["profanity_pattern_detected"] = pattern
                return RejectReason.ABUSIVE
        
        return None
    
    def _check_greeting_only(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """인사만 있는지 체크"""
        greetings = self.reaction_patterns.get("greetings", [])
        
        for greeting in greetings:
            # 정확히 일치하거나 매우 유사한 경우
            if text == greeting or self._is_similar(text, greeting, 0.9):
                metadata["greeting_detected"] = greeting
                return RejectReason.GREETING_ONLY
        
        return None
    
    def _check_reaction_only(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """반응만 있는지 체크 (ㅋㅋㅋ, 와, 오 등)"""
        reactions = self.reaction_patterns.get("reactions", [])
        
        # 공백 제거한 텍스트
        text_compact = text.replace(" ", "")
        
        for reaction in reactions:
            # 반응이 반복되는 경우 (ㅋㅋㅋㅋㅋ)
            if text_compact.startswith(reaction):
                # 같은 문자 반복인지 확인
                if len(set(text_compact)) <= 2:  # 1~2개 문자만 반복
                    metadata["reaction_detected"] = reaction
                    return RejectReason.REACTION_ONLY
        
        # 짧고 반응 단어만 있는 경우
        if text_compact in reactions:
            metadata["reaction_detected"] = text_compact
            return RejectReason.REACTION_ONLY
        
        return None
    
    def _check_first_comment(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """첫 댓글 패턴 체크 (1등, first 등)"""
        first_comments = self.reaction_patterns.get("first_comments", [])
        
        text_lower = text.lower().replace(" ", "")
        
        for pattern in first_comments:
            if pattern in text_lower:
                metadata["first_comment_detected"] = pattern
                return RejectReason.REACTION_ONLY
        
        return None
    
    def _check_creator_praise_only(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """유튜버 칭찬만 있는지 체크"""
        creator_praises = self.reaction_patterns.get("creator_praise", [])
        
        for praise in creator_praises:
            if praise in text:
                # 다른 내용이 거의 없는 경우만
                if len(text) - len(praise) < 10:
                    metadata["creator_praise_detected"] = praise
                    return RejectReason.CREATOR_PRAISE_ONLY
        
        return None
    
    def _check_promotional(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """홍보성 체크"""
        promotional_keywords = self.reaction_patterns.get("promotional_keywords", [])
        
        text_lower = text.lower()
        matched_keywords = []
        
        for keyword in promotional_keywords:
            if keyword in text_lower:
                matched_keywords.append(keyword)
        
        # 2개 이상 홍보 키워드가 있으면 홍보성으로 판단
        if len(matched_keywords) >= 2:
            metadata["promotional_keywords"] = matched_keywords
            return RejectReason.PROMOTIONAL
        
        return None
    
    def _check_duplicate(self, text: str, metadata: dict) -> Optional[RejectReason]:
        """중복 체크 (간단한 메모리 기반)"""
        if not self.config.enable_duplicate_check:
            return None
        
        # 정규화된 텍스트로 중복 체크
        normalized = text.lower().replace(" ", "")
        
        if normalized in self._seen_texts:
            metadata["duplicate_of"] = normalized
            return RejectReason.DUPLICATE_CANDIDATE
        
        self._seen_texts.add(normalized)
        return None
    
    # ========================================
    # 유틸리티
    # ========================================
    
    @staticmethod
    def _is_similar(text1: str, text2: str, threshold: float = 0.85) -> bool:
        """두 텍스트가 유사한지 체크 (SequenceMatcher)"""
        ratio = SequenceMatcher(None, text1, text2).ratio()
        return ratio >= threshold
    
    def reset_duplicate_cache(self):
        """중복 체크 캐시 초기화"""
        self._seen_texts.clear()
    
    def get_stats(self) -> dict:
        """필터 통계"""
        return {
            "version": self.config.version,
            "description": self.config.description,
            "total_rules": len(self.rules),
            "profanity_words_count": len(self.profanity_words),
            "duplicate_cache_size": len(self._seen_texts),
            "config": {
                "min_length": self.config.min_length,
                "max_emoji_ratio": self.config.max_emoji_ratio,
                "min_information_ratio": self.config.min_information_ratio,
            }
        }
