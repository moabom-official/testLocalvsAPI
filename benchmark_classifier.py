"""
기존 방식 vs Batch 방식 성능 비교 벤치마크

비교 항목:
- 총 처리 시간
- 평균 latency
- API 호출 횟수
- 실패율
- 처리량 (comments/sec)
"""
import asyncio
import time
import os
import sys
from typing import List, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from comment_filtering_agent.classifiers.async_batch_classifier import (
    AsyncBatchClassifier,
    Comment,
    ClassificationResult
)

try:
    from groq import Groq, AsyncGroq
except ImportError:
    Groq = None
    AsyncGroq = None


# ============================================================================
# 기존 방식 시뮬레이터 (1댓글 1호출)
# ============================================================================

class LegacyClassifier:
    """
    기존 방식 분류기 (1댓글 1호출)
    
    특징:
    - 댓글 1개당 API 호출 1번
    - 긴 few-shot 프롬프트 (25개 예시)
    - 순차 처리
    """
    
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        if Groq is None:
            raise ImportError("Groq not available")
        
        self.client = Groq(api_key=api_key)
        self.model = model
        
        # Statistics
        self.total_calls = 0
        self.failed_calls = 0
        self.call_times = []
    
    def classify_single(self, comment: Comment) -> ClassificationResult:
        """단일 댓글 분류"""
        self.total_calls += 1
        start_time = time.time()
        
        try:
            prompt = self._generate_long_prompt(comment)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a comment classifier."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            elapsed = time.time() - start_time
            self.call_times.append(elapsed)
            
            # Parse response
            content = response.choices[0].message.content.strip()
            
            # Simple parsing (label extraction)
            if "PRODUCT_OPINION" in content:
                label = "PRODUCT_OPINION"
            elif "QUESTION" in content:
                label = "QUESTION"
            elif "VIDEO_REACTION" in content:
                label = "VIDEO_REACTION"
            elif "OFF_TOPIC" in content:
                label = "OFF_TOPIC"
            else:
                label = "CHATTER"
            
            # Extract confidence (if available)
            confidence = 0.85  # Default
            if "confidence" in content.lower():
                try:
                    import re
                    match = re.search(r'confidence[:\s]+([0-9.]+)', content.lower())
                    if match:
                        confidence = float(match.group(1))
                except:
                    pass
            
            return ClassificationResult(
                comment_id=comment.id,
                label=label,
                confidence=confidence,
                needs_recheck=False,
                is_fallback=False
            )
        
        except Exception as e:
            self.failed_calls += 1
            elapsed = time.time() - start_time
            self.call_times.append(elapsed)
            
            return ClassificationResult(
                comment_id=comment.id,
                label="CHATTER",
                confidence=0.0,
                needs_recheck=True,
                is_fallback=True,
                error=str(e)
            )
    
    def classify_many(self, comments: List[Comment]) -> List[ClassificationResult]:
        """여러 댓글 분류 (순차)"""
        results = []
        for i, comment in enumerate(comments):
            print(f"  Legacy: Classifying {i+1}/{len(comments)}...", end='\r')
            result = self.classify_single(comment)
            results.append(result)
        print()  # New line
        return results
    
    def _generate_long_prompt(self, comment: Comment) -> str:
        """긴 프롬프트 생성 (25개 few-shot 예시)"""
        
        # Simulated long prompt (original style)
        prompt = f"""Classify this YouTube product review comment.

Comment: "{comment.text}"

Labels:
- PRODUCT_OPINION: Product evaluation, opinion, experience
- QUESTION: Product-related question
- VIDEO_REACTION: Reaction to video or reviewer
- CHATTER: Spam, meme, meaningless
- OFF_TOPIC: Unrelated to product

Few-shot examples:
1. "Battery drains too fast" → PRODUCT_OPINION
2. "Great review!" → VIDEO_REACTION
3. "Does it support 5G?" → QUESTION
4. "lol" → CHATTER
5. "What's the song name?" → OFF_TOPIC
6. "Overheating is serious" → PRODUCT_OPINION
7. "Thanks for the video" → VIDEO_REACTION
8. "How much RAM?" → QUESTION
9. "First!" → CHATTER
10. "Nice editing" → VIDEO_REACTION
11. "Camera quality is amazing" → PRODUCT_OPINION
12. "Subscribed!" → VIDEO_REACTION
13. "Worth buying?" → QUESTION
14. "Hahaha" → CHATTER
15. "Screen too dim" → PRODUCT_OPINION
16. "Great channel" → VIDEO_REACTION
17. "Better than iPhone?" → QUESTION
18. "spam spam spam" → CHATTER
19. "Build quality is cheap" → PRODUCT_OPINION
20. "Your accent is funny" → VIDEO_REACTION
21. "Does it have headphone jack?" → QUESTION
22. "ㅋㅋㅋ" → CHATTER
23. "Price too high" → PRODUCT_OPINION
24. "Keep up the good work" → VIDEO_REACTION
25. "Can you review Samsung?" → QUESTION

Output format:
Label: <LABEL>
Confidence: <0-1>
Rationale: <brief explanation>
"""
        return prompt
    
    def get_stats(self) -> Dict[str, Any]:
        """통계"""
        avg_latency = sum(self.call_times) / len(self.call_times) if self.call_times else 0
        failure_rate = (self.failed_calls / self.total_calls * 100) if self.total_calls > 0 else 0
        
        return {
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "success_calls": self.total_calls - self.failed_calls,
            "avg_latency": avg_latency,
            "failure_rate": failure_rate
        }


