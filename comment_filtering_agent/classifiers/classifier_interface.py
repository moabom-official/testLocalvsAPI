"""
분류기 인터페이스 설계 및 하이브리드 전략 구현

목적:
- Few-shot LLM과 Fine-tuned Classifier를 쉽게 교체 가능하도록 설계
- 하이브리드 전략 (Fine-tuned + LLM Fallback) 지원
- 기존 파이프라인 코드 변경 최소화
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ClassifierType(str, Enum):
    """분류기 타입"""
    FEW_SHOT_LLM = "few-shot-llm"
    FINE_TUNED = "fine-tuned"
    HYBRID = "hybrid"


@dataclass
class ClassificationResult:
    """
    분류 결과 (기존 모델과 동일)
    
    모든 분류기가 이 형식으로 반환해야 함
    """
    label: str
    confidence: float
    rationale_short: str
    needs_recheck: bool
    mentioned_product_features: list
    is_product_related: bool
    
    # 확장 필드
    classifier_used: Optional[str] = None  # "fine-tuned" or "llm-fallback"
    latency_ms: Optional[float] = None


class BaseCommentClassifier(ABC):
    """
    댓글 분류기 기본 인터페이스
    
    모든 분류기는 이 인터페이스를 구현해야 함:
    - FewShotLLMClassifier
    - FineTunedClassifier
    - HybridClassifier
    """
    
    @abstractmethod
    def classify(self, comment: str) -> ClassificationResult:
        """
        댓글 분류
        
        Args:
            comment: 댓글 텍스트
        
        Returns:
            ClassificationResult: 분류 결과
        """
        pass
    
    @abstractmethod
    def classify_batch(self, comments: list[str]) -> list[ClassificationResult]:
        """
        배치 분류 (성능 최적화용)
        
        Args:
            comments: 댓글 리스트
        
        Returns:
            list[ClassificationResult]: 분류 결과 리스트
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        분류기 통계 반환
        
        Returns:
            Dict: 통계 정보
        """
        pass


# ============================================================
# Few-shot LLM Classifier (현재 방식)
# ============================================================

class FewShotLLMClassifier(BaseCommentClassifier):
    """
    Few-shot LLM 기반 분류기
    
    현재 사용 중인 GroqClassifier를 래핑
    """
    
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        from .groq_classifier import GroqClassifier
        
        self.groq_classifier = GroqClassifier(api_key, model)
        self.stats = {
            "total_calls": 0,
            "total_cost_usd": 0.0,
            "avg_latency_ms": 0.0
        }
    
    def classify(self, comment: str) -> ClassificationResult:
        """단일 댓글 분류"""
        import time
        
        start = time.time()
        result = self.groq_classifier.classify(comment)
        latency_ms = (time.time() - start) * 1000
        
        # 통계 업데이트
        self.stats["total_calls"] += 1
        self.stats["total_cost_usd"] += 0.001  # 예시 비용
        self.stats["avg_latency_ms"] = (
            (self.stats["avg_latency_ms"] * (self.stats["total_calls"] - 1) + latency_ms)
            / self.stats["total_calls"]
        )
        
        result.classifier_used = "few-shot-llm"
        result.latency_ms = latency_ms
        
        return result
    
    def classify_batch(self, comments: list[str]) -> list[ClassificationResult]:
        """배치 분류 (순차 처리)"""
        return [self.classify(comment) for comment in comments]
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self.stats.copy()


# ============================================================
# Fine-tuned Classifier (미래 방식)
# ============================================================

class FineTunedClassifier(BaseCommentClassifier):
    """
    Fine-tuned 모델 기반 분류기
    
    사용 모델: KoBERT, KoELECTRA 등
    """
    
    def __init__(self, model_path: str, use_gpu: bool = True):
        """
        Args:
            model_path: 학습된 모델 경로
            use_gpu: GPU 사용 여부
        """
        self.model_path = model_path
        self.use_gpu = use_gpu
        self.model = None
        self.tokenizer = None
        
        self.stats = {
            "total_calls": 0,
            "avg_latency_ms": 0.0,
            "gpu_used": use_gpu
        }
        
        self._load_model()
    
    def _load_model(self):
        """모델 로드"""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            import torch
            
            logger.info(f"Loading fine-tuned model from {self.model_path}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
            
            if self.use_gpu and torch.cuda.is_available():
                self.model = self.model.cuda()
                logger.info("Model loaded on GPU")
            else:
                logger.info("Model loaded on CPU")
            
            self.model.eval()
            
        except ImportError:
            logger.error("transformers not installed. Install with: pip install transformers torch")
            raise
    
    def classify(self, comment: str) -> ClassificationResult:
        """단일 댓글 분류"""
        import time
        import torch
        
        start = time.time()
        
        # Tokenize
        inputs = self.tokenizer(
            comment,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            padding=True
        )
        
        if self.use_gpu and torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        # Predict
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)
            confidence, predicted = torch.max(probs, dim=-1)
        
        # Label mapping
        label_map = {
            0: "PRODUCT_OPINION",
            1: "VIDEO_REACTION",
            2: "CHATTER",
            3: "QUESTION",
            4: "OFF_TOPIC"
        }
        
        label = label_map[predicted.item()]
        confidence_score = confidence.item()
        
        latency_ms = (time.time() - start) * 1000
        
        # 통계 업데이트
        self.stats["total_calls"] += 1
        self.stats["avg_latency_ms"] = (
            (self.stats["avg_latency_ms"] * (self.stats["total_calls"] - 1) + latency_ms)
            / self.stats["total_calls"]
        )
        
        # ClassificationResult 생성
        result = ClassificationResult(
            label=label,
            confidence=confidence_score,
            rationale_short=f"Fine-tuned model prediction (conf: {confidence_score:.2f})",
            needs_recheck=(confidence_score < 0.6),
            mentioned_product_features=[],  # Fine-tuned는 aspect 추출 안 함
            is_product_related=(label in ["PRODUCT_OPINION", "QUESTION"]),
            classifier_used="fine-tuned",
            latency_ms=latency_ms
        )
        
        return result
    
    def classify_batch(self, comments: list[str]) -> list[ClassificationResult]:
        """배치 분류 (최적화)"""
        import time
        import torch
        
        start = time.time()
        
        # Batch tokenize
        inputs = self.tokenizer(
            comments,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            padding=True
        )
        
        if self.use_gpu and torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        # Batch predict
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1)
            confidences, predictions = torch.max(probs, dim=-1)
        
        # Label mapping
        label_map = {
            0: "PRODUCT_OPINION",
            1: "VIDEO_REACTION",
            2: "CHATTER",
            3: "QUESTION",
            4: "OFF_TOPIC"
        }
        
        latency_ms = (time.time() - start) * 1000
        
        # Results
        results = []
        for pred, conf in zip(predictions.cpu().numpy(), confidences.cpu().numpy()):
            label = label_map[int(pred)]
            confidence_score = float(conf)
            
            results.append(
                ClassificationResult(
                    label=label,
                    confidence=confidence_score,
                    rationale_short=f"Fine-tuned batch (conf: {confidence_score:.2f})",
                    needs_recheck=(confidence_score < 0.6),
                    mentioned_product_features=[],
                    is_product_related=(label in ["PRODUCT_OPINION", "QUESTION"]),
                    classifier_used="fine-tuned",
                    latency_ms=latency_ms / len(comments)
                )
            )
        
        self.stats["total_calls"] += len(comments)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return self.stats.copy()


# ============================================================
# Hybrid Classifier (권장 전략)
# ============================================================

class HybridClassifier(BaseCommentClassifier):
    """
    하이브리드 분류기 (Fine-tuned + LLM Fallback)
    
    전략:
    1. Fine-tuned 모델로 1차 분류
    2. Confidence ≥ threshold → 결과 사용
    3. Confidence < threshold → LLM으로 재분류
    
    장점:
    - 비용 75% 절감 (85% Fine-tuned, 15% LLM)
    - 품질 유지 (어려운 케이스는 LLM)
    """
    
    def __init__(
        self,
        fine_tuned: FineTunedClassifier,
        llm_fallback: FewShotLLMClassifier,
        confidence_threshold: float = 0.8
    ):
        """
        Args:
            fine_tuned: Fine-tuned 분류기
            llm_fallback: LLM fallback 분류기
            confidence_threshold: Confidence 임계값 (기본 0.8)
        """
        self.fine_tuned = fine_tuned
        self.llm_fallback = llm_fallback
        self.threshold = confidence_threshold
        
        self.stats = {
            "total_calls": 0,
            "fine_tuned_count": 0,
            "llm_fallback_count": 0,
            "fine_tuned_ratio": 0.0,
            "avg_latency_ms": 0.0
        }
    
    def classify(self, comment: str) -> ClassificationResult:
        """하이브리드 분류"""
        import time
        
        start = time.time()
        
        # 1차: Fine-tuned
        result = self.fine_tuned.classify(comment)
        
        # Confidence 체크
        if result.confidence >= self.threshold:
            # High confidence → Fine-tuned 결과 사용
            self.stats["fine_tuned_count"] += 1
            result.classifier_used = "fine-tuned"
            
            logger.debug(
                f"Fine-tuned (conf={result.confidence:.2f}): "
                f"{comment[:30]}... → {result.label}"
            )
        else:
            # Low confidence → LLM Fallback
            logger.info(
                f"Low confidence ({result.confidence:.2f}), using LLM fallback: "
                f"{comment[:30]}..."
            )
            
            result = self.llm_fallback.classify(comment)
            self.stats["llm_fallback_count"] += 1
            result.classifier_used = "llm-fallback"
        
        # 통계 업데이트
        self.stats["total_calls"] += 1
        self.stats["fine_tuned_ratio"] = (
            self.stats["fine_tuned_count"] / self.stats["total_calls"]
        )
        
        latency_ms = (time.time() - start) * 1000
        self.stats["avg_latency_ms"] = (
            (self.stats["avg_latency_ms"] * (self.stats["total_calls"] - 1) + latency_ms)
            / self.stats["total_calls"]
        )
        result.latency_ms = latency_ms
        
        return result
    
    def classify_batch(self, comments: list[str]) -> list[ClassificationResult]:
        """배치 분류 (최적화)"""
        # 1차: 전체 Fine-tuned 배치 처리
        fine_tuned_results = self.fine_tuned.classify_batch(comments)
        
        # 2차: Low confidence만 LLM으로 재분류
        final_results = []
        low_conf_indices = []
        
        for i, result in enumerate(fine_tuned_results):
            if result.confidence >= self.threshold:
                # High confidence
                result.classifier_used = "fine-tuned"
                final_results.append(result)
                self.stats["fine_tuned_count"] += 1
            else:
                # Low confidence → LLM 재분류 대기
                low_conf_indices.append(i)
                final_results.append(None)  # Placeholder
        
        # LLM Fallback (순차 처리)
        for idx in low_conf_indices:
            logger.info(f"LLM fallback for comment {idx}")
            result = self.llm_fallback.classify(comments[idx])
            result.classifier_used = "llm-fallback"
            final_results[idx] = result
            self.stats["llm_fallback_count"] += 1
        
        # 통계 업데이트
        self.stats["total_calls"] += len(comments)
        self.stats["fine_tuned_ratio"] = (
            self.stats["fine_tuned_count"] / self.stats["total_calls"]
        )
        
        return final_results
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        stats = self.stats.copy()
        stats["fine_tuned_stats"] = self.fine_tuned.get_stats()
        stats["llm_stats"] = self.llm_fallback.get_stats()
        return stats


# ============================================================
# Classifier Factory (편의 함수)
# ============================================================

class ClassifierFactory:
    """
    분류기 팩토리
    
    설정 파일 또는 환경 변수로 분류기 생성
    """
    
    @staticmethod
    def create_classifier(
        classifier_type: ClassifierType,
        config: Dict[str, Any]
    ) -> BaseCommentClassifier:
        """
        분류기 생성
        
        Args:
            classifier_type: 분류기 타입
            config: 설정 딕셔너리
        
        Returns:
            BaseCommentClassifier: 생성된 분류기
        """
        if classifier_type == ClassifierType.FEW_SHOT_LLM:
            return FewShotLLMClassifier(
                api_key=config["groq_api_key"],
                model=config.get("model", "llama-3.3-70b-versatile")
            )
        
        elif classifier_type == ClassifierType.FINE_TUNED:
            return FineTunedClassifier(
                model_path=config["model_path"],
                use_gpu=config.get("use_gpu", True)
            )
        
        elif classifier_type == ClassifierType.HYBRID:
            fine_tuned = FineTunedClassifier(
                model_path=config["model_path"],
                use_gpu=config.get("use_gpu", True)
            )
            llm_fallback = FewShotLLMClassifier(
                api_key=config["groq_api_key"],
                model=config.get("model", "llama-3.3-70b-versatile")
            )
            return HybridClassifier(
                fine_tuned=fine_tuned,
                llm_fallback=llm_fallback,
                confidence_threshold=config.get("threshold", 0.8)
            )
        
        else:
            raise ValueError(f"Unknown classifier type: {classifier_type}")


# ============================================================
# 파이프라인 통합 예시
# ============================================================

def update_pipeline_to_use_classifier(classifier: BaseCommentClassifier):
    """
    기존 파이프라인에 새 분류기 통합
    
    변경 최소화:
    - pipeline_orchestrator.py의 _stage_classification() 메서드만 수정
    """
    
    # Before (기존 코드)
    # self.classifier = GroqClassifier(config.groq_api_key)
    
    # After (새 코드)
    # self.classifier = classifier  # 인터페이스 호환
    
    # 사용법은 동일
    # result = self.classifier.classify(comment)
    
    pass  # 예시용


# ============================================================
# 사용 예시
# ============================================================

if __name__ == "__main__":
    # 예시 1: Few-shot LLM (현재)
    print("="*60)
    print("Example 1: Few-shot LLM")
    print("="*60)
    
    config_llm = {
        "groq_api_key": "your-api-key"
    }
    
    classifier_llm = ClassifierFactory.create_classifier(
        ClassifierType.FEW_SHOT_LLM,
        config_llm
    )
    
    # result = classifier_llm.classify("카메라 진짜 좋네요")
    # print(f"Label: {result.label}")
    # print(f"Confidence: {result.confidence}")
    print("Few-shot LLM classifier created\n")
    
    # 예시 2: Fine-tuned (미래)
    print("="*60)
    print("Example 2: Fine-tuned")
    print("="*60)
    
    config_fine_tuned = {
        "model_path": "./kobert-comment-classifier-v2",
        "use_gpu": True
    }
    
    # classifier_fine_tuned = ClassifierFactory.create_classifier(
    #     ClassifierType.FINE_TUNED,
    #     config_fine_tuned
    # )
    # result = classifier_fine_tuned.classify("카메라 진짜 좋네요")
    print("Fine-tuned classifier would be created here\n")
    
    # 예시 3: Hybrid (권장)
    print("="*60)
    print("Example 3: Hybrid")
    print("="*60)
    
    config_hybrid = {
        "model_path": "./kobert-comment-classifier-v2",
        "groq_api_key": "your-api-key",
        "use_gpu": True,
        "threshold": 0.8
    }
    
    # classifier_hybrid = ClassifierFactory.create_classifier(
    #     ClassifierType.HYBRID,
    #     config_hybrid
    # )
    # 
    # result = classifier_hybrid.classify("카메라 진짜 좋네요")
    # print(f"Classifier used: {result.classifier_used}")
    # 
    # stats = classifier_hybrid.get_stats()
    # print(f"Fine-tuned ratio: {stats['fine_tuned_ratio']:.1%}")
    print("Hybrid classifier would be created here\n")
    
    print("="*60)
    print("Interface design complete")
    print("="*60)
