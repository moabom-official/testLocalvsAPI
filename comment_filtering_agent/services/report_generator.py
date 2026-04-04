"""
댓글 분석 보고서 생성기

파이프라인 결과를 바탕으로 Markdown 및 JSON 보고서를 생성
"""
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime
from collections import Counter

from .report_models import (
    ReportData,
    ReportMetadata,
    CommentStatistics,
    SentimentDistribution,
    AspectMention,
    RepresentativeComment,
    QuestionTopic,
    ProductInsight,
    ReportConfig,
    SentimentType
)

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    댓글 분석 보고서 생성기
    
    파이프라인 결과를 받아서:
    1. 통계 계산
    2. 인사이트 추출
    3. Markdown 보고서 생성
    4. JSON 보고서 생성
    """
    
    def __init__(self, config: Optional[ReportConfig] = None):
        self.config = config or ReportConfig()
    
    def generate_report(
        self,
        video_id: str,
        pipeline_results: Dict,
        video_title: Optional[str] = None,
        product_name: Optional[str] = None
    ) -> ReportData:
        """
        보고서 생성
        
        Args:
            video_id: 비디오 ID
            pipeline_results: 파이프라인 실행 결과
            video_title: 비디오 제목 (선택)
            product_name: 제품명 (선택)
        
        Returns:
            ReportData: 생성된 보고서 데이터
        """
        logger.info(f"Generating report for video_id={video_id}")
        
        # 1. 메타데이터
        metadata = ReportMetadata(
            video_id=video_id,
            video_title=video_title,
            product_name=product_name,
            generated_at=datetime.now()
        )
        
        # 2. 통계
        statistics = self._calculate_statistics(pipeline_results)
        
        # 3. 전체 감정 분포
        overall_sentiment = self._calculate_overall_sentiment(pipeline_results)
        
        # 4. Aspect 분석
        aspect_mentions = self._calculate_aspect_mentions(pipeline_results)
        
        # 5. 대표 댓글
        rep_positive, rep_negative = self._extract_representative_comments(
            pipeline_results
        )
        
        # 6. 질문 주제
        question_topics = self._extract_question_topics(pipeline_results)
        
        # 7. 인사이트 생성
        insight = self._generate_insight(
            overall_sentiment,
            aspect_mentions,
            question_topics
        )
        
        # ReportData 구성
        report_data = ReportData(
            metadata=metadata,
            statistics=statistics,
            overall_sentiment=overall_sentiment,
            aspect_mentions=aspect_mentions,
            representative_positive=rep_positive,
            representative_negative=rep_negative,
            question_topics=question_topics,
            insight=insight
        )
        
        logger.info("Report generation completed")
        return report_data
    
    def _calculate_statistics(self, results: Dict) -> CommentStatistics:
        """통계 계산"""
        stats = results.get('statistics', {})
        rule_filter = stats.get('rule_filter', {})
        agent_decisions = stats.get('agent_decisions', {})
        
        return CommentStatistics(
            total_collected=stats.get('collected', 0),
            rule_filter_rejected=rule_filter.get('rejected', 0),
            llm_classified=stats.get('classified', 0),
            analyzed_count=agent_decisions.get('ANALYZE', 0),
            auxiliary_count=agent_decisions.get('AUXILIARY_STORE', 0),
            excluded_count=agent_decisions.get('EXCLUDE', 0),
            hold_count=agent_decisions.get('HOLD', 0),
            reclassify_count=agent_decisions.get('RECLASSIFY', 0)
        )
    
    def _calculate_overall_sentiment(self, results: Dict) -> SentimentDistribution:
        """전체 감정 분포 계산"""
        # 실제로는 sentiment_analysis 결과에서 집계
        # 여기서는 파이프라인 결과 구조에서 추출
        sentiments = results.get('sentiments', [])
        
        positive = sum(1 for s in sentiments if s.get('sentiment') == 'positive')
        neutral = sum(1 for s in sentiments if s.get('sentiment') == 'neutral')
        negative = sum(1 for s in sentiments if s.get('sentiment') == 'negative')
        
        return SentimentDistribution(
            positive_count=positive,
            neutral_count=neutral,
            negative_count=negative
        )
    
    def _calculate_aspect_mentions(self, results: Dict) -> List[AspectMention]:
        """Aspect별 언급 통계 계산"""
        # aspect_extractions 테이블 데이터 집계
        aspects_data = results.get('aspects', [])
        
        # aspect별로 그룹화
        aspect_counter = Counter()
        aspect_sentiments = {}
        
        for aspect_data in aspects_data:
            aspect = aspect_data.get('aspect')
            sentiment = aspect_data.get('sentiment')
            
            if not aspect:
                continue
            
            aspect_counter[aspect] += 1
            
            if aspect not in aspect_sentiments:
                aspect_sentiments[aspect] = {
                    'positive': 0,
                    'neutral': 0,
                    'negative': 0
                }
            
            aspect_sentiments[aspect][sentiment] += 1
        
        # AspectMention 리스트 생성
        aspect_mentions = []
        for aspect, count in aspect_counter.most_common(self.config.top_aspects_count):
            if count < self.config.min_aspect_mentions:
                continue
            
            sentiments = aspect_sentiments[aspect]
            aspect_mentions.append(
                AspectMention(
                    aspect=aspect,
                    total_mentions=count,
                    positive_count=sentiments['positive'],
                    neutral_count=sentiments['neutral'],
                    negative_count=sentiments['negative']
                )
            )
        
        return aspect_mentions
    
    def _extract_representative_comments(
        self,
        results: Dict
    ) -> Tuple[List[RepresentativeComment], List[RepresentativeComment]]:
        """대표 긍정/부정 댓글 추출"""
        comments = results.get('analyzed_comments', [])
        
        positive_comments = []
        negative_comments = []
        
        for comment in comments:
            sentiment = comment.get('overall_sentiment')
            
            rep_comment = RepresentativeComment(
                comment_id=comment.get('comment_id', ''),
                text=comment.get('text', ''),
                sentiment=SentimentType(sentiment) if sentiment else SentimentType.NEUTRAL,
                aspects=comment.get('aspects', []),
                like_count=comment.get('like_count', 0)
            )
            
            if sentiment == 'positive':
                positive_comments.append(rep_comment)
            elif sentiment == 'negative':
                negative_comments.append(rep_comment)
        
        # 좋아요 수로 정렬
        positive_comments.sort(key=lambda x: x.like_count, reverse=True)
        negative_comments.sort(key=lambda x: x.like_count, reverse=True)
        
        # 상위 N개만
        return (
            positive_comments[:self.config.representative_comments_count],
            negative_comments[:self.config.representative_comments_count]
        )
    
    def _extract_question_topics(self, results: Dict) -> List[QuestionTopic]:
        """질문 주제 추출"""
        questions = results.get('questions', [])
        
        # 카테고리별 집계
        category_counter = Counter()
        category_examples = {}
        
        for question in questions:
            categories = question.get('categories', [])
            question_text = question.get('question_text', '')
            
            for category in categories:
                category_counter[category] += 1
                
                if category not in category_examples:
                    category_examples[category] = []
                
                if len(category_examples[category]) < 3:
                    category_examples[category].append(question_text)
        
        # QuestionTopic 리스트 생성
        question_topics = []
        for category, count in category_counter.most_common(10):
            question_topics.append(
                QuestionTopic(
                    category=category,
                    count=count,
                    examples=category_examples.get(category, [])
                )
            )
        
        return question_topics
    
    def _generate_insight(
        self,
        overall_sentiment: SentimentDistribution,
        aspect_mentions: List[AspectMention],
        question_topics: List[QuestionTopic]
    ) -> ProductInsight:
        """제품 인사이트 생성"""
        strengths = []
        weaknesses = []
        neutral_points = []
        
        # Aspect별 감정으로 강점/약점 분류
        for aspect in aspect_mentions:
            if aspect.dominant_sentiment == SentimentType.POSITIVE:
                strengths.append(f"{aspect.aspect} ({aspect.positive_count}개 긍정)")
            elif aspect.dominant_sentiment == SentimentType.NEGATIVE:
                weaknesses.append(f"{aspect.aspect} ({aspect.negative_count}개 부정)")
            else:
                neutral_points.append(f"{aspect.aspect} (의견 분분)")
        
        # 사용자 관심사 (질문에서 추출)
        user_concerns = [
            f"{qt.category} ({qt.count}개 질문)"
            for qt in question_topics[:5]
        ]
        
        # 종합 요약 생성
        summary = self._generate_summary(
            overall_sentiment,
            strengths,
            weaknesses,
            user_concerns
        )
        
        return ProductInsight(
            strengths=strengths[:5],  # 상위 5개
            weaknesses=weaknesses[:5],
            neutral_points=neutral_points[:3],
            user_concerns=user_concerns,
            summary=summary
        )
    
    def _generate_summary(
        self,
        sentiment: SentimentDistribution,
        strengths: List[str],
        weaknesses: List[str],
        concerns: List[str]
    ) -> str:
        """종합 요약 생성"""
        sentiment_desc = ""
        if sentiment.sentiment_score > 30:
            sentiment_desc = "전반적으로 긍정적인 반응"
        elif sentiment.sentiment_score < -30:
            sentiment_desc = "전반적으로 부정적인 반응"
        else:
            sentiment_desc = "긍정과 부정이 혼재된 반응"
        
        summary_parts = [sentiment_desc]
        
        if strengths:
            top_strength = strengths[0].split('(')[0].strip()
            summary_parts.append(f"주요 강점은 {top_strength}")
        
        if weaknesses:
            top_weakness = weaknesses[0].split('(')[0].strip()
            summary_parts.append(f"주요 약점은 {top_weakness}")
        
        if concerns:
            summary_parts.append(f"사용자들은 특히 {concerns[0].split('(')[0].strip()}에 관심")
        
        return ". ".join(summary_parts) + "."
    
    def save_markdown(self, report_data: ReportData, output_path: Optional[Path] = None) -> Path:
        """Markdown 보고서 저장"""
        if output_path is None:
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / f"report_{report_data.metadata.video_id}.md"
        
        markdown = self._generate_markdown(report_data)
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        logger.info(f"Markdown report saved to: {output_path}")
        return output_path
    
    def save_json(self, report_data: ReportData, output_path: Optional[Path] = None) -> Path:
        """JSON 보고서 저장"""
        if output_path is None:
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / f"report_{report_data.metadata.video_id}.json"
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_data.to_json())
        
        logger.info(f"JSON report saved to: {output_path}")
        return output_path
    
    def _generate_markdown(self, data: ReportData) -> str:
        """Markdown 생성"""
        md_parts = []
        
        # 헤더
        md_parts.append(f"# 제품 리뷰 댓글 분석 보고서\n")
        md_parts.append(f"**제품**: {data.metadata.product_name or '미지정'}\n")
        md_parts.append(f"**비디오**: {data.metadata.video_title or data.metadata.video_id}\n")
        md_parts.append(f"**생성일시**: {data.metadata.generated_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        md_parts.append("\n---\n\n")
        
        # 1. 개요
        md_parts.append("## 📊 개요\n\n")
        stats = data.statistics
        md_parts.append(f"- **수집된 댓글**: {stats.total_collected:,}개\n")
        md_parts.append(f"- **1차 필터 제외**: {stats.rule_filter_rejected:,}개\n")
        md_parts.append(f"- **분석 완료**: {stats.analyzed_count:,}개\n")
        md_parts.append(f"- **질문 수집**: {stats.auxiliary_count:,}개\n")
        md_parts.append(f"- **제외율**: {stats.exclusion_rate:.1f}%\n")
        md_parts.append(f"- **분석 비율**: {stats.analysis_rate:.1f}%\n\n")
        
        # 2. 감정 분포
        md_parts.append("## 😊 전체 감정 분포\n\n")
        sentiment = data.overall_sentiment
        md_parts.append(f"**감정 스코어**: {sentiment.sentiment_score:+.1f} / 100\n\n")
        md_parts.append(f"- 😊 긍정: {sentiment.positive_count}개 ({sentiment.positive_ratio:.1f}%)\n")
        md_parts.append(f"- 😐 중립: {sentiment.neutral_count}개 ({sentiment.neutral_ratio:.1f}%)\n")
        md_parts.append(f"- 😞 부정: {sentiment.negative_count}개 ({sentiment.negative_ratio:.1f}%)\n\n")
        
        # 3. 주요 Aspect 분석
        md_parts.append("## 🔍 주요 제품 특성 분석\n\n")
        md_parts.append("| 항목 | 언급 | 긍정 | 중립 | 부정 | 주요 감정 | 스코어 |\n")
        md_parts.append("|------|------|------|------|------|----------|--------|\n")
        
        for aspect in data.aspect_mentions:
            emoji = "✅" if aspect.dominant_sentiment == SentimentType.POSITIVE else \
                    "❌" if aspect.dominant_sentiment == SentimentType.NEGATIVE else "⚪"
            
            md_parts.append(
                f"| {aspect.aspect} | {aspect.total_mentions} | "
                f"{aspect.positive_count} | {aspect.neutral_count} | {aspect.negative_count} | "
                f"{emoji} {aspect.dominant_sentiment.value} | "
                f"{aspect.sentiment_distribution.sentiment_score:+.0f} |\n"
            )
        
        md_parts.append("\n")
        
        # 4. 대표 댓글
        md_parts.append("## 💬 대표 의견\n\n")
        
        md_parts.append("### 긍정적 의견\n\n")
        for i, comment in enumerate(data.representative_positive, 1):
            md_parts.append(f"{i}. \"{comment.text}\"\n")
            md_parts.append(f"   - 언급 항목: {', '.join(comment.aspects)}\n")
            md_parts.append(f"   - 좋아요: {comment.like_count}\n\n")
        
        md_parts.append("### 부정적 의견\n\n")
        for i, comment in enumerate(data.representative_negative, 1):
            md_parts.append(f"{i}. \"{comment.text}\"\n")
            md_parts.append(f"   - 언급 항목: {', '.join(comment.aspects)}\n")
            md_parts.append(f"   - 좋아요: {comment.like_count}\n\n")
        
        # 5. 질문 분석
        if data.question_topics:
            md_parts.append("## ❓ 주요 질문 주제\n\n")
            for topic in data.question_topics:
                md_parts.append(f"### {topic.category} ({topic.count}개 질문)\n\n")
                for example in topic.examples:
                    md_parts.append(f"- \"{example}\"\n")
                md_parts.append("\n")
        
        # 6. 종합 인사이트
        md_parts.append("## 💡 종합 인사이트\n\n")
        md_parts.append(f"**{data.insight.summary}**\n\n")
        
        if data.insight.strengths:
            md_parts.append("### ✅ 주요 강점\n\n")
            for strength in data.insight.strengths:
                md_parts.append(f"- {strength}\n")
            md_parts.append("\n")
        
        if data.insight.weaknesses:
            md_parts.append("### ❌ 주요 약점\n\n")
            for weakness in data.insight.weaknesses:
                md_parts.append(f"- {weakness}\n")
            md_parts.append("\n")
        
        if data.insight.user_concerns:
            md_parts.append("### 🤔 사용자 관심사\n\n")
            for concern in data.insight.user_concerns:
                md_parts.append(f"- {concern}\n")
            md_parts.append("\n")
        
        return "".join(md_parts)
