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

# Model selection - change this to switch providers
LLM_PROVIDER = "gemini"  # "gemini" or "openai"
VISION_MODEL = "gemini-2.5-flash"  # for screenshot analysis (better quality)
TEXT_MODEL = "gemini-2.5-flash"  # best quality for tagging/synthesis

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
