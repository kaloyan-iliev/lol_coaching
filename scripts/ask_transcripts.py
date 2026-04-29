"""
Ask questions about coaching content and get answers with timestamped video links.

Usage:
    python scripts/ask_transcripts.py "When should I invade the enemy jungle?"
    python scripts/ask_transcripts.py "How do I play around baron?" --topic objectives
    python scripts/ask_transcripts.py "What is the ping pong concept?" --all
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

VALID_TOPICS = [
    "jungle_fundamentals", "clearing", "pathing", "early_game",
    "ganking", "objectives", "mid_game", "late_game",
    "vision", "mental", "matchups",
]

QA_PROMPT = """You are an expert League of Legends jungle coach. Answer the player's question
thoroughly using your COACHING GUIDE as the primary source of knowledge, and cite specific
video moments from the TRANSCRIPTS below.

COACHING GUIDE (your core knowledge):
{jungle_bible}

RAW TRANSCRIPTS (for finding specific video moments to cite):
{transcripts}

IMPORTANT RULES FOR CITATIONS:
1. When you reference advice, cite the specific video moment using this exact format:
   [Coach - "Video Title" at MM:SS](YOUTUBE_LINK)
2. The YouTube link format is: https://www.youtube.com/watch?v=VIDEO_ID&t=SECONDS
   For example, if the timestamp is [05:42], the seconds are 342, so the link is:
   https://www.youtube.com/watch?v=VIDEO_ID&t=342
3. Include multiple citations - aim for 3-6 video references spread through your answer.
4. Put citations inline right after the relevant advice.
5. Match timestamps carefully - find the moment in the transcript where the coach
   actually discusses this specific point.

ANSWER FORMAT:
- Give a thorough, structured answer with headers if the topic is complex
- Be specific and actionable - include exact timings, numbers, and decision frameworks
- Cover the topic comprehensively - don't give a surface-level answer
- If coaches give different perspectives, present both with citations
- End with a "Watch These" section listing the 3-5 most relevant video moments with links

PLAYER'S QUESTION: {question}
"""


def load_videos() -> list[dict]:
    with open(config.VIDEOS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_transcript(video_id: str) -> str | None:
    path = os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{video_id}.txt")
    if os.path.exists(path):
        return Path(path).read_text(encoding="utf-8")
    return None


def find_relevant_videos(videos: list[dict], topic: str = None) -> list[dict]:
    """Find videos matching a topic, or return all tagged videos."""
    if topic:
        from generate_jungle_bible import TOPICS
        if topic in TOPICS:
            match_tags = set(t.lower() for t in TOPICS[topic]["match_tags"])
            matched = []
            for v in videos:
                video_tags = set(t.lower() for t in v.get("tags", []))
                video_concepts = set(c.lower() for c in v.get("concepts", []))
                if (video_tags | video_concepts) & match_tags:
                    matched.append(v)
            return matched
    # Return all videos that have transcripts
    return [v for v in videos if v.get("tags")]


def build_transcript_block(videos: list[dict], max_chars: int = 150000) -> str:
    """Build transcript block with video metadata for context."""
    block = ""
    total_chars = 0

    for video in videos:
        transcript = load_transcript(video["id"])
        if not transcript:
            continue

        video_url = video["url"]
        video_id = video["id"]
        title = video.get("title", video_id)
        coach = video.get("coach", "unknown")

        header = f"\n{'='*60}\nVIDEO: {title}\nCOACH: {coach}\nURL: {video_url}\nVIDEO_ID: {video_id}\n{'='*60}\n"

        # Truncate long transcripts
        if total_chars + len(transcript) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 2000:
                transcript = transcript[:remaining] + "\n[...truncated...]"
            else:
                break

        block += header + transcript + "\n"
        total_chars += len(header) + len(transcript)

    return block


def ask_gemini(prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.VISION_MODEL)

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.3,
            max_output_tokens=4000,
        ),
    )
    return response.text


def ask_openai(prompt: str) -> str:
    import openai

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert League of Legends jungle coach."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4000,
    )
    return response.choices[0].message.content


def ask(prompt: str) -> str:
    if config.LLM_PROVIDER == "gemini":
        return ask_gemini(prompt)
    elif config.LLM_PROVIDER == "openai":
        return ask_openai(prompt)
    else:
        raise ValueError(f"Unknown provider: {config.LLM_PROVIDER}")


def load_jungle_bible() -> str:
    """Load the Jungle Bible if it exists."""
    if os.path.exists(config.JUNGLE_BIBLE_FILE):
        return Path(config.JUNGLE_BIBLE_FILE).read_text(encoding="utf-8")
    return "(No coaching guide found. Run generate_jungle_bible.py first.)"


def main():
    parser = argparse.ArgumentParser(description="Ask questions about coaching transcripts")
    parser.add_argument("question", help="Your question")
    parser.add_argument("--topic", help=f"Filter to a topic: {', '.join(VALID_TOPICS)}")
    parser.add_argument("--all", action="store_true", help="Search all transcripts")
    parser.add_argument("--max-videos", type=int, default=15, help="Max videos for citations (default: 15)")
    parser.add_argument("--no-bible", action="store_true", help="Skip Jungle Bible, use only raw transcripts")
    parser.add_argument("--cheap", action="store_true", help="Use gemini-2.5-flash-lite (6x cheaper)")

    args = parser.parse_args()

    # Override model for cheap mode
    if args.cheap:
        config.VISION_MODEL = "gemini-2.5-flash-lite"

    videos = load_videos()

    if args.all:
        relevant = find_relevant_videos(videos)
    elif args.topic:
        relevant = find_relevant_videos(videos, args.topic)
    else:
        relevant = find_relevant_videos(videos)

    relevant = relevant[:args.max_videos]

    if not relevant:
        print("No matching videos found.")
        return

    # Load Jungle Bible
    jungle_bible = "" if args.no_bible else load_jungle_bible()

    print(f"Using Jungle Bible: {'yes' if jungle_bible else 'no'}")
    print(f"Searching {len(relevant)} video transcripts for citations...\n")

    transcript_block = build_transcript_block(relevant)
    prompt = QA_PROMPT.format(
        jungle_bible=jungle_bible,
        transcripts=transcript_block,
        question=args.question,
    )

    answer = ask(prompt)
    print(answer)


if __name__ == "__main__":
    main()
