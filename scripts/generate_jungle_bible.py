"""
Generate "The Jungle Bible" - a comprehensive coaching guide synthesized
from all extracted transcripts.

This script reads all clean transcripts, groups them by topic, and uses
an LLM to synthesize them into a structured coaching document.

Usage:
    python scripts/generate_jungle_bible.py                  # Full generation
    python scripts/generate_jungle_bible.py --topic pathing  # Single topic
    python scripts/generate_jungle_bible.py --list-topics    # Show available topics
    python scripts/generate_jungle_bible.py --combine-only   # Just combine existing sections
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import openai
except ImportError:
    openai = None


# Topic definitions: each topic maps to tags that match it
TOPICS = {
    "jungle_fundamentals": {
        "title": "Jungle Fundamentals",
        "description": "Core concepts every jungler must understand: role identity, tempo, XP/gold sources, jungle economy",
        "match_tags": ["fundamentals", "basics", "beginner", "jungle_role", "economy"],
    },
    "clearing": {
        "title": "Clearing & Camp Mechanics",
        "description": "Efficient clearing, kiting camps, ability usage, clear speed optimization",
        "match_tags": ["clearing", "camps", "kiting", "clear_speed", "farming"],
    },
    "pathing": {
        "title": "Pathing & Routing",
        "description": "Jungle paths, route planning, 3-camp vs full clear, adaptive pathing",
        "match_tags": ["pathing", "routing", "path", "route", "full_clear", "3_camp"],
    },
    "early_game": {
        "title": "Early Game (Levels 1-6)",
        "description": "First clear decisions, early gank windows, scuttle crab, level 3/4 power spikes",
        "match_tags": ["early_game", "early", "first_clear", "level_3", "scuttle"],
    },
    "ganking": {
        "title": "Ganking - When, Where, How",
        "description": "Gank timing, lane state for ganks, angles, dive setups, counter-ganking",
        "match_tags": ["ganking", "gank", "ganks", "dive", "counter_gank", "counter_ganking"],
    },
    "objectives": {
        "title": "Objective Control",
        "description": "Dragon, Baron, Rift Herald, objective priority, setup, trading",
        "match_tags": ["objectives", "dragon", "baron", "herald", "rift_herald", "objective"],
    },
    "mid_game": {
        "title": "Mid Game Macro (Levels 6-14)",
        "description": "Transition from early to mid, power spikes, grouping, split decisions",
        "match_tags": ["mid_game", "macro", "mid", "transition", "grouping"],
    },
    "late_game": {
        "title": "Late Game & Teamfighting",
        "description": "Late game jungle role, teamfight positioning, engage/peel, Baron/Elder dances",
        "match_tags": ["late_game", "teamfight", "teamfighting", "late", "elder"],
    },
    "vision": {
        "title": "Vision & Enemy Tracking",
        "description": "Ward placement, jungle tracking, predicting enemy jungler, deep vision",
        "match_tags": ["vision", "wards", "tracking", "ward", "jungle_tracking"],
    },
    "mental": {
        "title": "Mental Framework & Decision-Making",
        "description": "Decision trees, win conditions, adapting to game state, tilt management",
        "match_tags": ["mental", "decision", "win_condition", "mindset", "tilt", "adapting"],
    },
    "matchups": {
        "title": "Champion Matchups & Picks",
        "description": "Jungle champion pool, matchup knowledge, counter-picking, team comp awareness",
        "match_tags": ["matchup", "matchups", "champion", "picks", "counter", "team_comp"],
    },
}


def load_videos_metadata() -> list[dict]:
    """Load video metadata from videos.json."""
    with open(config.VIDEOS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_transcript(video_id: str) -> str | None:
    """Load a clean transcript by video ID."""
    path = os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{video_id}.txt")
    if os.path.exists(path):
        return Path(path).read_text(encoding="utf-8")
    return None


def match_videos_to_topic(videos: list[dict], topic_key: str) -> list[dict]:
    """Find videos whose tags overlap with the topic's match_tags."""
    topic = TOPICS[topic_key]
    matched = []
    for video in videos:
        video_tags = set(t.lower() for t in video.get("tags", []))
        video_concepts = set(c.lower() for c in video.get("concepts", []))
        all_video_tags = video_tags | video_concepts

        topic_tags = set(t.lower() for t in topic["match_tags"])

        if all_video_tags & topic_tags:
            matched.append(video)

    return matched


