"""
속도 + 정확도 동시 비교 벤치마크

측정 항목:
1. 속도: 처리 시간, API 호출 수, 처리량
2. 정확도: 
   - Label 일치율 (Legacy vs Batch)
   - Confidence 비교
   - 선택적: Ground Truth와 비교
"""
import asyncio
import sys
import os
import time
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
sys.path.insert(0, r"C:\Users\seank\OneDrive\Desktop\Moabom_Prototype")

from dotenv import load_dotenv
from googleapiclient.discovery import build
from groq import Groq, AsyncGroq

from comment_filtering_agent.classifiers.async_batch_classifier import (
    AsyncBatchClassifier, Comment, ClassificationResult
)


# ============================================================================
# Utility Functions
# ============================================================================

def remove_emoji(text):
    """Remove emoji"""
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)


# ============================================================================
# Ground Truth (Optional)
# ============================================================================

GROUND_TRUTH = {
    # Format: "comment_text": "EXPECTED_LABEL"
    # Add your manual labels here for accuracy measurement
}


# ============================================================================
# Accuracy Metrics
# ============================================================================

@dataclass
class AccuracyMetrics:
    """정확도 측정 결과"""
    label_agreement_rate: float  # Legacy vs Batch 일치율
    avg_confidence_legacy: float
    avg_confidence_batch: float
    confidence_diff: float
    
    # Optional: Ground Truth 비교
    legacy_accuracy: Optional[float] = None
    batch_accuracy: Optional[float] = None
    
    # Per-label breakdown
    label_distribution_legacy: Dict[str, int] = None
    label_distribution_batch: Dict[str, int] = None
    
    def print_summary(self):
        """정확도 결과 출력"""
        print(f"\n{'='*70}")
        print("ACCURACY METRICS")
        print(f"{'='*70}")
        print(f"\nLabel Agreement:")
        print(f"  Legacy vs Batch:     {self.label_agreement_rate:.1%}")
        
        print(f"\nConfidence Scores:")
        print(f"  Legacy (avg):        {self.avg_confidence_legacy:.3f}")
        print(f"  Batch (avg):         {self.avg_confidence_batch:.3f}")
        print(f"  Difference:          {self.confidence_diff:+.3f}")
        
        if self.legacy_accuracy is not None:
            print(f"\nGround Truth Accuracy:")
            print(f"  Legacy:              {self.legacy_accuracy:.1%}")
            print(f"  Batch:               {self.batch_accuracy:.1%}")
        
        if self.label_distribution_legacy:
            print(f"\nLabel Distribution:")
            print(f"  {'Label':<20} {'Legacy':<10} {'Batch':<10}")
            print(f"  {'-'*40}")
            all_labels = set(self.label_distribution_legacy.keys()) | set(self.label_distribution_batch.keys())
            for label in sorted(all_labels):
                legacy_count = self.label_distribution_legacy.get(label, 0)
                batch_count = self.label_distribution_batch.get(label, 0)
                print(f"  {label:<20} {legacy_count:<10} {batch_count:<10}")


def calculate_accuracy(
    legacy_results: List[ClassificationResult],
    batch_results: List[ClassificationResult],
    ground_truth: Optional[Dict[str, str]] = None
) -> AccuracyMetrics:
    """정확도 계산"""
    
    # Create result maps
    legacy_map = {r.comment_id: r for r in legacy_results}
    batch_map = {r.comment_id: r for r in batch_results}
    
    # Label agreement
    agreements = 0
    total = 0
    
    for comment_id in legacy_map.keys():
        if comment_id in batch_map:
            total += 1
            if legacy_map[comment_id].label == batch_map[comment_id].label:
                agreements += 1
    
    label_agreement_rate = agreements / total if total > 0 else 0
    
    # Confidence scores
    legacy_confidences = [r.confidence for r in legacy_results if not r.is_fallback]
    batch_confidences = [r.confidence for r in batch_results if not r.is_fallback]
    
    avg_conf_legacy = sum(legacy_confidences) / len(legacy_confidences) if legacy_confidences else 0
    avg_conf_batch = sum(batch_confidences) / len(batch_confidences) if batch_confidences else 0
    conf_diff = avg_conf_batch - avg_conf_legacy
    
    # Label distribution
    legacy_dist = {}
    batch_dist = {}
    
    for r in legacy_results:
        legacy_dist[r.label] = legacy_dist.get(r.label, 0) + 1
    
    for r in batch_results:
        batch_dist[r.label] = batch_dist.get(r.label, 0) + 1
    
    # Ground Truth accuracy (if available)
    legacy_accuracy = None
    batch_accuracy = None
    
    if ground_truth:
        # TODO: Implement ground truth comparison
        pass
    
    return AccuracyMetrics(
        label_agreement_rate=label_agreement_rate,
        avg_confidence_legacy=avg_conf_legacy,
        avg_confidence_batch=avg_conf_batch,
        confidence_diff=conf_diff,
        legacy_accuracy=legacy_accuracy,
        batch_accuracy=batch_accuracy,
        label_distribution_legacy=legacy_dist,
        label_distribution_batch=batch_dist
    )


