"""
Config module - Environment variables and settings
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/techdb")

# API Keys
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# RunYourAI — 통합 LLM provider (OpenAI / Claude / Gemini 단일 키).
# 모델 형식: "openai/gpt-4.1", "claude/claude-haiku-4-5", "gemini/gemini-2.5-flash" 등.
RUNYOURAI_API_KEY = os.getenv("RUNYOURAI_API_KEY", "")
RUNYOURAI_BASE_URL = os.getenv("RUNYOURAI_BASE_URL", "https://api.runyour.ai/v1")
RUNYOURAI_MODEL = os.getenv("RUNYOURAI_MODEL", "openai/gpt-4.1-2025-04-14")

# Server
PORT = int(os.getenv("PORT", 8000))
HOST = "0.0.0.0"

# ── Phase 2-a: 보고서 ④ 입력 확장 (영상별 ①②③ 종합) on/off ──
# on  : ④ 가 영상 N개의 ①②③ 을 종합 (Phase 2-a 기본)
# off : Phase 2-a 이전과 정확히 동일 (영상별 ① + ⑤용 댓글 집계만)
# 회귀 비교·긴급 대응용. REPORT4_INPUT_EXPANSION=0/false/no/off → 비활성.
REPORT4_INPUT_EXPANSION = os.getenv(
    "REPORT4_INPUT_EXPANSION", "1"
).strip().lower() not in ("0", "false", "no", "off")
