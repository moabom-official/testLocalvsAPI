# 🎥 YouTube Product Analysis System - Architecture

## 📊 System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface (Web)                        │
│                     FastAPI + Jinja2 Templates                      │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend (main_youtube_analysis.py)   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   Product    │  │    Video     │  │   Comment    │             │
│  │  Management  │  │   Sync/Fetch │  │   Analysis   │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│         │                 │                   │                      │
│         └─────────────────┴───────────────────┘                      │
│                           │                                          │
└───────────────────────────┼──────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ↓                   ↓                   ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  PostgreSQL  │  │  YouTube API │  │   Groq API   │
│   Database   │  │ (Data v3 API)│  │ (Llama 3.3)  │
└──────────────┘  └──────────────┘  └──────────────┘
        │
        ↓
┌──────────────────────────────────────────────────┐
│            PDF Report Generation                 │
│         (FPDF + Korean Font Support)             │
└──────────────────────────────────────────────────┘
```

---

## 🏗️ System Architecture (Feature-based)

### 1️⃣ Product Management Module
```
┌─────────────────────────────────────────┐
│      Product Management                 │
├─────────────────────────────────────────┤
│ • Add/Edit/Delete Products              │
│ • Product List View                     │
│ • Link YouTube Channels                 │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│      Database (tech_products)           │
│  - product_id (PK)                      │
│  - name                                 │
│  - description                          │
│  - youtube_channel_id                   │
└─────────────────────────────────────────┘
```

### 2️⃣ Video Sync Module
```
┌─────────────────────────────────────────┐
│         Video Sync Service              │
├─────────────────────────────────────────┤
│ 1. Fetch videos from YouTube Channel    │
│    ↓ (YouTube Data API v3)              │
│ 2. Store video metadata                 │
│    ↓ (videos table)                     │
│ 3. Fetch transcripts with yt-dlp        │
│    ↓ (video_transcripts table)          │
│ 4. Fetch comments (top-level)           │
│    ↓ (comments table)                   │
│ 5. Filter product-related comments      │
│    ↓ (Keyword matching)                 │
│ 6. Sentiment analysis (Heuristic)       │
│    ↓ (comment_sentiments table)         │
└─────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────┐
│    External APIs Used                   │
│  • YouTube Data API v3                  │
│  • yt-dlp (transcript extraction)       │
└─────────────────────────────────────────┘
```

### 3️⃣ Comment Analysis Module
```
┌─────────────────────────────────────────────────────┐
│           Comment Processing Pipeline               │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Raw Comments                                       │
│       ↓                                             │
│  Product Keyword Filter                             │
│   (자막 언급 check: "고프로", "gopro" etc.)          │
│       ↓                                             │
│  Sentiment Analysis (Heuristic)                     │
│   • Positive keywords: "좋다", "훌륭", "최고" etc.    │
│   • Negative keywords: "나쁘다", "별로", "실망" etc.  │
│   • Score: 0.7 (pos) / 0.5 (neutral) / 0.3 (neg)   │
│       ↓                                             │
│  Store to DB (comment_sentiments)                   │
│       ↓                                             │
│  Generate Report (Groq Llama 3.3)                   │
│   • Input: All filtered comments                    │
│   • Output: Korean analysis report                  │
│       ↓                                             │
│  Save Report (video_reports)                        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 4️⃣ Report Generation Module
```
┌──────────────────────────────────────────────────────┐
│            AI-Powered Report Generation              │
├──────────────────────────────────────────────────────┤
│                                                      │
│  3 Types of Reports:                                 │
│  ┌────────────────────────────────────────────┐     │
│  │ 1. Transcript Report                       │     │
│  │    Input: Video transcript                 │     │
│  │    Analysis: Product features, pros/cons   │     │
│  └────────────────────────────────────────────┘     │
│                 ↓                                    │
│  ┌────────────────────────────────────────────┐     │
│  │ 2. Comment Sentiment Report                │     │
│  │    Input: All product-related comments     │     │
│  │    Analysis: Consumer reactions & opinions │     │
│  └────────────────────────────────────────────┘     │
│                 ↓                                    │
│  ┌────────────────────────────────────────────┐     │
│  │ 3. Integrated Analysis Report              │     │
│  │    Input: Transcript + Comment reports     │     │
│  │    Analysis: Reviewer vs Consumer feedback │     │
│  └────────────────────────────────────────────┘     │
│                                                      │
│  LLM: Groq (llama-3.3-70b-versatile)                │
│  Output: Korean text reports                         │
│  Cache: Stored in video_reports table               │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 5️⃣ Sentiment Filtering & Pagination
```
┌──────────────────────────────────────────────────────┐
│        Interactive Sentiment Filter                  │
├──────────────────────────────────────────────────────┤
│                                                      │
│  User Interface:                                     │
│  [ 🟢 Positive ] [ 🟡 Neutral ] [ 🔴 Negative ]      │
│           ↓ (Click)                                  │
│  URL Parameter: ?sentiment=positive&page=1           │
│           ↓                                          │
│  Server-side SQL Filter:                             │
│  SELECT * FROM comments c                            │
│  JOIN comment_sentiments cs ON ...                   │
│  WHERE cs.sentiment_label = 'positive'               │
│  LIMIT 10 OFFSET 0                                   │
│           ↓                                          │
│  Display: 10 comments per page (filtered)            │
│  Pagination: Maintains sentiment filter              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 6️⃣ PDF Export Module
```
┌──────────────────────────────────────────────────────┐
│              PDF Report Export                       │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Report Type Selection:                              │
│  • Transcript Report                                 │
│  • Comment Sentiment Report                          │
│  • Integrated Analysis Report                        │
│           ↓                                          │
│  Load from DB (video_reports table)                  │
│           ↓                                          │
│  FPDF Library + Korean Font (NanumGothic.ttf)        │
│           ↓                                          │
│  Generate PDF:                                       │
│  • Header: Product name + Video title                │
│  • Body: Report content (Korean)                     │
│  • Footer: Generated timestamp                       │
│           ↓                                          │
│  Download: {report_type}-{video_id}.pdf              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

### Backend
```
┌─────────────────────────────────────────┐
│           Python 3.11+                  │
├─────────────────────────────────────────┤
│ • FastAPI (Web Framework)               │
│ • Uvicorn (ASGI Server)                 │
│ • Psycopg2 (PostgreSQL Driver)          │
│ • yt-dlp (YouTube Transcript)           │
│ • FPDF (PDF Generation)                 │
│ • Groq SDK (LLM API Client)             │
│ • python-dotenv (Environment Config)    │
└─────────────────────────────────────────┘
```

### Database
```
┌─────────────────────────────────────────┐
│         PostgreSQL 15+                  │
├─────────────────────────────────────────┤
│ Tables:                                 │
│ • tech_products                         │
│ • videos                                │
│ • video_transcripts                     │
│ • comments                              │
│ • comment_sentiments                    │
│ • video_reports                         │
└─────────────────────────────────────────┘
```

### Frontend
```
┌─────────────────────────────────────────┐
│     HTML5 + CSS3 + JavaScript           │
├─────────────────────────────────────────┤
│ • Jinja2 Templates (Server-side)        │
│ • Vanilla JavaScript (Client-side)      │
│ • Responsive Grid Layout                │
│ • No external JS frameworks             │
└─────────────────────────────────────────┘
```

### AI/ML
```
┌─────────────────────────────────────────┐
│          Groq Cloud API                 │
├─────────────────────────────────────────┤
│ Model: llama-3.3-70b-versatile          │
│ • Report generation (Korean)            │
│ • Sentiment analysis prompts            │
│ • Rate limit: 100k tokens/day           │
└─────────────────────────────────────────┘
```

---

## 🔌 External APIs Used

### 1. YouTube Data API v3
```
Purpose: Fetch video metadata and comments
Endpoints:
  • channels().list() - Get channel info
  • search().list() - Search videos by channel
  • videos().list() - Get video details
  • commentThreads().list() - Fetch top-level comments

