"""
감정 및 항목(Aspect) 분석 - Groq API 구현
"""
import os
from typing import Optional
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from .base_analyzer import BaseAspectSentimentAnalyzer
from .models import AnalyzerConfig


class GroqAspectSentimentAnalyzer(BaseAspectSentimentAnalyzer):
    """Groq API를 사용한 감정 및 항목 분석기"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[AnalyzerConfig] = None
    ):
        """
        초기화
        
        Args:
            api_key: Groq API 키 (없으면 환경 변수 사용)
            config: 분석기 설정
        """
        super().__init__(config)
        
        # API 키 설정
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is required. "
                "Set it via environment variable or pass it to constructor."
            )
        
        # LangChain ChatGroq 클라이언트 생성
        self.llm = ChatGroq(
            model=self.config.model_name,
            api_key=self.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    
    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> str:
        """
        LangChain ChatGroq 호출
        (temperature / max_tokens 은 __init__ 에서 chain 생성 시 적용된 값 사용)

        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트

        Returns:
            LLM 응답 텍스트 (JSON 문자열)
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.llm.invoke(messages)
        return response.content


# 편의 함수
def create_analyzer(
    api_key: Optional[str] = None,
    model_name: str = "llama-3.3-70b-versatile",
    temperature: float = 0.1,
    max_tokens: int = 1000
) -> GroqAspectSentimentAnalyzer:
    """
    분석기 생성 편의 함수
    
    Args:
        api_key: Groq API 키
        model_name: 모델 이름
        temperature: 온도
        max_tokens: 최대 토큰 수
        
    Returns:
        GroqAspectSentimentAnalyzer
    """
    config = AnalyzerConfig(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens
    )
    
    return GroqAspectSentimentAnalyzer(api_key=api_key, config=config)
