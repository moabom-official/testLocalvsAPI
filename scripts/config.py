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

# ── Phase 2-b: 보고서 ④ 생성 RAG (의미 검색·재정렬) on/off ──
# on  : truncate_bundles(절삭) 자리에 RAG 검색·재정렬 (Phase 2-b 기본)
# off : Phase 2-a 동작(=truncate_bundles 절삭)과 정확히 동일
# REPORT4_INPUT_EXPANSION 이 off 면 RAG 도 무의미하므로 자동 off.
# RAG 실패(임베딩 API·벡터DB)는 절삭으로 안전 퇴화 — ④ 생성은 계속.
REPORT4_RAG = os.getenv(
    "REPORT4_RAG", "1"
).strip().lower() not in ("0", "false", "no", "off")
# 임베딩 모델 (기존 OpenAI 호환 경로 재활용). 변경 시 재인덱싱 필요.
REPORT4_RAG_EMBED_MODEL = os.getenv(
    "REPORT4_RAG_EMBED_MODEL", "text-embedding-3-small"
)
# RAG 전용 SQLite 벡터 저장소 경로 (기존 14테이블·PostgreSQL 과 완전 분리).
REPORT4_RAG_DB_PATH = os.getenv(
    "REPORT4_RAG_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), ".rag", "rag_vectors.sqlite3"),
)
# 검색 쿼리당 상위 청크 수.
REPORT4_RAG_TOP_K = int(os.getenv("REPORT4_RAG_TOP_K", "8"))
