"""
Auto-tag and summarize transcripts using an LLM (Gemini Flash by default).

Reads each clean transcript, sends it to the LLM for:
  - Title extraction (from content if not already set)
  - Tags (from our predefined taxonomy)
  - Concepts covered
  - Champion focus
  - Difficulty level
  - One-paragraph summary

Updates videos.json with the generated metadata.

Usage:
    python scripts/auto_tag_transcripts.py                # Tag all untagged videos
    python scripts/auto_tag_transcripts.py --id VIDEO_ID  # Tag a specific video
    python scripts/auto_tag_transcripts.py --all          # Re-tag everything (overwrites)
    python scripts/auto_tag_transcripts.py --dry-run      # Show what would be tagged without saving
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

VALID_TAGS = [
    "fundamentals", "basics", "beginner", "intermediate", "advanced",
    "clearing", "camps", "kiting", "clear_speed", "farming",
    "pathing", "routing", "full_clear", "3_camp",
    "early_game", "early", "first_clear", "level_3", "scuttle",
    "ganking", "gank", "dive", "counter_gank", "counter_ganking",
    "objectives", "dragon", "baron", "herald", "rift_herald",
    "mid_game", "macro", "transition", "grouping",
    "late_game", "teamfight", "teamfighting", "elder",
    "vision", "wards", "tracking", "jungle_tracking",
    "mental", "decision", "win_condition", "mindset", "adapting",
    "matchup", "matchups", "champion", "picks", "counter", "team_comp",
]

TAGGING_PROMPT = """Analyze this League of Legends jungle coaching video transcript and extract metadata.

TRANSCRIPT:
{transcript}

TASK: Return a JSON object with these fields:

{{
  "title": "A clear, descriptive title for this video based on its content",
  "tags": ["tag1", "tag2", ...],
  "concepts": ["specific concepts taught, e.g., 'full_clear', 'vertical_jungling', 'gank_timing'"],
  "champion_focus": ["champion names mentioned/focused on, or 'general' if no specific champion"],
  "difficulty": "beginner|intermediate|advanced",
  "summary": "2-3 sentence summary of what this video teaches and the key takeaways",
  "key_timestamps": ["brief descriptions of important moments, e.g., '5:30 - explains when to invade'"]
}}

RULES FOR TAGS - only use tags from this list:
{valid_tags}

Pick ALL tags that apply (usually 3-6 per video). Choose based on what the coach
actually discusses, not just mentions in passing.

RULES FOR DIFFICULTY:
- beginner: basic concepts, aimed at new/low-elo players
- intermediate: assumes basic knowledge, teaches nuanced decision-making
- advanced: high-elo concepts, complex situations, assumes strong fundamentals

Return ONLY the JSON object, no other text.
"""


def load_videos() -> list[dict]:
    with open(config.VIDEOS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_videos(videos: list[dict]):
    with open(config.VIDEOS_FILE, "w", encoding="utf-8") as f:
        json.dump(videos, f, indent=2, ensure_ascii=False)


def load_transcript(video_id: str) -> str | None:
    path = os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{video_id}.txt")
    if os.path.exists(path):
        return Path(path).read_text(encoding="utf-8")
    return None


def tag_with_gemini(transcript: str) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.TEXT_MODEL)

    # Truncate very long transcripts to save tokens
    if len(transcript) > 30000:
        # Keep first and last parts for context
        transcript = transcript[:20000] + "\n\n[...middle truncated...]\n\n" + transcript[-10000:]

    prompt = TAGGING_PROMPT.format(
        transcript=transcript,
        valid_tags=", ".join(VALID_TAGS),
    )

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=4000,
            response_mime_type="application/json",
        ),
    )

    text = response.text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from response if it has extra text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError(f"Could not parse LLM response as JSON: {text[:500]}")


def tag_with_openai(transcript: str) -> dict:
    import openai

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

    if len(transcript) > 30000:
        transcript = transcript[:20000] + "\n\n[...middle truncated...]\n\n" + transcript[-10000:]

    prompt = TAGGING_PROMPT.format(
        transcript=transcript,
        valid_tags=", ".join(VALID_TAGS),
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a League of Legends expert. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


def tag_transcript(transcript: str) -> dict:
    if config.LLM_PROVIDER == "gemini":
        return tag_with_gemini(transcript)
    elif config.LLM_PROVIDER == "openai":
        return tag_with_openai(transcript)
    else:
        raise ValueError(f"Unknown provider: {config.LLM_PROVIDER}")


def needs_tagging(video: dict) -> bool:
    """Check if a video needs tagging (no tags or empty tags)."""
    return not video.get("tags") or video.get("title", "").startswith("Video ")


def main():
    parser = argparse.ArgumentParser(description="Auto-tag transcripts using LLM")
    parser.add_argument("--id", help="Tag a specific video by ID")
    parser.add_argument("--all", action="store_true", help="Re-tag all videos (overwrites existing tags)")
    parser.add_argument("--dry-run", action="store_true", help="Show results without saving")

    args = parser.parse_args()

    videos = load_videos()
    updated = 0

    for video in videos:
        vid = video["id"]

        # Skip if not targeted
        if args.id and vid != args.id:
            continue

        # Skip if already tagged (unless --all)
        if not args.all and not needs_tagging(video):
            print(f"Skipping (already tagged): {vid}")
            continue

        # Load transcript
        transcript = load_transcript(vid)
        if not transcript:
            print(f"Skipping (no transcript): {vid}")
            continue

        print(f"Tagging: {vid}...")

        # Rate limit: free tier = 5 req/min for Gemini 2.5 Flash
        # Wait 15s between requests to stay safe
        if updated > 0:
            print("  (waiting 15s for rate limit...)")
            time.sleep(15)

        try:
            result = tag_transcript(transcript)
        except Exception as e:
            print(f"  FAILED: {e}")
            continue

        # Show results
        print(f"  Title:      {result.get('title', '?')}")
        print(f"  Tags:       {result.get('tags', [])}")
        print(f"  Concepts:   {result.get('concepts', [])}")
        print(f"  Champions:  {result.get('champion_focus', [])}")
        print(f"  Difficulty:  {result.get('difficulty', '?')}")
        print(f"  Summary:    {result.get('summary', '?')[:100]}...")

        if not args.dry_run:
            # Update video entry (preserve coach and url, update everything else)
            video["title"] = result.get("title", video.get("title", ""))
            video["tags"] = result.get("tags", [])
            video["concepts"] = result.get("concepts", [])
            video["champion_focus"] = result.get("champion_focus", ["general"])
            video["difficulty"] = result.get("difficulty", "intermediate")
            video["summary"] = result.get("summary", "")
            if result.get("key_timestamps"):
                video["key_timestamps"] = result["key_timestamps"]
            updated += 1

    if not args.dry_run and updated > 0:
        save_videos(videos)
        print(f"\nUpdated {updated} videos in videos.json")
    elif args.dry_run:
        print(f"\n(Dry run - nothing saved. Would have updated {updated} videos)")


if __name__ == "__main__":
    main()
