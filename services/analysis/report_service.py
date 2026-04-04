from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class IntegratedReport:
    pros: List[str]
    cons: List[str]
    key_issues: List[str]
    comment_summary: str
    conclusion: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pros": self.pros,
            "cons": self.cons,
            "key_issues": self.key_issues,
            "comment_summary": self.comment_summary,
            "conclusion": self.conclusion,
        }


class ReportGenerator(Protocol):
    def __call__(
        self,
        product_info: Dict[str, Any],
        video_summary: str,
        comment_analysis: Dict[str, Any],
        sentiment_analysis: Dict[str, Any],
    ) -> IntegratedReport:
        ...


class RuleBasedReportGenerator:
    """Default report generator used until an LLM generator is plugged in."""

    def __call__(
        self,
        product_info: Dict[str, Any],
        video_summary: str,
        comment_analysis: Dict[str, Any],
        sentiment_analysis: Dict[str, Any],
    ) -> IntegratedReport:
        product_name = str(product_info.get("name") or product_info.get("product_name") or "제품")

        positive_count = int(sentiment_analysis.get("positive_count", 0) or 0)
        negative_count = int(sentiment_analysis.get("negative_count", 0) or 0)
        neutral_count = int(sentiment_analysis.get("neutral_count", 0) or 0)
        total = positive_count + negative_count + neutral_count

        pros = self._build_pros(product_info, positive_count, video_summary)
        cons = self._build_cons(product_info, negative_count, comment_analysis)
        key_issues = self._build_key_issues(comment_analysis, sentiment_analysis)
        comment_summary = self._build_comment_summary(
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            total=total,
            product_name=product_name,
        )
        conclusion = self._build_conclusion(
            product_name=product_name,
            positive_count=positive_count,
            negative_count=negative_count,
            total=total,
        )

        return IntegratedReport(
            pros=pros,
            cons=cons,
            key_issues=key_issues,
            comment_summary=comment_summary,
            conclusion=conclusion,
        )

    def _build_pros(self, product_info: Dict[str, Any], positive_count: int, video_summary: str) -> List[str]:
        pros: List[str] = []

        if positive_count > 0:
            pros.append(f"긍정 댓글 {positive_count}건으로 전반 반응이 확인됨")

        spec_points = self._extract_list(product_info.get("highlights") or product_info.get("pros"))
        pros.extend(spec_points[:2])

        if video_summary:
            pros.append(f"영상 요약 기반 장점 단서: {video_summary[:80]}")

        if not pros:
            pros.append("장점 데이터가 충분하지 않아 추가 검증이 필요함")

        return pros[:5]

    def _build_cons(self, product_info: Dict[str, Any], negative_count: int, comment_analysis: Dict[str, Any]) -> List[str]:
        cons: List[str] = []

        if negative_count > 0:
            cons.append(f"부정 댓글 {negative_count}건으로 불만 포인트 존재")

        known_cons = self._extract_list(product_info.get("cons") or product_info.get("weaknesses"))
        cons.extend(known_cons[:2])

        risk_points = self._extract_list(comment_analysis.get("risks") or comment_analysis.get("issues"))
        cons.extend(risk_points[:2])

        if not cons:
            cons.append("명확한 단점 데이터가 부족함")

        return cons[:5]

    def _build_key_issues(self, comment_analysis: Dict[str, Any], sentiment_analysis: Dict[str, Any]) -> List[str]:
        issues = self._extract_list(comment_analysis.get("key_issues") or comment_analysis.get("issues"))

        top_negative_terms = self._extract_list(sentiment_analysis.get("top_negative_terms"))
        if top_negative_terms:
            issues.append("부정 키워드: " + ", ".join(top_negative_terms[:3]))

        if not issues:
            issues.append("핵심 이슈 추출 데이터 없음")

        return issues[:5]

    def _build_comment_summary(
        self,
        positive_count: int,
        negative_count: int,
        neutral_count: int,
        total: int,
        product_name: str,
    ) -> str:
        if total <= 0:
            return f"{product_name} 관련 댓글 데이터가 없습니다."

        return (
            f"{product_name} 댓글 {total}건 분석 결과 "
            f"긍정 {positive_count}건, 부정 {negative_count}건, 중립 {neutral_count}건입니다."
        )

    def _build_conclusion(self, product_name: str, positive_count: int, negative_count: int, total: int) -> str:
        if total <= 0:
            return f"{product_name}은 댓글/감성 데이터가 부족하여 결론 보류가 필요합니다."

        if positive_count >= negative_count * 2:
            return f"{product_name}은 현재 반응 기준으로 긍정 우세이며 구매 검토 가치가 있습니다."

        if negative_count >= positive_count * 2:
            return f"{product_name}은 부정 이슈가 상대적으로 많아 신중한 비교가 필요합니다."

        return f"{product_name}은 반응이 혼재되어 핵심 이슈 확인 후 판단하는 것이 좋습니다."

    @staticmethod
    def _extract_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str) and value.strip():
            return [value.strip()]

        return []


class ReportService:
    """
    Integrates product/video/comment/sentiment signals into a unified report.

    Swap `generator` with an LLM-backed generator later without changing callers.
    """

    def __init__(self, generator: Optional[ReportGenerator] = None) -> None:
        self._generator: ReportGenerator = generator or RuleBasedReportGenerator()

    def build_report(
        self,
        product_info: Dict[str, Any],
        video_summary: str,
        comment_analysis: Dict[str, Any],
        sentiment_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        report = self._generator(
            product_info=product_info or {},
            video_summary=video_summary or "",
            comment_analysis=comment_analysis or {},
            sentiment_analysis=sentiment_analysis or {},
        )
        return report.to_dict()
