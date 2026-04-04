"""
댓글 분석 파이프라인 오케스트레이터

전체 파이프라인을 조율하고 실행하는 메인 서비스
"""
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

from .comment_collector import YouTubeCommentCollector, Comment
from ..filters.rule_based_filter import RuleBasedFilter
from ..core.agent import AgentDecisionEngine
from ..core.models import AgentAction

# LLM 컴포넌트는 선택적 import
try:
    from ..classifiers.groq_classifier import GroqClassifier
    from ..analyzers.groq_analyzer import GroqAspectSentimentAnalyzer
    from ..analyzers.question_processor import ProductQuestionProcessor
    GROQ_AVAILABLE = True
except ImportError:
    logger.warning("Groq components not available. Install: pip install groq")
    GroqClassifier = None
    GroqAspectSentimentAnalyzer = None
    ProductQuestionProcessor = None
    GROQ_AVAILABLE = False


@dataclass
class PipelineConfig:
    """파이프라인 설정"""
    # API 키
    youtube_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    
    # 수집 설정
    max_comments: int = 100
    
    # 배치 설정
    batch_size: int = 50
    
    # 재시도 설정
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # 로깅
    log_level: str = "INFO"


@dataclass
class PipelineResult:
    """파이프라인 실행 결과"""
    video_id: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    
    # 각 단계 통계
    collected_count: int = 0
    rule_passed_count: int = 0
    rule_rejected_count: int = 0
    classified_count: int = 0
    
    # Agent 결정 통계
    analyze_count: int = 0
    auxiliary_count: int = 0
    exclude_count: int = 0
    hold_count: int = 0
    reclassify_count: int = 0
    
    # 분석 결과
    sentiment_analyzed_count: int = 0
    questions_processed_count: int = 0
    
    # 에러
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "video_id": self.video_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "statistics": {
                "collected": self.collected_count,
                "rule_filter": {
                    "passed": self.rule_passed_count,
                    "rejected": self.rule_rejected_count
                },
                "classified": self.classified_count,
                "agent_decisions": {
                    "ANALYZE": self.analyze_count,
                    "AUXILIARY_STORE": self.auxiliary_count,
                    "EXCLUDE": self.exclude_count,
                    "HOLD": self.hold_count,
                    "RECLASSIFY": self.reclassify_count
                },
                "analysis": {
                    "sentiment_analyzed": self.sentiment_analyzed_count,
                    "questions_processed": self.questions_processed_count
                }
            },
            "errors": self.errors
        }


