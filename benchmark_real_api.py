"""
실제 YouTube + Groq API를 사용한 벤치마크

주의: 실제 API 호출로 토큰 소비됨!
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
    from googleapiclient.discovery import build
except ImportError as e:
    print(f"ERROR: Missing dependencies: {e}")
    print("Install with: pip install groq google-api-python-client")
    sys.exit(1)


# ============================================================================
# YouTube API 댓글 수집
# ============================================================================

def fetch_youtube_comments(api_key: str, video_id: str, max_results: int = 20) -> List[Comment]:
    """YouTube에서 실제 댓글 가져오기"""
    print(f"\n[YouTube API] Fetching comments from video: {video_id}")
    print(f"              Max results: {max_results}")
    
    try:
        import emoji
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        request = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=max_results,
            textFormat='plainText',
            order='relevance'
        )
        
        response = request.execute()
        
        comments = []
        for idx, item in enumerate(response.get('items', [])):
            snippet = item['snippet']['topLevelComment']['snippet']
            text = snippet['textDisplay']
            
            # Remove emoji
            text = emoji.replace_emoji(text, '')
            text = text.strip()
            
            # Skip if empty after emoji removal
            if not text:
                continue
            
            comments.append(Comment(
                id=str(idx + 1),
                text=text
            ))
        
        print(f"              Collected: {len(comments)} comments")
        return comments
    
    except Exception as e:
        print(f"\nERROR: YouTube API failed: {e}")
        return []


# ============================================================================
# Legacy 방식 (1댓글 1호출)
# ============================================================================

class LegacyClassifier:
    """기존 방식 - 순차 처리"""
    
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.total_calls = 0
        self.failed_calls = 0
        self.call_times = []
    
    def classify_single(self, comment: Comment) -> ClassificationResult:
        """단일 댓글 분류"""
        self.total_calls += 1
        start_time = time.time()
        
        try:
            # Short prompt for faster testing
            prompt = f"""Classify this comment:

Comment: "{comment.text}"

Labels: PRODUCT_OPINION, QUESTION, VIDEO_REACTION, CHATTER, OFF_TOPIC

Output format: Label: <LABEL>, Confidence: <0-1>"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Comment classifier. Be concise."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            
            elapsed = time.time() - start_time
            self.call_times.append(elapsed)
            
            content = response.choices[0].message.content.strip()
            
            # Parse label
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
            
            # Parse confidence
            confidence = 0.8
            import re
            match = re.search(r'confidence[:\s]+([0-9.]+)', content.lower())
            if match:
                confidence = float(match.group(1))
            
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
        """순차 처리"""
        results = []
        for i, comment in enumerate(comments):
            print(f"  Legacy: {i+1}/{len(comments)}...", end='\r')
            result = self.classify_single(comment)
            results.append(result)
            time.sleep(0.5)  # Rate limit protection
        print()
        return results


# ============================================================================
# 벤치마크 결과
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
    throughput: float
    failure_rate: float
    
    def print_summary(self):
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


def print_comparison(legacy: BenchmarkResult, batch: BenchmarkResult):
    """비교 출력"""
    time_improvement = ((legacy.total_time - batch.total_time) / legacy.total_time * 100) if legacy.total_time > 0 else 0
    call_reduction = ((legacy.api_calls - batch.api_calls) / legacy.api_calls * 100) if legacy.api_calls > 0 else 0
    throughput_improvement = ((batch.throughput - legacy.throughput) / legacy.throughput * 100) if legacy.throughput > 0 else 0
    
    print(f"\n{'='*70}")
    print("PERFORMANCE COMPARISON")
    print(f"{'='*70}")
    print(f"\n{'Metric':<25} {'Legacy':<20} {'Batch':<20} {'Improvement':<15}")
    print("-" * 80)
    print(f"{'Total Time':<25} {legacy.total_time:>8.2f}s {batch.total_time:>16.2f}s {time_improvement:>12.1f}%")
    print(f"{'API Calls':<25} {legacy.api_calls:>8} {batch.api_calls:>16} {call_reduction:>12.1f}%")
    print(f"{'Avg Latency':<25} {legacy.avg_latency:>8.3f}s {batch.avg_latency:>16.3f}s {'-':<15}")
    print(f"{'Throughput':<25} {legacy.throughput:>8.2f}/s {batch.throughput:>16.2f}/s {throughput_improvement:>12.1f}%")
    print(f"{'Failure Rate':<25} {legacy.failure_rate:>8.1f}% {batch.failure_rate:>16.1f}% {'-':<15}")
    
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Time saved:        {legacy.total_time - batch.total_time:.2f}s ({time_improvement:.1f}%)")
    print(f"  Calls reduced:     {legacy.api_calls - batch.api_calls} ({call_reduction:.1f}%)")
    print(f"  Speedup factor:    {legacy.total_time / batch.total_time:.2f}x")
    print(f"  Throughput boost:  {throughput_improvement:.1f}%")
    print(f"{'='*70}")


# ============================================================================
# 메인 벤치마크
# ============================================================================

