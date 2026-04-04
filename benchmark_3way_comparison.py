"""
3-Way 비교 벤치마크: Original vs Legacy vs Batch

비교 대상:
1. Original: 기존 Agent 시스템 (GroqClassifier - 1댓글 1호출, few-shot 25개)
2. Legacy:   벤치마크용 간단 버전 (1댓글 1호출, 짧은 프롬프트)
3. Batch:    새로운 배치 방식 (10댓글 1호출, 압축 프롬프트)

측정 항목:
- 속도: 처리 시간, API 호출 수
- 정확도: 3-way agreement (다수결), confidence
- 일관성: Pairwise agreement
"""
import asyncio
import sys
import os
import time
import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from collections import Counter
sys.path.insert(0, r"C:\Users\seank\OneDrive\Desktop\Moabom_Prototype")

from dotenv import load_dotenv
from googleapiclient.discovery import build
from groq import Groq

from comment_filtering_agent.classifiers.groq_classifier import GroqClassifier
from comment_filtering_agent.classifiers.models import ClassificationConfig
from comment_filtering_agent.classifiers.async_batch_classifier import (
    AsyncBatchClassifier, Comment, ClassificationResult
)


def remove_emoji(text):
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
# Legacy Classifier (Simple)
# ============================================================================

class SimpleLegacyClassifier:
    """간단한 Legacy 분류기"""
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
                    "content": f'Classify: "{comment.text}"\nLabels: PRODUCT_OPINION, QUESTION, VIDEO_REACTION, CHATTER, OFF_TOPIC\nOutput: Label + confidence'
                }],
                max_tokens=50,
                temperature=0.1
            )
            elapsed = time.time() - start
            self.times.append(elapsed)
            
            content = response.choices[0].message.content.strip()
            label = "CHATTER"
            for l in ["PRODUCT_OPINION", "QUESTION", "VIDEO_REACTION", "OFF_TOPIC", "CHATTER"]:
                if l in content:
                    label = l
                    break
            
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
# 3-Way Comparison Metrics
# ============================================================================

@dataclass
class ThreeWayMetrics:
    """3-way 비교 결과"""
    # Agreement rates
    original_legacy_agreement: float
    original_batch_agreement: float
    legacy_batch_agreement: float
    three_way_agreement: float  # 3개 모두 일치
    
    # Majority voting
    majority_confidence: float  # 다수결 신뢰도
    unanimous_count: int  # 만장일치 개수
    split_count: int  # 의견 분열 개수
    
    # Label distribution
    original_dist: Dict[str, int]
    legacy_dist: Dict[str, int]
    batch_dist: Dict[str, int]
    
    # Confidence scores
    original_avg_conf: float
    legacy_avg_conf: float
    batch_avg_conf: float
    
    def print_summary(self):
        print(f"\n{'='*70}")
        print("3-WAY COMPARISON RESULTS")
        print(f"{'='*70}")
        
        print(f"\nPairwise Agreement:")
        print(f"  Original vs Legacy:  {self.original_legacy_agreement:.1%}")
        print(f"  Original vs Batch:   {self.original_batch_agreement:.1%}")
        print(f"  Legacy vs Batch:     {self.legacy_batch_agreement:.1%}")
        
        print(f"\n3-Way Agreement:")
        print(f"  All 3 agree:         {self.three_way_agreement:.1%}")
        print(f"  Unanimous:           {self.unanimous_count} comments")
        print(f"  Split decision:      {self.split_count} comments")
        
        print(f"\nConfidence Scores:")
        print(f"  Original (avg):      {self.original_avg_conf:.3f}")
        print(f"  Legacy (avg):        {self.legacy_avg_conf:.3f}")
        print(f"  Batch (avg):         {self.batch_avg_conf:.3f}")
        print(f"  Majority confidence: {self.majority_confidence:.3f}")
        
        print(f"\nLabel Distribution:")
        all_labels = set(self.original_dist.keys()) | set(self.legacy_dist.keys()) | set(self.batch_dist.keys())
        print(f"  {'Label':<20} {'Original':<12} {'Legacy':<12} {'Batch':<12}")
        print(f"  {'-'*56}")
        for label in sorted(all_labels):
            orig = self.original_dist.get(label, 0)
            leg = self.legacy_dist.get(label, 0)
            bat = self.batch_dist.get(label, 0)
            print(f"  {label:<20} {orig:<12} {leg:<12} {bat:<12}")