# ============================================================================
# Result Comparison
# ============================================================================

def print_detailed_comparison(
    comments: List[Comment],
    legacy_results: List[ClassificationResult],
    batch_results: List[ClassificationResult]
):
    """상세 비교 출력"""
    print(f"\n{'='*70}")
    print("DETAILED CLASSIFICATION COMPARISON")
    print(f"{'='*70}")
    
    legacy_map = {r.comment_id: r for r in legacy_results}
    batch_map = {r.comment_id: r for r in batch_results}
    comment_map = {c.id: c for c in comments}
    
    print(f"\n{'ID':<5} {'Comment':<40} {'Legacy':<20} {'Batch':<20} {'Match':<5}")
    print("-" * 95)
    
    for comment_id in sorted(legacy_map.keys()):
        comment = comment_map.get(comment_id)
        legacy_r = legacy_map.get(comment_id)
        batch_r = batch_map.get(comment_id)
        
        if comment and legacy_r and batch_r:
            text_preview = comment.text[:37] + "..." if len(comment.text) > 37 else comment.text
            match = "YES" if legacy_r.label == batch_r.label else "NO"
            match_marker = " " if match == "YES" else "[X]"
            
            print(f"{comment_id:<5} {text_preview:<40} {legacy_r.label:<20} {batch_r.label:<20} {match:<5} {match_marker}")


# ============================================================================
# Legacy Classifier
# ============================================================================

class LegacyClassifier:
    """Legacy 방식 분류기"""
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.calls = 0
        self.times = []
    
    def classify(self, comment: Comment) -> ClassificationResult:
        self.calls += 1
        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": f'Classify this YouTube comment:\n"{comment.text}"\n\nLabels:\n- PRODUCT_OPINION: Product evaluation\n- QUESTION: Product question\n- VIDEO_REACTION: Video/reviewer reaction\n- CHATTER: Spam/meme/meaningless\n- OFF_TOPIC: Unrelated\n\nOutput: Label and confidence (0-1)'
                }],
                max_tokens=50,
                temperature=0.1
            )
            elapsed = time.time() - start
            self.times.append(elapsed)
            
            content = response.choices[0].message.content.strip()
            
            # Parse label
            label = "CHATTER"
            for l in ["PRODUCT_OPINION", "QUESTION", "VIDEO_REACTION", "OFF_TOPIC", "CHATTER"]:
                if l in content:
                    label = l
                    break
            
            # Parse confidence
            confidence = 0.8
            import re
            match = re.search(r'([0-9.]+)', content)
            if match:
                try:
                    conf_val = float(match.group(1))
                    if 0 <= conf_val <= 1:
                        confidence = conf_val
                except:
                    pass
            
            return ClassificationResult(comment.id, label, confidence, False, False)
        
        except Exception as e:
            elapsed = time.time() - start
            self.times.append(elapsed)
            return ClassificationResult(comment.id, "CHATTER", 0.0, True, True, str(e))


# ============================================================================
# Main Benchmark
# ============================================================================

