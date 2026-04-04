# -*- coding: utf-8 -*-
"""
Set API Keys and Run Full Pipeline with REAL Groq LLM
"""
import os
import subprocess
import sys
from dotenv import load_dotenv

# Load .env file (override existing environment variables)
load_dotenv(override=True)

# MUST get API keys from environment variables (loaded from .env)
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# Validate
if not YOUTUBE_API_KEY:
    print("ERROR: YOUTUBE_API_KEY environment variable not set!")
    print("Set it first: $env:YOUTUBE_API_KEY='your_key'")
    sys.exit(1)

if not GROQ_API_KEY:
    print("ERROR: GROQ_API_KEY environment variable not set!")
    print("Set it first: $env:GROQ_API_KEY='your_key'")
    sys.exit(1)

print("API Keys loaded from environment:")
print(f"  YouTube: {YOUTUBE_API_KEY[:20]}...")
print(f"  Groq:    {GROQ_API_KEY[:20]}...")
print()

# Run test
print("Running full pipeline with REAL Groq LLM...")
print("="*60)

result = subprocess.run(
    [sys.executable, "test_real_api.py"],
    capture_output=True,
    timeout=180,  # Increased timeout for LLM calls
    env=os.environ.copy()
)

# Output
stdout = result.stdout.decode('utf-8', errors='replace')
stderr = result.stderr.decode('utf-8', errors='replace')

print(stdout)

if 'mock mode' in stderr.lower() or 'Mock' in stdout:
    print("\nNote: Some components may still use Mock mode")
    
if stderr and 'error' in stderr.lower():
    print("\nErrors:")
    print(stderr[:500])

print(f"\nExit Code: {result.returncode}")
print("Status:", "SUCCESS" if result.returncode == 0 else "FAILED")