def build_synthesis_prompt(topic_key: str, transcripts: list[tuple[str, str]]) -> str:
    """
    Build the prompt for synthesizing transcripts into a guide section.
    transcripts: list of (coach_name, transcript_text)
    """
    topic = TOPICS[topic_key]

    transcript_block = ""
    for coach, text in transcripts:
        # Truncate very long transcripts to avoid token limits
        if len(text) > 15000:
            text = text[:15000] + "\n\n[... transcript truncated for length ...]"
        transcript_block += f"\n--- Coach: {coach} ---\n{text}\n"

    return f"""You are creating a section of "The Jungle Bible" - a comprehensive
League of Legends jungle coaching guide. This section covers: {topic['title']}.

Topic description: {topic['description']}

Below are transcripts from trusted jungle coaches discussing this topic.
Synthesize ALL of their knowledge into a single, well-organized guide section.

TRANSCRIPTS:
{transcript_block}

INSTRUCTIONS:
1. Extract ALL actionable coaching advice from these transcripts.
2. Organize into clear subsections with markdown headers (## and ###).
3. Preserve specific tips, timings, numbers, and decision frameworks.
   Example: "At level 3 with double buffs, you have a 15-second window to gank
   before the enemy jungler reaches the same side" - keep specifics like this.
4. Remove filler, repetition, and off-topic tangents.
5. When coaches agree, state the consensus. When they disagree, note both views.
6. Use direct, actionable language a player can immediately apply.
7. Include a "Common Mistakes" subsection at the end.
8. Include a "Quick Reference" subsection with the 3-5 most important takeaways.
9. Do NOT add information the coaches didn't mention. Stay faithful to the source.
10. Use bullet points for lists, numbered lists for sequential steps.

OUTPUT FORMAT:
## {topic['title']}

[Your synthesized guide section in clean markdown]

### Common Mistakes
[List of mistakes coaches warn about]

### Quick Reference
[3-5 key takeaways]
"""


def synthesize_with_gemini(prompt: str) -> str:
    """Use Gemini to synthesize transcripts."""
    if genai is None:
        raise ImportError("google-generativeai not installed. Run: pip install google-generativeai")

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.TEXT_MODEL)

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.3,  # Lower temp for factual synthesis
            max_output_tokens=8000,
        ),
    )
    return response.text


def synthesize_with_openai(prompt: str) -> str:
    """Use OpenAI to synthesize transcripts."""
    if openai is None:
        raise ImportError("openai not installed. Run: pip install openai")

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert League of Legends coach and technical writer."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=8000,
    )
    return response.choices[0].message.content


def synthesize(prompt: str) -> str:
    """Synthesize using configured provider."""
    if config.LLM_PROVIDER == "gemini":
        return synthesize_with_gemini(prompt)
    elif config.LLM_PROVIDER == "openai":
        return synthesize_with_openai(prompt)
    else:
        raise ValueError(f"Unknown LLM provider: {config.LLM_PROVIDER}")


def generate_topic_section(topic_key: str, videos: list[dict]) -> str | None:
    """Generate a single topic section of the Jungle Bible."""
    matched = match_videos_to_topic(videos, topic_key)
    topic = TOPICS[topic_key]

    if not matched:
        print(f"  No videos matched for topic: {topic['title']}")
        print(f"  Expected tags: {topic['match_tags']}")
        return None

    # Load transcripts for matched videos
    transcripts = []
    for video in matched:
        text = load_transcript(video["id"])
        if text:
            transcripts.append((video.get("coach", "unknown"), text))

    if not transcripts:
        print(f"  Videos matched but no transcripts found for: {topic['title']}")
        return None

    print(f"  Synthesizing {len(transcripts)} transcripts for: {topic['title']}")

    prompt = build_synthesis_prompt(topic_key, transcripts)
    section = synthesize(prompt)

    # Save individual section
    section_path = os.path.join(config.KNOWLEDGE_DIR, f"section_{topic_key}.md")
    Path(section_path).write_text(section, encoding="utf-8")
    print(f"  Saved section: {section_path}")

    return section


def combine_sections() -> str:
    """Combine all generated sections into the full Jungle Bible."""
    bible = "# The Jungle Bible\n"
    bible += "### A Comprehensive League of Legends Jungle Coaching Guide\n"
    bible += "*Synthesized from coaching content by JungleGapGG, KireiLoL, PerryJG, and Agurin*\n\n"
    bible += "---\n\n"

    # Table of contents
    bible += "## Table of Contents\n\n"
    for i, (key, topic) in enumerate(TOPICS.items(), 1):
        bible += f"{i}. [{topic['title']}](#{key})\n"
    bible += "\n---\n\n"

    # Add each section
    for key, topic in TOPICS.items():
        section_path = os.path.join(config.KNOWLEDGE_DIR, f"section_{key}.md")
        if os.path.exists(section_path):
            section_text = Path(section_path).read_text(encoding="utf-8")
            bible += section_text + "\n\n---\n\n"
        else:
            bible += f"## {topic['title']}\n\n*Section not yet generated. "
            bible += f"Add videos with tags: {', '.join(topic['match_tags'])}*\n\n---\n\n"

    return bible


