"""
감정 및 항목(Aspect) 분석 — Azure OpenAI (GPT-4.1-mini)

원래 Groq Llama 기반이었으나 일일 토큰 한도(100K TPD) 문제로 Azure 로 전환.
클래스명(GroqAspectSentimentAnalyzer) 은 호출부 호환을 위해 그대로 유지.
"""
import os
from typing import Optional
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .base_analyzer import BaseAspectSentimentAnalyzer
from .models import AnalyzerConfig


_AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
_AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
_AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
_AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")


class GroqAspectSentimentAnalyzer(BaseAspectSentimentAnalyzer):
    """Azure OpenAI 를 사용한 감정 및 항목 분석기 (이름은 하위호환성 유지)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[AnalyzerConfig] = None
    ):
        """
        Args:
            api_key: 호환을 위해 받지만 사용하지 않음 (Azure 는 환경변수로 인증)
            config: 분석기 설정 — model_name 은 무시되고 Azure deployment 가 우선
        """
        super().__init__(config)

        if not _AZURE_ENDPOINT or not _AZURE_API_KEY:
            raise ValueError(
                "Azure OpenAI 가 구성되지 않았습니다. "
                "AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY 환경변수를 확인하세요."
            )
        self.api_key = _AZURE_API_KEY

        self.llm = AzureChatOpenAI(
            azure_endpoint=_AZURE_ENDPOINT,
            api_key=_AZURE_API_KEY,
            api_version=_AZURE_API_VERSION,
            azure_deployment=_AZURE_DEPLOYMENT,
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
        """LangChain AzureChatOpenAI 호출 (temperature / max_tokens 은 __init__ 시 적용됨)."""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = self.llm.invoke(messages)
        return response.content


def create_analyzer(
    api_key: Optional[str] = None,
    model_name: str = "gpt-4.1-mini",
    temperature: float = 0.1,
    max_tokens: int = 1000
) -> GroqAspectSentimentAnalyzer:
    """분석기 생성 편의 함수 (Azure 사용)."""
    config = AnalyzerConfig(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return GroqAspectSentimentAnalyzer(api_key=api_key, config=config)
