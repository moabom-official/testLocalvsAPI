"""
LLM Classification 결과 캐싱 레이어

특징:
- normalized_text 기반 중복 제거
- prompt_version 버전 관리
- TTL (Time To Live) 지원
- Redis 교체 가능한 추상 인터페이스
"""
import hashlib
import re
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass


# ============================================================================
# 캐시 항목 데이터 클래스
# ============================================================================

@dataclass
class CachedResult:
    """캐시된 분류 결과"""
    label: str
    confidence: float
    needs_recheck: bool
    cached_at: float  # Unix timestamp
    ttl: Optional[int] = None  # seconds
    metadata: Optional[Dict[str, Any]] = None
    
    def is_expired(self) -> bool:
        """TTL 만료 여부 확인"""
        if self.ttl is None:
            return False
        
        elapsed = time.time() - self.cached_at
        return elapsed > self.ttl
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "label": self.label,
            "confidence": self.confidence,
            "needs_recheck": self.needs_recheck,
            "cached_at": self.cached_at,
            "ttl": self.ttl,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CachedResult':
        """딕셔너리에서 생성"""
        return cls(
            label=data["label"],
            confidence=data["confidence"],
            needs_recheck=data["needs_recheck"],
            cached_at=data["cached_at"],
            ttl=data.get("ttl"),
            metadata=data.get("metadata")
        )


# ============================================================================
# 텍스트 정규화
# ============================================================================

class TextNormalizer:
    """텍스트 정규화 유틸리티"""
    
    @staticmethod
    def normalize(text: str) -> str:
        """
        텍스트 정규화
        
        규칙:
        1. 소문자화
        2. 연속 공백 → 단일 공백
        3. 앞뒤 공백 제거
        4. 특수문자 일부 제거 (느낌표, 물음표 제외)
        
        Args:
            text: 원본 텍스트
        
        Returns:
            정규화된 텍스트
        """
        # 소문자 변환
        normalized = text.lower()
        
        # 특수문자 제거 (느낌표, 물음표는 유지)
        normalized = re.sub(r'[^\w\s!?ㄱ-ㅎㅏ-ㅣ가-힣]', '', normalized)
        
        # 연속 공백 → 단일 공백
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # 앞뒤 공백 제거
        normalized = normalized.strip()
        
        return normalized
    
    @staticmethod
    def generate_hash(text: str, prompt_version: str = "v1") -> str:
        """
        정규화된 텍스트의 해시 생성
        
        Args:
            text: 텍스트
            prompt_version: 프롬프트 버전
        
        Returns:
            MD5 해시 (32자)
        """
        normalized = TextNormalizer.normalize(text)
        key_str = f"{prompt_version}:{normalized}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()


# ============================================================================
# 추상 캐시 인터페이스
# ============================================================================

class ClassificationCache(ABC):
    """
    분류 결과 캐시 추상 인터페이스
    
    구현체:
    - InMemoryCache: 메모리 기반 (기본)
    - RedisCache: Redis 기반 (확장)
    """
    
    def __init__(self, prompt_version: str = "v1", default_ttl: Optional[int] = None):
        """
        Args:
            prompt_version: 프롬프트 버전 (캐시 무효화용)
            default_ttl: 기본 TTL (초), None이면 무제한
        """
        self.prompt_version = prompt_version
        self.default_ttl = default_ttl
        self.normalizer = TextNormalizer()
    
    @abstractmethod
    def get(self, text: str) -> Optional[Dict[str, Any]]:
        """캐시에서 결과 조회"""
        pass
    
    @abstractmethod
    def set(self, text: str, result: Dict[str, Any], ttl: Optional[int] = None):
        """캐시에 결과 저장"""
        pass
    
    @abstractmethod
    def delete(self, text: str) -> bool:
        """캐시에서 결과 삭제"""
        pass
    
    @abstractmethod
    def clear(self):
        """캐시 전체 삭제"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계"""
        pass


# ============================================================================
# In-Memory 캐시 구현
# ============================================================================