def generate_for_unmatched_transcripts(videos: list[dict]) -> str | None:
    """
    For any transcripts that didn't match a specific topic,
    generate a general section.
    """
    all_matched_ids = set()
    for topic_key in TOPICS:
        matched = match_videos_to_topic(videos, topic_key)
        for v in matched:
            all_matched_ids.add(v["id"])

    unmatched = [v for v in videos if v["id"] not in all_matched_ids]

    if not unmatched:
        return None

    print(f"\n  {len(unmatched)} videos didn't match any topic:")
    for v in unmatched:
        print(f"    - {v['id']}: tags={v.get('tags', [])}")
    print("  Consider adding matching tags to videos.json or adding new topics.")

    # Still process them as "general" knowledge
    transcripts = []
    for video in unmatched:
        text = load_transcript(video["id"])
        if text:
            transcripts.append((video.get("coach", "unknown"), text))

    if not transcripts:
        return None

    prompt = f"""You are creating a supplementary section for "The Jungle Bible" -
a comprehensive League of Legends jungle coaching guide.

These transcripts cover various jungle topics that don't fit neatly into
a single category. Extract and organize all useful coaching advice.

TRANSCRIPTS:
"""
    for coach, text in transcripts:
        if len(text) > 15000:
            text = text[:15000] + "\n[truncated]"
        prompt += f"\n--- Coach: {coach} ---\n{text}\n"

    prompt += """
INSTRUCTIONS:
1. Extract all actionable advice.
2. Group by whatever themes emerge naturally.
3. Use clear markdown formatting with headers.
4. Keep specific tips, timings, and frameworks.

OUTPUT: A well-organized supplementary guide section.
"""

    section = synthesize(prompt)
    section_path = os.path.join(config.KNOWLEDGE_DIR, "section_supplementary.md")
    Path(section_path).write_text(section, encoding="utf-8")
    return section


def main():
    parser = argparse.ArgumentParser(description="Generate The Jungle Bible from coaching transcripts")
    parser.add_argument("--topic", help="Generate a single topic section")
    parser.add_argument("--list-topics", action="store_true", help="List available topics and exit")
    parser.add_argument("--combine-only", action="store_true", help="Just combine existing sections into final document")
    parser.add_argument("--show-matching", action="store_true", help="Show which videos match which topics (dry run)")

    args = parser.parse_args()

    if args.list_topics:
        print("Available topics:\n")
        for key, topic in TOPICS.items():
            print(f"  {key:25s} {topic['title']}")
            print(f"  {'':25s} Tags: {', '.join(topic['match_tags'])}")
            print()
        return

    if args.combine_only:
        bible = combine_sections()
        Path(config.JUNGLE_BIBLE_FILE).write_text(bible, encoding="utf-8")
        print(f"Jungle Bible assembled: {config.JUNGLE_BIBLE_FILE}")
        word_count = len(bible.split())
        print(f"Total words: {word_count}")
        return

    # Check for transcripts
    videos = load_videos_metadata()
    transcripts_exist = any(
        os.path.exists(os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{v['id']}.txt"))
        for v in videos
    )

    if not transcripts_exist:
        print("No transcripts found. Run extract_transcripts.py first.")
        sys.exit(1)

    if args.show_matching:
        print("Video -> Topic matching:\n")
        for key, topic in TOPICS.items():
            matched = match_videos_to_topic(videos, key)
            print(f"  {topic['title']} ({len(matched)} videos)")
            for v in matched:
                print(f"    - [{v['coach']}] {v['title']}")
        return

    os.makedirs(config.KNOWLEDGE_DIR, exist_ok=True)

    if args.topic:
        if args.topic not in TOPICS:
            print(f"Unknown topic: {args.topic}")
            print(f"Available: {', '.join(TOPICS.keys())}")
            sys.exit(1)
        generate_topic_section(args.topic, videos)
    else:
        # Generate all topics
        print("Generating The Jungle Bible\n")
        for topic_key in TOPICS:
            print(f"\n[{topic_key}]")
            generate_topic_section(topic_key, videos)

        # Handle unmatched transcripts
        generate_for_unmatched_transcripts(videos)

    # Combine into final document
    print("\nAssembling final document...")
    bible = combine_sections()
    Path(config.JUNGLE_BIBLE_FILE).write_text(bible, encoding="utf-8")
    word_count = len(bible.split())
    print(f"\nJungle Bible saved: {config.JUNGLE_BIBLE_FILE}")
    print(f"Total words: {word_count} (~{word_count * 4 // 3} tokens)")


if __name__ == "__main__":
    main()
