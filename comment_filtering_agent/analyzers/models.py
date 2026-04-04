"""
감정 및 항목(Aspect) 분석 - 데이터 모델
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class SentimentType(str, Enum):
    """감정 타입"""
    POSITIVE = "POSITIVE"       # 긍정
    NEUTRAL = "NEUTRAL"         # 중립
    NEGATIVE = "NEGATIVE"       # 부정


class IntensityType(str, Enum):
    """감정 강도"""
    STRONG = "STRONG"           # 강함 (매우 좋다, 최악)
    MODERATE = "MODERATE"       # 보통 (좋다, 별로)
    WEAK = "WEAK"               # 약함 (괜찮다, 그럭저럭)


@dataclass
class AspectSentiment:
    """항목별 감정 분석 결과"""
    aspect: str                     # 항목 이름 (예: "발열", "성능")
    aspect_category: str            # 카테고리 (예: "성능", "품질")
    sentiment: SentimentType        # 감정 (POSITIVE/NEUTRAL/NEGATIVE)
    score: float                    # 감정 점수 (-1.0 ~ +1.0)
    intensity: IntensityType        # 강도 (STRONG/MODERATE/WEAK)
    mention_text: Optional[str] = None      # 언급된 텍스트 (예: "발열은 심한데")
    reasoning: Optional[str] = None         # 판단 이유
    
    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "aspect": self.aspect,
            "aspect_category": self.aspect_category,
            "sentiment": self.sentiment.value,
            "score": self.score,
            "intensity": self.intensity.value,
            "mention_text": self.mention_text,
            "reasoning": self.reasoning
        }


@dataclass
class SentimentAnalysisResult:
    """전체 감정 분석 결과"""
    # 기본 정보
    index: int                              # 댓글 인덱스
    original_comment: str                   # 원본 댓글
    
    # 전체 감정
    overall_sentiment: SentimentType        # 전체 감정
    overall_score: float                    # 전체 감정 점수 (-1.0 ~ +1.0)
    overall_intensity: IntensityType        # 전체 강도
    overall_reasoning: Optional[str] = None # 전체 감정 판단 이유
    
    # 항목별 감정
    aspects: List[AspectSentiment] = field(default_factory=list)
    
    # 메타데이터
    total_aspects: int = 0                  # 추출된 항목 수
    positive_aspects: int = 0               # 긍정 항목 수
    neutral_aspects: int = 0                # 중립 항목 수
    negative_aspects: int = 0               # 부정 항목 수
    
    # 분석 정보
    analyzer_version: str = "1.0"
    model_name: Optional[str] = None
    analyzer_type: str = "LLM"              # LLM / RULE / HYBRID
    latency_ms: Optional[int] = None
    analyzed_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "index": self.index,
            "original_comment": self.original_comment,
            "overall_sentiment": self.overall_sentiment.value,
            "overall_score": self.overall_score,
            "overall_intensity": self.overall_intensity.value,
            "overall_reasoning": self.overall_reasoning,
            "aspects": [asp.to_dict() for asp in self.aspects],
            "metadata": {
                "total_aspects": self.total_aspects,
                "positive_aspects": self.positive_aspects,
                "neutral_aspects": self.neutral_aspects,
                "negative_aspects": self.negative_aspects,
                "analyzer_version": self.analyzer_version,
                "model_name": self.model_name,
                "analyzer_type": self.analyzer_type,
                "latency_ms": self.latency_ms
            },
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None
        }
    
    def __post_init__(self):
        """후처리: 통계 계산"""
        self.total_aspects = len(self.aspects)
        self.positive_aspects = sum(1 for asp in self.aspects if asp.sentiment == SentimentType.POSITIVE)
        self.neutral_aspects = sum(1 for asp in self.aspects if asp.sentiment == SentimentType.NEUTRAL)
        self.negative_aspects = sum(1 for asp in self.aspects if asp.sentiment == SentimentType.NEGATIVE)


@dataclass
class AnalyzerConfig:
    """분석기 설정"""
    # 모델 설정
    model_name: str = "llama-3.3-70b-versatile"
    temperature: float = 0.1
    max_tokens: int = 1000
    
    # 분석 설정
    extract_mention_text: bool = True       # 언급 텍스트 추출 여부
    extract_reasoning: bool = True          # 판단 이유 추출 여부
    
    # Aspect 설정
    predefined_aspects: List[str] = field(default_factory=lambda: [
        "발열", "성능", "배터리", "소음", "카메라", 
        "가격", "디스플레이", "디자인", "휴대성", "내구성", "기능"
    ])
    
    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 30
    
    # 버전 정보
    version: str = "1.0"
    description: str = "LLM 기반 감정 및 항목 분석기"


# Aspect 카테고리 매핑
ASPECT_CATEGORIES = {
    "발열": "성능",
    "성능": "성능",
    "배터리": "성능",
    "소음": "품질",
    "디자인": "품질",
    "내구성": "품질",
    "휴대성": "사용성",
    "편의성": "사용성",
    "화면": "디스플레이",
    "디스플레이": "디스플레이",
    "카메라": "디스플레이",
    "가격": "가격",
    "기능": "기능"
}
