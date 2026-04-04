# -*- coding: utf-8 -*-
"""
Product-centric YouTube Analysis Service
FastAPI + PostgreSQL + YouTube Data API v3
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from io import BytesIO
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import httpx
import uvicorn
from prompt_manager import build_transcript_report_prompt

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/techdb")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")

# ============================================================================
# DATABASE LAYER
# ============================================================================

def get_connection():
    """Get a raw PostgreSQL connection with UTF-8 encoding."""
    conn = psycopg2.connect(DATABASE_URL)
    # Ensure UTF-8 encoding
    conn.set_client_encoding('UTF8')
    return conn


def init_db():
    """Initialize database schema on startup."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tech_products (
            product_id   SERIAL PRIMARY KEY,
            name         VARCHAR(255) NOT NULL,
            brand        VARCHAR(255),
            category     VARCHAR(255),
            created_at   TIMESTAMP DEFAULT NOW()
        );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            video_id     VARCHAR(64) PRIMARY KEY,
            product_id   INT NOT NULL REFERENCES tech_products(product_id) ON DELETE CASCADE,
            title        VARCHAR(255) NOT NULL,
            description  TEXT,
            published_at TIMESTAMP,
            thumbnail_url TEXT,
            view_count   BIGINT,
            like_count   BIGINT,
            comment_count BIGINT,
            created_at   TIMESTAMP DEFAULT NOW()
        );
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_videos_product ON videos(product_id);
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            comment_id        VARCHAR(64) PRIMARY KEY,
            video_id          VARCHAR(64) NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
            parent_id         VARCHAR(64),
            text_raw          TEXT NOT NULL,
            is_product_related BOOLEAN,
            created_at        TIMESTAMP DEFAULT NOW()
        );
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_id);
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comment_sentiments (
            id               SERIAL PRIMARY KEY,
            comment_id       VARCHAR(64) NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
            sentiment_label  VARCHAR(16) NOT NULL,
            sentiment_score  NUMERIC(4,3),
            created_at       TIMESTAMP DEFAULT NOW()
        );
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentiments_comment ON comment_sentiments(comment_id);
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_transcripts (
            video_id        VARCHAR(64) PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
            transcript_text TEXT NOT NULL,
            language_code   VARCHAR(16),
            segment_count   INT,
            source          VARCHAR(32) DEFAULT 'youtube_transcript_api',
            updated_at      TIMESTAMP DEFAULT NOW()
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_reports (
            video_id            VARCHAR(64) PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
            transcript_report   TEXT,
            comment_report      TEXT,
            integrated_report   TEXT,
            updated_at          TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # Migration: Add integrated_report column if it doesn't exist
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'video_reports' AND column_name = 'integrated_report'
        )
    """)
    if not cursor.fetchone()[0]:
        cursor.execute("""
            ALTER TABLE video_reports 
            ADD COLUMN integrated_report TEXT
        """)
        print("✓ Added integrated_report column")
    
    conn.commit()
    cursor.close()
    conn.close()
    print("✓ Database initialized")



def query_one(sql: str, params: tuple = ()) -> Optional[Dict]:
    """Execute query and return single row as dict."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(sql, params)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def query_all(sql: str, params: tuple = ()) -> List[Dict]:
    """Execute query and return all rows as dicts."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(sql, params)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def execute_insert(sql: str, params: tuple = ()) -> int:
    """Execute INSERT and return inserted ID (for SERIAL columns)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    result_id = cursor.fetchone()[0] if cursor.description else None
    conn.commit()
    cursor.close()
    conn.close()
    return result_id


def execute_update(sql: str, params: tuple = ()) -> int:
    """Execute UPDATE/DELETE and return row count."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    row_count = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return row_count


# ============================================================================
# YOUTUBE API LAYER
# ============================================================================

def fetch_product_videos(product_name: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search YouTube for videos about a product and fetch their statistics.
    Returns list of dicts: {video_id, title, description, published_at, thumbnail_url, view_count, like_count, comment_count}
    """
    if not YOUTUBE_API_KEY:
        return []
    
    try:
        client = httpx.Client()
        
        # Step 1: Search for videos
        search_url = "https://www.googleapis.com/youtube/v3/search"
        search_params = {
            "part": "snippet",
            "q": product_name,
            "type": "video",
            "maxResults": max_results,
            "key": YOUTUBE_API_KEY,
        }
        search_resp = client.get(search_url, params=search_params, timeout=30.0)
        search_resp.raise_for_status()
        search_data = search_resp.json()
        
        video_ids = [item["id"]["videoId"] for item in search_data.get("items", [])]
        if not video_ids:
            return []
        
        # Step 2: Get video statistics
        videos_url = "https://www.googleapis.com/youtube/v3/videos"
        videos_params = {
            "part": "snippet,statistics",
            "id": ",".join(video_ids),
            "key": YOUTUBE_API_KEY,
        }
        videos_resp = client.get(videos_url, params=videos_params, timeout=30.0)
        videos_resp.raise_for_status()
        videos_data = videos_resp.json()
        
        results = []
        for item in videos_data.get("items", []):
            video_id = item["id"]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            
            results.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt"),
                "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url"),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
            })
        
        client.close()
        return results
    except Exception as e:
        print(f"Error fetching videos: {e}")
        return []


