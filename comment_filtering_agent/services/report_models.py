"""
보고서 생성을 위한 데이터 모델

ReportData를 중심으로 보고서에 필요한 모든 통계와 인사이트를 구조화
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class SentimentType(str, Enum):
    """감정 타입"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass
class CommentStatistics:
    """댓글 통계"""
    total_collected: int  # 수집된 전체 댓글 수
    rule_filter_rejected: int  # 1차 필터에서 제외
    llm_classified: int  # 2차 분류 완료
    
    # Agent 결정 결과
    analyzed_count: int  # ANALYZE (감정 분석 완료)
    auxiliary_count: int  # AUXILIARY_STORE (질문 저장)
    excluded_count: int  # EXCLUDE (제외)
    hold_count: int  # HOLD (보류)
    reclassify_count: int  # RECLASSIFY (재분류)
    
    @property
    def exclusion_rate(self) -> float:
        """제외율 (%)"""
        if self.total_collected == 0:
            return 0.0
        excluded_total = (
            self.rule_filter_rejected + 
            self.excluded_count
        )
        return (excluded_total / self.total_collected) * 100
    
    @property
    def analysis_rate(self) -> float:
        """분석 비율 (%)"""
        if self.total_collected == 0:
            return 0.0
        return (self.analyzed_count / self.total_collected) * 100


@dataclass
class SentimentDistribution:
    """감정 분포"""
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0
    
    @property
    def total(self) -> int:
        return self.positive_count + self.neutral_count + self.negative_count
    
    @property
    def positive_ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.positive_count / self.total) * 100
    
    @property
    def neutral_ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.neutral_count / self.total) * 100
    
    @property
    def negative_ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.negative_count / self.total) * 100
    
    @property
    def sentiment_score(self) -> float:
        """
        전체 감정 스코어 (-100 ~ 100)
        positive를 +1, neutral을 0, negative를 -1로 계산
        """
        if self.total == 0:
            return 0.0
        score = (self.positive_count - self.negative_count) / self.total * 100
        return round(score, 2)


@dataclass
class AspectMention:
    """항목별 언급 통계"""
    aspect: str  # 항목 이름 (발열, 성능, 배터리 등)
    total_mentions: int  # 총 언급 횟수
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0
    
    @property
    def sentiment_distribution(self) -> SentimentDistribution:
        return SentimentDistribution(
            positive_count=self.positive_count,
            neutral_count=self.neutral_count,
            negative_count=self.negative_count
        )
    
    @property
    def dominant_sentiment(self) -> SentimentType:
        """주요 감정"""
        if self.positive_count >= self.neutral_count and self.positive_count >= self.negative_count:
            return SentimentType.POSITIVE
        elif self.negative_count >= self.neutral_count:
            return SentimentType.NEGATIVE
        else:
            return SentimentType.NEUTRAL


@dataclass
class RepresentativeComment:
    """대표 댓글"""
    comment_id: str
    text: str
    sentiment: SentimentType
    aspects: List[str]  # 언급된 항목들
    like_count: int = 0
    
    def __str__(self) -> str:
        return f'"{self.text}" (좋아요: {self.like_count})'


@dataclass
class QuestionTopic:
    """질문 주제"""
    category: str  # 성능, 게임, 발열 등
    count: int  # 해당 주제 질문 수
    examples: List[str] = field(default_factory=list)  # 예시 질문들


@dataclass
class ProductInsight:
    """제품 인사이트"""
    strengths: List[str]  # 강점
    weaknesses: List[str]  # 약점
    neutral_points: List[str]  # 중립적 특징
    user_concerns: List[str]  # 사용자 관심사 (질문에서 추출)
    summary: str  # 종합 요약


@dataclass
class ReportMetadata:
    """보고서 메타데이터"""
    video_id: str
    video_title: Optional[str] = None
    product_name: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.now)
    pipeline_version: str = "1.0.0"
    analysis_period: Optional[str] = None


@dataclass
class ReportData:
    """보고서 전체 데이터"""
    metadata: ReportMetadata
    statistics: CommentStatistics
    overall_sentiment: SentimentDistribution
    aspect_mentions: List[AspectMention]
    representative_positive: List[RepresentativeComment]
    representative_negative: List[RepresentativeComment]
    question_topics: List[QuestionTopic]
    insight: ProductInsight
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (JSON 직렬화용)"""
        return {
            'metadata': {
                'video_id': self.metadata.video_id,
                'video_title': self.metadata.video_title,
                'product_name': self.metadata.product_name,
                'generated_at': self.metadata.generated_at.isoformat(),
                'pipeline_version': self.metadata.pipeline_version,
                'analysis_period': self.metadata.analysis_period
            },
            'statistics': {
                'total_collected': self.statistics.total_collected,
                'rule_filter_rejected': self.statistics.rule_filter_rejected,
                'llm_classified': self.statistics.llm_classified,
                'analyzed_count': self.statistics.analyzed_count,
                'auxiliary_count': self.statistics.auxiliary_count,
                'excluded_count': self.statistics.excluded_count,
                'exclusion_rate': round(self.statistics.exclusion_rate, 2),
                'analysis_rate': round(self.statistics.analysis_rate, 2)
            },
            'overall_sentiment': {
                'positive_count': self.overall_sentiment.positive_count,
                'neutral_count': self.overall_sentiment.neutral_count,
                'negative_count': self.overall_sentiment.negative_count,
                'positive_ratio': round(self.overall_sentiment.positive_ratio, 2),
                'neutral_ratio': round(self.overall_sentiment.neutral_ratio, 2),
                'negative_ratio': round(self.overall_sentiment.negative_ratio, 2),
                'sentiment_score': self.overall_sentiment.sentiment_score
            },
            'aspect_analysis': [
                {
                    'aspect': am.aspect,
                    'total_mentions': am.total_mentions,
                    'positive_count': am.positive_count,
                    'neutral_count': am.neutral_count,
                    'negative_count': am.negative_count,
                    'dominant_sentiment': am.dominant_sentiment.value,
                    'sentiment_score': am.sentiment_distribution.sentiment_score
                }
                for am in self.aspect_mentions
            ],
            'representative_comments': {
                'positive': [
                    {
                        'text': c.text,
                        'aspects': c.aspects,
                        'like_count': c.like_count
                    }
                    for c in self.representative_positive
                ],
                'negative': [
                    {
                        'text': c.text,
                        'aspects': c.aspects,
                        'like_count': c.like_count
                    }
                    for c in self.representative_negative
                ]
            },
            'question_topics': [
                {
                    'category': qt.category,
                    'count': qt.count,
                    'examples': qt.examples[:3]  # 상위 3개만
                }
                for qt in self.question_topics
            ],
            'insight': {
                'strengths': self.insight.strengths,
                'weaknesses': self.insight.weaknesses,
                'neutral_points': self.insight.neutral_points,
                'user_concerns': self.insight.user_concerns,
                'summary': self.insight.summary
            }
        }
    
    def to_json(self) -> str:
        """JSON 문자열로 변환"""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ReportConfig:
    """보고서 생성 설정"""
    top_aspects_count: int = 10  # 상위 N개 항목만 표시
    representative_comments_count: int = 5  # 대표 댓글 개수
    min_aspect_mentions: int = 2  # 최소 언급 횟수 (이하는 제외)
    include_excluded_stats: bool = True  # 제외된 댓글 통계 포함 여부
    generate_markdown: bool = True
    generate_json: bool = True
    output_dir: str = "reports"
