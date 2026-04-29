# MVP Plan: LoL Jungle Screenshot Coach

## Goal
Send a LoL screenshot + question -> get coaching advice grounded in your trusted coaches' methodology.

**Realistic timeline**: 3-5 days (not 1-2 weeks)
- Day 1: Transcript collection pipeline
- Day 2: Generate "The Jungle Bible" from transcripts
- Day 3: Build the bot/app + craft system prompt
- Day 4-5: Test, iterate on prompts, add few-shot examples

---

## Day 1: Transcript Collection Pipeline

### Step 1: Gather Video URLs

Create a master list of videos to process. Sources:
- YouTube channels: @JungleGapGG, @KireiLoL, @PerryJG, Agurin
- Patreon pages (if you have access to exclusive content)
- Any saved playlists

Start with **20-30 of the best/most fundamental videos**. You can always add more later.

### Step 2: Build the Transcript Extractor

```python
# scripts/extract_transcripts.py
from youtube_transcript_api import YouTubeTranscriptApi
import json, os

def extract_transcript(video_url):
    """Extract transcript from a YouTube video URL."""
    video_id = video_url.split("v=")[-1].split("&")[0]
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    # Returns: [{"text": "...", "start": 0.0, "duration": 4.5}, ...]
    
    # Join into readable text with timestamps
    full_text = ""
    for segment in transcript:
        minutes = int(segment["start"] // 60)
        seconds = int(segment["start"] % 60)
        full_text += f"[{minutes:02d}:{seconds:02d}] {segment['text']}\n"
    
    return full_text, transcript

def process_video_list(video_list_file, output_dir):
    """Process all videos from a JSON list."""
    with open(video_list_file) as f:
        videos = json.load(f)
    
    os.makedirs(output_dir, exist_ok=True)
    
    for video in videos:
        print(f"Processing: {video['title']}")
        try:
            full_text, raw = extract_transcript(video["url"])
            
            # Save clean transcript
            with open(f"{output_dir}/{video['id']}.txt", "w") as f:
                f.write(f"# {video['title']}\n")
                f.write(f"# Coach: {video['coach']}\n")
                f.write(f"# Tags: {', '.join(video['tags'])}\n\n")
                f.write(full_text)
            
            # Save raw JSON for later processing
            with open(f"{output_dir}/{video['id']}_raw.json", "w") as f:
                json.dump(raw, f)
                
            print(f"  OK - {len(full_text)} chars")
        except Exception as e:
            print(f"  FAILED: {e}")
```

### Step 3: Create Video Metadata File

```json
// data/videos.json
[
  {
    "id": "jgg_pathing_101",
    "url": "https://youtube.com/watch?v=XXXXX",
    "title": "Jungle Pathing Guide for Beginners",
    "coach": "JungleGapGG",
    "tags": ["pathing", "fundamentals", "beginner"],
    "concepts": ["full_clear", "3_camp", "gank_timing"],
    "champion_focus": ["general"]
  },
  {
    "id": "kirei_tempo",
    "url": "https://youtube.com/watch?v=YYYYY",
    "title": "Understanding Jungle Tempo",
    "coach": "KireiLoL",
    "tags": ["tempo", "macro", "intermediate"],
    "concepts": ["tempo", "reset_timing", "map_pressure"],
    "champion_focus": ["general"]
  }
]
```

**You fill this in manually** for your 20-30 selected videos. Takes ~30-60 min.

---

## Day 2: Generate "The Jungle Bible"

### The Idea

Instead of using raw transcripts (messy, repetitive, too many tokens), use an LLM to **distill** all transcripts into one comprehensive coaching guide. This is the core knowledge artifact.

### Process

```python
# scripts/generate_jungle_bible.py

import os
from pathlib import Path

def load_transcripts(transcript_dir):
    """Load all transcripts grouped by topic tag."""
    # Group transcripts by their primary concept
    transcripts = {}
    for f in Path(transcript_dir).glob("*.txt"):
        text = f.read_text()
        transcripts[f.stem] = text
    return transcripts

SYNTHESIS_PROMPT = """You are creating "The Jungle Bible" - a comprehensive 
League of Legends jungle coaching guide synthesized from transcripts of 
top coaching content.

TRANSCRIPTS ON THE TOPIC OF "{topic}":
{transcripts}

INSTRUCTIONS:
1. Extract all actionable coaching advice from these transcripts
2. Organize into clear sections with headers
3. Preserve specific tips, timings, numbers, and decision frameworks
4. Remove filler, repetition, and off-topic content  
5. When coaches disagree, note both perspectives
6. Use clear, direct language a player can act on
7. Include "Common Mistakes" for each section
8. Format as clean markdown

OUTPUT: A comprehensive guide section on "{topic}" for jungle players."""

# Process each topic group through Claude/GPT-4o
# Then assemble into one document with table of contents
```

