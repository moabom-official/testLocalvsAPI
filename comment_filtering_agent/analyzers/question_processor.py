"""
제품 질문 처리 - 프로세서
"""
import os
import time
import json
from typing import List, Optional
from pathlib import Path
from datetime import datetime
from groq import Groq

from .question_models import (
    ProductQuestion,
    QuestionCategory,
    UrgencyLevel,
    QuestionProcessorConfig
)


class ProductQuestionProcessor:
    """제품 질문 프로세서"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[QuestionProcessorConfig] = None
    ):
        """
        초기화
        
        Args:
            api_key: Groq API 키 (없으면 환경 변수 사용)
            config: 프로세서 설정
        """
        self.config = config or QuestionProcessorConfig()
        
        # API 키 설정
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GROQ_API_KEY is required. "
                "Set it via environment variable or pass it to constructor."
            )
        
        # Groq 클라이언트 생성
        self.client = Groq(api_key=self.api_key)
        
        # 프롬프트 로드
        self._load_prompts()
    
    def _load_prompts(self):
        """프롬프트 로드"""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompt_file = prompts_dir / "question_analysis_prompt.md"
        
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # System prompt 추출
        system_start = content.find("## SYSTEM PROMPT")
        system_end = content.find("---", system_start)
        self.system_prompt = self._extract_code_block(content[system_start:system_end])
        
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
    
    def _call_llm(self, user_prompt: str) -> str:
        """
        LLM API 호출
        
        Args:
            user_prompt: 사용자 프롬프트
            
        Returns:
            LLM 응답 텍스트
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            response_format={"type": "json_object"}
        )
        
        return response.choices[0].message.content
    
    def process_single(self, comment: str, index: int = 0) -> ProductQuestion:
        """
        단일 질문 댓글 처리
        
        Args:
            comment: 질문 댓글
            index: 인덱스
            
        Returns:
            ProductQuestion
        """
        start_time = time.time()
        
        # 재시도 로직
        for attempt in range(self.config.max_retries):
            try:
                # User prompt 생성
                user_prompt = self.user_prompt_template.replace("{comment}", comment)
                
                # LLM 호출
                response = self._call_llm(user_prompt)
                
                # JSON 파싱
                result_dict = self._parse_json_response(response)
                
                # 검증
                self._validate_response(result_dict)
                
                # ProductQuestion 생성
                question = self._create_question(comment, index, result_dict)
                
                # 메타데이터 추가
                latency_ms = int((time.time() - start_time) * 1000)
                question.latency_ms = latency_ms
                question.processed_at = datetime.now()
                
                # 제품 무관이면서 필터링 설정이 켜져있으면 None 반환
                if self.config.require_product_related and not question.is_product_related:
                    return None
                
                return question
                
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    # 마지막 시도 실패 시 기본값 반환
                    return self._create_fallback_question(comment, index, str(e))
                
                # 재시도 전 대기
                time.sleep(self.config.retry_delay)
        
        return self._create_fallback_question(comment, index, "Max retries exceeded")
    
    def process_batch(self, comments: List[str]) -> List[ProductQuestion]:
        """
        여러 질문 댓글 일괄 처리
        
        Args:
            comments: 질문 댓글 리스트
            
        Returns:
            ProductQuestion 리스트 (제품 무관은 제외될 수 있음)
        """
        results = []
        for i, comment in enumerate(comments):
            question = self.process_single(comment, index=i)
            if question is not None:  # 제품 관련만 추가
                results.append(question)
        
        return results
    
    def _parse_json_response(self, response: str) -> dict:
        """JSON 파싱"""
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}\nResponse: {response[:200]}")
    
    def _validate_response(self, result_dict: dict):
        """응답 검증"""
        required_fields = ["question_text", "is_product_related", "categories", "primary_category"]
        for field in required_fields:
            if field not in result_dict:
                raise ValueError(f"Missing required field: {field}")
    
    def _create_question(
        self,
        comment: str,
        index: int,
        result_dict: dict
    ) -> ProductQuestion:
        """ProductQuestion 생성"""
        # 카테고리 변환
        categories = [
            self._str_to_category(cat) 
            for cat in result_dict.get("categories", [])
        ]
        primary_category = self._str_to_category(result_dict["primary_category"])
        
        # 긴급도 변환
        urgency = None
        if result_dict.get("urgency"):
            try:
                urgency = UrgencyLevel(result_dict["urgency"])
            except ValueError:
                urgency = None
        
        question = ProductQuestion(
            index=index,
            original_comment=comment,
            question_text=result_dict["question_text"],
            is_product_related=result_dict["is_product_related"],
            categories=categories,
            primary_category=primary_category,
            has_buying_intent=result_dict.get("has_buying_intent", False),
            urgency=urgency,
            answerable_from_video=result_dict.get("answerable_from_video", False),
            mentioned_aspects=result_dict.get("mentioned_aspects", []),
            keywords=result_dict.get("keywords", []),
            reasoning=result_dict.get("reasoning"),
            confidence=result_dict.get("confidence", 0.0),
            processor_version=self.config.version,
            model_name=self.config.model_name
        )
        
        return question
    
    def _str_to_category(self, cat_str: str) -> QuestionCategory:
        """문자열을 QuestionCategory로 변환"""
        for category in QuestionCategory:
            if category.value == cat_str:
                return category
        return QuestionCategory.OTHER
    
    def _create_fallback_question(
        self,
        comment: str,
        index: int,
        error_msg: str
    ) -> ProductQuestion:
        """에러 시 기본 질문 생성"""
        return ProductQuestion(
            index=index,
            original_comment=comment,
            question_text=comment,
            is_product_related=False,
            categories=[QuestionCategory.OTHER],
            primary_category=QuestionCategory.OTHER,
            reasoning=f"Processing failed: {error_msg}",
            confidence=0.0,
            processor_version=self.config.version,
            model_name=self.config.model_name
        )
    
    def get_statistics(self, questions: List[ProductQuestion]) -> dict:
        """
        질문 통계
        
        Args:
            questions: 질문 리스트
            
        Returns:
            통계 딕셔너리
        """
        if not questions:
            return {}
        
        total = len(questions)
        product_related = sum(1 for q in questions if q.is_product_related)
        
        # 카테고리별 집계
        category_counts = {}
        for question in questions:
            for cat in question.categories:
                if cat.value not in category_counts:
                    category_counts[cat.value] = 0
                category_counts[cat.value] += 1
        
        # 구매 의도 집계
        buying_intent_count = sum(1 for q in questions if q.has_buying_intent)
        
        # 긴급도 집계
        urgency_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for question in questions:
            if question.urgency:
                urgency_counts[question.urgency.value] += 1
        
        # 영상 답변 가능 집계
        answerable_count = sum(1 for q in questions if q.answerable_from_video)
        
        return {
            "total_questions": total,
            "product_related": product_related,
            "product_related_pct": round(product_related / total * 100, 2),
            "buying_intent": buying_intent_count,
            "buying_intent_pct": round(buying_intent_count / total * 100, 2),
            "urgency_distribution": urgency_counts,
            "answerable_from_video": answerable_count,
            "answerable_pct": round(answerable_count / total * 100, 2),
            "category_distribution": sorted(
                category_counts.items(),
                key=lambda x: x[1],
                reverse=True
            ),
            "top_categories": sorted(
                category_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            "average_confidence": round(
                sum(q.confidence for q in questions) / total, 3
            ),
            "average_latency_ms": int(
                sum(q.latency_ms or 0 for q in questions) / total
            ) if any(q.latency_ms for q in questions) else None
        }


# 편의 함수
def create_processor(
    api_key: Optional[str] = None,
    model_name: str = "llama-3.3-70b-versatile",
    require_product_related: bool = True
) -> ProductQuestionProcessor:
    """
    프로세서 생성 편의 함수
    
    Args:
        api_key: Groq API 키
        model_name: 모델 이름
        require_product_related: 제품 관련 질문만 처리
        
    Returns:
        ProductQuestionProcessor
    """
    config = QuestionProcessorConfig(
        model_name=model_name,
        require_product_related=require_product_related
    )
    
    return ProductQuestionProcessor(api_key=api_key, config=config)
