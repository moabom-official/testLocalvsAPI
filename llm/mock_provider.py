from __future__ import annotations

import re

from llm.base_provider import BaseLLMProvider


class MockProvider(BaseLLMProvider):
    """Deterministic mock summarizer for local development and tests."""

    def summarize(self, text: str, max_chars: int = 500) -> str:
        cleaned = self._normalize(text)
        if not cleaned:
            return "요약할 자막이 없습니다."

        sentences = self._split_sentences(cleaned)
        if not sentences:
            return cleaned[:max_chars]

        # Use the first 2 sentences as a stable mock summary.
        summary = " ".join(sentences[:2]).strip()
        return summary[:max_chars]

    @staticmethod
    def _normalize(text: str) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        return compact

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [p.strip() for p in parts if p.strip()]