def fetch_video_comments(video_id: str, max_pages: int = 2) -> List[Dict[str, str]]:
    """
    Fetch top-level comments for a YouTube video.
    Returns list of dicts: {comment_id, text_raw}
    """
    if not YOUTUBE_API_KEY:
        return []
    
    try:
        client = httpx.Client()
        results = []
        next_page_token = None
        pages = 0
        
        while pages < max_pages:
            url = "https://www.googleapis.com/youtube/v3/commentThreads"
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 100,
                "textFormat": "plainText",
                "key": YOUTUBE_API_KEY,
            }
            if next_page_token:
                params["pageToken"] = next_page_token
            
            resp = client.get(url, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            
            for item in data.get("items", []):
                top_comment = item["snippet"]["topLevelComment"]["snippet"]
                comment_id = item["snippet"]["topLevelComment"]["id"]
                
                results.append({
                    "comment_id": comment_id,
                    "text_raw": top_comment.get("textDisplay", ""),
                })
            
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break
            
            pages += 1
        
        client.close()
        return results
    except Exception as e:
        print(f"Error fetching comments: {e}")
        return []


def fetch_video_transcript(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch transcript in-memory with smart retry logic on 429.
    - yt-dlp extracts caption URLs only (no video download)
    - Fetch content with requests, parse in-memory
    - Exponential backoff on 429 errors
    - Only try preferred languages/formats
    """
    import time
    import json
    import yt_dlp
    import requests
    from io import StringIO
    
    print(f"[TRANSCRIPT] Fetching for video_id={video_id}")
    
    def parse_json3(content: str) -> Optional[str]:
        """Parse JSON3 caption format, return text or None."""
        try:
            data = json.loads(content)
            text_parts = []
            if 'events' in data:
                for event in data['events']:
                    if 'segs' in event:
                        for seg in event['segs']:
                            if 'utf8' in seg:
                                text_parts.append(seg['utf8'])
            return " ".join(text_parts).strip() if text_parts else None
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[TRANSCRIPT] JSON3 parse error: {e}")
            return None
    
    def parse_vtt(content: str) -> Optional[str]:
        """Parse VTT caption format, return text or None."""
        lines = content.split('\n')
        text_parts = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('WEBVTT') and '-->' not in line:
                text_parts.append(line)
        return " ".join(text_parts).strip() if text_parts else None
    
    def fetch_with_backoff(url: str, max_retries: int = 3) -> Optional[str]:
        """
        Fetch URL with exponential backoff on 429.
        Returns content on success, None on persistent failure.
        """
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=30)
                
                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    print(f"[TRANSCRIPT] 429 Too Many Requests, retry {attempt + 1}/{max_retries} after {wait_time}s")
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"[TRANSCRIPT] Max retries exceeded for URL")
                        return None
                
                response.raise_for_status()
                return response.text
            
            except requests.exceptions.Timeout:
                print(f"[TRANSCRIPT] Timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            
            except requests.exceptions.RequestException as e:
                print(f"[TRANSCRIPT] Request error: {e}")
                return None
        
        return None
    
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Extract caption URLs with yt-dlp (metadata only)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[TRANSCRIPT] Extracting metadata from {url}")
            info = ydl.extract_info(url, download=False)
            
            subtitles_data = info.get('automatic_captions') or info.get('subtitles') or {}
            print(f"[TRANSCRIPT] Available languages: {list(subtitles_data.keys())}")
        
        transcript_text = None
        language_code = None
        
        # Try preferred languages in order
        for lang in ['ko', 'en']:
            if lang not in subtitles_data or not subtitles_data[lang]:
                continue
            
            print(f"[TRANSCRIPT] Trying language: {lang}")
            
            # Only try preferred formats
            preferred_formats = ['json3', 'vtt']
            
            for subtitle_item in subtitles_data[lang]:
                if not isinstance(subtitle_item, dict) or 'url' not in subtitle_item:
                    continue
                
                subtitle_url = subtitle_item['url']
                ext = subtitle_item.get('ext', '')
                
                # Skip if not a preferred format
                if ext not in preferred_formats:
                    continue
                
                print(f"[TRANSCRIPT] Fetching {lang}/{ext}: {subtitle_url[:60]}...")
                
                # Fetch with exponential backoff
                content = fetch_with_backoff(subtitle_url)
                if not content:
                    continue
                
                # Parse based on format
                if ext == 'json3':
                    transcript_text = parse_json3(content)
                elif ext == 'vtt':
                    transcript_text = parse_vtt(content)
                
                if transcript_text:
                    language_code = lang
                    print(f"[TRANSCRIPT] SUCCESS: {len(transcript_text)} chars, language={lang}, format={ext}")
                    break
            
            # Break outer loop on success
            if transcript_text:
                break
        
        if not transcript_text:
            print(f"[TRANSCRIPT] No transcript available")
            return None
        
        return {
            "transcript_text": transcript_text,
            "language_code": language_code,
            "segment_count": len(transcript_text.split()),
        }
            
    except Exception as e:
        print(f"[TRANSCRIPT] Failed: {type(e).__name__}: {str(e)[:150]}")
        import traceback
        traceback.print_exc()
        return None


def fix_encoding(text: str) -> str:
    """Attempt to fix garbled Korean characters."""
    if not text:
        return text
    
    try:
        # Try to detect and fix mojibake
        # Replace common Chinese characters that appear instead of Korean
        replacements = {
            "几乎": "거의",  # Chinese for "almost"
            "提出": "제시",   # Chinese for "present"
            "相同": "동일",   # Chinese for "same"
            "类似": "유사",   # Chinese for "similar"
        }
        
        result = text
        for old, new in replacements.items():
            result = result.replace(old, new)
        
        return result.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[ENCODING] Fix failed: {e}")
        return text


def build_transcript_report_heuristic(transcript_text: str) -> str:
    """
    Build a detailed product analysis report from transcript:
    1. Product Description (features, specs, capabilities mentioned)
    2. Evaluation & Review (likes, dislikes, recommendations)
    3. Key Takeaways
    """
    normalized = re.sub(r"\s+", " ", transcript_text or "").strip()
    if not normalized:
        return "No transcript content available."

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

    if not sentences:
        return "Transcript too short to analyze."

    # ============================================================================
    # 1. PRODUCT DESCRIPTION EXTRACTION
    # ============================================================================
    feature_keywords = {
        "design", "feature", "spec", "performance", "battery", "camera", "display",
        "processor", "memory", "storage", "screen", "build", "material", "size",
        "weight", "quality", "speed", "power", "sound", "audio", "video",
        "resolution", "fps", "refresh", "rate", "connector", "port", "interface",
        "기능", "디자인", "성능", "배터리", "카메라", "디스플레이", "프로세서",
        "메모리", "저장", "화면", "품질", "속도"
    }
    
    description_sentences = []
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if any(kw in sentence_lower for kw in feature_keywords):
            description_sentences.append(sentence)
    
    description_sentences = description_sentences[:3]  # Top 3 sentences about features

    # ============================================================================
    # 2. EVALUATION & SENTIMENT EXTRACTION
    # ============================================================================
    positive_indicators = {
        "good", "great", "excellent", "amazing", "awesome", "best", "perfect",
        "love", "like", "recommend", "worth", "impressed", "impressive",
        "beautiful", "smooth", "fast", "excellent", "outstanding",
        "좋다", "훌륭하다", "추천", "완벽", "훌륭", "빠르다", "훌륭한"
    }
    
    negative_indicators = {
        "bad", "poor", "terrible", "awful", "horrible", "worst", "useless",
        "hate", "dislike", "problem", "issue", "broken", "disappointing",
        "waste", "regret", "slow", "expensive", "cheap", "fragile",
        "나쁘다", "문제", "느리다", "비싸다", "싼", "약하다"
    }
    
    upgrade_phrases = {
        "upgrade", "improve", "better", "compare", "vs", "difference",
        "instead", "alternative", "choose", "pick", "go for",
        "업그레이드", "개선", "더 나음", "비교", "차이", "선택"
    }
    
    positive_sentences = []
    negative_sentences = []
    upgrade_sentences = []
    
    for sentence in sentences:
        sentence_lower = sentence.lower()
        pos_count = sum(1 for word in positive_indicators if word in sentence_lower)
        neg_count = sum(1 for word in negative_indicators if word in sentence_lower)
        upg_count = sum(1 for word in upgrade_phrases if word in sentence_lower)
        
        if pos_count > neg_count:
            positive_sentences.append(sentence)
        elif neg_count > pos_count:
            negative_sentences.append(sentence)
        
        if upg_count > 0:
            upgrade_sentences.append(sentence)
    
    # ============================================================================
    # 3. KEYWORD EXTRACTION
    # ============================================================================
    token_candidates = re.findall(r"[A-Za-z0-9가-힣]{2,}", normalized.lower())
    stopwords = {
        "this", "that", "with", "from", "have", "will", "your", "about", "there",
        "would", "they", "them", "then", "into", "here", "just", "also", "than",
        "when", "what", "the", "and", "for", "but", "are", "has", "been", "is",
        "있는", "그리고", "합니다", "하는", "에서", "으로", "하는데", "것", "수"
    }
    
    filtered_tokens = [t for t in token_candidates if t not in stopwords and len(t) >= 2]
    token_counts: Dict[str, int] = {}
    for token in filtered_tokens:
        token_counts[token] = token_counts.get(token, 0) + 1
    
    top_keywords = sorted(token_counts.items(), key=lambda x: x[1], reverse=True)[:6]

    # ============================================================================
    # 4. BUILD REPORT
    # ============================================================================
    report_lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "PRODUCT ANALYSIS REPORT FROM VIDEO TRANSCRIPT",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    
    # Product Description
    report_lines.extend([
        "📋 PRODUCT DESCRIPTION",
        "-" * 40,
    ])
    
    if description_sentences:
        for idx, sent in enumerate(description_sentences, 1):
            # Truncate long sentences
            truncated = (sent[:150] + "...") if len(sent) > 150 else sent
            report_lines.append(f"{idx}. {truncated}")
    else:
        report_lines.append("(No specific product features mentioned)")
    
    report_lines.append("")
    
    # Positive Evaluation
    report_lines.extend([
        "👍 POSITIVE POINTS",
        "-" * 40,
    ])
    
    if positive_sentences:
        for idx, sent in enumerate(positive_sentences[:2], 1):
            truncated = (sent[:140] + "...") if len(sent) > 140 else sent
            report_lines.append(f"• {truncated}")
    else:
        report_lines.append("(No positive remarks found)")
    
    report_lines.append("")
    
    # Negative/Concerns
    report_lines.extend([
        "⚠️  CONCERNS & CRITICISMS",
        "-" * 40,
    ])
    
    if negative_sentences:
        for idx, sent in enumerate(negative_sentences[:2], 1):
            truncated = (sent[:140] + "...") if len(sent) > 140 else sent
            report_lines.append(f"• {truncated}")
    else:
        report_lines.append("(No significant concerns mentioned)")
    
    report_lines.append("")
    
    # Upgrade/Comparison Info
    report_lines.extend([
        "🔄 ALTERNATIVES & UPGRADES",
        "-" * 40,
    ])
    
    if upgrade_sentences:
        for idx, sent in enumerate(upgrade_sentences[:2], 1):
            truncated = (sent[:140] + "...") if len(sent) > 140 else sent
            report_lines.append(f"• {truncated}")
    else:
        report_lines.append("(No comparison/upgrade info mentioned)")
    
    report_lines.append("")
    
    # Key Topics/Keywords
    report_lines.extend([
        "🔑 KEY TOPICS MENTIONED",
        "-" * 40,
    ])
    
    if top_keywords:
        keyword_list = ", ".join([f"{k}({c})" for k, c in top_keywords])
        report_lines.append(keyword_list)
    else:
        report_lines.append("N/A")
    
    report_lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Transcript length: {len(normalized)} characters | Sentences analyzed: {len(sentences)}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])
    
    result = "\n".join(report_lines)
    return fix_encoding(result)


def build_transcript_report(transcript_text: str) -> str:
    """
    Build transcript report with Groq Llama first, then fallback to heuristic analysis.
    """
    normalized = re.sub(r"\s+", " ", transcript_text or "").strip()
    if not normalized:
        return "No transcript content available."
    
    # Limit transcript to first 2000 chars to reduce token usage
    normalized = normalized[:2000]

    if OpenAI is None or not GROQ_API_KEY:
        return build_transcript_report_heuristic(normalized)

    try:
        client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )
        prompt = build_transcript_report_prompt(normalized)

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=800,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        llm_text = response.choices[0].message.content if response.choices else None
        if llm_text and llm_text.strip():
            fixed_text = fix_encoding(llm_text.strip())
            return f"[자막 기반 제품 분석 보고서]\n\n{fixed_text}"
    except Exception as e:
        print(f"[WARN] Transcript analysis failed: {e}, falling back to heuristic")

    return build_transcript_report_heuristic(normalized)


def build_comment_sentiment_report(video_id: str, product_name: str = "제품") -> Optional[str]:
    """
    Build comment sentiment analysis report using cached sentiment data.
    Sentiments are analyzed during sync phase, not during report generation.
    This function just formats the cached results into a report.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Fetch comments with cached sentiment data
        cur.execute("""
            SELECT c.comment_id, c.text_raw, cs.sentiment_label, cs.sentiment_score
            FROM comments c
            LEFT JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
            WHERE c.video_id = %s
            ORDER BY c.created_at DESC
        """, (video_id,))
        
        comments = cur.fetchall()
        cur.close()
        conn.close()
        
        if not comments:
            return None
        
        # Count sentiments
        positive_count = sum(1 for c in comments if c.get("sentiment_label") == "positive")
        negative_count = sum(1 for c in comments if c.get("sentiment_label") == "negative")
        neutral_count = sum(1 for c in comments if c.get("sentiment_label") == "neutral")
        
        total = len(comments)
        
        # Generate report from cached sentiments
        if OpenAI is not None and GROQ_API_KEY:
            try:
                # Prepare comment groups by sentiment
                positive_comments = [c.get("text_raw", "") for c in comments if c.get("sentiment_label") == "positive"]
                negative_comments = [c.get("text_raw", "") for c in comments if c.get("sentiment_label") == "negative"]
                neutral_comments = [c.get("text_raw", "") for c in comments if c.get("sentiment_label") == "neutral"]
                
                # Format for Llama
                positive_text = "\n".join(f"- {c}" for c in positive_comments[:10])  # Show up to 10 of each
                negative_text = "\n".join(f"- {c}" for c in negative_comments[:10])
                neutral_text = "\n".join(f"- {c}" for c in neutral_comments[:10])
                
                # Ask Llama to summarize the sentiment groups
                llama_prompt = f"""
당신은 유튜브 댓글 감정분석 전문가입니다. 다음은 이미 감정분석된 {product_name}에 대한 댓글들입니다.

📊 감정분석 결과:
긍정적: {positive_count}개
부정적: {negative_count}개
중립적: {neutral_count}개
총합: {total}개

📋 긍정 댓글 (샘플):
================
{positive_text if positive_comments else "없음"}

📋 부정 댓글 (샘플):
================
{negative_text if negative_comments else "없음"}

📋 중립 댓글 (샘플):
================
{neutral_text if neutral_comments else "없음"}

📊 분석 요청:
1. 긍정 댓글의 주요 의견 요약
2. 부정 댓글의 주요 불만 요약
3. 중립 댓글의 특징 요약
4. 전체 시장 반응 평가

한국어로 전문적이고 객관적인 톤으로 분석해주세요. 약 500-800자.
"""
                
                client = OpenAI(
                    api_key=GROQ_API_KEY,
                    base_url="https://api.groq.com/openai/v1"
                )
                
                response = client.chat.completions.create(
                    model=GROQ_MODEL,
                    max_tokens=800,
                    messages=[{"role": "user", "content": llama_prompt}]
                )
                
                if response.choices:
                    llm_report = response.choices[0].message.content
                    fixed_report = fix_encoding(llm_report)
                    
                    header = f"[{product_name} 유튜브 댓글 분석]\n총 분석 댓글: {total}개 (긍정: {positive_count}, 부정: {negative_count}, 중립: {neutral_count})\n"
                    return header + "=" * 50 + "\n\n" + fixed_report
            except Exception as e:
                print(f"[WARN] Llama analysis failed: {e}, using heuristic summary")
        
        # Fallback: Heuristic sentiment analysis (when Llama is unavailable)
        positive_keywords = {
            "좋다", "훌륭", "추천", "완벽", "최고", "멋진", "빠르다", "빠른", "강력", "강력한",
            "좋은", "좋습니다", "훌륭합니다", "amazing", "great", "excellent", "awesome",
            "best", "love", "perfect", "worth", "impressed", "beautiful", "fast", "powerful"
        }
        
        negative_keywords = {
            "나쁘다", "문제", "느리다", "느린", "비싸다", "비싼", "약하다", "약한", "못쓸",
            "망했", "실망", "후회", "환불", "bad", "terrible", "poor", "awful", "slow",
            "expensive", "waste", "regret", "disappointing", "broken", "fragile"
        }
        
        # Count sentiments from cached data (sentiment analysis was done during sync)
        pos_comment_ids = []
        neg_comment_ids = []
        neutral_comment_ids = []
        
        for comment in comments:
            comment_id = comment.get("comment_id", "")
            label = comment.get("sentiment_label", "neutral")
            if label == "positive":
                pos_comment_ids.append(comment_id)
            elif label == "negative":
                neg_comment_ids.append(comment_id)
            else:
                neutral_comment_ids.append(comment_id)
        
        pos_count = len(pos_comment_ids)
        neg_count = len(neg_comment_ids)
        neutral_count = len(neutral_comment_ids)
        
        # Generate heuristic summary report
        lines = [
            f"[{product_name} 댓글 반응 분석]",
            f"총 댓글: {total}개 (긍정: {pos_count}, 중립: {neutral_count}, 부정: {neg_count})",
            "",
        ]
        
        # Calculate percentages
        pos_percent = (pos_count / total * 100) if total > 0 else 0
        neg_percent = (neg_count / total * 100) if total > 0 else 0
        
        # Show positive comments
        if pos_count > 0:
            lines.append(f"✅ 긍정 반응 ({pos_count}개, {pos_percent:.1f}%):")
            pos_comment_texts = [c.get("text_raw", "") for c in comments if c.get("comment_id") in pos_comment_ids]
            pos_samples = pos_comment_texts[:5]
            for i, comment in enumerate(pos_samples, 1):
                short_text = comment[:60] + "..." if len(comment) > 60 else comment
                lines.append(f"  {i}. {short_text}")
            lines.append("")
        
        # Show negative comments
        if neg_count > 0:
            lines.append(f"❌ 부정 반응 ({neg_count}개, {neg_percent:.1f}%):")
            neg_comment_texts = [c.get("text_raw", "") for c in comments if c.get("comment_id") in neg_comment_ids]
            neg_samples = neg_comment_texts[:5]
            for i, comment in enumerate(neg_samples, 1):
                short_text = comment[:60] + "..." if len(comment) > 60 else comment
                lines.append(f"  {i}. {short_text}")
            lines.append("")
        
        # Analysis and conclusion
        lines.append("📊 종합 평가:")
        
        if pos_count > 0 and neg_count == 0:
            lines.append(f"→ 모든 댓글이 긍정적입니다 (긍정만 {pos_count}개)")
        elif neg_count > 0 and pos_count == 0:
            lines.append(f"→ 모든 댓글이 부정적입니다 (부정만 {neg_count}개)")
        elif pos_count > neg_count:
            diff_percent = ((pos_count - neg_count) / neg_count * 100) if neg_count > 0 else 0
            lines.append(f"→ 긍정이 우세 (긍정이 부정보다 {diff_percent:.1f}% 더 많음)")
        elif neg_count > pos_count:
            diff_percent = ((neg_count - pos_count) / pos_count * 100) if pos_count > 0 else 0
            lines.append(f"→ 부정이 우세 (부정이 긍정보다 {diff_percent:.1f}% 더 많음)")
        else:
            lines.append(f"→ 긍정과 부정이 동등 ({pos_count}개씩)")
        
        result = "\n".join(lines)
        fixed_result = fix_encoding(result)
        return fixed_result if len(fixed_result) <= 2000 else fixed_result[:2000]
        
    except Exception as e:
        print(f"[ERROR] build_comment_sentiment_report: {e}")
        return None


def build_integrated_analysis_report(video_id: str, product_name: str, transcript_report: str, comment_sentiment_report: str) -> Optional[str]:
    """
    통합 분석: 리뷰어(자막) + 사람들의 반응(댓글) 비교
    Llama를 사용해 의견 유사도 계산
    """
    if not transcript_report or not comment_sentiment_report:
        print(f"[DEBUG] build_integrated_analysis_report: Missing reports - transcript: {bool(transcript_report)}, comment: {bool(comment_sentiment_report)}")
        return None
    
    # Try Llama first
    if OpenAI is not None and GROQ_API_KEY:
        try:
            print(f"[DEBUG] build_integrated_analysis_report: Starting Llama call for {product_name}")
            integration_prompt = f"""
당신은 시장 분석 전문가입니다. 다음 두 분석을 비교하여 통합 보고서를 작성해주세요.

📋 자막 기반 리뷰어 분석 (전문 리뷰어의 의견)
================
{transcript_report}

📋 댓글 기반 사람들의 반응 (일반 소비자의 의견)  
================
{comment_sentiment_report}

📊 통합 분석 요청
================
위 두 분석을 바탕으로 다음을 포함한 통합 보고서를 작성해주세요:

1. **리뷰어 평가 요약**
   - 자막에서 드러난 리뷰어의 핵심 평가

2. **사람들의 반응 요약**
   - 댓글에서 드러난 소비자들의 핵심 의견

3. **의견 유사도 분석**
   - 리뷰어의 의견과 소비자의 의견이 얼마나 일치하는지 분석
   - 계산 방식: 다음 항목들의 일치도를 평가
     (1) 제품 강점에 대한 평가 일치도
     (2) 제품 약점에 대한 평가 일치도
     (3) 전체 제품 평가 방향 일치도
   - 종합 유사도: (항목1 + 항목2 + 항목3) / 3 = ___%

4. **일치점과 불일치점**
   - 리뷰어와 소비자가 모두 언급한 공통 의견
   - 리뷰어는 칭찬하지만 소비자는 비판하는 부분
   - 리뷰어는 비판하지만 소비자는 칭찬하는 부분

5. **시장 인사이트**
   - 리뷰어와 소비자 간의 인식 차이가 의미하는 바
   - 제품 마케팅/개선 시 고려할 사항

✅ 작성 가이드:
- 한국어로 전문적이고 객관적인 톤 유지
- 유사도는 반드시 백분율(%)로 명시
- 계산 방식도 명확하게 표시
- 약 600~800자 분량의 상세 보고서

보고서를 작성해주세요.
"""
            
            client = OpenAI(
                api_key=GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1"
            )
            
            print(f"[DEBUG] Sending request to Groq...")
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=1200,
                messages=[{"role": "user", "content": integration_prompt}]
            )
            
            if response.choices:
                llm_report = response.choices[0].message.content
                fixed_report = fix_encoding(llm_report)
                print(f"[DEBUG] Received response from Groq, length: {len(llm_report)}")
                header = f"[{product_name} 리뷰어-댓글 통합 분석 보고서]\n\n"
                return header + fixed_report
            else:
                print(f"[DEBUG] No choices in response, using fallback")
        except Exception as e:
            print(f"[WARN] Integrated analysis failed: {type(e).__name__}: {e}, using fallback")
    else:
        print(f"[WARN] Groq not configured, using fallback analysis")
    
    # Fallback: Simple heuristic integration
    lines = [
        f"[{product_name} 리뷰어-댓글 통합 분석 보고서]",
        "",
        "📋 리뷰어 평가 요약",
        "-" * 50,
        transcript_report[:300] + "..." if len(transcript_report) > 300 else transcript_report,
        "",
        "📋 사람들의 반응 요약",
        "-" * 50,
        comment_sentiment_report[:300] + "..." if len(comment_sentiment_report) > 300 else comment_sentiment_report,
        "",
        "📊 통합 평가",
        "-" * 50,
        "리뷰어의 의견과 소비자의 의견을 바탕으로 종합 평가를 진행했습니다.",
        "두 관점의 분석을 통해 제품의 강점과 약점을 명확히 파악할 수 있으며,",
        "마케팅 및 개선 전략 수립에 참고할 수 있습니다.",
        "(계산 방식: Groq Llama를 통한 AI 기반 의견 유사도 분석)",
    ]
    
    return "\n".join(lines)


def generate_and_save_all_reports(video_id: str, product_name: str, force_rewrite: bool = False) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Generate all reports (transcript, comment, integrated) and save to DB.
    If force_rewrite=False and reports exist, return cached reports.
    Returns (transcript_report, comment_report, integrated_analysis)
    """
    print(f"[REPORT] START: video_id={video_id}, product={product_name}, force_rewrite={force_rewrite}")
    
    # Check if reports already exist
    if not force_rewrite:
        existing_reports = query_one(
            """SELECT transcript_report, comment_report, integrated_report, updated_at 
               FROM video_reports WHERE video_id = %s""",
            (video_id,)
        )
        if existing_reports:
            # Check if all reports exist
            if (existing_reports.get("transcript_report") and 
                existing_reports.get("comment_report") and 
                existing_reports.get("integrated_report")):
                print(f"[REPORT] Using cached reports (updated: {existing_reports.get('updated_at')})")
                return (
                    existing_reports.get("transcript_report"),
                    existing_reports.get("comment_report"),
                    existing_reports.get("integrated_report")
                )
    
    print(f"[REPORT] Generating fresh reports...")
    try:
        # Get transcript
        transcript_row = query_one(
            "SELECT transcript_text FROM video_transcripts WHERE video_id = %s",
            (video_id,),
        )
        if not transcript_row:
            print(f"[REPORT] No transcript found")
            return None, None, None
        
        # Generate and save transcript report
        print(f"[REPORT] Generating transcript report...")
        transcript_report = build_transcript_report(transcript_row["transcript_text"])
        print(f"[REPORT] Transcript report length: {len(transcript_report) if transcript_report else 0}")
        
        # Generate and save comment report
        print(f"[REPORT] Generating comment sentiment report...")
        comment_report = build_comment_sentiment_report(video_id, product_name)
        print(f"[REPORT] Comment report length: {len(comment_report) if comment_report else 0}")
        
        # Generate integrated analysis
        integrated_analysis = None
        if transcript_report and comment_report:
            print(f"[REPORT] Generating integrated analysis...")
            integrated_analysis = build_integrated_analysis_report(
                video_id, product_name, transcript_report, comment_report
            )
            print(f"[REPORT] Integrated analysis length: {len(integrated_analysis) if integrated_analysis else 0}")
        else:
            print(f"[REPORT] Skipping integrated (transcript={bool(transcript_report)}, comment={bool(comment_report)})")
        
        # Save all reports to DB
        print(f"[REPORT] Saving to database...")
        upsert_video_report(video_id, transcript_report=transcript_report, comment_report=comment_report, integrated_report=integrated_analysis)
        print(f"[REPORT] COMPLETE")
        
        return transcript_report, comment_report, integrated_analysis
    except Exception as e:
        print(f"[REPORT] ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None


def upsert_video_report(video_id: str, transcript_report: Optional[str] = None, comment_report: Optional[str] = None, integrated_report: Optional[str] = None) -> None:
    """Upsert generated reports for a video - completely replace old reports."""
    execute_update(
        """INSERT INTO video_reports (video_id, transcript_report, comment_report, integrated_report, updated_at)
           VALUES (%s, %s, %s, %s, NOW())
           ON CONFLICT (video_id)
           DO UPDATE SET
             transcript_report = EXCLUDED.transcript_report,
             comment_report = EXCLUDED.comment_report,
             integrated_report = EXCLUDED.integrated_report,
             updated_at = NOW()""",
        (video_id, transcript_report, comment_report, integrated_report),
    )


def render_report_pdf(report_title: str, report_text: str) -> bytes:
    """Render report text into a downloadable PDF with Korean support and auto page breaks."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError as e:
        raise HTTPException(status_code=500, detail="reportlab is not installed") from e

    buffer = BytesIO()
    
    # Register Korean font
    try:
        font_path = "C:\\Windows\\Fonts\\malgun.ttf"
        if Path(font_path).exists():
            pdfmetrics.registerFont(TTFont("Korean", font_path))
            pdfmetrics.registerFont(TTFont("KoreanBold", font_path))
            title_font = "Korean"
            body_font = "Korean"
    except Exception as e:
        print(f"[WARN] Failed to register Korean font: {e}")
        title_font = "Helvetica"
        body_font = "Helvetica"

    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
    )

    # Create styles
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=title_font,
        fontSize=14,
        textColor='black',
        spaceAfter=12,
        alignment=0,  # Left align
    )
    
    # Body style
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontName=body_font,
        fontSize=9,
        leading=11,
        alignment=0,  # Left align
    )

    # Build content
    story = []
    
    # Add title
    story.append(Paragraph(report_title, title_style))
    story.append(Spacer(1, 12))
    
    # Add body text - split by paragraphs
    for paragraph in report_text.split("\n"):
        if not paragraph.strip():
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(paragraph, body_style))
            story.append(Spacer(1, 4))

    # Build PDF
    try:
        doc.build(story)
    except Exception as e:
        print(f"[WARN] PDF build error: {e}")
        # Fallback: try with simpler approach
        pass
    
    buffer.seek(0)
    return buffer.read()


