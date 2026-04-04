"""
자동으로 실행하는 벤치마크 스크립트
"""
import asyncio
import sys
import os

# Mock input for automatic execution
class MockInput:
    def __init__(self, responses):
        self.responses = responses
        self.index = 0
    
    def __call__(self, prompt=""):
        if self.index < len(self.responses):
            response = self.responses[self.index]
            self.index += 1
            print(f"{prompt}{response}")
            return response
        return ""

# Replace built-in input
sys.path.insert(0, os.path.dirname(__file__))
__builtins__.input = MockInput([
    "dQw4w9WgXcQ",  # video ID
    "5",            # number of comments
    "y"             # confirm
])

# Import and run
from benchmark_real_api import run_real_benchmark

if __name__ == "__main__":
    asyncio.run(run_real_benchmark())