Auth: API Key (YOUTUBE_API_KEY)
Quota: 10,000 units/day
```

### 2. yt-dlp (CLI Tool)
```
Purpose: Extract video transcripts
Usage: Subprocess call with --write-auto-sub flag
Formats: JSON subtitle files
Languages: Auto-detect (prefers Korean → English)
```

### 3. Groq API
```
Purpose: LLM-powered report generation
Model: llama-3.3-70b-versatile
Endpoints:
  • /chat/completions - Generate reports

Auth: API Key (GROQ_API_KEY)
Rate Limit: 100k tokens/day (free tier)
Output: Korean language analysis reports
```

---

## 📁 Database Schema

### Core Tables
```sql
-- Products
tech_products (
  product_id SERIAL PRIMARY KEY,
  name VARCHAR(255),
  description TEXT,
  youtube_channel_id VARCHAR(255)
)

-- Videos
videos (
  id SERIAL PRIMARY KEY,
  video_id VARCHAR(255) UNIQUE,
  product_id INTEGER REFERENCES tech_products,
  title TEXT,
  published_at TIMESTAMP,
  view_count INTEGER,
  like_count INTEGER,
  comment_count INTEGER
)

-- Transcripts
video_transcripts (
  video_id VARCHAR(255) PRIMARY KEY,
  transcript_text TEXT,
  language_code VARCHAR(10),
  segment_count INTEGER,
  source VARCHAR(50)
)

