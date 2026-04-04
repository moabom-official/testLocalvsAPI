# -*- coding: utf-8 -*-
"""
Debug Groq API call
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

sys.path.insert(0, str(Path.cwd()))

print("Testing Groq API call with error details...")
print("="*60)

from comment_filtering_agent.classifiers.groq_classifier import GroqClassifier

classifier = GroqClassifier()

# Test with simple Korean text
test_text = "이 제품 정말 좋아요. 성능도 좋고 가격도 괜찮네요."

print(f"\nTest comment: {test_text}")
print("\nCalling Groq API...")

try:
    result = classifier.classify_single(test_text, 0)
    print(f"\nSUCCESS!")
    print(f"  Label: {result.label.value}")
    print(f"  Confidence: {result.confidence:.2f}")
    print(f"  Product Related: {result.is_product_related}")
except Exception as e:
    print(f"\nFAILED!")
    print(f"  Error type: {type(e).__name__}")
    print(f"  Error message: {str(e)}")
    
    # Get more details
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
