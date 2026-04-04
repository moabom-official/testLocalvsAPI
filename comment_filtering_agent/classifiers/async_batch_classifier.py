"""
Asyncio 기반 병렬 Batch Classification

특징:
- Semaphore로 동시 요청 제한
- Batch 단위 병렬 처리
- Retry 로직 (exponential backoff)
- Timeout 처리
- Fallback 처리
"""
import asyncio
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Groq async client
try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None


# ============================================================================
# 데이터 클래스
# ============================================================================

@dataclass
class Comment:
    """댓글 데이터"""
    id: str
    text: str
    
    def __repr__(self):
        preview = self.text[:30] + "..." if len(self.text) > 30 else self.text
        return f"Comment(id={self.id}, text='{preview}')"


@dataclass
class ClassificationResult:
    """분류 결과"""
    comment_id: str
    label: str
    confidence: float
    needs_recheck: bool
    is_fallback: bool = False
    error: Optional[str] = None
    
    def __repr__(self):
        status = "FALLBACK" if self.is_fallback else "OK"
        return f"Result(id={self.comment_id}, label={self.label}, conf={self.confidence:.2f}, {status})"


# ============================================================================
# Async Batch Classifier
# ============================================================================

class AsyncBatchClassifier:
    """
    비동기 배치 분류기
    
    특징:
    - 병렬 처리로 처리량 증가
    - Semaphore로 과부하 방지
    - Retry + timeout으로 안정성 확보
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        max_concurrent: int = 5,
        timeout: int = 30,
        max_retries: int = 3,
        batch_size: int = 10
    ):
        """
        Args:
            api_key: Groq API key
            model: LLM 모델명
            max_concurrent: 최대 동시 요청 수
            timeout: 요청 타임아웃 (초)
            max_retries: 재시도 횟수
            batch_size: 배치 크기
        """
        if AsyncGroq is None:
            raise ImportError("AsyncGroq not available. Install with: pip install groq")
        
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.max_retries = max_retries
        self.batch_size = batch_size
        
        # Semaphore for concurrency control
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.fallback_count = 0
        self.retry_count = 0
    
    async def classify_batch(
        self,
        comments: List[Comment],
        batch_id: int = 0
    ) -> List[ClassificationResult]:
        """
        하나의 배치를 분류 (async)
        
        Args:
            comments: 댓글 리스트 (최대 batch_size개)
            batch_id: 배치 ID (로깅용)
        
        Returns:
            분류 결과 리스트
        """
        async with self.semaphore:
            self.total_requests += 1
            
            # Retry logic with exponential backoff
            for attempt in range(self.max_retries):
                try:
                    # Timeout wrapper
                    result = await asyncio.wait_for(
                        self._classify_batch_llm(comments, batch_id),
                        timeout=self.timeout
                    )
                    
                    self.successful_requests += 1
                    return result
                
                except asyncio.TimeoutError:
                    self.retry_count += 1
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # 1, 2, 4 seconds
                        print(f"  ⏱️  Batch {batch_id} timeout, retry {attempt+1}/{self.max_retries} after {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"  ❌ Batch {batch_id} timeout after {self.max_retries} attempts")
                        self.failed_requests += 1
                        return self._create_fallback_results(comments, "Timeout")
                
                except Exception as e:
                    self.retry_count += 1
                    error_msg = str(e)
                    
                    # Rate limit → longer wait
                    if "rate_limit" in error_msg.lower() or "429" in error_msg:
                        wait_time = 10 * (2 ** attempt)  # 10, 20, 40 seconds
                        if attempt < self.max_retries - 1:
                            print(f"  🚦 Batch {batch_id} rate limited, retry {attempt+1}/{self.max_retries} after {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        else:
                            print(f"  ❌ Batch {batch_id} rate limit exceeded")
                            self.failed_requests += 1
                            return self._create_fallback_results(comments, "Rate limit")
                    else:
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            print(f"  ⚠️  Batch {batch_id} error: {error_msg[:50]}, retry {attempt+1}/{self.max_retries}...")
                            await asyncio.sleep(wait_time)
                        else:
                            print(f"  ❌ Batch {batch_id} failed: {error_msg[:100]}")
                            self.failed_requests += 1
                            return self._create_fallback_results(comments, error_msg)
    
    async def _classify_batch_llm(
        self,
        comments: List[Comment],
        batch_id: int
    ) -> List[ClassificationResult]:
        """
        LLM API 호출 (실제 분류 수행)
        
        Args:
            comments: 댓글 리스트
            batch_id: 배치 ID
        
        Returns:
            분류 결과 리스트
        """
        # Generate prompt
        prompt = self._generate_batch_prompt(comments)
        
        # Call LLM
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a comment classifier. Output JSON array only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )
        
        # Parse response
        content = response.choices[0].message.content.strip()
        
        # Extract JSON
        import json
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        results_data = json.loads(content)
        
        # Map results to comment IDs
        results = []
        result_map = {r["id"]: r for r in results_data}
        
        for comment in comments:
            if comment.id in result_map:
                r = result_map[comment.id]
                results.append(ClassificationResult(
                    comment_id=comment.id,
                    label=r["label"],
                    confidence=r["confidence"],
                    needs_recheck=r.get("needs_recheck", False),
                    is_fallback=False
                ))
            else:
                # Missing result → fallback
                results.append(ClassificationResult(
                    comment_id=comment.id,
                    label="CHATTER",
                    confidence=0.0,
                    needs_recheck=True,
                    is_fallback=True,
                    error="Missing in LLM response"
                ))
        
        return results
    
    def _generate_batch_prompt(self, comments: List[Comment]) -> str:
        """배치 프롬프트 생성 (압축 버전)"""
        
        # Comment list
        comment_list = "\n".join([
            f'  {{"{c.id}": "{c.text}"}}'
            for c in comments
        ])
        
        prompt = f"""Classify these comments:

