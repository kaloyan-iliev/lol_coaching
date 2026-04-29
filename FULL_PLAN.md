# LoL AI Jungle Coach - Full Plan (End to Finish)

## Vision

An AI-powered League of Legends coaching tool that understands the game like a Diamond+ coach. It analyzes screenshots, post-game data, and live game state to give contextual, conversational coaching advice grounded in methodology from trusted coaches (@JungleGapGG, @KireiLoL, @PerryJG, Agurin).

---

## Phase 0: Knowledge Base Construction (Week 1-2)

**This is the foundation everything else builds on.**

### Step 1: Video Collection & Metadata

Create a structured catalog of coaching videos:

```
videos/
  metadata.json          # Master index of all videos
  transcripts/
    raw/                 # Raw transcripts from YouTube
    clean/               # Cleaned, timestamped transcripts
```

**metadata.json structure**:
```json
[
  {
    "id": "video_001",
    "youtube_url": "https://youtube.com/watch?v=...",
    "title": "How to Path as a Jungler in Season 14",
    "coach": "JungleGapGG",
    "source": "youtube|patreon",
    "tags": ["pathing", "early_game", "fundamentals"],
    "champion_focus": ["general"],
    "concepts": ["3-camp clear", "full clear", "vertical jungling"],
    "difficulty": "beginner|intermediate|advanced",
    "patch": "14.5",
    "duration_minutes": 22,
    "summary": "Explains the 3 main jungle paths and when to use each...",
    "transcript_file": "transcripts/clean/video_001.txt"
  }
]
```

**Tools**:
- `youtube-transcript-api` for auto-generated transcripts
- `yt-dlp` + OpenAI Whisper for higher quality transcription
- Python script to batch-process a list of video URLs

### Step 2: Transcript Processing Pipeline

```
Raw transcript
    -> Clean (remove filler words, fix timestamps)
    -> Segment by topic (use chapter markers or LLM-based splitting)
    -> Tag each segment with concepts/champions
    -> Store as structured chunks
```

### Step 3: Generate "The Jungle Bible" (Distilled Coaching Guide)

**This is the key insight.** Don't just store raw transcripts - use an LLM to synthesize ALL transcripts into a single, comprehensive, structured coaching guide.

**Process**:
1. Feed transcripts (in batches by topic) to Claude/GPT-4o
2. Prompt: "You are creating a comprehensive jungle coaching guide. Synthesize these coaching transcripts into structured knowledge, organized by topic. Preserve specific tips, timings, and decision frameworks. Remove filler and repetition. Cite which coach said what."
3. Output: A 20-50 page structured document covering:
   - Jungle fundamentals (clearing, pathing, tempo)
   - Early game (levels 1-6): paths, gank timing, when to invade
   - Mid game (6-14): objective control, counter-jungling, vision
   - Late game (14+): teamfighting as jungler, baron/elder setup
   - Champion-specific advice
   - Matchup principles
   - Mental framework & decision-making
   - Common mistakes by rank

**Why this is powerful**:
- Deduplicates knowledge across 4 coaches
- Creates structured, searchable content
- Fits more knowledge into fewer tokens
- The guide itself is a valuable standalone artifact
- Can be used as direct context (no RAG needed for MVP)
- Can be the RAG corpus later (already well-chunked by topic)

### Step 4: Concept Taxonomy

Build a tagging system for coaching concepts:

```
jungle_concepts:
  clearing:
    - full_clear
    - 3_camp_clear
    - leashless_start
    - kite_optimization
  pathing:
    - mirror_pathing
    - vertical_jungling
    - path_toward_winning_lane
    - gank_timing
  objectives:
    - dragon_priority
    - herald_timing
    - baron_setup
    - objective_trading
  macro:
    - tempo
    - lane_priority
    - wave_state_awareness
    - map_pressure
  ganking:
    - gank_angles
    - dive_setup
    - lane_state_for_ganks
    - counter_ganking
  vision:
    - jungle_tracking
    - deep_wards
    - objective_vision
  teamfighting:
    - engage_timing
    - peel_vs_dive
    - target_selection
```

---

## Phase 1: MVP - Screenshot Coach (Week 2-3)

### What it does
- User sends a LoL screenshot + question
- AI analyzes the screenshot using vision model
- AI responds with coaching advice, grounded in "The Jungle Bible"
- Delivered via Discord bot or simple web app

### Architecture
```
User (Discord/Web)
    |
    [Screenshot + Question]
    |
    v
Python Backend (FastAPI)
    |
    [Build prompt: system prompt + Jungle Bible excerpt + screenshot + question]
    |
    v
Vision LLM API (Gemini Flash / GPT-4o-mini)
    |
    [Coaching response]
    |
    v
User
```

### System Prompt Design

The system prompt is the most important piece. It includes:
1. **Role**: "You are a Diamond+ jungle coach..."
2. **Coaching style**: Based on how JungleGapGG/KireiLoL/PerryJG teach
3. **Jungle Bible excerpt**: Relevant section(s) based on detected game state
4. **Few-shot examples**: 3-5 examples of screenshot -> good coaching advice
5. **Output format**: Structured advice (what to do, why, what to avoid)

### Key Files
```
lol_coaching/
  app/
    main.py              # FastAPI server or Discord bot
    prompts/
      system_prompt.txt  # Base coaching persona
      few_shot.json      # Example interactions
    llm_client.py        # API calls to Gemini/OpenAI
  knowledge/
    jungle_bible.md      # The distilled coaching guide
    champion_data/       # From DataDragon/CommunityDragon
  config.py              # API keys, model selection
  requirements.txt
```

