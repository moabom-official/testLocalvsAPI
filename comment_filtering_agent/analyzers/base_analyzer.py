"""
감정 및 항목(Aspect) 분석 - 추상 베이스 클래스
"""
from abc import ABC, abstractmethod
from typing import List, Optional
import time
import json
from pathlib import Path
from datetime import datetime

from .models import (
    SentimentAnalysisResult,
    AspectSentiment,
    SentimentType,
    IntensityType,
    AnalyzerConfig,
    ASPECT_CATEGORIES
)


class BaseAspectSentimentAnalyzer(ABC):
    """감정 및 항목 분석기 추상 클래스"""
    
    def __init__(self, config: Optional[AnalyzerConfig] = None):
        """
        초기화
        
        Args:
            config: 분석기 설정 (없으면 기본값 사용)
        """
        self.config = config or AnalyzerConfig()
        self._load_prompts()
    
    def _load_prompts(self):
        """프롬프트 로드"""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompt_file = prompts_dir / "aspect_sentiment_prompt.md"
        
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # System prompt 추출
        system_start = content.find("## SYSTEM PROMPT")
        system_end = content.find("---", system_start)
        self.system_prompt = self._extract_code_block(content[system_start:system_end])
        
        # Few-shot examples 추출
        examples_start = content.find("## FEW-SHOT EXAMPLES")
        examples_end = content.find("## USER PROMPT TEMPLATE", examples_start)
        self.few_shot_examples = content[examples_start:examples_end].strip()
        
        # User prompt template 추출
        user_start = content.find("## USER PROMPT TEMPLATE")
        user_end = content.find("## OUTPUT JSON SCHEMA", user_start)
        self.user_prompt_template = self._extract_code_block(content[user_start:user_end])
    
    def _extract_code_block(self, text: str) -> str:
        """마크다운 코드 블록에서 내용 추출"""
        lines = text.split("\n")
        in_block = False
        result = []
        
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                result.append(line)
        
        return "\n".join(result).strip()
    
    @abstractmethod
    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1000
    ) -> str:
        """
        LLM API 호출 (하위 클래스에서 구현)
        
        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트
            temperature: 온도 (기본 0.1)
            max_tokens: 최대 토큰 수
            
        Returns:
            LLM 응답 텍스트
        """
        pass
    
    def analyze_single(self, comment: str, index: int = 0) -> SentimentAnalysisResult:
        """
        단일 댓글 분석
        
        Args:
            comment: 댓글 텍스트
            index: 댓글 인덱스
            
        Returns:
            SentimentAnalysisResult
        """
        start_time = time.time()
        
        # 재시도 로직
        for attempt in range(self.config.max_retries):
            try:
                # User prompt 생성
                user_prompt = self.user_prompt_template.replace("{comment}", comment)
                
                # LLM 호출
                response = self._call_llm(
                    system_prompt=self.system_prompt,
                    user_prompt=user_prompt,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
                
                # JSON 파싱
                result_dict = self._parse_json_response(response)
                
                # 검증
                self._validate_response(result_dict)
                
                # SentimentAnalysisResult 생성
                result = self._create_result(comment, index, result_dict)
                
                # 메타데이터 추가
                latency_ms = int((time.time() - start_time) * 1000)
                result.latency_ms = latency_ms
                result.analyzed_at = datetime.now()
                
                return result
                
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    # 마지막 시도 실패 시 기본값 반환
                    return self._create_fallback_result(comment, index, str(e))
                
                # 재시도 전 대기
                time.sleep(self.config.retry_delay)
        
        # 도달 불가 (위에서 return)
        return self._create_fallback_result(comment, index, "Max retries exceeded")
    
    def analyze_batch(self, comments: List[str]) -> List[SentimentAnalysisResult]:
        """
        여러 댓글 일괄 분석
        
        Args:
            comments: 댓글 리스트
            
        Returns:
            SentimentAnalysisResult 리스트
        """
        results = []
        for i, comment in enumerate(comments):
            result = self.analyze_single(comment, index=i)
            results.append(result)
        
        return results
    
    def _parse_json_response(self, response: str) -> dict:
        """
        LLM 응답에서 JSON 파싱
        
        Args:
            response: LLM 응답 텍스트
            
        Returns:
            파싱된 딕셔너리
        """
        # ```json 블록 제거
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        # JSON 파싱
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}\nResponse: {response[:200]}")
    
    def _validate_response(self, result_dict: dict):
        """
        응답 검증
        
        Args:
            result_dict: 응답 딕셔너리
            
        Raises:
            ValueError: 필수 필드 누락 시
        """
        required_fields = ["overall_sentiment", "overall_score", "overall_intensity", "aspects"]
        for field in required_fields:
            if field not in result_dict:
                raise ValueError(f"Missing required field: {field}")
        
        # 감정 타입 검증
        if result_dict["overall_sentiment"] not in ["POSITIVE", "NEUTRAL", "NEGATIVE"]:
            raise ValueError(f"Invalid sentiment: {result_dict['overall_sentiment']}")
        
        # 점수 범위 검증
        score = result_dict["overall_score"]
        if not (-1.0 <= score <= 1.0):
            raise ValueError(f"Invalid score: {score} (must be -1.0 ~ 1.0)")
    
    def _create_result(
        self,
        comment: str,
        index: int,
        result_dict: dict
    ) -> SentimentAnalysisResult:
        """
        SentimentAnalysisResult 생성
        
        Args:
            comment: 원본 댓글
            index: 인덱스
            result_dict: LLM 응답 딕셔너리
            
        Returns:
            SentimentAnalysisResult
        """
        # Aspect 리스트 생성
        aspects = []
        for asp_dict in result_dict.get("aspects", []):
            aspect_name = asp_dict["aspect"]
            aspect_category = asp_dict.get("aspect_category", 
                                           ASPECT_CATEGORIES.get(aspect_name, "기타"))
            
            aspect = AspectSentiment(
                aspect=aspect_name,
                aspect_category=aspect_category,
                sentiment=SentimentType(asp_dict["sentiment"]),
                score=asp_dict["score"],
                intensity=IntensityType(asp_dict["intensity"]),
                mention_text=asp_dict.get("mention_text"),
                reasoning=asp_dict.get("reasoning")
            )
            aspects.append(aspect)
        
        # 결과 생성
        result = SentimentAnalysisResult(
            index=index,
            original_comment=comment,
            overall_sentiment=SentimentType(result_dict["overall_sentiment"]),
            overall_score=result_dict["overall_score"],
            overall_intensity=IntensityType(result_dict["overall_intensity"]),
            overall_reasoning=result_dict.get("overall_reasoning"),
            aspects=aspects,
            analyzer_version=self.config.version,
            model_name=self.config.model_name,
            analyzer_type="LLM"
        )
        
        return result
    
    def _create_fallback_result(
        self,
        comment: str,
        index: int,
        error_msg: str
    ) -> SentimentAnalysisResult:
        """
        에러 발생 시 기본 결과 생성
        
        Args:
            comment: 원본 댓글
            index: 인덱스
            error_msg: 에러 메시지
            
        Returns:
            SentimentAnalysisResult (중립)
        """
        return SentimentAnalysisResult(
            index=index,
            original_comment=comment,
            overall_sentiment=SentimentType.NEUTRAL,
            overall_score=0.0,
            overall_intensity=IntensityType.WEAK,
            overall_reasoning=f"Analysis failed: {error_msg}",
            aspects=[],
            analyzer_version=self.config.version,
            model_name=self.config.model_name,
            analyzer_type="LLM"
        )
    
    def get_statistics(self, results: List[SentimentAnalysisResult]) -> dict:
        """
        분석 결과 통계
        
        Args:
            results: 분석 결과 리스트
            
        Returns:
            통계 딕셔너리
        """
        if not results:
            return {}
        
        total = len(results)
        positive_count = sum(1 for r in results if r.overall_sentiment == SentimentType.POSITIVE)
        neutral_count = sum(1 for r in results if r.overall_sentiment == SentimentType.NEUTRAL)
        negative_count = sum(1 for r in results if r.overall_sentiment == SentimentType.NEGATIVE)
        
        avg_score = sum(r.overall_score for r in results) / total
        
        # Aspect 통계
        aspect_counts = {}
        aspect_sentiments = {}
        
        for result in results:
            for aspect in result.aspects:
                aspect_name = aspect.aspect
                
                if aspect_name not in aspect_counts:
                    aspect_counts[aspect_name] = 0
                    aspect_sentiments[aspect_name] = {"POSITIVE": 0, "NEUTRAL": 0, "NEGATIVE": 0}
                
                aspect_counts[aspect_name] += 1
                aspect_sentiments[aspect_name][aspect.sentiment.value] += 1
        
        return {
            "total_comments": total,
            "overall_sentiment_distribution": {
                "positive": positive_count,
                "neutral": neutral_count,
                "negative": negative_count,
                "positive_pct": round(positive_count / total * 100, 2),
                "neutral_pct": round(neutral_count / total * 100, 2),
                "negative_pct": round(negative_count / total * 100, 2)
            },
            "average_score": round(avg_score, 3),
            "total_aspects_extracted": sum(len(r.aspects) for r in results),
            "unique_aspects": len(aspect_counts),
            "top_aspects": sorted(aspect_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "aspect_sentiments": aspect_sentiments,
            "average_latency_ms": int(sum(r.latency_ms or 0 for r in results) / total) if any(r.latency_ms for r in results) else None
        }
