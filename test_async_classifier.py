"""
Async Batch Classifier 테스트

실제 Groq API를 사용한 병렬 분류 테스트
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from comment_filtering_agent.classifiers.async_batch_classifier import (
    AsyncBatchClassifier,
    Comment,
    classify_comments_async
)


async def test_basic_classification():
    """기본 분류 테스트"""
    print("="*70)
    print("Test 1: Basic Async Classification")
    print("="*70)
    
    # Load API key
    load_dotenv(override=True)
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("❌ GROQ_API_KEY not found")
        return
    
    # Test comments (small batch)
    comments = [
        Comment(id="1", text="Battery life is terrible but performance is good"),
        Comment(id="2", text="Great video, thanks!"),
        Comment(id="3", text="Does it support wireless charging?"),
        Comment(id="4", text="lol haha"),
        Comment(id="5", text="What's the background music?"),
    ]
    
    print(f"\n📝 Test comments: {len(comments)}")
    for c in comments:
        print(f"  - {c}")
    
    # Classify
    classifier = AsyncBatchClassifier(
        api_key=api_key,
        max_concurrent=2,
        batch_size=5,
        timeout=30,
        max_retries=2
    )
    
    results = await classifier.classify_many(comments, show_progress=True)
    
    # Show results
    print("\n📊 Results:")
    for r in results:
        status = "⚠️ FALLBACK" if r.is_fallback else "✅"
        print(f"  {status} [{r.comment_id}] {r.label} (conf={r.confidence:.2f})")
        if r.error:
            print(f"      Error: {r.error}")
    
    # Stats
    print("\n📈 Statistics:")
    stats = classifier.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    return results


async def test_parallel_batches():
    """병렬 배치 처리 테스트"""
    print("\n" + "="*70)
    print("Test 2: Parallel Batch Processing")
    print("="*70)
    
    load_dotenv(override=True)
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("❌ GROQ_API_KEY not found")
        return
    
    # More comments (2 batches)
    comments = [
        Comment(id=str(i), text=f"Test comment {i}")
        for i in range(1, 16)  # 15 comments = 2 batches (size=10)
    ]
    
    # Real comments
    real_texts = [
        "Overheating is a serious problem",
        "Nice review!",
        "How much RAM does it have?",
        "First!",
        "Camera quality is amazing",
        "Subscribed",
        "Screen is too dim",
        "Thanks!",
        "Better than iPhone?",
        "Build quality is cheap",
        "lol",
        "Price too high",
        "Does it have headphone jack?",
        "Great channel",
        "Worth buying?",
    ]
    
    for i, text in enumerate(real_texts):
        comments[i].text = text
    
    print(f"\n📝 Test comments: {len(comments)}")
    
    # Classify with higher concurrency
    classifier = AsyncBatchClassifier(
        api_key=api_key,
        max_concurrent=3,
        batch_size=8,
        timeout=30
    )
    
    results = await classifier.classify_many(comments, show_progress=True)
    
    # Count labels
    label_counts = {}
    for r in results:
        label_counts[r.label] = label_counts.get(r.label, 0) + 1
    
    print("\n📊 Label distribution:")
    for label, count in sorted(label_counts.items()):
        print(f"  {label}: {count}")
    
    return results


async def test_convenience_function():
    """편의 함수 테스트"""
    print("\n" + "="*70)
    print("Test 3: Convenience Function")
    print("="*70)
    
    load_dotenv(override=True)
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("❌ GROQ_API_KEY not found")
        return
    
    comments = [
        Comment(id="1", text="Battery drains too fast"),
        Comment(id="2", text="Thanks for the video"),
        Comment(id="3", text="Does it have 120Hz display?"),
    ]
    
    print(f"\n📝 Comments: {len(comments)}")
    
    # Use convenience function
    results = await classify_comments_async(
        comments=comments,
        api_key=api_key,
        max_concurrent=2,
        batch_size=3,
        timeout=30
    )
    
    print("\n📊 Results:")
    for r in results:
        print(f"  [{r.comment_id}] {r.label} ({r.confidence:.2f})")
    
    return results


async def main():
    """모든 테스트 실행"""
    print("\n" + "🚀 "*20)
    print("Async Batch Classifier - Full Test Suite")
    print("🚀 "*20 + "\n")
    
    try:
        # Test 1: Basic
        results1 = await test_basic_classification()
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Test 2: Parallel batches
        results2 = await test_parallel_batches()
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Test 3: Convenience function
        results3 = await test_convenience_function()
        
        print("\n" + "="*70)
        print("✅ All tests completed successfully!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