-- Comments
comments (
  comment_id VARCHAR(255) PRIMARY KEY,
  video_id VARCHAR(255) REFERENCES videos(video_id),
  text_raw TEXT,
  is_product_related BOOLEAN,
  created_at TIMESTAMP
)

-- Sentiment Analysis
comment_sentiments (
  comment_id VARCHAR(255) REFERENCES comments,
  sentiment_label VARCHAR(20),  -- 'positive', 'neutral', 'negative'
  sentiment_score FLOAT
)

-- Reports
video_reports (
  video_id VARCHAR(255) PRIMARY KEY,
  transcript_report TEXT,
  comment_sentiment_report TEXT,
  integrated_analysis TEXT,
  updated_at TIMESTAMP
)
```

---

## 🗄️ Database ERD (Entity Relationship Diagram)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PostgreSQL Database Schema                            │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────┐
│   tech_products          │
├──────────────────────────┤
│ PK product_id (SERIAL)   │
│    name (VARCHAR)        │
│    description (TEXT)    │
│    youtube_channel_id    │
└──────────────────────────┘
            │
            │ 1:N
            │
            ↓
┌──────────────────────────┐         ┌──────────────────────────┐
│   videos                 │         │   video_transcripts      │
├──────────────────────────┤         ├──────────────────────────┤
│ PK id (SERIAL)           │         │ PK video_id (VARCHAR)    │
│ UK video_id (VARCHAR)    │←───────→│    transcript_text (TEXT)│
│ FK product_id            │   1:1   │    language_code         │
│    title (TEXT)          │         │    segment_count (INT)   │
│    published_at          │         │    source (VARCHAR)      │
│    view_count (INT)      │         │    updated_at            │
│    like_count (INT)      │         └──────────────────────────┘
│    comment_count (INT)   │
└──────────────────────────┘
            │
            │ 1:N
            │
            ↓
┌──────────────────────────┐         ┌──────────────────────────┐
│   comments               │         │   comment_sentiments     │
├──────────────────────────┤         ├──────────────────────────┤
│ PK comment_id (VARCHAR)  │←───────→│ FK comment_id (VARCHAR)  │
│ FK video_id              │   1:1   │    sentiment_label       │
│    text_raw (TEXT)       │         │    sentiment_score       │
│    is_product_related    │         │                          │
│    created_at            │         │                          │
└──────────────────────────┘         └──────────────────────────┘

            ↓
            │ (associated with video)
            │
┌──────────────────────────┐
│   video_reports          │
├──────────────────────────┤
│ PK video_id (VARCHAR)    │
│    transcript_report     │
│    comment_sentiment_rep │
│    integrated_analysis   │
│    updated_at            │
└──────────────────────────┘
```

### Table Relationships

```
tech_products ──1:N──→ videos
                        │
                        ├──1:1──→ video_transcripts
                        │
                        ├──1:N──→ comments
                        │           │
                        │           └──1:1──→ comment_sentiments
                        │
                        └──1:1──→ video_reports
```

### Detailed Relationships

1. **tech_products → videos** (1:N)
   - One product can have many videos
   - FK: `videos.product_id → tech_products.product_id`

2. **videos → video_transcripts** (1:1)
   - One video has one transcript
   - FK: `video_transcripts.video_id → videos.video_id`

3. **videos → comments** (1:N)
   - One video can have many comments
   - FK: `comments.video_id → videos.video_id`

4. **comments → comment_sentiments** (1:1)
   - One comment has one sentiment analysis
   - FK: `comment_sentiments.comment_id → comments.comment_id`

5. **videos → video_reports** (1:1)
   - One video has one set of reports
   - FK: `video_reports.video_id → videos.video_id`

### Indexes

```sql
-- Primary Keys (Auto-indexed)
CREATE UNIQUE INDEX idx_tech_products_pk ON tech_products(product_id);
CREATE UNIQUE INDEX idx_videos_pk ON videos(id);
CREATE UNIQUE INDEX idx_videos_video_id ON videos(video_id);
CREATE UNIQUE INDEX idx_transcripts_pk ON video_transcripts(video_id);
CREATE UNIQUE INDEX idx_comments_pk ON comments(comment_id);
CREATE UNIQUE INDEX idx_reports_pk ON video_reports(video_id);

-- Foreign Keys
CREATE INDEX idx_videos_product_id ON videos(product_id);
CREATE INDEX idx_comments_video_id ON comments(video_id);
CREATE INDEX idx_sentiments_comment_id ON comment_sentiments(comment_id);

-- Query Optimization
CREATE INDEX idx_comments_product_related ON comments(is_product_related);
CREATE INDEX idx_sentiments_label ON comment_sentiments(sentiment_label);
CREATE INDEX idx_videos_published_at ON videos(published_at DESC);
```

### Data Constraints

