import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

# Riot API routing (EUW)
RIOT_PLATFORM = "euw1"  # platform host: league-v4, champion-mastery-v4
RIOT_REGION = "europe"  # regional host: match-v5, account-v1

# Model selection - change this to switch providers. Env var wins so one-off
# runs can switch without editing this file:  $env:LLM_PROVIDER='openrouter'
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # "gemini", "openai" or "openrouter"
# gemini-3.5-flash: published free tier 1,500 req/day / 10 RPM / 250k TPM —
# but this project's LIVE caps have been lower than published before (3-flash:
# 20/day), so treat quotas as observed, not promised. Verified working 2026-07-05.
VISION_MODEL = "gemini-3.5-flash"
TEXT_MODEL = "gemini-3.5-flash"
# Tried in order when the primary model hits quota (429) or capacity (503).
# Free-tier daily quotas are per-model, so falling back = fresh quota pool.
LLM_FALLBACK_MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
# Backup provider: set LLM_PROVIDER = "openrouter" (needs OPENROUTER_API_KEY in
# .env; ":free" models = 50 req/day, or 1000/day after a one-time $10 top-up)
# Free model ids rotate - list current ones: GET https://openrouter.ai/api/v1/models
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")
# LLM-as-judge (scripts/judge_review.py): deliberately a DIFFERENT model than the
# generator (TEXT_MODEL) to reduce self-preference bias. gemini-3-pro-preview is a
# stronger judge if its free quota allows; 3-flash-preview is the safe free default.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3-flash-preview")

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")
TRANSCRIPTS_RAW_DIR = os.path.join(DATA_DIR, "transcripts", "raw")
TRANSCRIPTS_CLEAN_DIR = os.path.join(DATA_DIR, "transcripts", "clean")
VIDEOS_FILE = os.path.join(DATA_DIR, "videos.json")
JUNGLE_BIBLE_FILE = os.path.join(KNOWLEDGE_DIR, "jungle_bible.md")
HOUSE_RULES_FILE = os.path.join(KNOWLEDGE_DIR, "house_rules.md")

# Riot data paths
RIOT_DIR = os.path.join(DATA_DIR, "riot")
MATCHES_DIR = os.path.join(RIOT_DIR, "matches")
TIMELINES_DIR = os.path.join(RIOT_DIR, "timelines")
FACTS_DIR = os.path.join(RIOT_DIR, "facts")
MATCH_INDEX_FILE = os.path.join(RIOT_DIR, "match_index.json")
DISCOVERY_STATE_FILE = os.path.join(RIOT_DIR, "discovery_state.json")
BASELINE_FILE = os.path.join(RIOT_DIR, "baseline_ekko.json")  # legacy single-champion file
BASELINES_DIR = os.path.join(RIOT_DIR, "baselines")  # per-champion + _generic.json
REVIEWS_DIR = os.path.join(DATA_DIR, "reviews")
PREGAME_DIR = os.path.join(DATA_DIR, "pregame")
