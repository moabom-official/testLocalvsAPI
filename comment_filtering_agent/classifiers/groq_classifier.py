"""
LLM 댓글 분류기 - Groq 구현체

Groq API를 사용한 댓글 분류
"""
from typing import Optional
import os

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("Warning: groq package not installed. Install with: pip install groq")

from comment_filtering_agent.classifiers.base_classifier import LLMClassifier
from comment_filtering_agent.classifiers.models import ClassificationConfig


class GroqClassifier(LLMClassifier):
    """
    Groq API 기반 댓글 분류기
    
    지원 모델:
    - llama-3.3-70b-versatile (추천)
    - llama-3.1-8b-instant (빠름)
    - mixtral-8x7b-32768
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[ClassificationConfig] = None
    ):
        """
        Args:
            api_key: Groq API 키 (None이면 환경변수에서 가져옴)
            config: 분류기 설정
        """
        if not GROQ_AVAILABLE:
            raise ImportError("groq package is required. Install with: pip install groq")
        
        super().__init__(config)
        
        # API 키 설정
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY가 설정되지 않았습니다.")
        
        # Groq 클라이언트 생성
        self.client = Groq(api_key=self.api_key)
        
        # 기본 모델 설정
        if self.config.model_name == "gpt-4o-mini":
            self.config.model_name = "llama-3.3-70b-versatile"
    
    def _call_llm(self, prompt: str, **kwargs) -> str:
        """
        Groq API 호출
        
        Args:
            prompt: 프롬프트 문자열
            **kwargs: 추가 파라미터
        
        Returns:
            LLM 응답 문자열
        """
        try:
            completion = self.client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that classifies YouTube comments."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=kwargs.get("temperature", self.config.temperature),
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                top_p=1,
                stream=False,
                response_format={"type": "json_object"},  # JSON 모드
                stop=None
            )
            
            # 토큰 사용량 기록
            if hasattr(completion, "usage"):
                self._last_tokens_used = completion.usage.total_tokens
            
            return completion.choices[0].message.content
            
        except Exception as e:
            raise Exception(f"Groq API 호출 실패: {e}")
    
    def _get_provider_name(self) -> str:
        """LLM 제공자 이름 반환"""
        return "groq"


# 편의 함수
def create_groq_classifier(
    api_key: Optional[str] = None,
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.1
) -> GroqClassifier:
    """
    Groq 분류기 생성 편의 함수
    
    Args:
        api_key: Groq API 키
        model: 모델 이름
        temperature: Temperature (0.0~2.0)
    
    Returns:
        GroqClassifier 인스턴스
    """
    config = ClassificationConfig(
        model_name=model,
        temperature=temperature
    )
    
    return GroqClassifier(api_key=api_key, config=config)