```sql
-- NOT NULL constraints
ALTER TABLE tech_products 
  ALTER COLUMN name SET NOT NULL,
  ALTER COLUMN youtube_channel_id SET NOT NULL;

ALTER TABLE videos 
  ALTER COLUMN video_id SET NOT NULL,
  ALTER COLUMN product_id SET NOT NULL;

ALTER TABLE comments 
  ALTER COLUMN comment_id SET NOT NULL,
  ALTER COLUMN video_id SET NOT NULL,
  ALTER COLUMN is_product_related SET NOT NULL;

-- CHECK constraints
ALTER TABLE comment_sentiments
  ADD CONSTRAINT check_sentiment_label 
  CHECK (sentiment_label IN ('positive', 'neutral', 'negative'));

ALTER TABLE comment_sentiments
  ADD CONSTRAINT check_sentiment_score 
  CHECK (sentiment_score >= 0 AND sentiment_score <= 1);

-- DEFAULT values
ALTER TABLE comments 
  ALTER COLUMN created_at SET DEFAULT NOW();

ALTER TABLE video_reports 
  ALTER COLUMN updated_at SET DEFAULT NOW();
```

---

## 🔄 Data Flow

### Complete Pipeline
```
1. User adds product + YouTube channel
   ↓
2. Click "Sync Videos"
   ↓
3. Fetch videos from YouTube API
   ↓
4. For each video:
   a. Store video metadata
   b. Extract transcript (yt-dlp)
   c. Fetch comments (YouTube API)
   d. Filter product-related comments (keyword matching)
   e. Analyze sentiment (heuristic keywords)
   f. Store sentiment results
   ↓
5. User views video detail page
   ↓
6. Generate reports (Groq LLM):
   - Transcript analysis
   - Comment sentiment analysis
   - Integrated comparison
   ↓
7. Cache reports in DB
   ↓
8. Display on UI with:
   - Interactive sentiment filter
   - Pagination (10 per page)
   - PDF export option
```

---

## 🎯 Key Features

### ✅ Implemented Features

1. **Product Management**
   - Add/Edit/Delete tech products
   - Link to YouTube channels

2. **Video Sync**
   - Auto-fetch videos from YouTube
   - Extract transcripts
   - Fetch and filter comments

3. **Sentiment Analysis**
   - Heuristic keyword-based analysis
   - Real-time during sync (one-time)
   - Cached in database

4. **AI Report Generation**
   - 3 types of reports (transcript, comment, integrated)
   - Korean language output
   - Cached for performance

5. **Interactive UI**
   - Sentiment filtering (server-side)
   - Pagination with filter persistence
   - PDF export

### 🚧 Potential Enhancements

- [ ] Advanced LLM sentiment analysis (replace heuristic)
- [ ] Real-time video monitoring
- [ ] Comment reply threading
- [ ] Multi-product comparison
- [ ] Airflow DAG integration (scheduled sync)
- [ ] Dashboard with charts/graphs

---

## 📝 File Structure

```
Moabom_Prototype - (4)/
│
├── main_youtube_analysis.py    # Main FastAPI application
├── requirements.txt             # Python dependencies
├── .env                        # Environment variables (API keys)
│
├── templates/                  # Jinja2 HTML templates
│   ├── products.html           # Product list page
│   ├── product_detail.html     # Product + video list
│   └── video_detail.html       # Video analysis page
│
├── services/                   # Service modules
│   └── youtube_service.py      # YouTube API wrapper
│
├── llm/                        # LLM integration
│   └── groq_llm.py            # Groq API client
│
└── dags/                       # Airflow DAGs (optional)
    └── youtube_analysis_dag.py # Scheduled sync pipeline
```

---

## 🔐 Environment Variables

```bash
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/techdb

# YouTube API
YOUTUBE_API_KEY=your_youtube_api_key_here

# Groq LLM
GROQ_API_KEY=your_groq_api_key_here

# Server
HOST=0.0.0.0
PORT=8000
```

---

## 🚀 Deployment

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
# (PostgreSQL must be running)

# Run server
python main_youtube_analysis.py
# or
uvicorn main_youtube_analysis:app --reload
```

### Production Considerations
- Use environment-specific configs
- Enable HTTPS
- Set up reverse proxy (Nginx)
- Configure rate limiting
- Monitor API quota usage
- Implement logging & monitoring

---

## 📊 Performance Notes

- **Comment sync**: ~1 video/second (YouTube API limit)
- **Sentiment analysis**: Real-time during sync (cached)
- **Report generation**: 5-10 seconds per report (LLM API)
- **Report caching**: Instant load after first generation
- **Pagination**: Server-side (efficient for large datasets)

---

**Last Updated**: 2026-04-01
**Version**: 1.0
**Author**: Moabom Team
