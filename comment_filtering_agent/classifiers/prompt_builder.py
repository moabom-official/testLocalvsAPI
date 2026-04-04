"""
LLM 댓글 분류기 - 프롬프트 빌더

Few-shot 기반 분류를 위한 프롬프트 생성
"""
from pathlib import Path
from typing import Dict, List, Optional
import json


class ClassificationPromptBuilder:
    """
    댓글 분류 프롬프트 생성기
    
    System prompt + Few-shot examples + User prompt를 조합하여
    LLM에 전달할 최종 프롬프트를 생성합니다.
    """
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Args:
            prompts_dir: 프롬프트 파일이 있는 디렉토리
        """
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent / "prompts"
        
        self.prompts_dir = prompts_dir
        
        # 프롬프트 로드
        self.system_prompt = self._load_system_prompt()
        self.few_shot_examples = self._load_few_shot_examples()
        self.user_prompt_template = self._load_user_prompt_template()
        self.json_schema = self._load_json_schema()
    
    def _load_system_prompt(self) -> str:
        """시스템 프롬프트 로드"""
        system_file = self.prompts_dir / "system_prompt.md"
        if not system_file.exists():
            raise FileNotFoundError(f"System prompt not found: {system_file}")
        
        with open(system_file, "r", encoding="utf-8") as f:
            return f.read()
    
    def _load_few_shot_examples(self) -> str:
        """Few-shot 예시 로드"""
        examples_file = self.prompts_dir / "few_shot_examples.md"
        if not examples_file.exists():
            raise FileNotFoundError(f"Few-shot examples not found: {examples_file}")
        
        with open(examples_file, "r", encoding="utf-8") as f:
            return f.read()
    
    def _load_user_prompt_template(self) -> str:
        """유저 프롬프트 템플릿 로드"""
        template_file = self.prompts_dir / "user_prompt_template.md"
        if not template_file.exists():
            raise FileNotFoundError(f"User prompt template not found: {template_file}")
        
        with open(template_file, "r", encoding="utf-8") as f:
            return f.read()
    
    def _load_json_schema(self) -> dict:
        """JSON 스키마 로드"""
        schema_file = self.prompts_dir / "classification_schema.json"
        if not schema_file.exists():
            raise FileNotFoundError(f"JSON schema not found: {schema_file}")
        
        with open(schema_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def build_messages(
        self,
        comment: str,
        product_name: str = "테크 제품",
        product_category: str = "전자기기",
        include_examples: bool = True,
        num_examples: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        LLM에 전달할 메시지 리스트 생성 (OpenAI Chat API 형식)
        
        Args:
            comment: 분류할 댓글
            product_name: 제품명
            product_category: 제품 카테고리
            include_examples: Few-shot 예시 포함 여부
            num_examples: 포함할 예시 개수 (None이면 전체)
        
        Returns:
            [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
        """
        messages = []
        
        # 1. System prompt
        system_content = self.system_prompt
        
        # 2. Few-shot examples (선택)
        if include_examples:
            examples_content = self.few_shot_examples
            
            # 예시 개수 제한 (개발자가 원할 경우)
            if num_examples is not None:
                # 간단한 구현: 전체 예시에서 앞부분만 사용
                # 더 정교하게 하려면 예시를 파싱해서 선택
                examples_content = self._limit_examples(examples_content, num_examples)
            
            system_content += "\n\n---\n\n" + examples_content
        
        messages.append({
            "role": "system",
            "content": system_content
        })
        
        # 3. User prompt
        user_content = self.user_prompt_template.format(
            comment=comment,
            product_name=product_name,
            product_category=product_category
        )
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        return messages
    
    def build_single_prompt(
        self,
        comment: str,
        product_name: str = "테크 제품",
        product_category: str = "전자기기",
        include_examples: bool = True
    ) -> str:
        """
        단일 문자열 프롬프트 생성 (단일 프롬프트 LLM용)
        
        Args:
            comment: 분류할 댓글
            product_name: 제품명
            product_category: 제품 카테고리
            include_examples: Few-shot 예시 포함 여부
        
        Returns:
            완성된 프롬프트 문자열
        """
        prompt_parts = [self.system_prompt]
        
        if include_examples:
            prompt_parts.append(self.few_shot_examples)
        
        user_prompt = self.user_prompt_template.format(
            comment=comment,
            product_name=product_name,
            product_category=product_category
        )
        prompt_parts.append(user_prompt)
        
        return "\n\n---\n\n".join(prompt_parts)
    
    def _limit_examples(self, examples_content: str, num_examples: int) -> str:
        """
        예시 개수 제한 (간단한 구현)
        
        실제로는 예시를 파싱해서 정확히 num_examples개만 선택하는 것이 좋음
        """
        # 간단하게 전체 길이의 비율로 제한
        # 더 정교한 구현은 예시를 파싱해서 개별 선택
        lines = examples_content.split('\n')
        max_lines = min(len(lines), num_examples * 20)  # 예시당 약 20줄
        return '\n'.join(lines[:max_lines])
    
    def get_json_schema(self) -> dict:
        """JSON 스키마 반환"""
        return self.json_schema
    
    def validate_response(self, response: dict) -> bool:
        """
        LLM 응답이 스키마에 맞는지 간단 검증
        
        Args:
            response: LLM이 반환한 JSON 딕셔너리
        
        Returns:
            유효하면 True
        """
        required_fields = [
            "label",
            "confidence",
            "rationale_short",
            "needs_recheck",
            "mentioned_product_features",
            "is_product_related"
        ]
        
        # 필수 필드 체크
        for field in required_fields:
            if field not in response:
                return False
        
        # label 값 체크
        valid_labels = [
            "PRODUCT_OPINION",
            "VIDEO_REACTION",
            "CHATTER",
            "QUESTION",
            "OFF_TOPIC"
        ]
        if response["label"] not in valid_labels:
            return False
        
        # confidence 범위 체크
        if not (0.0 <= response["confidence"] <= 1.0):
            return False
        
        # mentioned_product_features 타입 체크
        if not isinstance(response["mentioned_product_features"], list):
            return False
        
        return True