### Target Structure for The Jungle Bible

```markdown
# The Jungle Bible - Comprehensive Coaching Guide

## Table of Contents
1. Jungle Fundamentals
2. Clearing & Camp Mechanics
3. Pathing Decision Framework
4. Early Game (Levels 1-6)
5. Ganking - When, Where, How
6. Objective Control
7. Mid Game Macro (Levels 6-14)
8. Late Game & Teamfighting
9. Vision & Tracking
10. Mental Framework & Decision-Making
11. Champion-Specific Notes
12. Common Mistakes by Rank

## 1. Jungle Fundamentals
### What is your job as a jungler?
[Synthesized from all coaches' intro content]

### Tempo explained
[KireiLoL's framework + JungleGapGG's examples]

...
```

### Why This Works Better Than RAG for MVP

- **Fits in context**: A well-written 15-30 page guide = ~10,000-20,000 tokens. Easily fits in the context window alongside a screenshot.
- **No infrastructure needed**: No vector DB, no embeddings, no retrieval logic.
- **Higher quality**: Pre-synthesized knowledge is more coherent than retrieved chunks.
- **You can review and edit it**: Since it's a readable document, you can fix mistakes or add your own insights.
- **It's a valuable artifact on its own**: Even without the AI, this guide would be useful.

### Approach for Context Stuffing (MVP)

For MVP, you don't need the FULL bible in every prompt. Smart selection:

```python
def select_bible_sections(screenshot_analysis, jungle_bible_sections):
    """Pick the most relevant 2-3 sections based on game state."""
    game_time = screenshot_analysis.get("game_time", "unknown")
    
    # Simple heuristic: pick sections by game phase
    if game_time < 6:
        return ["early_game", "pathing", "ganking"]
    elif game_time < 14:
        return ["mid_game", "objectives", "vision"]
    else:
        return ["late_game", "teamfighting", "objectives"]
```

Or even simpler for v0: just include the whole thing if it fits under ~20K tokens.

---

## Day 3: Build the App

### Option A: Discord Bot (Recommended for personal use)

```python
# app/bot.py
import discord
from discord import app_commands
import aiohttp
import base64
from llm_client import analyze_screenshot

bot = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(bot)

@tree.command(name="coach", description="Get jungle coaching from a screenshot")
async def coach(interaction: discord.Interaction, 
                screenshot: discord.Attachment,
                question: str = "What should I do here?"):
    await interaction.response.defer()  # Vision API takes a few seconds
    
    # Download the screenshot
    image_bytes = await screenshot.read()
    
    # Get coaching advice
    advice = await analyze_screenshot(image_bytes, question)
    
    await interaction.followup.send(advice)

@tree.command(name="ask", description="Ask a jungle coaching question (no screenshot)")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    advice = await ask_coaching_question(question)
    await interaction.followup.send(advice)
```

### Option B: Streamlit Web App (Even simpler)

```python
# app/streamlit_app.py
import streamlit as st
from llm_client import analyze_screenshot, ask_coaching_question

st.title("Jungle Coach AI")

tab1, tab2 = st.tabs(["Screenshot Analysis", "Ask a Question"])

with tab1:
    uploaded = st.file_uploader("Upload a game screenshot", type=["png", "jpg"])
    question = st.text_input("What do you want to know?", "What should I do here?")
    
    if uploaded and st.button("Get Coaching"):
        with st.spinner("Analyzing..."):
            advice = analyze_screenshot(uploaded.read(), question)
        st.markdown(advice)

with tab2:
    q = st.text_area("Ask any jungle question")
    if q and st.button("Ask Coach"):
        with st.spinner("Thinking..."):
            advice = ask_coaching_question(q)
        st.markdown(advice)
```

### The LLM Client (core logic)

