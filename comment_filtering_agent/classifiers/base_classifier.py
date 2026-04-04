"""
LLM 댓글 분류기 - 추상 인터페이스

다양한 LLM 제공자(OpenAI, Groq, Anthropic 등)를 지원하기 위한
추상 클래스입니다.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
import json
import time
from datetime import datetime

from comment_filtering_agent.classifiers.models import (
    ClassificationResult,
    ClassificationConfig,
    CommentLabel,
    ClassifierType
)
from comment_filtering_agent.classifiers.prompt_builder import ClassificationPromptBuilder


class LLMClassifier(ABC):
    """
    LLM 기반 댓글 분류기 추상 클래스
    
    구현체:
    - OpenAIClassifier (GPT-4, GPT-3.5)
    - GroqClassifier (Llama, Mixtral)
    - AnthropicClassifier (Claude)
    """
    
    def __init__(self, config: Optional[ClassificationConfig] = None):
        """
        Args:
            config: 분류기 설정
        """
        self.config = config or ClassificationConfig()
        self.prompt_builder = ClassificationPromptBuilder()
    
    @abstractmethod
    def _call_llm(self, prompt: str, **kwargs) -> str:
        """
        LLM API 호출 (구현 필요)
        
        Args:
            prompt: 프롬프트 문자열
            **kwargs: 추가 파라미터
        
        Returns:
            LLM 응답 문자열
        """
        pass
    
    def classify_single(
        self,
        comment: str,
        product_name: str = "테크 제품",
        product_category: str = "전자기기",
        index: int = 0
    ) -> ClassificationResult:
        """
        단일 댓글 분류
        
        Args:
            comment: 분류할 댓글
            product_name: 제품명
            product_category: 제품 카테고리
            index: 댓글 인덱스
        
        Returns:
            ClassificationResult
        """
        start_time = time.time()
        
        # 프롬프트 생성
        prompt = self.prompt_builder.build_single_prompt(
            comment=comment,
            product_name=product_name,
            product_category=product_category,
            include_examples=self.config.include_examples
        )
        
        # LLM 호출 (재시도 로직 포함)
        response_text = None
        last_error = None
        
        for attempt in range(self.config.max_retries):
            try:
                response_text = self._call_llm(
                    prompt,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    timeout=self.config.timeout
                )
                break
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                continue
        
        if response_text is None:
            raise Exception(f"LLM 호출 실패: {last_error}")
        
        # JSON 파싱
        response_dict = self._parse_json_response(response_text)
        
        # 응답 검증
        if not self.prompt_builder.validate_response(response_dict):
            raise ValueError(f"유효하지 않은 응답 형식: {response_dict}")
        
        # ClassificationResult 생성
        latency_ms = int((time.time() - start_time) * 1000)
        
        result = ClassificationResult(
            index=index,
            original_comment=comment,
            label=CommentLabel(response_dict["label"]),
            confidence=response_dict["confidence"],
            rationale_short=response_dict["rationale_short"],
            needs_recheck=response_dict.get("needs_recheck", False),
            mentioned_product_features=response_dict.get("mentioned_product_features", []),
            is_product_related=response_dict.get("is_product_related", False),
            classifier_type=self.config.classifier_type,
            model_name=self.config.model_name,
            prompt_version=self.config.prompt_version,
            llm_provider=self._get_provider_name(),
            latency_ms=latency_ms,
            raw_response=response_dict,
            classified_at=datetime.now()
        )
        
        return result
    
    def classify_batch(
        self,
        comments: List[str],
        product_name: str = "테크 제품",
        product_category: str = "전자기기",
        start_index: int = 0
    ) -> List[ClassificationResult]:
        """
        배치 댓글 분류 (토큰 절감: 10개씩 묶어서 처리)
        
        Args:
            comments: 분류할 댓글 리스트
            product_name: 제품명
            product_category: 제품 카테고리
            start_index: 시작 인덱스
        
        Returns:
            분류 결과 리스트
        """
        if not comments:
            return []
        
        start_time = time.time()
        
        # 배치 프롬프트 생성
        batch_input = []
        for i, comment in enumerate(comments):
            batch_input.append({
                "index": start_index + i,
                "comment": comment
            })
        
        batch_json = json.dumps(batch_input, ensure_ascii=False, indent=2)
        
        prompt = f"""다음 {len(comments)}개의 YouTube 댓글을 모두 분류하세요.