async def run_speed_accuracy_benchmark():
    """속도 + 정확도 벤치마크 실행"""
    
    load_dotenv(override=True)
    youtube_key = os.getenv("YOUTUBE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    print("="*70)
    print("SPEED + ACCURACY BENCHMARK")
    print("="*70)
    print("\nComparing Legacy vs Batch classification methods")
    print("Metrics: Speed, API calls, Label agreement, Confidence")
    
    # Fetch YouTube comments
    print(f"\n{'='*70}")
    print("[1/4] Fetching YouTube comments")
    print(f"{'='*70}")
    
    youtube = build('youtube', 'v3', developerKey=youtube_key)
    video_id = 'dQw4w9WgXcQ'
    num_comments = 10
    
    request = youtube.commentThreads().list(
        part='snippet',
        videoId=video_id,
        maxResults=num_comments,
        textFormat='plainText'
    )
    response = request.execute()
    
    comments = []
    for idx, item in enumerate(response.get('items', [])):
        text = item['snippet']['topLevelComment']['snippet']['textDisplay']
        text = remove_emoji(text).strip()
        if text:
            comments.append(Comment(id=str(idx+1), text=text))
    
    print(f"\nCollected: {len(comments)} comments")
    for c in comments[:5]:
        preview = c.text[:50] + "..." if len(c.text) > 50 else c.text
        print(f"  [{c.id}] {preview}")
    if len(comments) > 5:
        print(f"  ... and {len(comments)-5} more")
    
    # Legacy benchmark
    print(f"\n{'='*70}")
    print("[2/4] Legacy Method (Sequential, 1 comment = 1 API call)")
    print(f"{'='*70}")
    
    legacy = LegacyClassifier(groq_key)
    legacy_start = time.time()
    legacy_results = []
    
    for i, c in enumerate(comments):
        print(f"  Processing {i+1}/{len(comments)}...", end='\r')
        result = legacy.classify(c)
        legacy_results.append(result)
        time.sleep(0.3)  # Rate limit protection
    
    print()
    legacy_time = time.time() - legacy_start
    legacy_throughput = len(comments) / legacy_time if legacy_time > 0 else 0
    
    print(f"\n  Time:       {legacy_time:.2f}s")
    print(f"  API calls:  {legacy.calls}")
    print(f"  Throughput: {legacy_throughput:.2f} comments/sec")
    
    # Wait
    print("\n  Waiting 3 seconds before next test...")
    await asyncio.sleep(3)
    
    # Batch benchmark
    print(f"\n{'='*70}")
    print("[3/4] Batch Method (Async, 10 comments = 1 API call)")
    print(f"{'='*70}")
    
    classifier = AsyncBatchClassifier(
        api_key=groq_key,
        batch_size=10,
        max_concurrent=2,
        timeout=30
    )
    
    batch_start = time.time()
    batch_results = await classifier.classify_many(comments, show_progress=False)
    batch_time = time.time() - batch_start
    batch_stats = classifier.get_stats()
    batch_throughput = len(comments) / batch_time if batch_time > 0 else 0
    
    print(f"\n  Time:       {batch_time:.2f}s")
    print(f"  API calls:  {batch_stats['total_requests']}")
    print(f"  Throughput: {batch_throughput:.2f} comments/sec")
    
    # Calculate accuracy
    print(f"\n{'='*70}")
    print("[4/4] Calculating Accuracy Metrics")
    print(f"{'='*70}")
    
    accuracy = calculate_accuracy(legacy_results, batch_results, GROUND_TRUTH)
    
    # Print results
    print(f"\n{'='*70}")
    print("FINAL RESULTS")
    print(f"{'='*70}")
    
    # Speed comparison
    print(f"\nSPEED METRICS:")
    speedup = legacy_time / batch_time if batch_time > 0 else 0
    time_saved = legacy_time - batch_time
    time_saved_pct = time_saved / legacy_time * 100 if legacy_time > 0 else 0
    call_reduction = legacy.calls - batch_stats['total_requests']
    call_reduction_pct = call_reduction / legacy.calls * 100 if legacy.calls > 0 else 0
    
    print(f"  Legacy:      {legacy_time:.2f}s, {legacy.calls} calls, {legacy_throughput:.2f} cmt/s")
    print(f"  Batch:       {batch_time:.2f}s, {batch_stats['total_requests']} calls, {batch_throughput:.2f} cmt/s")
    print(f"  Speedup:     {speedup:.2f}x")
    print(f"  Time saved:  {time_saved:.2f}s ({time_saved_pct:.1f}%)")
    print(f"  Calls reduced: {call_reduction} ({call_reduction_pct:.1f}%)")
    
    # Accuracy comparison
    accuracy.print_summary()
    
    # Detailed comparison
    print_detailed_comparison(comments, legacy_results, batch_results)
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"\nSpeed:     Batch is {speedup:.2f}x faster")
    print(f"Cost:      {call_reduction_pct:.1f}% fewer API calls")
    print(f"Agreement: {accuracy.label_agreement_rate:.1%} label agreement")
    print(f"Quality:   Batch has {accuracy.confidence_diff:+.3f} avg confidence diff")
    
    if accuracy.label_agreement_rate >= 0.8:
        print(f"\nConclusion: High agreement ({accuracy.label_agreement_rate:.1%})")
        print("           -> Batch method is RELIABLE + FASTER")
    elif accuracy.label_agreement_rate >= 0.6:
        print(f"\nConclusion: Moderate agreement ({accuracy.label_agreement_rate:.1%})")
        print("           -> Review disagreements, but Batch is faster")
    else:
        print(f"\nConclusion: Low agreement ({accuracy.label_agreement_rate:.1%})")
        print("           -> Investigate discrepancies")
    
    print(f"\n{'='*70}")
    print("[SUCCESS] Benchmark complete!")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(run_speed_accuracy_benchmark())