def get_default_prompt_builder() -> ClassificationPromptBuilder:
    """기본 프롬프트 빌더 인스턴스 반환"""
    return ClassificationPromptBuilder()


# ============================================
# 사용 예시
# ============================================

if __name__ == "__main__":
    # 프롬프트 빌더 생성
    builder = ClassificationPromptBuilder()
    
    # 예시 1: 단일 문자열 프롬프트
    print("=" * 80)
    print("예시 1: 단일 문자열 프롬프트")
    print("=" * 80)
    
    comment = "발열은 심한데 성능은 좋네요"
    prompt = builder.build_single_prompt(
        comment=comment,
        product_name="갤럭시 S25",
        product_category="스마트폰"
    )
    
    print(f"프롬프트 길이: {len(prompt)} 글자")
    print(f"\n첫 200자:\n{prompt[:200]}...")
    print()
    
    # 예시 2: Chat API 메시지 형식
    print("=" * 80)
    print("예시 2: Chat API 메시지 형식")
    print("=" * 80)
    
    messages = builder.build_messages(
        comment=comment,
        product_name="갤럭시 S25",
        product_category="스마트폰"
    )
    
    print(f"메시지 개수: {len(messages)}")
    for i, msg in enumerate(messages):
        print(f"\n메시지 {i+1} ({msg['role']}):")
        print(f"  길이: {len(msg['content'])} 글자")
        print(f"  첫 100자: {msg['content'][:100]}...")
    print()
    
    # 예시 3: JSON 스키마 확인
    print("=" * 80)
    print("예시 3: JSON 스키마")
    print("=" * 80)
    
    schema = builder.get_json_schema()
    print(json.dumps(schema, indent=2, ensure_ascii=False)[:500])
    print("...")
    print()
    
    # 예시 4: 응답 검증
    print("=" * 80)
    print("예시 4: 응답 검증")
    print("=" * 80)
    
    valid_response = {
        "label": "PRODUCT_OPINION",
        "confidence": 0.95,
        "rationale_short": "제품의 발열과 성능에 대한 평가",
        "needs_recheck": False,
        "mentioned_product_features": ["발열", "성능"],
        "is_product_related": True
    }
    
    invalid_response = {
        "label": "INVALID_LABEL",
        "confidence": 1.5,  # 범위 초과
    }
    
    print(f"유효한 응답: {builder.validate_response(valid_response)}")
    print(f"유효하지 않은 응답: {builder.validate_response(invalid_response)}")