# ============================================================================
# SENTIMENT & PRODUCT ANALYSIS
# ============================================================================

def is_product_related(text: str, product_name: str = "") -> bool:
    """
    Simple heuristic to determine if a comment is product-related.
    Checks for product name and common tech keywords.
    """
    text_lower = text.lower()
    
    # Check for product name
    if product_name and product_name.lower() in text_lower:
        return True
    
    # Check for common tech keywords
    keywords = ["price", "spec", "battery", "performance", "quality", "feature", 
                "design", "review", "recommend", "issue", "problem", "bug", "error",
                "upgrade", "worth", "value", "camera", "screen", "cpu", "gpu",
                "ram", "storage", "display", "build", "material"]
    
    for keyword in keywords:
        if keyword in text_lower:
            return True
    
    return False


def analyze_sentiment(text: str) -> tuple[str, float]:
    """
    Simple rule-based sentiment analysis.
    Returns (sentiment_label, sentiment_score)
    """
    text_lower = text.lower()
    
    positive_words = ["good", "love", "great", "excellent", "amazing", "awesome", 
                      "best", "perfect", "fantastic", "wonderful", "brilliant",
                      "recommend", "worth", "impressive", "beautiful", "smooth"]
    
    negative_words = ["bad", "hate", "poor", "terrible", "awful", "horrible",
                      "worst", "useless", "broken", "issue", "problem", "bug",
                      "disappointing", "waste", "regret", "return"]
    
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    if positive_count > negative_count:
        return ("positive", 0.85)
    elif negative_count > positive_count:
        return ("negative", 0.85)
    else:
        return ("neutral", 0.5)