제품명: {product_name}
카테고리: {product_category}

댓글 목록:
{batch_json}

**분류 기준**:
- PRODUCT_OPINION: 제품 성능/품질/특성에 대한 평가
- VIDEO_REACTION: 영상/리뷰어/편집에 대한 반응
- QUESTION: 제품 관련 질문
- CHATTER: 의미 없는 짧은 반응 (ㅋㅋ, 와, 오 등)
- OFF_TOPIC: 제품과 완전히 무관한 내용

**중요**: 반드시 JSON 배열로 응답하세요. 각 항목 형식:
{{"index": 0, "label": "PRODUCT_OPINION", "confidence": 0.95, "rationale_short": "이유", "needs_recheck": false, "mentioned_product_features": ["발열", "성능"], "is_product_related": true}}

JSON 배열만 출력:"""
        
        # LLM 호출 (재시도 로직)
        response_text = None
        last_error = None
        
        for attempt in range(self.config.max_retries):
            try:
                response_text = self._call_llm(
                    prompt,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens * len(comments),
                    timeout=self.config.timeout * 2
                )
                break
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                continue
        
        if response_text is None:
            raise Exception(f"LLM 배치 호출 실패: {last_error}")
        
        # JSON 파싱 (배열)
        try:
            response_text_clean = response_text.strip()
            if response_text_clean.startswith("```json"):
                response_text_clean = response_text_clean[7:]
            if response_text_clean.endswith("```"):
                response_text_clean = response_text_clean[:-3]
            response_text_clean = response_text_clean.strip()
            
            response_array = json.loads(response_text_clean)
            if not isinstance(response_array, list):
                raise ValueError(f"응답이 JSON 배열이 아닙니다: {type(response_array)}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파싱 실패: {e}\n응답: {response_text[:300]}")
        
        # 결과 변환
        results = []
        latency_ms = int((time.time() - start_time) * 1000)
        
        for i, item in enumerate(response_array):
            idx = item.get("index", start_index + i)
            original_comment = comments[i] if i < len(comments) else ""
            
            result = ClassificationResult(
                index=idx,
                original_comment=original_comment,
                label=CommentLabel(item.get("label", "CHATTER")),
                confidence=float(item.get("confidence", 0.5)),
                rationale_short=item.get("rationale_short", ""),
                needs_recheck=item.get("needs_recheck", False),
                mentioned_product_features=item.get("mentioned_product_features", []),
                is_product_related=item.get("is_product_related", False),
                classifier_type=self.config.classifier_type,
                model_name=self.config.model_name,
                prompt_version=self.config.prompt_version,
                llm_provider=self._get_provider_name(),
                latency_ms=latency_ms // len(comments),
                raw_response=item,
                classified_at=datetime.now()
            )
            results.append(result)
        
        return results
    
    def _parse_json_response(self, response_text: str) -> dict:
        """
        LLM 응답에서 JSON 추출 및 파싱
        
        Args:
            response_text: LLM 응답 문자열
        
        Returns:
            파싱된 JSON 딕셔너리
        """
        # JSON 블록 추출 (```json ... ``` 형식)
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            json_str = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            json_str = response_text[start:end].strip()
        else:
            json_str = response_text.strip()
        
        # JSON 파싱
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 파싱 실패: {e}\n응답: {response_text}")
    
    @abstractmethod
    def _get_provider_name(self) -> str:
        """LLM 제공자 이름 반환"""
        pass
    
    def get_stats(self) -> dict:
        """분류기 통계"""
        return {
            "classifier_type": self.config.classifier_type.value,
            "model_name": self.config.model_name,
            "prompt_version": self.config.prompt_version,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "include_examples": self.config.include_examples,
            "max_retries": self.config.max_retries,
            "timeout": self.config.timeout,
            "batch_size": self.config.batch_size,
        }
