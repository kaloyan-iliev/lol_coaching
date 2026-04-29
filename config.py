import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