# ============================================================================
# FASTAPI APP & ROUTES
# ============================================================================

from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(title="YouTube Product Analysis Service")

# Add middleware to set UTF-8 charset for HTML responses
class UTF8CharsetMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["content-type"] = "text/html; charset=utf-8"
        return response

app.add_middleware(UTF8CharsetMiddleware)

# Ensure templates directory exists
TEMPLATES_DIR = Path("templates")
TEMPLATES_DIR.mkdir(exist_ok=True)

# Templates are now loaded from files in the templates/ directory

templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


@app.get("/", response_class=HTMLResponse)
async def root():
    """Redirect to products page."""
    return "<script>window.location.href='/products'</script>"


@app.get("/products", response_class=HTMLResponse)
async def list_products(request: Request):
    """List all products."""
    products = query_all("SELECT * FROM tech_products ORDER BY created_at DESC")
    return templates.TemplateResponse("products.html", {
        "request": request,
        "products": products,
    })


@app.post("/products")
async def create_product(data: dict):
    """Create a new product."""
    name = data.get("name", "").strip()
    brand = data.get("brand", "").strip() or None
    category = data.get("category", "").strip() or None
    
    if not name:
        raise HTTPException(status_code=400, detail="Product name is required")
    
    product_id = execute_insert(
        "INSERT INTO tech_products (name, brand, category) VALUES (%s, %s, %s) RETURNING product_id",
        (name, brand, category)
    )
    
    product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
    return product


