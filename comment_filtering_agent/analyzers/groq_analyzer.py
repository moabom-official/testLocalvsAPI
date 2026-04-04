"""
감정 및 항목(Aspect) 분석 - Groq API 구현
"""
import os
from typing import Optional
from groq import Groq

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
        
        # Groq 클라이언트 생성
        self.client = Groq(api_key=self.api_key)
    
    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> str:
        """
        Groq API 호출
        
        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트
            temperature: 온도
            max_tokens: 최대 토큰 수
            
        Returns:
            LLM 응답 텍스트
        """
        # 메시지 구성
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Groq API 호출
        response = self.client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}  # JSON 모드
        )
        
        # 응답 추출
        content = response.choices[0].message.content
        return content


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
