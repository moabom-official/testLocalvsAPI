from __future__ import annotations

from llm.base_provider import BaseLLMProvider
from llm.mock_provider import MockProvider


class SummarizationService:
    """Service for transcript summarization with pluggable provider."""

    def __init__(self, provider: BaseLLMProvider | None = None, max_chars: int = 500) -> None:
        self._provider = provider or MockProvider()
        self._max_chars = max_chars

    def summarize_transcript(self, transcript_text: str) -> str:
        text = (transcript_text or "").strip()
        if not text:
            return "요약할 자막이 없습니다."

        return self._provider.summarize(text=text, max_chars=self._max_chars)