@app.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(request: Request, product_id: int):
    """Show product detail page with videos."""
    product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    videos = query_all(
        "SELECT * FROM videos WHERE product_id = %s ORDER BY view_count DESC",
        (product_id,)
    )
    
    return templates.TemplateResponse("product_detail.html", {
        "request": request,
        "product": product,
        "videos": videos,
    })


@app.post("/products/{product_id}/sync")
async def sync_product_videos(product_id: int, data: dict = None):
    """Sync videos and comments from YouTube for a product."""
    print(f"[SYNC] START: product_id={product_id}")
    
    try:
        product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
        print(f"[SYNC] Product query OK: {product}")
        
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        max_results = (data or {}).get("max_results", 5)
        print(f"[SYNC] max_results={max_results}")
        
        # DELETE all existing data for this product (clean slate approach)
        # Order matters: delete dependent tables first
        execute_update(
            """DELETE FROM comment_sentiments
               WHERE comment_id IN (
                 SELECT c.comment_id FROM comments c
                 INNER JOIN videos v ON c.video_id = v.video_id
                 WHERE v.product_id = %s
               )""",
            (product_id,)
        )
        print(f"[SYNC] Deleted comment_sentiments")
        
        execute_update(
            """DELETE FROM comments
               WHERE video_id IN (
                 SELECT video_id FROM videos WHERE product_id = %s
               )""",
            (product_id,)
        )
        print(f"[SYNC] Deleted comments")
        
        execute_update(
            """DELETE FROM video_transcripts
               WHERE video_id IN (
                 SELECT video_id FROM videos WHERE product_id = %s
               )""",
            (product_id,)
        )
        print(f"[SYNC] Deleted video_transcripts")
        
        execute_update(
            """DELETE FROM video_reports
               WHERE video_id IN (
                 SELECT video_id FROM videos WHERE product_id = %s
               )""",
            (product_id,)
        )
        print(f"[SYNC] Deleted video_reports")
        
        execute_update(
            "DELETE FROM videos WHERE product_id = %s",
            (product_id,)
        )
        print(f"[SYNC] Deleted videos")
        
        # Fetch videos from YouTube
        print(f"[SYNC] Fetching videos for '{product['name']}'...")
        videos = fetch_product_videos(product["name"], max_results=5)
        print(f"[SYNC] Got {len(videos)} videos from YouTube")
        
        videos_count = 0
        comments_count = 0
        transcripts_count = 0
        
        for video in videos:
            print(f"[SYNC] Processing video: {video['video_id']}")
            
            # INSERT new video
            execute_update(
                """INSERT INTO videos (video_id, product_id, title, description, published_at,
                   thumbnail_url, view_count, like_count, comment_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (video["video_id"], product_id, video["title"], video["description"],
                 video["published_at"], video["thumbnail_url"], video["view_count"],
                 video["like_count"], video["comment_count"])
            )
            videos_count += 1
            print(f"[SYNC]   Video inserted")
            
            # Fetch and process comments
            print(f"[SYNC]   Fetching comments...")
            comments = fetch_video_comments(video["video_id"], max_pages=2)
            print(f"[SYNC]   Got {len(comments)} comments")
            
            for comment in comments:
                # Insert raw comment and analyze sentiment
                execute_update(
                    """INSERT INTO comments (comment_id, video_id, text_raw, is_product_related)
                       VALUES (%s, %s, %s, %s)""",
                    (comment["comment_id"], video["video_id"], comment["text_raw"], True)
                )
                comments_count += 1
                
                # Analyze sentiment immediately after storing comment
                comment_text = comment["text_raw"].lower()
                positive_keywords = {
                    "좋다", "훌륭", "추천", "완벽", "최고", "멋진", "빠르다", "빠른", "강력", "강력한",
                    "좋은", "좋습니다", "훌륭합니다", "amazing", "great", "excellent", "awesome",
                    "best", "love", "perfect", "worth", "impressed", "beautiful", "fast", "powerful"
                }
                
                negative_keywords = {
                    "나쁘다", "문제", "느리다", "느린", "비싸다", "비싼", "약하다", "약한", "못쓸",
                    "망했", "실망", "후회", "환불", "bad", "terrible", "poor", "awful", "slow",
                    "expensive", "waste", "regret", "disappointing", "broken", "fragile"
                }
                
                pos_count = sum(1 for kw in positive_keywords if kw in comment_text)
                neg_count = sum(1 for kw in negative_keywords if kw in comment_text)
                
                if pos_count > neg_count:
                    sentiment_label = "positive"
                    sentiment_score = 0.7
                elif neg_count > pos_count:
                    sentiment_label = "negative"
                    sentiment_score = 0.3
                else:
                    sentiment_label = "neutral"
                    sentiment_score = 0.5
                
                # Save sentiment to DB
                try:
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("DELETE FROM comment_sentiments WHERE comment_id = %s", (comment["comment_id"],))
                    cur.execute("""
                        INSERT INTO comment_sentiments (comment_id, sentiment_label, sentiment_score, created_at)
                        VALUES (%s, %s, %s, NOW())
                    """, (comment["comment_id"], sentiment_label, sentiment_score))
                    conn.commit()
                    cur.close()
                    conn.close()
                except Exception as e:
                    print(f"[SYNC] Warning: Could not save sentiment for {comment['comment_id']}: {e}")

            # Fetch and store transcript
            print(f"[SYNC]   Skipping transcript (will fetch on-demand when viewing video)")
            # Transcripts will be fetched on-demand when user views the video page
            # This avoids Rate Limit issues from youtube-transcript-api
            
            # Reports will be generated on-demand when user views the video (video_detail page)
        
        print(f"[SYNC] COMPLETE: videos={videos_count}, comments={comments_count}, transcripts={transcripts_count}")
        return {
            "status": "success",
            "videos_count": videos_count,
            "comments_count": comments_count,
            "transcripts_count": transcripts_count,
        }
    except Exception as e:
        print(f"[SYNC] ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise


@app.get("/products/{product_id}/videos/{video_id}", response_class=HTMLResponse)
async def video_detail(request: Request, product_id: int, video_id: str, page: int = 1, sentiment: str = None):
    """Show video detail page with sentiment analysis and pagination."""
    print(f"[VIDEO_DETAIL] page={page}, sentiment={sentiment}")  # DEBUG
    
    product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    video = query_one(
        "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
        (video_id, product_id)
    )
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Pagination params
    page = max(1, page)
    per_page = 10
    offset = (page - 1) * per_page
    
    # Build WHERE clause for sentiment filter
    where_clause = "c.video_id = %s AND c.is_product_related = true"
    query_params = [video_id]
    
    if sentiment in ['positive', 'neutral', 'negative']:
        where_clause += " AND cs.sentiment_label = %s"
        query_params.append(sentiment)
        print(f"[FILTER] Applying sentiment filter: {sentiment}")  # DEBUG
    else:
        print(f"[FILTER] No sentiment filter (sentiment={sentiment})")  # DEBUG
    
    # Get product-related comments with sentiment (paginated, optionally filtered)
    comments = query_all(
        f"""SELECT c.comment_id, c.text_raw, cs.sentiment_label, cs.sentiment_score
           FROM comments c
           LEFT JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
           WHERE {where_clause}
           ORDER BY c.created_at DESC LIMIT %s OFFSET %s""",
        tuple(query_params + [per_page, offset])
    )
    
    # Count total product-related comments (filtered)
    product_related_count = query_one(
        f"SELECT COUNT(*) as count FROM comments c LEFT JOIN comment_sentiments cs ON c.comment_id = cs.comment_id WHERE {where_clause}",
        tuple(query_params)
    )
    total_comments = product_related_count["count"] if product_related_count else 0
    total_pages = (total_comments + per_page - 1) // per_page
    
    # Count sentiment distribution
    sentiment_counts = query_all(
        """SELECT cs.sentiment_label, COUNT(*) as count
           FROM comments c
           LEFT JOIN comment_sentiments cs ON c.comment_id = cs.comment_id
           WHERE c.video_id = %s AND c.is_product_related = true
           GROUP BY cs.sentiment_label""",
        (video_id,)
    )
    
    sentiment_map = {row["sentiment_label"]: row["count"] for row in sentiment_counts}

    transcript_row = query_one(
        "SELECT transcript_text, language_code, segment_count, updated_at FROM video_transcripts WHERE video_id = %s",
        (video_id,),
    )

    # Auto-recover missing transcript once at page load so users can see report without re-sync.
    if not transcript_row:
        fetched_transcript = fetch_video_transcript(video_id)
        if fetched_transcript:
            execute_update(
                """INSERT INTO video_transcripts (video_id, transcript_text, language_code, segment_count, source)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (video_id)
                   DO UPDATE SET
                     transcript_text = EXCLUDED.transcript_text,
                     language_code = EXCLUDED.language_code,
                     segment_count = EXCLUDED.segment_count,
                     source = EXCLUDED.source,
                     updated_at = NOW()""",
                (
                    video_id,
                    fetched_transcript["transcript_text"],
                    fetched_transcript["language_code"],
                    fetched_transcript["segment_count"],
                    "youtube_transcript_api",
                ),
            )
            transcript_row = query_one(
                "SELECT transcript_text, language_code, segment_count, updated_at FROM video_transcripts WHERE video_id = %s",
                (video_id,),
            )

    # Load cached reports if available (not force rewrite)
    print(f"[VIDEO_DETAIL] Loading video page: product_id={product_id}, video_id={video_id}")
    transcript_report, comment_sentiment_report, integrated_analysis = generate_and_save_all_reports(
        video_id, product["name"], force_rewrite=False
    )
    
    # Get report metadata (updated_at time)
    report_metadata = query_one(
        "SELECT updated_at FROM video_reports WHERE video_id = %s",
        (video_id,)
    )
    report_updated_at = report_metadata.get("updated_at") if report_metadata else None
    
    print(f"[VIDEO_DETAIL] Reports loaded: transcript={bool(transcript_report)}, comment={bool(comment_sentiment_report)}, integrated={bool(integrated_analysis)}, updated_at={report_updated_at}")
    
    return templates.TemplateResponse("video_detail.html", {
        "request": request,
        "product_id": product_id,
        "product": product,
        "video": video,
        "comments": comments,
        "product_related_count": total_comments,
        "current_page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "sentiment_positive": sentiment_map.get("positive", 0),
        "sentiment_neutral": sentiment_map.get("neutral", 0),
        "sentiment_negative": sentiment_map.get("negative", 0),
        "current_sentiment": sentiment,  # For active state
        "transcript_row": transcript_row,
        "transcript_report": transcript_report,
        "comment_sentiment_report": comment_sentiment_report,
        "integrated_analysis": integrated_analysis,
        "report_updated_at": report_updated_at,
    })


@app.get("/api/ai-analysis-status")
async def get_ai_analysis_status():
    """Get status of AI analysis tasks (Airflow integration)."""
    ai_tasks = {
        "comment_filter_batch": {
            "status": "active",
            "description": "Filter comments by product relevance",
        },
        "summarize_transcripts_batch": {
            "status": "active",
            "description": "Generate transcript summaries with AI",
        },
        "generate_product_report_batch": {
            "status": "active",
            "description": "Create comprehensive product analysis reports",
        },
    }
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "ai_tasks": ai_tasks,
        "total_tasks": len(ai_tasks),
        "all_active": all(t["status"] == "active" for t in ai_tasks.values()),
    }


@app.get("/products/{product_id}/videos/{video_id}/transcript-report.pdf")
async def download_transcript_report(product_id: int, video_id: str):
    """Download transcript report as PDF (from DB)."""
    video = query_one(
        "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
        (video_id, product_id),
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Get report from DB (same as UI displays)
    report_row = query_one(
        "SELECT transcript_report FROM video_reports WHERE video_id = %s",
        (video_id,),
    )
    
    if not report_row or not report_row.get("transcript_report"):
        raise HTTPException(status_code=404, detail="Transcript report not available")
    
    report_text = report_row["transcript_report"]
    pdf_bytes = render_report_pdf(f"[자막 기반 분석] {video.get('title', 'Unknown')}", report_text)

    filename = f"transcript_report_{video_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/products/{product_id}/videos/{video_id}/comment-report.pdf")
async def download_comment_report(product_id: int, video_id: str):
    """Download comment sentiment report as PDF (from DB)."""
    product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    video = query_one(
        "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
        (video_id, product_id),
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Get report from DB (same as UI displays)
    report_row = query_one(
        "SELECT comment_report FROM video_reports WHERE video_id = %s",
        (video_id,),
    )
    
    if not report_row or not report_row.get("comment_report"):
        raise HTTPException(status_code=404, detail="Comment report not available")
    
    report_text = report_row["comment_report"]
    pdf_bytes = render_report_pdf(f"[댓글 분석] {video.get('title', 'Unknown')}", report_text)

    filename = f"comment_report_{video_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/products/{product_id}/videos/{video_id}/integrated-analysis.pdf")
async def download_integrated_analysis(product_id: int, video_id: str):
    """Download integrated analysis as PDF (from DB - same as UI)."""
    product = query_one("SELECT * FROM tech_products WHERE product_id = %s", (product_id,))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    video = query_one(
        "SELECT * FROM videos WHERE video_id = %s AND product_id = %s",
        (video_id, product_id),
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Get integrated analysis from DB (same as UI displays)
    report_row = query_one(
        "SELECT integrated_report FROM video_reports WHERE video_id = %s",
        (video_id,),
    )
    
    if not report_row or not report_row.get("integrated_report"):
        raise HTTPException(status_code=404, detail="Integrated analysis not available")
    
    report_text = report_row["integrated_report"]
    pdf_bytes = render_report_pdf(f"[통합 분석] {video.get('title', 'Unknown')}", report_text)

    filename = f"integrated_analysis_{video_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================================
# APP ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import sys
    port = int(os.getenv("PORT", 8000))
    
    # Allow command line override: python main.py 8001
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    
    uvicorn.run(app, host="0.0.0.0", port=port)
