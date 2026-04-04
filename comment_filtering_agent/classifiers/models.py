"""
LLM 댓글 분류기 - 데이터 모델
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class CommentLabel(str, Enum):
    """댓글 분류 라벨"""
    PRODUCT_OPINION = "PRODUCT_OPINION"   # 제품 평가
    VIDEO_REACTION = "VIDEO_REACTION"     # 영상 반응
    CHATTER = "CHATTER"                   # 잡담/무의미
    QUESTION = "QUESTION"                 # 제품 관련 질문
    OFF_TOPIC = "OFF_TOPIC"               # 제품 무관


class ClassifierType(str, Enum):
    """분류기 타입"""
    FEW_SHOT = "FEW_SHOT"                 # Few-shot learning
    FINE_TUNED = "FINE_TUNED"             # Fine-tuned model


@dataclass
class ClassificationResult:
    """LLM 분류 결과"""
    # 기본 정보
    index: int                                      # 댓글 인덱스
    original_comment: str                           # 원본 댓글
    
    # 분류 결과
    label: CommentLabel                             # 분류 라벨
    confidence: float                               # 확신도 (0.0~1.0)
    rationale_short: str                            # 분류 이유 (한 줄)
    needs_recheck: bool                             # 재확인 필요 여부
    mentioned_product_features: List[str]           # 언급된 제품 특성
    is_product_related: bool                        # 제품 관련 여부
    
    # 메타데이터
    classifier_type: ClassifierType = ClassifierType.FEW_SHOT
    model_name: str = "unknown"
    prompt_version: str = "1.0"
    llm_provider: str = "unknown"
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    
    # 추가 정보
    raw_response: Optional[dict] = None             # 원본 LLM 응답
    classification_metadata: dict = field(default_factory=dict)
    classified_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "index": self.index,
            "original_comment": self.original_comment,
            "label": self.label.value,
            "confidence": self.confidence,
            "rationale_short": self.rationale_short,
            "needs_recheck": self.needs_recheck,
            "mentioned_product_features": self.mentioned_product_features,
            "is_product_related": self.is_product_related,
            "classifier_type": self.classifier_type.value,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "llm_provider": self.llm_provider,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "classification_metadata": self.classification_metadata,
            "classified_at": self.classified_at.isoformat() if self.classified_at else None
        }
    
    @property
    def is_high_confidence(self) -> bool:
        """고확신 분류인지 (confidence >= 0.8)"""
        return self.confidence >= 0.8
    
    @property
    def is_low_confidence(self) -> bool:
        """저확신 분류인지 (confidence < 0.6)"""
        return self.confidence < 0.6
    
    @property
    def should_analyze(self) -> bool:
        """감정/항목 분석 대상인지"""
        return self.label == CommentLabel.PRODUCT_OPINION
    
    @property
    def should_store_as_question(self) -> bool:
        """질문으로 저장해야 하는지"""
        return self.label == CommentLabel.QUESTION


@dataclass
class ClassificationConfig:
    """분류기 설정"""
    # 모델 설정
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.1                        # 낮은 temperature로 일관성 확보
    max_tokens: int = 500
    
    # 프롬프트 설정
    prompt_version: str = "1.0"
    include_examples: bool = True
    num_examples: Optional[int] = None              # None이면 전체 예시 사용
    
    # 분류기 타입
    classifier_type: ClassifierType = ClassifierType.FEW_SHOT
    
    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0                        # 초
    
    # 타임아웃
    timeout: int = 30                               # 초
    
    # 확신도 임계값
    low_confidence_threshold: float = 0.6
    high_confidence_threshold: float = 0.8
    
    # 배치 크기
    batch_size: int = 10
    
    # 버전 정보
    version: str = "1.0"
    description: str = "Few-shot 기반 댓글 분류기"