class InMemoryCache(ClassificationCache):
    """
    메모리 기반 캐시 구현
    
    특징:
    - 빠른 접근
    - 프로세스 종료 시 사라짐
    - 메모리 제한 (max_size)
    """
    
    def __init__(
        self,
        prompt_version: str = "v1",
        default_ttl: Optional[int] = None,
        max_size: int = 10000
    ):
        """
        Args:
            prompt_version: 프롬프트 버전
            default_ttl: 기본 TTL (초)
            max_size: 최대 캐시 크기
        """
        super().__init__(prompt_version, default_ttl)
        self.max_size = max_size
        self.cache: Dict[str, CachedResult] = {}
        
        # 통계
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def get(self, text: str) -> Optional[Dict[str, Any]]:
        """캐시 조회"""
        cache_key = self.normalizer.generate_hash(text, self.prompt_version)
        
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            
            # TTL 체크
            if cached.is_expired():
                del self.cache[cache_key]
                self.misses += 1
                return None
            
            self.hits += 1
            return cached.to_dict()
        
        self.misses += 1
        return None
    
    def set(self, text: str, result: Dict[str, Any], ttl: Optional[int] = None):
        """캐시 저장"""
        # 캐시 크기 제한
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        cache_key = self.normalizer.generate_hash(text, self.prompt_version)
        
        # TTL 결정
        actual_ttl = ttl if ttl is not None else self.default_ttl
        
        # CachedResult 생성
        cached = CachedResult(
            label=result.get("label", "CHATTER"),
            confidence=result.get("confidence", 0.0),
            needs_recheck=result.get("needs_recheck", False),
            cached_at=time.time(),
            ttl=actual_ttl,
            metadata=result.get("metadata")
        )
        
        self.cache[cache_key] = cached
    
    def delete(self, text: str) -> bool:
        """캐시 삭제"""
        cache_key = self.normalizer.generate_hash(text, self.prompt_version)
        
        if cache_key in self.cache:
            del self.cache[cache_key]
            return True
        
        return False
    
    def clear(self):
        """캐시 전체 삭제"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def _evict_oldest(self):
        """가장 오래된 항목 제거 (FIFO)"""
        if not self.cache:
            return
        
        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].cached_at)
        del self.cache[oldest_key]
        self.evictions += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        
        return {
            "type": "in_memory",
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "evictions": self.evictions,
            "prompt_version": self.prompt_version
        }


# ============================================================================
# 캐시 팩토리
# ============================================================================

def create_cache(
    cache_type: str = "memory",
    prompt_version: str = "v1",
    default_ttl: Optional[int] = None,
    **kwargs
) -> ClassificationCache:
    """
    캐시 인스턴스 생성
    
    Args:
        cache_type: "memory" 또는 "redis"
        prompt_version: 프롬프트 버전
        default_ttl: 기본 TTL
        **kwargs: 추가 옵션
    
    Returns:
        ClassificationCache 인스턴스
    """
    if cache_type == "memory":
        return InMemoryCache(
            prompt_version=prompt_version,
            default_ttl=default_ttl,
            max_size=kwargs.get("max_size", 10000)
        )
    else:
        raise ValueError(f"Unknown cache type: {cache_type}")


# ============================================================================
# 사용 예시
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("Classification Cache Example")
    print("="*70)
    
    # 1. Create cache
    cache = InMemoryCache(
        prompt_version="compact_v1",
        default_ttl=3600,
        max_size=1000
    )
    
    print("\n[1] Save to cache")
    cache.set("bad heat", {"label": "PRODUCT_OPINION", "confidence": 0.95, "needs_recheck": False})
    print("  Saved: 'bad heat'")
    
    # 2. Get from cache
    print("\n[2] Get from cache")
    result = cache.get("bad heat")
    print(f"  Result: {result}")
    
    # Normalized text also works
    result2 = cache.get("  BAD   HEAT  ")
    print(f"  Normalized: {result2}")
    
    # 3. Stats
    print("\n[3] Cache stats")
    stats = cache.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # 4. Duplicate test
    print("\n[4] Duplicate test")
    comments = ["bad heat", "bad   heat", "BAD HEAT", "good performance"]
    
    for comment in comments:
        result = cache.get(comment)
        if result:
            print(f"  '{comment}' -> HIT")
        else:
            print(f"  '{comment}' -> MISS")
            cache.set(comment, {"label": "PRODUCT_OPINION", "confidence": 0.9, "needs_recheck": False})
    
    print("\nDone!")
