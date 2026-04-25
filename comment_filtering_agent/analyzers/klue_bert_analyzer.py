"""
감정 분석 - HuggingFace Inference API (hun3359/klue-bert-base-sentiment)
Groq는 API 호출 실패 시 fallback
"""
import os
import time
import requests
from datetime import datetime
from typing import Optional

from .models import (
    SentimentAnalysisResult,
    SentimentType,
    IntensityType,
    AnalyzerConfig,
)
from .groq_analyzer import GroqAspectSentimentAnalyzer

HF_API_URL = "https://api-inference.huggingface.co/models/hun3359/klue-bert-base-sentiment"

# 모델 라벨 → SentimentType 매핑
# hun3359/klue-bert-base-sentiment: 5단계 (0=매우부정 ~ 4=매우긍정)
_LABEL_TO_SENTIMENT = {
    "LABEL_0": SentimentType.NEGATIVE,   # 매우 부정
    "LABEL_1": SentimentType.NEGATIVE,   # 부정
    "LABEL_2": SentimentType.NEUTRAL,    # 중립
    "LABEL_3": SentimentType.POSITIVE,   # 긍정
    "LABEL_4": SentimentType.POSITIVE,   # 매우 긍정
}

# 라벨 → score (-1.0 ~ +1.0)
_LABEL_TO_BASE_SCORE = {
    "LABEL_0": -1.0,
    "LABEL_1": -0.5,
    "LABEL_2": 0.0,
    "LABEL_3": 0.5,
    "LABEL_4": 1.0,
}

# score 범위 → IntensityType
def _score_to_intensity(score: float) -> IntensityType:
    abs_score = abs(score)
    if abs_score >= 0.7:
        return IntensityType.STRONG
    elif abs_score >= 0.4:
        return IntensityType.MODERATE
    return IntensityType.WEAK


class KlueBertSentimentAnalyzer:
    """
    HuggingFace Inference API 기반 감정 분석기.
    API 호출 실패 시 GroqAspectSentimentAnalyzer로 fallback.
    """

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        groq_config: Optional[AnalyzerConfig] = None,
        hf_token: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 2,
    ):
        self._hf_token = hf_token or os.getenv("HF_TOKEN")
        self._timeout = timeout
        self._max_retries = max_retries
        self._headers = {"Authorization": f"Bearer {self._hf_token}"} if self._hf_token else {}

        self._groq_fallback = GroqAspectSentimentAnalyzer(
            api_key=groq_api_key,
            config=groq_config,
        )

    def analyze_single(self, comment: str, index: int = 0) -> SentimentAnalysisResult:
        start_time = time.time()

        for attempt in range(self._max_retries):
            try:
                response = requests.post(
                    HF_API_URL,
                    headers=self._headers,
                    json={"inputs": comment[:512]},  # BERT 토큰 한계
                    timeout=self._timeout,
                )

                # 모델 로딩 중 (cold start)
                if response.status_code == 503:
                    wait = response.json().get("estimated_time", 20)
                    print(f"[KLUE-BERT] Model loading, waiting {wait:.0f}s...")
                    time.sleep(min(wait, 30))
                    continue

                response.raise_for_status()
                data = response.json()

                # 응답 형식: [[{label, score}, ...]] 또는 [{label, score}, ...]
                if isinstance(data, list) and isinstance(data[0], list):
                    candidates = data[0]
                else:
                    candidates = data

                # confidence 가장 높은 라벨 선택
                top = max(candidates, key=lambda x: x["score"])
                label = top["label"]      # e.g. "LABEL_3"
                confidence = top["score"]  # 0.0 ~ 1.0

                sentiment = _LABEL_TO_SENTIMENT.get(label, SentimentType.NEUTRAL)
                base_score = _LABEL_TO_BASE_SCORE.get(label, 0.0)
                # confidence로 score 보정: base_score 방향 유지하되 크기를 confidence로 스케일
                overall_score = round(base_score * confidence, 4)
                intensity = _score_to_intensity(overall_score)

                latency_ms = int((time.time() - start_time) * 1000)
                print(
                    f"[KLUE-BERT] label={label} confidence={confidence:.3f} "
                    f"→ {sentiment.value} score={overall_score} latency={latency_ms}ms"
                )

                return SentimentAnalysisResult(
                    index=index,
                    original_comment=comment,
                    overall_sentiment=sentiment,
                    overall_score=overall_score,
                    overall_intensity=intensity,
                    overall_reasoning=f"HF API: {label} (confidence={confidence:.3f})",
                    aspects=[],  # BERT 단일 분류 모델 — aspect 추출 불가
                    analyzer_version="1.0",
                    model_name="hun3359/klue-bert-base-sentiment",
                    analyzer_type="HF_API",
                    latency_ms=latency_ms,
                    analyzed_at=datetime.now(),
                )

            except Exception as e:
                print(f"[KLUE-BERT] Attempt {attempt + 1} failed: {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(2)
                    continue

                # 모든 재시도 실패 → Groq fallback
                print("[KLUE-BERT] Falling back to Groq...")
                return self._groq_fallback.analyze_single(comment, index)

        # 도달 불가
        return self._groq_fallback.analyze_single(comment, index)

    def analyze_batch(self, comments: list) -> list:
        return [self.analyze_single(c, i) for i, c in enumerate(comments)]
