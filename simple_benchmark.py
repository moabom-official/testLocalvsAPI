"""
간단한 벤치마크 실행 스크립트
"""
import asyncio
import sys
import os
import time
import re
sys.path.insert(0, r"C:\Users\seank\OneDrive\Desktop\Moabom_Prototype")

from dotenv import load_dotenv
from googleapiclient.discovery import build
from groq import Groq, AsyncGroq

from comment_filtering_agent.classifiers.async_batch_classifier import (
    AsyncBatchClassifier, Comment, ClassificationResult
)

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

load_dotenv(override=True)

# Get API keys
youtube_key = os.getenv("YOUTUBE_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")

print("="*70)
print("SIMPLE BENCHMARK: Legacy vs Batch")
print("="*70)

# Fetch YouTube comments
print("\n[1] Fetching 5 YouTube comments...")
youtube = build('youtube', 'v3', developerKey=youtube_key)
request = youtube.commentThreads().list(
    part='snippet',
    videoId='dQw4w9WgXcQ',
    maxResults=5,
    textFormat='plainText'
)
response = request.execute()

comments = []
for idx, item in enumerate(response.get('items', [])):
    text = item['snippet']['topLevelComment']['snippet']['textDisplay']
    text = remove_emoji(text).strip()
    if text:
        comments.append(Comment(id=str(idx+1), text=text))

print(f"   Collected: {len(comments)} comments")

# Legacy test
print("\n[2] Legacy Method (sequential)...")
class LegacyClassifier:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)
        self.calls = 0
    
    def classify(self, comment):
        self.calls += 1
        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": f'Classify: "{comment.text}"\nLabel: PRODUCT_OPINION/QUESTION/VIDEO_REACTION/CHATTER/OFF_TOPIC'}],
                max_tokens=30,
                temperature=0.1
            )
            content = response.choices[0].message.content
            label = "CHATTER"
            for l in ["PRODUCT_OPINION", "QUESTION", "VIDEO_REACTION", "OFF_TOPIC"]:
                if l in content:
                    label = l
                    break
            return ClassificationResult(comment.id, label, 0.8, False, False)
        except:
            return ClassificationResult(comment.id, "CHATTER", 0.0, True, True)

legacy = LegacyClassifier(groq_key)
legacy_start = time.time()
for c in comments:
    legacy.classify(c)
    time.sleep(0.3)
legacy_time = time.time() - legacy_start

print(f"   Time: {legacy_time:.2f}s, Calls: {legacy.calls}")

# Batch test
print("\n[3] Batch Method (async)...")
time.sleep(3)

async def run_batch():
    classifier = AsyncBatchClassifier(
        api_key=groq_key,
        batch_size=10,
        max_concurrent=2
    )
    start = time.time()
    results = await classifier.classify_many(comments, show_progress=False)
    elapsed = time.time() - start
    return elapsed, classifier.get_stats()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
batch_time, batch_stats = loop.run_until_complete(run_batch())
loop.close()

print(f"   Time: {batch_time:.2f}s, Calls: {batch_stats['total_requests']}")

# Results
print("\n" + "="*70)
print("RESULTS")
print("="*70)
speedup = legacy_time / batch_time if batch_time > 0 else 0
time_saved_pct = (legacy_time - batch_time) / legacy_time * 100 if legacy_time > 0 else 0
call_reduction_pct = (legacy.calls - batch_stats['total_requests']) / legacy.calls * 100 if legacy.calls > 0 else 0

print(f"\nLegacy:  {legacy_time:.2f}s, {legacy.calls} calls")
print(f"Batch:   {batch_time:.2f}s, {batch_stats['total_requests']} calls")
print(f"\nSpeedup: {speedup:.2f}x")
print(f"Time saved: {time_saved_pct:.1f}%")
print(f"Calls reduced: {call_reduction_pct:.1f}%")
print("\n" + "="*70)
print("[SUCCESS] Done!")