async def run_real_benchmark():
    """실제 API 벤치마크"""
    
    print("="*70)
    print("REAL API BENCHMARK: Legacy vs Batch")
    print("="*70)
    
    # Load API keys
    load_dotenv(override=True)
    youtube_key = os.getenv("YOUTUBE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    if not youtube_key or not groq_key:
        print("\nERROR: API keys not found")
        print(f"  YOUTUBE_API_KEY: {'SET' if youtube_key else 'MISSING'}")
        print(f"  GROQ_API_KEY:    {'SET' if groq_key else 'MISSING'}")
        return
    
    print(f"\nAPI Keys:")
    print(f"  YOUTUBE_API_KEY: SET")
    print(f"  GROQ_API_KEY:    SET (starts with {groq_key[:4]}...)")
    
    # Fetch real YouTube comments
    video_id = "dQw4w9WgXcQ"  # Default video
    custom_video = input(f"\nEnter YouTube video ID (default: {video_id}): ").strip()
    if custom_video:
        video_id = custom_video
    
    num_comments = 10
    custom_num = input(f"Number of comments to test (default: {num_comments}): ").strip()
    if custom_num and custom_num.isdigit():
        num_comments = int(custom_num)
    
    comments = fetch_youtube_comments(youtube_key, video_id, num_comments)
    
    if not comments:
        print("\nERROR: Failed to fetch comments")
        return
    
    print(f"\n{'='*70}")
    print(f"Test Dataset: {len(comments)} comments")
    print(f"{'='*70}")
    for i, c in enumerate(comments[:5]):
        preview = c.text[:60] + "..." if len(c.text) > 60 else c.text
        print(f"  [{c.id}] {preview}")
    if len(comments) > 5:
        print(f"  ... and {len(comments)-5} more")
    
    print("\nWARNING: This will consume Groq API tokens!")
    print(f"Estimated: ~{len(comments) + len(comments)//10 + 1} API calls")
    
    confirm = input("\nContinue? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return
    
    try:
        # Test 1: Legacy
        print(f"\n{'='*70}")
        print("TEST 1: Legacy Method (Sequential, 1 comment per call)")
        print(f"{'='*70}")
        
        legacy_classifier = LegacyClassifier(groq_key)
        legacy_start = time.time()
        legacy_results = legacy_classifier.classify_many(comments)
        legacy_time = time.time() - legacy_start
        
        legacy_stats = {
            "total_calls": legacy_classifier.total_calls,
            "failed_calls": legacy_classifier.failed_calls,
            "success_calls": legacy_classifier.total_calls - legacy_classifier.failed_calls,
            "avg_latency": sum(legacy_classifier.call_times) / len(legacy_classifier.call_times) if legacy_classifier.call_times else 0
        }
        
        legacy_result = BenchmarkResult(
            method="Legacy (Sequential)",
            total_comments=len(comments),
            total_time=legacy_time,
            api_calls=legacy_stats["total_calls"],
            successful_calls=legacy_stats["success_calls"],
            failed_calls=legacy_stats["failed_calls"],
            avg_latency=legacy_stats["avg_latency"],
            throughput=len(comments) / legacy_time if legacy_time > 0 else 0,
            failure_rate=(legacy_stats["failed_calls"] / legacy_stats["total_calls"] * 100) if legacy_stats["total_calls"] > 0 else 0
        )
        
        legacy_result.print_summary()
        
        # Wait
        print("\nWaiting 5 seconds before next test...")
        await asyncio.sleep(5)
        
        # Test 2: Batch
        print(f"\n{'='*70}")
        print("TEST 2: Batch Method (Async, 10 comments per call)")
        print(f"{'='*70}")
        
        batch_classifier = AsyncBatchClassifier(
            api_key=groq_key,
            max_concurrent=2,
            batch_size=10,
            timeout=30,
            max_retries=2
        )
        
        batch_start = time.time()
        batch_results = await batch_classifier.classify_many(comments, show_progress=True)
        batch_time = time.time() - batch_start
        
        batch_stats = batch_classifier.get_stats()
        
        batch_result = BenchmarkResult(
            method="Batch (Async)",
            total_comments=len(comments),
            total_time=batch_time,
            api_calls=batch_stats["total_requests"],
            successful_calls=batch_stats["successful_requests"],
            failed_calls=batch_stats["failed_requests"],
            avg_latency=batch_time / batch_stats["total_requests"] if batch_stats["total_requests"] > 0 else 0,
            throughput=len(comments) / batch_time if batch_time > 0 else 0,
            failure_rate=(batch_stats["failed_requests"] / batch_stats["total_requests"] * 100) if batch_stats["total_requests"] > 0 else 0
        )
        
        batch_result.print_summary()
        
        # Comparison
        print_comparison(legacy_result, batch_result)
        
        # Sample results
        print(f"\n{'='*70}")
        print("SAMPLE CLASSIFICATIONS")
        print(f"{'='*70}")
        print("\nLegacy Results (first 5):")
        for r in legacy_results[:5]:
            status = "FALLBACK" if r.is_fallback else "OK"
            print(f"  [{r.comment_id}] {r.label:<20} (conf={r.confidence:.2f}) [{status}]")
        
        print("\nBatch Results (first 5):")
        for r in batch_results[:5]:
            status = "FALLBACK" if r.is_fallback else "OK"
            print(f"  [{r.comment_id}] {r.label:<20} (conf={r.confidence:.2f}) [{status}]")
        
        print(f"\n{'='*70}")
        print("[SUCCESS] Real API benchmark completed!")
        print(f"{'='*70}")
        
    except KeyboardInterrupt:
        print("\n\nBenchmark cancelled.")
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_real_benchmark())