Labels:
- PRODUCT_OPINION: Product evaluation
- QUESTION: Product question
- VIDEO_REACTION: Video/reviewer reaction
- CHATTER: Spam, meme, meaningless
- OFF_TOPIC: Unrelated to product

Comments:
{comment_list}

Output JSON array with id, label, confidence (0-1), needs_recheck (bool).
Example: [{{"id": "1", "label": "PRODUCT_OPINION", "confidence": 0.85, "needs_recheck": false}}]

JSON only, no explanation:"""
        
        return prompt
    
    def _create_fallback_results(
        self,
        comments: List[Comment],
        error: str
    ) -> List[ClassificationResult]:
        """Fallback 결과 생성 (실패 시)"""
        self.fallback_count += len(comments)
        
        return [
            ClassificationResult(
                comment_id=c.id,
                label="CHATTER",
                confidence=0.0,
                needs_recheck=True,
                is_fallback=True,
                error=error
            )
            for c in comments
        ]
    
    async def classify_many(
        self,
        comments: List[Comment],
        show_progress: bool = True
    ) -> List[ClassificationResult]:
        """
        여러 댓글을 병렬로 분류
        
        Args:
            comments: 전체 댓글 리스트
            show_progress: 진행률 표시 여부
        
        Returns:
            전체 분류 결과 리스트
        """
        # Split into batches
        batches = [
            comments[i:i+self.batch_size]
            for i in range(0, len(comments), self.batch_size)
        ]
        
        if show_progress:
            print(f"\n🚀 Starting async classification")
            print(f"   Total: {len(comments)} comments")
            print(f"   Batches: {len(batches)} (size={self.batch_size})")
            print(f"   Max concurrent: {self.max_concurrent}")
            print(f"   Timeout: {self.timeout}s")
            print()
        
        # Create tasks
        tasks = [
            self.classify_batch(batch, batch_id=i)
            for i, batch in enumerate(batches)
        ]
        
        # Execute in parallel
        start_time = time.time()
        batch_results = await asyncio.gather(*tasks, return_exceptions=False)
        elapsed = time.time() - start_time
        
        # Flatten results
        all_results = []
        for batch_result in batch_results:
            all_results.extend(batch_result)
        
        # Statistics
        if show_progress:
            print(f"\n✅ Classification complete")
            print(f"   Time: {elapsed:.1f}s")
            print(f"   Throughput: {len(comments)/elapsed:.1f} comments/sec")
            print(f"   Success: {self.successful_requests}/{self.total_requests} batches")
            print(f"   Fallback: {self.fallback_count} comments")
            if self.retry_count > 0:
                print(f"   Retries: {self.retry_count}")
        
        return all_results
    
    def get_stats(self) -> Dict[str, Any]:
        """통계 정보"""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "fallback_count": self.fallback_count,
            "retry_count": self.retry_count,
            "success_rate": f"{self.successful_requests/self.total_requests*100:.1f}%" if self.total_requests > 0 else "0%"
        }


# ============================================================================
# 편의 함수
# ============================================================================

async def classify_comments_async(
    comments: List[Comment],
    api_key: str,
    max_concurrent: int = 5,
    batch_size: int = 10,
    timeout: int = 30
) -> List[ClassificationResult]:
    """
    댓글 비동기 분류 (편의 함수)
    
    Args:
        comments: 댓글 리스트
        api_key: Groq API key
        max_concurrent: 최대 동시 요청
        batch_size: 배치 크기
        timeout: 타임아웃
    
    Returns:
        분류 결과 리스트
    """
    classifier = AsyncBatchClassifier(
        api_key=api_key,
        max_concurrent=max_concurrent,
        batch_size=batch_size,
        timeout=timeout
    )
    
    return await classifier.classify_many(comments)


# ============================================================================
# 실행 예시
# ============================================================================

async def main():
    """실행 예시"""
    import os
    from dotenv import load_dotenv
    
    print("="*70)
    print("Async Batch Classification Example")
    print("="*70)
    
    # Load API key
    load_dotenv(override=True)
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("❌ GROQ_API_KEY not found in environment")
        return
    
    # Test comments
    test_comments = [
        Comment(id="1", text="Battery drains fast but performance is good"),
        Comment(id="2", text="Great video!"),
        Comment(id="3", text="Does it support 5G?"),
        Comment(id="4", text="lol"),
        Comment(id="5", text="What's the background music?"),
        Comment(id="6", text="Overheating issue is serious"),
        Comment(id="7", text="Thanks for the review"),
        Comment(id="8", text="Camera quality is amazing"),
        Comment(id="9", text="How much does it cost?"),
        Comment(id="10", text="First!"),
        Comment(id="11", text="Screen is too dim outdoors"),
        Comment(id="12", text="Subscribed!"),
        Comment(id="13", text="Worth the price?"),
        Comment(id="14", text="Sound quality disappoints"),
        Comment(id="15", text="Waiting for your next video"),
        Comment(id="16", text="Charging speed is impressive"),
        Comment(id="17", text="Can you review iPhone next?"),
        Comment(id="18", text="Build quality feels cheap"),
        Comment(id="19", text="Hahaha"),
        Comment(id="20", text="Better than Samsung?"),
    ]
    
    # Method 1: Using classifier directly
    print("\n[Method 1] Using AsyncBatchClassifier")
    print("-" * 70)
    
    classifier = AsyncBatchClassifier(
        api_key=api_key,
        max_concurrent=3,
        batch_size=5,
        timeout=30,
        max_retries=2
    )
    
    results = await classifier.classify_many(test_comments)
    
    # Show results
    print("\nResults:")
    for r in results[:10]:  # Show first 10
        status = "⚠️" if r.is_fallback else "✅"
        print(f"  {status} {r.comment_id}: {r.label} ({r.confidence:.2f})")
    
    print(f"\n... and {len(results)-10} more")
    
    # Show stats
    print("\nStatistics:")
    stats = classifier.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Method 2: Using convenience function
    print("\n" + "="*70)
    print("\n[Method 2] Using convenience function")
    print("-" * 70)
    
    results2 = await classify_comments_async(
        comments=test_comments[:10],
        api_key=api_key,
        max_concurrent=2,
        batch_size=5
    )
    
    print(f"\nClassified {len(results2)} comments")
    
    print("\n✅ Done!")


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