def calculate_3way_metrics(
    original_results: List[ClassificationResult],
    legacy_results: List[ClassificationResult],
    batch_results: List[ClassificationResult]
) -> ThreeWayMetrics:
    """3-way 비교 메트릭 계산"""
    
    # Create maps
    orig_map = {r.comment_id: r for r in original_results}
    leg_map = {r.comment_id: r for r in legacy_results}
    bat_map = {r.comment_id: r for r in batch_results}
    
    # Pairwise agreement
    orig_leg_agree = 0
    orig_bat_agree = 0
    leg_bat_agree = 0
    three_way_agree = 0
    unanimous = 0
    split = 0
    
    total = len(orig_map)
    
    for comment_id in orig_map.keys():
        if comment_id in leg_map and comment_id in bat_map:
            o_label = orig_map[comment_id].label
            l_label = leg_map[comment_id].label
            b_label = bat_map[comment_id].label
            
            # Pairwise
            if o_label == l_label:
                orig_leg_agree += 1
            if o_label == b_label:
                orig_bat_agree += 1
            if l_label == b_label:
                leg_bat_agree += 1
            
            # 3-way
            if o_label == l_label == b_label:
                three_way_agree += 1
                unanimous += 1
            elif o_label != l_label and o_label != b_label and l_label != b_label:
                split += 1  # 3개 모두 다름
    
    # Majority voting confidence
    majority_votes = []
    for comment_id in orig_map.keys():
        if comment_id in leg_map and comment_id in bat_map:
            labels = [
                orig_map[comment_id].label,
                leg_map[comment_id].label,
                bat_map[comment_id].label
            ]
            most_common = Counter(labels).most_common(1)[0]
            majority_votes.append(most_common[1])  # count
    
    majority_conf = sum(v >= 2 for v in majority_votes) / len(majority_votes) if majority_votes else 0
    
    # Confidence scores
    orig_confs = [r.confidence for r in original_results if not r.is_fallback]
    leg_confs = [r.confidence for r in legacy_results if not r.is_fallback]
    bat_confs = [r.confidence for r in batch_results if not r.is_fallback]
    
    # Label distributions
    orig_dist = {}
    leg_dist = {}
    bat_dist = {}
    
    for r in original_results:
        orig_dist[r.label] = orig_dist.get(r.label, 0) + 1
    for r in legacy_results:
        leg_dist[r.label] = leg_dist.get(r.label, 0) + 1
    for r in batch_results:
        bat_dist[r.label] = bat_dist.get(r.label, 0) + 1
    
    return ThreeWayMetrics(
        original_legacy_agreement=orig_leg_agree / total if total > 0 else 0,
        original_batch_agreement=orig_bat_agree / total if total > 0 else 0,
        legacy_batch_agreement=leg_bat_agree / total if total > 0 else 0,
        three_way_agreement=three_way_agree / total if total > 0 else 0,
        majority_confidence=majority_conf,
        unanimous_count=unanimous,
        split_count=split,
        original_dist=orig_dist,
        legacy_dist=leg_dist,
        batch_dist=bat_dist,
        original_avg_conf=sum(orig_confs)/len(orig_confs) if orig_confs else 0,
        legacy_avg_conf=sum(leg_confs)/len(leg_confs) if leg_confs else 0,
        batch_avg_conf=sum(bat_confs)/len(bat_confs) if bat_confs else 0
    )


def print_detailed_3way_comparison(
    comments: List[Comment],
    original_results: List[ClassificationResult],
    legacy_results: List[ClassificationResult],
    batch_results: List[ClassificationResult]
):
    """상세 3-way 비교"""
    print(f"\n{'='*70}")
    print("DETAILED 3-WAY COMPARISON")
    print(f"{'='*70}")
    
    orig_map = {r.comment_id: r for r in original_results}
    leg_map = {r.comment_id: r for r in legacy_results}
    bat_map = {r.comment_id: r for r in batch_results}
    comm_map = {c.id: c for c in comments}
    
    print(f"\n{'ID':<5} {'Comment':<30} {'Original':<15} {'Legacy':<15} {'Batch':<15} {'Verdict':<10}")
    print("-" * 95)
    
    for comment_id in sorted(orig_map.keys()):
        comment = comm_map.get(comment_id)
        orig_r = orig_map.get(comment_id)
        leg_r = leg_map.get(comment_id)
        bat_r = bat_map.get(comment_id)
        
        if comment and orig_r and leg_r and bat_r:
            text_preview = comment.text[:27] + "..." if len(comment.text) > 27 else comment.text
            
            # Verdict
            labels = [orig_r.label, leg_r.label, bat_r.label]
            counter = Counter(labels)
            most_common = counter.most_common(1)[0]
            
            if most_common[1] == 3:
                verdict = "ALL"
            elif most_common[1] == 2:
                verdict = "2/3"
            else:
                verdict = "SPLIT"
            
            print(f"{comment_id:<5} {text_preview:<30} {orig_r.label[:14]:<15} {leg_r.label[:14]:<15} {bat_r.label[:14]:<15} {verdict:<10}")


# ============================================================================
# Main Benchmark
# ============================================================================

