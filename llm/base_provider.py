from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Provider abstraction for text generation tasks."""

    @abstractmethod
    def summarize(self, text: str, max_chars: int = 500) -> str:
        """Return a summary string from the given source text."""
        raise NotImplementedError
