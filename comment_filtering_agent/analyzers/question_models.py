"""
제품 질문 처리 - 데이터 모델
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class QuestionCategory(str, Enum):
    """질문 카테고리"""
    PERFORMANCE = "성능"          # 성능 관련
    GAMING = "게임"               # 게임 성능
    HEAT = "발열"                 # 발열 관련
    BATTERY = "배터리"            # 배터리 관련
    PRICE = "가격"                # 가격/구매
    CAMERA = "카메라"             # 카메라 성능
    COMPATIBILITY = "호환성"       # 호환성/연결
    DURABILITY = "내구성"         # 내구성/품질
    DISPLAY = "디스플레이"        # 화면 관련
    DESIGN = "디자인"             # 디자인/외관
    FEATURES = "기능"             # 기능/스펙
    PURCHASE = "구매추천"         # 구매 추천
    COMPARISON = "비교"           # 제품 비교
    OTHER = "기타"                # 기타


class UrgencyLevel(str, Enum):
    """질문 긴급도"""
    HIGH = "HIGH"           # 높음 (구매 직전)
    MEDIUM = "MEDIUM"       # 보통
    LOW = "LOW"             # 낮음


@dataclass
class ProductQuestion:
    """제품 질문 분석 결과"""
    # 기본 정보
    index: int                              # 댓글 인덱스
    original_comment: str                   # 원본 댓글
    
    # 질문 정보
    question_text: str                      # 추출된 질문 텍스트
    is_product_related: bool                # 제품 관련 여부
    
    # 분류
    categories: List[QuestionCategory]      # 질문 카테고리 (다중 가능)
    primary_category: QuestionCategory      # 주 카테고리
    
    # 추가 속성
    has_buying_intent: bool = False         # 구매 의도 포함 여부
    urgency: Optional[UrgencyLevel] = None  # 긴급도
    answerable_from_video: bool = False     # 영상에서 답변 가능 여부
    
    # 추출 정보
    mentioned_aspects: List[str] = field(default_factory=list)  # 언급된 제품 특성
    keywords: List[str] = field(default_factory=list)           # 주요 키워드
    
    # 메타정보
    reasoning: Optional[str] = None         # 판단 이유
    confidence: float = 0.0                 # 신뢰도
    processor_version: str = "1.0"
    model_name: Optional[str] = None
    latency_ms: Optional[int] = None
    processed_at: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "index": self.index,
            "original_comment": self.original_comment,
            "question_text": self.question_text,
            "is_product_related": self.is_product_related,
            "categories": [cat.value for cat in self.categories],
            "primary_category": self.primary_category.value,
            "has_buying_intent": self.has_buying_intent,
            "urgency": self.urgency.value if self.urgency else None,
            "answerable_from_video": self.answerable_from_video,
            "mentioned_aspects": self.mentioned_aspects,
            "keywords": self.keywords,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "metadata": {
                "processor_version": self.processor_version,
                "model_name": self.model_name,
                "latency_ms": self.latency_ms
            },
            "processed_at": self.processed_at.isoformat() if self.processed_at else None
        }


@dataclass
class QuestionProcessorConfig:
    """질문 프로세서 설정"""
    # 모델 설정
    model_name: str = "llama-3.3-70b-versatile"
    temperature: float = 0.1
    max_tokens: int = 800
    
    # 필터링 설정
    min_confidence: float = 0.5         # 최소 신뢰도
    require_product_related: bool = True # 제품 관련 질문만 처리
    
    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 30
    
    # 버전 정보
    version: str = "1.0"
    description: str = "LLM 기반 제품 질문 프로세서"


# 질문 카테고리별 키워드 매핑
CATEGORY_KEYWORDS = {
    QuestionCategory.PERFORMANCE: ["성능", "빠른지", "느린지", "속도", "처리"],
    QuestionCategory.GAMING: ["게임", "프레임", "fps", "렉", "겜"],
    QuestionCategory.HEAT: ["발열", "뜨거운지", "열", "온도"],
    QuestionCategory.BATTERY: ["배터리", "충전", "지속시간", "오래가는지"],
    QuestionCategory.PRICE: ["가격", "얼마", "비싼지", "할인"],
    QuestionCategory.CAMERA: ["카메라", "사진", "화질", "야간촬영"],
    QuestionCategory.COMPATIBILITY: ["호환", "연결", "지원", "작동"],
    QuestionCategory.DURABILITY: ["내구성", "튼튼", "깨지는지", "고장"],
    QuestionCategory.DISPLAY: ["화면", "디스플레이", "밝기", "해상도"],
    QuestionCategory.DESIGN: ["디자인", "예쁜지", "크기", "무게"],
    QuestionCategory.FEATURES: ["기능", "있나요", "지원", "스펙"],
    QuestionCategory.PURCHASE: ["살까요", "추천", "괜찮을까요", "어떤가요"],
    QuestionCategory.COMPARISON: ["vs", "비교", "차이", "어느게"]
}
