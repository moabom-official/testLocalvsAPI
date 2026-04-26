"""
자막 기반 제품 핵심 인사이트 보고서 생성 (Azure OpenAI / GPT-4.1-mini)

- 중앙화 프롬프트(`scripts.utils.prompt_manager.build_transcript_report_prompt`) 사용
- `[END]` 마커 + 본문 길이 검증 후 최대 3회 재시도
- 자막이 매우 길 경우(150,000자 초과) 청킹 후 청크별 중간 요약 → 최종 보고서로 합성
- get_report_llm_client / REPORT_LLM_DEPLOYMENT: comment_report.py /
  integrated_report.py 가 동일 클라이언트를 재사용하도록 export
"""
import re
from openai import AzureOpenAI

from scripts.config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
)
from scripts.utils.prompt_manager import build_transcript_report_prompt

# ── 청킹 기준 ──────────────────────────────────────────────────
# GPT-4.1-mini 128K 컨텍스트 기준
CHUNK_THRESHOLD = 150_000
CHUNK_SIZE = 100_000
CHUNK_OVERLAP = 3_000

# ── 검증/재시도 파라미터 ────────────────────────────────────────
MAX_ATTEMPTS = 3
INITIAL_CHAR_LIMIT = 1000
CHAR_LIMIT_DECREMENT = 100
VALIDATION_MAX_CHARS = 1500

# 보고서가 사용하는 Azure 배포 이름 (모듈 표면에 export)
REPORT_LLM_DEPLOYMENT = AZURE_OPENAI_DEPLOYMENT

# ── LLM 클라이언트 ──────────────────────────────────────────────
_client = None


def get_report_llm_client() -> AzureOpenAI:
    """보고서 3종이 공유하는 Azure OpenAI lazy 싱글턴."""
    global _client
    if _client is None:
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
            raise ValueError(
                "Azure OpenAI 가 구성되지 않았습니다. "
                "AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY 를 확인하세요."
            )
        _client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    return _client


def _get_client() -> AzureOpenAI:  # 내부 호환 alias
    return get_report_llm_client()


# ── 검증 / 인코딩 보정 ─────────────────────────────────────────

def _extract_validated_report(llm_text: str, min_chars: int = 1, max_chars: int = VALIDATION_MAX_CHARS) -> str:
    """[END] 마커와 본문 길이를 검증하고 통과 시 본문 텍스트를 반환."""
    if not llm_text:
        return ""
    text = llm_text.strip()
    if not text.endswith("[END]"):
        return ""
    body = text[: text.rfind("[END]")].strip()
    body_len = len(body)
    if body_len < min_chars or body_len > max_chars:
        return ""
    return body


def fix_encoding(text: str) -> str:
    """한국어 인코딩 깨짐 보정 (integrated_report.py에서도 사용)."""
    if not text:
        return text
    try:
        return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return text


# ── 내부 유틸 ───────────────────────────────────────────────────

def _split_chunks(text: str) -> list:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP if end < len(text) else end
    return chunks


def _call_llm_validated(prompt: str) -> str:
    """검증/재시도가 포함된 LLM 호출. 본문이 검증을 통과하면 반환, 아니면 빈 문자열."""
    client = _get_client()
    char_limit = INITIAL_CHAR_LIMIT

    for attempt in range(MAX_ATTEMPTS):
        if attempt == 0:
            full_prompt = prompt
        else:
            retry_instruction = (
                f"\n\n이전 응답이 형식 조건을 충족하지 않았습니다. "
                f"이번에는 반드시 본문 {char_limit}자 이내로 작성하고, "
                "마지막 줄 단독 [END]를 지켜 다시 작성하세요."
            )
            full_prompt = prompt + retry_instruction

        response = client.chat.completions.create(
            model=REPORT_LLM_DEPLOYMENT,
            max_tokens=2000,
            messages=[{"role": "user", "content": full_prompt}],
        )
        llm_text = response.choices[0].message.content if response.choices else None
        validated = _extract_validated_report(llm_text or "")
        if validated:
            return validated

        char_limit -= CHAR_LIMIT_DECREMENT
        print(
            f"[WARN] Transcript analysis format invalid at attempt {attempt + 1}/{MAX_ATTEMPTS} "
            f"(validation_max={VALIDATION_MAX_CHARS}) → next limit: {char_limit}"
        )

    return ""


# ── 메인 함수 ────────────────────────────────────────────────────

def build_transcript_report(transcript_text: str) -> str:
    """
    자막 기반 제품 핵심 인사이트 보고서 생성.

    - 150,000자 이하: 전체 자막을 한 번에 처리
    - 150,000자 초과: 청크별 중간 요약 후 최종 보고서 합성
    - 모든 LLM 호출은 [END] 마커 + 본문 길이 검증을 거쳐 최대 3회 재시도
    """
    normalized = re.sub(r"\s+", " ", transcript_text or "").strip()
    if not normalized:
        return "No transcript content available."

    if not AZURE_OPENAI_API_KEY:
        error_msg = "[ERROR] Transcript report generation failed: AZURE_OPENAI_API_KEY not configured."
        print(error_msg)
        return error_msg

    print(f"  [자막 보고서] 자막 길이: {len(normalized):,}자")

    try:
        if len(normalized) <= CHUNK_THRESHOLD:
            prompt = build_transcript_report_prompt(normalized)
            validated = _call_llm_validated(prompt)
        else:
            chunks = _split_chunks(normalized)
            print(f"  [자막 보고서] {len(chunks)}개 청크로 분할 처리")
            summaries = []
            for i, chunk in enumerate(chunks):
                print(f"  [자막 보고서] 청크 {i + 1}/{len(chunks)} 중간 요약 중...")
                chunk_prompt = build_transcript_report_prompt(chunk)
                chunk_validated = _call_llm_validated(chunk_prompt)
                if not chunk_validated:
                    error_msg = (
                        f"[ERROR] Transcript chunk {i + 1}/{len(chunks)} format invalid "
                        f"after {MAX_ATTEMPTS} attempts"
                    )
                    print(error_msg)
                    return error_msg
                summaries.append(chunk_validated)

            combined = "\n\n---\n\n".join(summaries)
            print(f"  [자막 보고서] 최종 보고서 생성 중...")
            final_prompt = build_transcript_report_prompt(combined)
            validated = _call_llm_validated(final_prompt)

        if not validated:
            error_msg = f"[ERROR] Transcript analysis output format invalid after {MAX_ATTEMPTS} attempts"
            print(error_msg)
            return error_msg

        return f"[자막 기반 제품 분석 보고서]\n\n{fix_encoding(validated)}"

    except Exception as e:
        error_msg = f"[ERROR] Transcript analysis failed: {e}"
        print(error_msg)
        return error_msg
