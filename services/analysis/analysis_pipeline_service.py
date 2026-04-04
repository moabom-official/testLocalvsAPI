from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from services.analysis.comment_filter_service import CommentFilterService
from services.analysis.report_service import ReportService
from services.analysis.summarization_service import SummarizationService


class CommentAnalysisBuilder(Protocol):
    def build(self, filtered_comments: List[Dict[str, Any]]) -> Dict[str, Any]:
        ...


class SentimentAnalysisBuilder(Protocol):
    def build(self, filtered_comments: List[Dict[str, Any]]) -> Dict[str, Any]:
        ...


class RuleBasedCommentAnalysisBuilder:
    """Builds issue/risk signals from filtered comment results."""

    def build(self, filtered_comments: List[Dict[str, Any]]) -> Dict[str, Any]:
        included = [c for c in filtered_comments if c.get("include_in_analysis")]
        excluded = [c for c in filtered_comments if not c.get("include_in_analysis")]

        question_comments = [
            c for c in included if c.get("class") == "PRODUCT_QUESTION"
        ]
        opinion_comments = [
            c for c in included if c.get("class") == "PRODUCT_OPINION"
        ]

        issues: List[str] = []
        risks: List[str] = []

        if question_comments:
            issues.append(f"제품 관련 질문 {len(question_comments)}건")
        if excluded:
            risks.append(f"분석 제외 댓글 {len(excluded)}건")
        if not issues:
            issues.append("핵심 질문 이슈 없음")
        if not risks:
            risks.append("주요 리스크 신호 없음")

        samples = [c.get("text", "") for c in opinion_comments[:3] if c.get("text")]

        return {
            "issues": issues,
            "risks": risks,
            "included_count": len(included),
            "excluded_count": len(excluded),
            "sample_opinions": samples,
        }


class RuleBasedSentimentAnalysisBuilder:
    """Derives sentiment counters from filter classes (rule-based bootstrap)."""

    def build(self, filtered_comments: List[Dict[str, Any]]) -> Dict[str, Any]:
        positive_count = 0
        negative_count = 0
        neutral_count = 0

        top_negative_terms: List[str] = []

        for item in filtered_comments:
            clazz = item.get("class")
            text = str(item.get("text") or "")

            if clazz == "PRODUCT_OPINION":
                if self._looks_negative(text):
                    negative_count += 1
                elif self._looks_positive(text):
                    positive_count += 1
                else:
                    neutral_count += 1
            elif clazz == "PRODUCT_QUESTION":
                neutral_count += 1

            if self._looks_negative(text):
                for token in ("비싸", "느림", "불편", "문제", "아쉽", "별로"):
                    if token in text and token not in top_negative_terms:
                        top_negative_terms.append(token)

        return {
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "top_negative_terms": top_negative_terms[:5],
        }

    @staticmethod
    def _looks_positive(text: str) -> bool:
        return any(token in text for token in ("좋", "만족", "추천", "훌륭", "최고", "괜찮"))

    @staticmethod
    def _looks_negative(text: str) -> bool:
        return any(token in text for token in ("별로", "아쉽", "불편", "문제", "비싸", "최악", "느림"))


@dataclass
class AnalysisPipelineService:
    """
    Orchestration-only pipeline.

    Execution order:
    1) comment filtering
    2) transcript summarization
    3) issue/pros-cons signal generation
    4) integrated report generation
    """

    comment_filter_service: CommentFilterService
    summarization_service: SummarizationService
    report_service: ReportService
    comment_analysis_builder: CommentAnalysisBuilder
    sentiment_analysis_builder: SentimentAnalysisBuilder

    def __init__(
        self,
        comment_filter_service: Optional[CommentFilterService] = None,
        summarization_service: Optional[SummarizationService] = None,
        report_service: Optional[ReportService] = None,
        comment_analysis_builder: Optional[CommentAnalysisBuilder] = None,
        sentiment_analysis_builder: Optional[SentimentAnalysisBuilder] = None,
    ) -> None:
        self.comment_filter_service = comment_filter_service or CommentFilterService()
        self.summarization_service = summarization_service or SummarizationService()
        self.report_service = report_service or ReportService()
        self.comment_analysis_builder = (
            comment_analysis_builder or RuleBasedCommentAnalysisBuilder()
        )
        self.sentiment_analysis_builder = (
            sentiment_analysis_builder or RuleBasedSentimentAnalysisBuilder()
        )

    def run(
        self,
        *,
        product_info: Dict[str, Any],
        comments: List[Any],
        transcript_text: str,
    ) -> Dict[str, Any]:
        # 1) 댓글 필터링
        filtered_comments = self.comment_filter_service.filter_comments(comments)

        # 2) 자막 요약
        video_summary = self.summarization_service.summarize_transcript(transcript_text)

        # 3) 장단점/핵심 이슈 생성에 필요한 중간 분석 결과 생성
        comment_analysis = self.comment_analysis_builder.build(filtered_comments)
        sentiment_analysis = self.sentiment_analysis_builder.build(filtered_comments)

        # 4) 통합 리포트 생성
        report = self.report_service.build_report(
            product_info=product_info,
            video_summary=video_summary,
            comment_analysis=comment_analysis,
            sentiment_analysis=sentiment_analysis,
        )

        return {
            "filtered_comments": filtered_comments,
            "video_summary": video_summary,
            "comment_analysis": comment_analysis,
            "sentiment_analysis": sentiment_analysis,
            "report": report,
        }
