"""
Config module - Environment variables and settings
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/techdb")

# API Keys
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Azure OpenAI — 보고서 3종(transcript / comment / integrated) + 댓글 분류 / 감성 분석
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

# Server
PORT = int(os.getenv("PORT", 8000))
HOST = "0.0.0.0"