```python
# app/llm_client.py
import google.generativeai as genai  # or openai
import base64
from pathlib import Path

# Load the Jungle Bible
JUNGLE_BIBLE = Path("knowledge/jungle_bible.md").read_text()

SYSTEM_PROMPT = """You are an expert League of Legends jungle coach. 
Your coaching style is direct, specific, and actionable - like a Diamond+ 
coach doing a live VOD review.

Your knowledge is grounded in coaching methodology from top jungle educators.

COACHING KNOWLEDGE:
{jungle_bible_section}

RULES:
1. Analyze the screenshot carefully: identify champions, items, game time, 
   minimap positions, health bars, gold, and objectives.
2. Give SPECIFIC advice for THIS exact game state, not generic tips.
3. Explain the WHY behind your advice (the reasoning).
4. If you can see the minimap, comment on map state and positioning.
5. Prioritize the most impactful action the player should take RIGHT NOW.
6. Mention what to watch for in the next 30-60 seconds.
7. Be concise but thorough. Think like a coach reviewing a VOD.
8. If you can't read something in the screenshot, say so - don't guess.

FORMAT:
**Situation**: [Brief description of what you see]
**Do This Now**: [Most important immediate action]
**Why**: [Reasoning based on game state]  
**Watch For**: [What to look for in next 30-60 seconds]
**Avoid**: [Common mistake in this situation]
"""

async def analyze_screenshot(image_bytes: bytes, question: str) -> str:
    """Send screenshot + question to vision LLM, get coaching advice."""
    
    # Option 1: Gemini (cheapest for vision)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    response = model.generate_content([
        SYSTEM_PROMPT.format(jungle_bible_section=JUNGLE_BIBLE),
        {"mime_type": "image/png", "data": image_bytes},
        f"Player's question: {question}"
    ])
    
    return response.text

async def ask_coaching_question(question: str) -> str:
    """Answer a coaching question using the Jungle Bible as context."""
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    response = model.generate_content([
        SYSTEM_PROMPT.format(jungle_bible_section=JUNGLE_BIBLE),
        f"Player's question: {question}"
    ])
    
    return response.text
```

---

## Day 4-5: Test & Iterate

### What to test
1. Take 10-15 screenshots from your own games at different game states
2. Ask varied questions:
   - "What should I do here?" (general)
   - "Should I gank top or take dragon?" (decision)
   - "Who wins this teamfight?" (analysis)
   - "Where should I path next?" (pathing)
   - "What's my win condition?" (macro)
3. Compare AI advice to what you think the right answer is
4. Compare to what your trusted coaches would say

### What to iterate on
- **System prompt**: This is 80% of the quality. Tweak heavily.
- **Jungle Bible content**: Add sections the AI seems weak on.
- **Few-shot examples**: Add 3-5 great example interactions to the prompt.
- **Model choice**: Try Gemini Flash vs GPT-4o-mini vs Claude Haiku. Compare quality/cost.

### Quality checklist
- [ ] Can it correctly identify champions from a screenshot?
- [ ] Can it read the game timer?
- [ ] Can it assess minimap state? (harder)
- [ ] Can it read item builds?
- [ ] Does the advice align with coaching methodology?
- [ ] Is it specific to the game state, not generic?
- [ ] Does it explain the WHY?

---

## Project Structure (MVP)

```
lol_coaching/
├── README.md
├── requirements.txt
├── config.py                    # API keys, model selection
├── scripts/
│   ├── extract_transcripts.py   # YouTube transcript extraction
│   ├── generate_jungle_bible.py # Synthesize transcripts into guide
│   └── fetch_champion_data.py   # Pull from DataDragon (optional)
├── data/
│   ├── videos.json              # Video metadata catalog
│   └── transcripts/
│       ├── raw/                 # Raw YouTube transcripts
│       └── clean/               # Cleaned transcripts
├── knowledge/
│   ├── jungle_bible.md          # THE distilled coaching guide
│   └── few_shot_examples.json   # Example coaching interactions
├── app/
│   ├── main.py                  # Entry point (Discord bot or Streamlit)
│   ├── llm_client.py            # LLM API wrapper
│   └── prompts/
│       └── system_prompt.txt    # Base coaching persona
└── tests/
    └── test_screenshots/        # Test screenshots for evaluation
```

---

## Requirements

```
# requirements.txt
youtube-transcript-api>=0.6.0
google-generativeai>=0.5.0      # For Gemini (cheapest vision)
# openai>=1.0.0                 # Alternative: GPT-4o-mini
discord.py>=2.3.0               # If using Discord bot
streamlit>=1.30.0               # If using web app
python-dotenv>=1.0.0
Pillow>=10.0.0
```

---

## Cost Estimate (Personal Use)

| What | Cost |
|---|---|
| YouTube transcript extraction | Free |
| Generating Jungle Bible (~100K tokens through LLM) | $0.10-0.50 |
| Daily use: ~20 screenshot analyses/day | $0.30-1.00/day |
| Monthly personal use | **$5-15/month** |
| Gemini Flash (cheapest vision model) | $0.075/1M input tokens |

**Gemini 2.5 Flash is the recommended model for MVP**: cheapest vision-capable model, good quality, fast.

---

## What Comes After MVP

Once the MVP works and you're getting useful advice:

1. **More transcripts** (50-100+ videos) -> richer Jungle Bible
2. **RAG** over raw transcripts for niche questions the Bible doesn't cover
3. **Riot API integration** for post-game analysis
4. **Prompt refinement** based on where the AI gets things wrong
5. **Champion-specific knowledge** (matchup guides, ability interactions)