class CommentAnalysisPipeline:
    """댓글 분석 파이프라인"""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        초기화
        
        Args:
            config: 파이프라인 설정
        """
        self.config = config or PipelineConfig()
        
        # 로깅 설정
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        
        # 컴포넌트 초기화
        logger.info("Initializing pipeline components...")
        
        self.collector = YouTubeCommentCollector(api_key=self.config.youtube_api_key)
        self.rule_filter = RuleBasedFilter()
        
        # LLM 컴포넌트는 API 키가 있을 때만 초기화
        if self.config.groq_api_key:
            self.classifier = GroqClassifier(api_key=self.config.groq_api_key)
            self.sentiment_analyzer = GroqAspectSentimentAnalyzer(api_key=self.config.groq_api_key)
            self.question_processor = ProductQuestionProcessor(api_key=self.config.groq_api_key)
        else:
            logger.warning("GROQ_API_KEY not set. LLM components will be skipped.")
            self.classifier = None
            self.sentiment_analyzer = None
            self.question_processor = None
        
        self.agent = AgentDecisionEngine()
        
        logger.info("Pipeline initialized successfully")
    
    def run(self, video_id: str) -> PipelineResult:
        """
        전체 파이프라인 실행
        
        Args:
            video_id: YouTube 비디오 ID
            
        Returns:
            PipelineResult
        """
        start_time = datetime.now()
        logger.info(f"=" * 60)
        logger.info(f"Pipeline started: video_id={video_id}")
        logger.info(f"=" * 60)
        
        result = PipelineResult(
            video_id=video_id,
            start_time=start_time,
            end_time=start_time  # 임시
        )
        
        try:
            # Stage 1: 댓글 수집
            comments = self._stage_collect(video_id, result)
            
            # Stage 2: 1차 규칙 필터
            passed_comments = self._stage_rule_filter(comments, result)
            
            # Stage 3: 2차 LLM 분류
            classified_comments = self._stage_classify(passed_comments, result)
            
            # Stage 4: Agent 결정
            decisions = self._stage_agent_decide(classified_comments, result)
            
            # Stage 5a: 감정 분석 (ANALYZE)
            self._stage_sentiment_analysis(decisions.get('ANALYZE', []), result)
            
            # Stage 5b: 질문 처리 (AUXILIARY_STORE)
            self._stage_question_processing(decisions.get('AUXILIARY_STORE', []), result)
            
            logger.info("=" * 60)
            logger.info(f"Pipeline completed successfully")
            logger.info(f"=" * 60)
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            result.errors.append(str(e))
        
        finally:
            end_time = datetime.now()
            result.end_time = end_time
            result.duration_seconds = (end_time - start_time).total_seconds()
            
            self._log_summary(result)
        
        return result
    
    def _stage_collect(self, video_id: str, result: PipelineResult) -> List[Comment]:
        """Stage 1: 댓글 수집"""
        logger.info("[Stage 1] Collecting comments...")
        
        comments = self.collector.collect_comments(
            video_id=video_id,
            max_results=self.config.max_comments
        )
        
        result.collected_count = len(comments)
        logger.info(f"Collected {len(comments)} comments")
        
        return comments
    
    def _stage_rule_filter(self, comments: List[Comment], result: PipelineResult) -> List[Dict]:
        """Stage 2: 1차 규칙 필터"""
        logger.info("[Stage 2] Rule-based filtering...")
        
        passed = []
        
        for comment in comments:
            filter_result = self.rule_filter.filter_single(comment.text_original)
            
            if filter_result.is_passed:
                passed.append({
                    'comment': comment,
                    'filter_result': filter_result
                })
                result.rule_passed_count += 1
            else:
                result.rule_rejected_count += 1
        
        logger.info(f"Passed: {result.rule_passed_count}, Rejected: {result.rule_rejected_count}")
        
        return passed
    
    def _stage_classify(self, passed_comments: List[Dict], result: PipelineResult) -> List[Dict]:
        """Stage 3: 2차 LLM 분류"""
        if not self.classifier:
            logger.warning("[Stage 3] Skipped (LLM classifier not available)")
            return passed_comments
        
        logger.info("[Stage 3] LLM classification...")
        
        classified = []
        
        for item in passed_comments:
            try:
                classification = self.classifier.classify_single(item['comment'].text_original)
                item['classification'] = classification
                classified.append(item)
                result.classified_count += 1
            except Exception as e:
                logger.error(f"Classification failed for comment {item['comment'].comment_id}: {e}")
                result.errors.append(f"Classification error: {e}")
        
        logger.info(f"Classified {result.classified_count} comments")
        
        return classified
    
    def _stage_agent_decide(self, classified_comments: List[Dict], result: PipelineResult) -> Dict[str, List]:
        """Stage 4: Agent 결정"""
        logger.info("[Stage 4] Agent decision making...")
        
        decisions = {
            'ANALYZE': [],
            'AUXILIARY_STORE': [],
            'EXCLUDE': [],
            'HOLD': [],
            'RECLASSIFY': []
        }
        
        for item in classified_comments:
            try:
                decision = self.agent.decide(
                    comment=item['comment'].text_original,
                    filter_result=item['filter_result'],
                    classification=item.get('classification')
                )
                
                item['decision'] = decision
                action = decision.final_action.value
                decisions[action].append(item)
                
                # 통계 업데이트
                if action == 'ANALYZE':
                    result.analyze_count += 1
                elif action == 'AUXILIARY_STORE':
                    result.auxiliary_count += 1
                elif action == 'EXCLUDE':
                    result.exclude_count += 1
                elif action == 'HOLD':
                    result.hold_count += 1
                elif action == 'RECLASSIFY':
                    result.reclassify_count += 1
                    
            except Exception as e:
                logger.error(f"Agent decision failed: {e}")
                result.errors.append(f"Agent error: {e}")
        
        logger.info(
            f"ANALYZE: {result.analyze_count}, "
            f"AUXILIARY: {result.auxiliary_count}, "
            f"EXCLUDE: {result.exclude_count}, "
            f"HOLD: {result.hold_count}, "
            f"RECLASSIFY: {result.reclassify_count}"
        )
        
        return decisions
    
    def _stage_sentiment_analysis(self, analyze_items: List[Dict], result: PipelineResult):
        """Stage 5a: 감정 분석"""
        if not self.sentiment_analyzer:
            logger.warning("[Stage 5a] Skipped (Sentiment analyzer not available)")
            return
        
        if not analyze_items:
            logger.info("[Stage 5a] No items to analyze")
            return
        
        logger.info(f"[Stage 5a] Analyzing sentiment for {len(analyze_items)} comments...")
        
        for item in analyze_items:
            try:
                sentiment = self.sentiment_analyzer.analyze_single(item['comment'].text_original)
                item['sentiment'] = sentiment
                result.sentiment_analyzed_count += 1
            except Exception as e:
                logger.error(f"Sentiment analysis failed: {e}")
                result.errors.append(f"Sentiment error: {e}")
        
        logger.info(f"Analyzed {result.sentiment_analyzed_count} comments")
    
    def _stage_question_processing(self, auxiliary_items: List[Dict], result: PipelineResult):
        """Stage 5b: 질문 처리"""
        if not self.question_processor:
            logger.warning("[Stage 5b] Skipped (Question processor not available)")
            return
        
        if not auxiliary_items:
            logger.info("[Stage 5b] No questions to process")
            return
        
        logger.info(f"[Stage 5b] Processing {len(auxiliary_items)} questions...")
        
        for item in auxiliary_items:
            try:
                question = self.question_processor.process_single(item['comment'].text_original)
                if question and question.is_product_related:
                    item['question'] = question
                    result.questions_processed_count += 1
            except Exception as e:
                logger.error(f"Question processing failed: {e}")
                result.errors.append(f"Question error: {e}")
        
        logger.info(f"Processed {result.questions_processed_count} questions")
    
    def _log_summary(self, result: PipelineResult):
        """최종 요약 로그"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("PIPELINE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Video ID: {result.video_id}")
        logger.info(f"Duration: {result.duration_seconds:.2f}s")
        logger.info("")
        logger.info(f"Collected: {result.collected_count}")
        logger.info(f"Rule Filter: Passed={result.rule_passed_count}, Rejected={result.rule_rejected_count}")
        logger.info(f"Classified: {result.classified_count}")
        logger.info(f"Agent Decisions:")
        logger.info(f"  - ANALYZE: {result.analyze_count}")
        logger.info(f"  - AUXILIARY_STORE: {result.auxiliary_count}")
        logger.info(f"  - EXCLUDE: {result.exclude_count}")
        logger.info(f"  - HOLD: {result.hold_count}")
        logger.info(f"  - RECLASSIFY: {result.reclassify_count}")
        logger.info(f"Sentiment Analyzed: {result.sentiment_analyzed_count}")
        logger.info(f"Questions Processed: {result.questions_processed_count}")
        
        if result.errors:
            logger.info(f"Errors: {len(result.errors)}")
            for error in result.errors[:5]:  # 최대 5개만
                logger.info(f"  - {error}")
        
        logger.info("=" * 60)