### Cost: $0-5/month (personal use, ~20-50 queries/day)

---

## Phase 2: RAG + Deeper Knowledge (Week 4-8)

### Why RAG now (not in MVP)

MVP works by stuffing the most relevant Jungle Bible section into context. This works for general questions but fails when:
- User asks about a specific champion matchup
- User asks about a niche scenario the guide section doesn't cover
- Context window gets too large with full guide + screenshot

RAG solves this by retrieving only the most relevant chunks.

### What changes
- Chunk the Jungle Bible + raw transcripts into embeddings
- Store in Chroma (dev) or Qdrant (prod)
- On each query: embed the question -> retrieve top-k relevant chunks -> include in prompt
- Add patch notes and champion data to the knowledge base

### Additional data sources
- **Riot DataDragon**: Champion stats, abilities, item data (JSON, free)
- **Patch notes**: Scrape and ingest every 2 weeks
- **Lolalytics/U.GG**: Win rates, matchup data (for grounding advice in stats)

---

## Phase 3: Post-Game Analyst (Week 6-10)

### What it does
- User provides summoner name + recent match
- System pulls full match timeline from Riot API
- Converts timeline to a narrative ("At 3:00 you started red buff. At 5:15 you ganked mid...")
- LLM analyzes the narrative against coaching knowledge
- Outputs: what you did well, mistakes, missed opportunities, specific timestamps

### Riot API Integration
- **Library**: Cassiopeia or RiotWatcher (Python)
- **Key endpoints**:
  - Match-V5 timeline: positions, gold, events every 60s
  - Match-V5 details: final stats, items, runes
  - League: player rank for context
- **Rate limits**: Dev key = 100 req/2min. Production key = higher (need approval)

### Narrative Generation
Convert raw API data to human-readable game story:
```python
# Example output:
"0:00-3:00: You started Blue side (Blue->Gromp->Red). 
Enemy jungler (Lee Sin) started Red side.
3:15: You ganked top lane. Enemy top (Darius) was pushed to your tower. 
Kill secured (+300g). Good gank timing - lane state was correct.
5:00: Dragon spawned. You were topside. Enemy jungler took dragon uncontested.
MISSED OPPORTUNITY: After the top gank, you should have pathed bot-side 
to contest dragon. Your bot lane had priority (wave was pushing in)."
```

---

## Phase 4: Live Companion (Month 3-4)

### Approach A: Screenshot-based (safe)
- User Alt-Tabs, pastes screenshot into Discord/web
- Gets advice in 3-8 seconds
- Zero Riot policy risk

### Approach B: Live Client Data API (powerful)
- Desktop app (Tauri) polls localhost:2999 every 30-60s
- Gets: your items, gold, level, abilities, game events, team comps
- Generates periodic macro advice
- Gray area for Riot policy but currently tolerated

### Delivery options
- Discord bot (simplest)
- Web app with chat interface
- Desktop overlay (Tauri - lightweight)
- TTS voice coaching (later)

---

## Phase 5: Personalization & Fine-tuning (Month 5-7)

### What it does
- Tracks user's games over time (Riot API)
- Identifies recurring patterns (always dies to ganks at 5min, poor dragon control, etc.)
- Generates personalized improvement plan
- Adapts coaching to user's rank and weaknesses

### Fine-tuning
- **When**: After accumulating 1,000+ real coaching interactions
- **What**: Fine-tune Llama 3.1 8B or Gemma 4 E4B on coaching Q&A pairs
- **Cost**: $50-200 including data prep and experimentation
- **Platform**: Together AI ($3-15) or RunPod A100 rental ($1-3/hr)

---

## Phase 6: Production & Monetization (Month 7+)

### Self-hosted option
- Package with Gemma 4 26B A4B (MoE) via Ollama
- User needs RTX 4090 or Mac 48GB+
- Sell as one-time download ($50-80)

### SaaS option
- Freemium: 3-5 free analyses/day
- Premium: $7-10/month unlimited
- Distribution: web app + Discord bot

### Expansion
- All 5 roles (not just jungle)
- Voice coaching (TTS during games)
- Replay video analysis (frame-by-frame teamfight breakdown)
- Team coaching (analyze full team coordination)

---

## Tech Stack Summary

| Component | Tool | Why |
|---|---|---|
| Language | Python | Best ML/AI ecosystem |
| Web framework | FastAPI | Fast, async, easy |
| LLM (MVP) | Gemini 2.5 Flash or GPT-4o-mini | Cheapest vision-capable models |
| LLM (production) | GPT-4o / Claude Sonnet | Better reasoning |
| LLM (self-hosted) | Gemma 4 26B A4B | Apache 2.0, multimodal, efficient MoE |
| Embeddings | text-embedding-3-small (OpenAI) or Gemini Embedding | Good quality, cheap |
| Vector DB (dev) | Chroma | Zero config, Python-native |
| Vector DB (prod) | Qdrant | Best self-hosted performance |
| Structured DB | SQLite (dev) -> PostgreSQL (prod) | Match data, user data |
| Transcript extraction | youtube-transcript-api + Whisper | Free, high quality |
| Riot API | Cassiopeia or RiotWatcher | Typed Python wrappers |
| Frontend (MVP) | Discord bot or Streamlit | Fastest to ship |
| Frontend (prod) | React or SvelteKit | Better UX |
| Desktop app | Tauri | Lightweight, Rust + WebView |