# ============================================================================
# 벤치마크 실행기
# ============================================================================

@dataclass
class BenchmarkResult:
    """벤치마크 결과"""
    method: str
    total_comments: int
    total_time: float
    api_calls: int
    successful_calls: int
    failed_calls: int
    avg_latency: float
    throughput: float  # comments/sec
    failure_rate: float  # %
    
    def print_summary(self):
        """결과 요약 출력"""
        print(f"\n{'='*70}")
        print(f"  Method: {self.method}")
        print(f"{'='*70}")
        print(f"  Total comments:    {self.total_comments}")
        print(f"  Total time:        {self.total_time:.2f}s")
        print(f"  API calls:         {self.api_calls}")
        print(f"  Successful:        {self.successful_calls}")
        print(f"  Failed:            {self.failed_calls}")
        print(f"  Avg latency:       {self.avg_latency:.3f}s")
        print(f"  Throughput:        {self.throughput:.2f} comments/sec")
        print(f"  Failure rate:      {self.failure_rate:.1f}%")


async def benchmark_batch_method(comments: List[Comment], api_key: str) -> BenchmarkResult:
    """Batch 방식 벤치마크"""
    print("\n" + "="*70)
    print("BENCHMARK: Batch Method (Async)")
    print("="*70)
    
    classifier = AsyncBatchClassifier(
        api_key=api_key,
        max_concurrent=3,
        batch_size=10,
        timeout=30,
        max_retries=2
    )
    
    start_time = time.time()
    results = await classifier.classify_many(comments, show_progress=True)
    elapsed = time.time() - start_time
    
    stats = classifier.get_stats()
    
    # Calculate metrics
    successful = stats["successful_requests"]
    failed = stats["failed_requests"]
    total_calls = stats["total_requests"]
    
    # Estimate avg latency (total time / batches)
    avg_latency = elapsed / total_calls if total_calls > 0 else 0
    
    return BenchmarkResult(
        method="Batch (Async)",
        total_comments=len(comments),
        total_time=elapsed,
        api_calls=total_calls,
        successful_calls=successful,
        failed_calls=failed,
        avg_latency=avg_latency,
        throughput=len(comments) / elapsed if elapsed > 0 else 0,
        failure_rate=(failed / total_calls * 100) if total_calls > 0 else 0
    )


def benchmark_legacy_method(comments: List[Comment], api_key: str) -> BenchmarkResult:
    """기존 방식 벤치마크"""
    print("\n" + "="*70)
    print("BENCHMARK: Legacy Method (Sequential)")
    print("="*70)
    
    classifier = LegacyClassifier(api_key=api_key)
    
    start_time = time.time()
    results = classifier.classify_many(comments)
    elapsed = time.time() - start_time
    
    stats = classifier.get_stats()
    
    return BenchmarkResult(
        method="Legacy (Sequential)",
        total_comments=len(comments),
        total_time=elapsed,
        api_calls=stats["total_calls"],
        successful_calls=stats["success_calls"],
        failed_calls=stats["failed_calls"],
        avg_latency=stats["avg_latency"],
        throughput=len(comments) / elapsed if elapsed > 0 else 0,
        failure_rate=stats["failure_rate"]
    )