async def run_3way_benchmark():
    """3-way 벤치마크 실행"""
    
    load_dotenv(override=True)
    youtube_key = os.getenv("YOUTUBE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    print("="*70)
    print("3-WAY BENCHMARK: Original vs Legacy vs Batch")
    print("="*70)
    print("\nComparing:")
    print("  1. Original: Agent System (GroqClassifier)")
    print("  2. Legacy:   Simple Sequential")
    print("  3. Batch:    New Optimized Batch")
    
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
    
    # Test 1: Original (Agent System)
    print(f"\n{'='*70}")
    print("[2/4] Original Agent System (GroqClassifier)")
    print(f"{'='*70}")
    
    config = ClassificationConfig(model_name="llama-3.3-70b-versatile")
    original_classifier = GroqClassifier(api_key=groq_key, config=config)
    
    original_start = time.time()
    original_results = []
    
    for i, c in enumerate(comments):
        print(f"  Processing {i+1}/{len(comments)}...", end='\r')
        result = original_classifier.classify_single(c.text, comment_id=c.id)
        original_results.append(ClassificationResult(
            comment_id=c.id,
            label=result.label,
            confidence=result.confidence,
            needs_recheck=False,
            is_fallback=False
        ))
        time.sleep(0.3)
    
    print()
    original_time = time.time() - original_start
    
    print(f"\n  Time: {original_time:.2f}s")
    print(f"  Calls: {len(comments)}")
    
    await asyncio.sleep(3)
    
    # Test 2: Legacy
    print(f"\n{'='*70}")
    print("[3/4] Legacy Method (Simple Sequential)")
    print(f"{'='*70}")
    
    legacy = SimpleLegacyClassifier(groq_key)
    legacy_start = time.time()
    legacy_results = []
    
    for i, c in enumerate(comments):
        print(f"  Processing {i+1}/{len(comments)}...", end='\r')
        result = legacy.classify(c)
        legacy_results.append(result)
        time.sleep(0.3)
    
    print()
    legacy_time = time.time() - legacy_start
    
    print(f"\n  Time: {legacy_time:.2f}s")
    print(f"  Calls: {legacy.calls}")
    
    await asyncio.sleep(3)
    
    # Test 3: Batch
    print(f"\n{'='*70}")
    print("[4/4] Batch Method (Optimized Async)")
    print(f"{'='*70}")
    
    batch_classifier = AsyncBatchClassifier(
        api_key=groq_key,
        batch_size=10,
        max_concurrent=2
    )
    
    batch_start = time.time()
    batch_results = await batch_classifier.classify_many(comments, show_progress=False)
    batch_time = time.time() - batch_start
    batch_stats = batch_classifier.get_stats()
    
    print(f"\n  Time: {batch_time:.2f}s")
    print(f"  Calls: {batch_stats['total_requests']}")
    
    # Calculate metrics
    print(f"\n{'='*70}")
    print("CALCULATING METRICS")
    print(f"{'='*70}")
    
    metrics = calculate_3way_metrics(original_results, legacy_results, batch_results)
    
    # Print results
    print(f"\n{'='*70}")
    print("SPEED COMPARISON")
    print(f"{'='*70}")
    print(f"\n  {'Method':<20} {'Time':<12} {'Calls':<12} {'Speed (cmt/s)':<15}")
    print(f"  {'-'*59}")
    print(f"  {'Original (Agent)':<20} {original_time:>7.2f}s {len(comments):<12} {len(comments)/original_time:>10.2f}")
    print(f"  {'Legacy (Simple)':<20} {legacy_time:>7.2f}s {legacy.calls:<12} {len(comments)/legacy_time:>10.2f}")
    print(f"  {'Batch (Optimized)':<20} {batch_time:>7.2f}s {batch_stats['total_requests']:<12} {len(comments)/batch_time:>10.2f}")
    
    # Accuracy metrics
    metrics.print_summary()
    
    # Detailed comparison
    print_detailed_3way_comparison(comments, original_results, legacy_results, batch_results)
    
    # Final summary
    print(f"\n{'='*70}")
    print("FINAL VERDICT")
    print(f"{'='*70}")
    
    fastest = min(original_time, legacy_time, batch_time)
    
    print(f"\nSpeed:")
    if batch_time == fastest:
        print(f"  WINNER: Batch ({batch_time:.2f}s)")
        print(f"  vs Original: {original_time/batch_time:.2f}x faster")
        print(f"  vs Legacy: {legacy_time/batch_time:.2f}x faster")
    
    print(f"\nAccuracy (3-way agreement):")
    print(f"  All 3 methods agree: {metrics.three_way_agreement:.1%}")
    if metrics.three_way_agreement >= 0.7:
        print(f"  VERDICT: High consistency")
    elif metrics.three_way_agreement >= 0.5:
        print(f"  VERDICT: Moderate consistency")
    else:
        print(f"  VERDICT: Low consistency - review needed")
    
    print(f"\nMajority Voting:")
    print(f"  2+ methods agree: {metrics.majority_confidence:.1%}")
    print(f"  Unanimous: {metrics.unanimous_count}/{len(comments)}")
    print(f"  Split: {metrics.split_count}/{len(comments)}")
    
    print(f"\nRecommendation:")
    if metrics.three_way_agreement >= 0.6 and batch_time < original_time * 0.5:
        print(f"  USE BATCH METHOD")
        print(f"  - {original_time/batch_time:.1f}x faster than original")
        print(f"  - {metrics.original_batch_agreement:.1%} agreement with original")
        print(f"  - {batch_stats['total_requests']/len(comments)*100:.0f}% cost reduction")
    else:
        print(f"  REVIEW NEEDED")
        print(f"  - Low agreement between methods")
    
    print(f"\n{'='*70}")
    print("[SUCCESS] 3-way benchmark complete!")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(run_3way_benchmark())