def print_comparison(legacy: BenchmarkResult, batch: BenchmarkResult):
    """비교 테이블 출력"""
    print("\n" + "="*70)
    print("PERFORMANCE COMPARISON")
    print("="*70)
    
    # Calculate improvements
    time_improvement = ((legacy.total_time - batch.total_time) / legacy.total_time * 100) if legacy.total_time > 0 else 0
    call_reduction = ((legacy.api_calls - batch.api_calls) / legacy.api_calls * 100) if legacy.api_calls > 0 else 0
    throughput_improvement = ((batch.throughput - legacy.throughput) / legacy.throughput * 100) if legacy.throughput > 0 else 0
    
    print(f"\n{'Metric':<25} {'Legacy':<20} {'Batch':<20} {'Improvement':<15}")
    print("-" * 80)
    print(f"{'Total Time':<25} {legacy.total_time:>8.2f}s {batch.total_time:>16.2f}s {time_improvement:>12.1f}%")
    print(f"{'API Calls':<25} {legacy.api_calls:>8} {batch.api_calls:>16} {call_reduction:>12.1f}%")
    print(f"{'Avg Latency':<25} {legacy.avg_latency:>8.3f}s {batch.avg_latency:>16.3f}s {'-':<15}")
    print(f"{'Throughput':<25} {legacy.throughput:>8.2f}/s {batch.throughput:>16.2f}/s {throughput_improvement:>12.1f}%")
    print(f"{'Failure Rate':<25} {legacy.failure_rate:>8.1f}% {batch.failure_rate:>16.1f}% {'-':<15}")
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Time saved:        {legacy.total_time - batch.total_time:.2f}s ({time_improvement:.1f}%)")
    print(f"  Calls reduced:     {legacy.api_calls - batch.api_calls} ({call_reduction:.1f}%)")
    print(f"  Speedup factor:    {legacy.total_time / batch.total_time:.2f}x")
    print(f"  Throughput boost:  {throughput_improvement:.1f}%")
    print("="*70)


# ============================================================================
# 메인 벤치마크
# ============================================================================

async def run_benchmark():
    """전체 벤치마크 실행"""
    
    print("="*70)
    print("PERFORMANCE BENCHMARK: Legacy vs Batch Classification")
    print("="*70)
    
    # Load API key
    load_dotenv(override=True)
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("\nERROR: GROQ_API_KEY not found in environment")
        return
    
    # Test data (30 comments)
    test_comments = [
        Comment(id="1", text="Battery life is terrible but performance is good"),
        Comment(id="2", text="Great video, thanks for the review!"),
        Comment(id="3", text="Does it support wireless charging?"),
        Comment(id="4", text="lol haha"),
        Comment(id="5", text="What's the background music?"),
        Comment(id="6", text="Overheating issue is serious"),
        Comment(id="7", text="Thanks for the detailed explanation"),
        Comment(id="8", text="Camera quality is amazing"),
        Comment(id="9", text="How much does it cost?"),
        Comment(id="10", text="First comment!"),
        Comment(id="11", text="Screen is too dim outdoors"),
        Comment(id="12", text="Subscribed and liked!"),
        Comment(id="13", text="Worth the price?"),
        Comment(id="14", text="Sound quality disappoints"),
        Comment(id="15", text="Waiting for your next video"),
        Comment(id="16", text="Charging speed is impressive"),
        Comment(id="17", text="Can you review iPhone next?"),
        Comment(id="18", text="Build quality feels cheap"),
        Comment(id="19", text="Hahaha so funny"),
        Comment(id="20", text="Better than Samsung?"),
        Comment(id="21", text="Love your channel"),
        Comment(id="22", text="Does it have 5G?"),
        Comment(id="23", text="spam spam buy now"),
        Comment(id="24", text="Display colors are vivid"),
        Comment(id="25", text="Your editing is great"),
        Comment(id="26", text="Can it run heavy games?"),
        Comment(id="27", text="ㅋㅋㅋㅋ"),
        Comment(id="28", text="Storage space is limited"),
        Comment(id="29", text="Thanks again!"),
        Comment(id="30", text="Any deals available?"),
    ]
    
    print(f"\nTest dataset: {len(test_comments)} comments")
    print("\nWARNING: This will make real API calls and consume tokens!")
    print("Press Ctrl+C to cancel...")
    await asyncio.sleep(3)
    
    try:
        # Run Legacy benchmark
        legacy_result = benchmark_legacy_method(test_comments, api_key)
        legacy_result.print_summary()
        
        # Wait between tests
        print("\nWaiting 5 seconds before next test...")
        await asyncio.sleep(5)
        
        # Run Batch benchmark
        batch_result = await benchmark_batch_method(test_comments, api_key)
        batch_result.print_summary()
        
        # Print comparison
        print_comparison(legacy_result, batch_result)
        
        print("\n[SUCCESS] Benchmark completed!")
        
    except KeyboardInterrupt:
        print("\n\nBenchmark cancelled by user")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_benchmark())
