"""
Generate "The Jungle Bible" - a comprehensive coaching guide synthesized
from all extracted transcripts.

This script reads all clean transcripts, groups them by topic, and uses
an LLM to synthesize them into a structured coaching document.

Usage:
    python scripts/generate_jungle_bible.py                  # Full generation (all coaches)
    python scripts/generate_jungle_bible.py --topic pathing  # Single topic
    python scripts/generate_jungle_bible.py --list-topics    # Show available topics
    python scripts/generate_jungle_bible.py --combine-only   # Just combine existing sections

Source filtering (per-coach / per-channel docs, kept separate from the main bible):
    python scripts/generate_jungle_bible.py --coaches KireiLoL            # one coach
    python scripts/generate_jungle_bible.py --channels KireiVODs          # one channel
    python scripts/generate_jungle_bible.py --coaches KireiLoL,JungleGapGG --name duo
Filtered outputs go to knowledge/subsets/<slug>/section_*.md and
knowledge/jungle_bible_<slug>.md; the unfiltered run keeps the legacy paths.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

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


SECTIONS_META_FILE = os.path.join(config.KNOWLEDGE_DIR, "sections_meta.json")


class OutputPaths:
    """Where sections/meta/bible go. Unfiltered runs keep the legacy layout;
    coach/channel-filtered runs get an isolated subset directory + suffixed bible."""

    def __init__(self, slug: str | None):
        self.slug = slug
        if slug:
            self.sections_dir = os.path.join(config.KNOWLEDGE_DIR, "subsets", slug)
            self.meta_file = os.path.join(self.sections_dir, "sections_meta.json")
            self.bible_file = os.path.join(config.KNOWLEDGE_DIR, f"jungle_bible_{slug}.md")
        else:
            self.sections_dir = config.KNOWLEDGE_DIR
            self.meta_file = SECTIONS_META_FILE
            self.bible_file = config.JUNGLE_BIBLE_FILE

    def section_path(self, key: str) -> str:
        return os.path.join(self.sections_dir, f"section_{key}.md")


def load_sections_meta(paths: OutputPaths) -> dict:
    """Which transcript IDs fed each section at last generation."""
    if os.path.exists(paths.meta_file):
        with open(paths.meta_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_sections_meta(meta: dict, paths: OutputPaths):
    os.makedirs(os.path.dirname(paths.meta_file), exist_ok=True)
    with open(paths.meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def load_videos_metadata(coaches: list[str] | None = None,
                         channels: list[str] | None = None) -> list[dict]:
    """Load video metadata from videos.json, optionally filtered by coach/channel.
    Videos without an explicit 'channel' field count as channel == coach."""
    with open(config.VIDEOS_FILE, "r", encoding="utf-8") as f:
        videos = json.load(f)
    if coaches:
        wanted = {c.lower() for c in coaches}
        videos = [v for v in videos if v.get("coach", "").lower() in wanted]
    if channels:
        wanted = {c.lower() for c in channels}
        videos = [v for v in videos
                  if (v.get("channel") or v.get("coach", "")).lower() in wanted]
    return videos


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


# Free-tier input-token budget is 250k/min; 55-transcript topics blew it.
# Cap per-topic transcripts (round-robin across coaches so minority coaches
# keep representation) and per-transcript length.
MAX_TRANSCRIPTS_PER_TOPIC = 24
MAX_TRANSCRIPT_CHARS = 12000


def select_transcripts(transcripts: list[tuple[str, str]],
                       cap: int = MAX_TRANSCRIPTS_PER_TOPIC) -> list[tuple[str, str]]:
    """Round-robin across coaches until the cap - preserves coach diversity."""
    if len(transcripts) <= cap:
        return transcripts
    by_coach: dict[str, list[tuple[str, str]]] = {}
    for t in transcripts:
        by_coach.setdefault(t[0], []).append(t)
    picked, queues = [], list(by_coach.values())
    while len(picked) < cap and any(queues):
        for q in queues:
            if q and len(picked) < cap:
                picked.append(q.pop(0))
    return picked


def build_synthesis_prompt(topic_key: str, transcripts: list[tuple[str, str]]) -> str:
    """
    Build the prompt for synthesizing transcripts into a guide section.
    transcripts: list of (coach_name, transcript_text)
    """
    topic = TOPICS[topic_key]

    transcript_block = ""
    for coach, text in transcripts:
        # Truncate very long transcripts to avoid token limits
        if len(text) > MAX_TRANSCRIPT_CHARS:
            text = text[:MAX_TRANSCRIPT_CHARS] + "\n\n[... transcript truncated for length ...]"
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


SYNTH_MODEL = None  # optional override, set from --model


def synthesize(prompt: str) -> str:
    """Synthesize using the configured LLM provider."""
    from app.llm_client import generate_text

    return generate_text(
        prompt,
        system="You are an expert League of Legends coach and technical writer.",
        temperature=0.3,  # Lower temp for factual synthesis
        max_tokens=8000,
        model=SYNTH_MODEL,
    )


def generate_topic_section(topic_key: str, videos: list[dict], paths: OutputPaths) -> str | None:
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

    selected = select_transcripts(transcripts)
    note = f" (capped from {len(transcripts)})" if len(selected) < len(transcripts) else ""
    print(f"  Synthesizing {len(selected)} transcripts{note} for: {topic['title']}")

    prompt = build_synthesis_prompt(topic_key, selected)
    section = synthesize(prompt)

    # Save individual section
    section_path = paths.section_path(topic_key)
    os.makedirs(os.path.dirname(section_path), exist_ok=True)
    Path(section_path).write_text(section, encoding="utf-8")
    print(f"  Saved section: {section_path}")

    return section


def combine_sections(paths: OutputPaths, videos: list[dict]) -> str:
    """Combine all generated sections into the full Jungle Bible."""
    coaches = sorted({v.get("coach", "unknown") for v in videos if v.get("coach")})
    scope = f" — sources: {', '.join(coaches)}" if paths.slug else ""
    bible = "# The Jungle Bible\n"
    bible += "### A Comprehensive League of Legends Jungle Coaching Guide\n"
    bible += f"*Synthesized from coaching content by {', '.join(coaches) or 'various coaches'}{scope}*\n\n"
    bible += "---\n\n"

    # Table of contents
    bible += "## Table of Contents\n\n"
    for i, (key, topic) in enumerate(TOPICS.items(), 1):
        bible += f"{i}. [{topic['title']}](#{key})\n"
    bible += "\n---\n\n"

    # Add each section
    for key, topic in TOPICS.items():
        section_path = paths.section_path(key)
        if os.path.exists(section_path):
            section_text = Path(section_path).read_text(encoding="utf-8")
            bible += section_text + "\n\n---\n\n"
        else:
            bible += f"## {topic['title']}\n\n*Section not yet generated. "
            bible += f"Add videos with tags: {', '.join(topic['match_tags'])}*\n\n---\n\n"

    return bible


def generate_for_unmatched_transcripts(videos: list[dict], paths: OutputPaths) -> str | None:
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
    section_path = paths.section_path("supplementary")
    os.makedirs(os.path.dirname(section_path), exist_ok=True)
    Path(section_path).write_text(section, encoding="utf-8")
    return section


def main():
    parser = argparse.ArgumentParser(description="Generate The Jungle Bible from coaching transcripts")
    parser.add_argument("--topic", help="Generate a single topic section")
    parser.add_argument("--list-topics", action="store_true", help="List available topics and exit")
    parser.add_argument("--combine-only", action="store_true", help="Just combine existing sections into final document")
    parser.add_argument("--show-matching", action="store_true", help="Show which videos match which topics (dry run)")
    parser.add_argument("--incremental", action="store_true",
                        help="Only regenerate sections whose matched transcript set changed")
    parser.add_argument("--coaches", help="Comma-separated coach names to include (default: all)")
    parser.add_argument("--channels", help="Comma-separated channel names to include (default: all)")
    parser.add_argument("--name", help="Slug for filtered output files (default: derived from filters)")
    parser.add_argument("--model", help="Override LLM model for synthesis")

    args = parser.parse_args()

    if args.model:
        global SYNTH_MODEL
        SYNTH_MODEL = args.model

    coaches = [c.strip() for c in args.coaches.split(",") if c.strip()] if args.coaches else None
    channels = [c.strip() for c in args.channels.split(",") if c.strip()] if args.channels else None
    slug = None
    if coaches or channels:
        slug = args.name or "-".join(
            s.lower().replace(" ", "_") for s in (coaches or []) + (channels or []))
    paths = OutputPaths(slug)
    if slug:
        print(f"Source filter: coaches={coaches or 'all'} channels={channels or 'all'} -> "
              f"outputs under slug '{slug}'\n")

    if args.list_topics:
        print("Available topics:\n")
        for key, topic in TOPICS.items():
            print(f"  {key:25s} {topic['title']}")
            print(f"  {'':25s} Tags: {', '.join(topic['match_tags'])}")
            print()
        return

    if args.combine_only:
        bible = combine_sections(paths, load_videos_metadata(coaches, channels))
        Path(paths.bible_file).write_text(bible, encoding="utf-8")
        print(f"Jungle Bible assembled: {paths.bible_file}")
        word_count = len(bible.split())
        print(f"Total words: {word_count}")
        return

    # Check for transcripts
    videos = load_videos_metadata(coaches, channels)
    if not videos:
        print("No videos match the coach/channel filter.")
        sys.exit(1)
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

    os.makedirs(paths.sections_dir, exist_ok=True)

    if args.topic:
        if args.topic not in TOPICS:
            print(f"Unknown topic: {args.topic}")
            print(f"Available: {', '.join(TOPICS.keys())}")
            sys.exit(1)
        generate_topic_section(args.topic, videos, paths)
        meta = load_sections_meta(paths)
        meta[args.topic] = sorted(v["id"] for v in match_videos_to_topic(videos, args.topic))
        save_sections_meta(meta, paths)
    else:
        # Generate all topics (or only changed ones with --incremental)
        meta = load_sections_meta(paths)
        mode = "incrementally" if args.incremental else ""
        print(f"Generating The Jungle Bible {mode}\n")
        for topic_key in TOPICS:
            matched_ids = sorted(v["id"] for v in match_videos_to_topic(videos, topic_key))
            section_path = paths.section_path(topic_key)
            if (args.incremental and meta.get(topic_key) == matched_ids
                    and os.path.exists(section_path)):
                print(f"\n[{topic_key}] unchanged ({len(matched_ids)} transcripts), skipping")
                continue
            print(f"\n[{topic_key}]")
            if generate_topic_section(topic_key, videos, paths) is not None:
                meta[topic_key] = matched_ids
                save_sections_meta(meta, paths)
                time.sleep(25)  # free-tier input-token/minute headroom

        # Handle unmatched transcripts
        all_matched = set()
        for topic_key in TOPICS:
            all_matched.update(v["id"] for v in match_videos_to_topic(videos, topic_key))
        unmatched_ids = sorted(v["id"] for v in videos if v["id"] not in all_matched)
        supp_path = paths.section_path("supplementary")
        if (args.incremental and meta.get("_supplementary") == unmatched_ids
                and os.path.exists(supp_path)):
            print(f"\n[supplementary] unchanged ({len(unmatched_ids)} transcripts), skipping")
        else:
            generate_for_unmatched_transcripts(videos, paths)
            meta["_supplementary"] = unmatched_ids
            save_sections_meta(meta, paths)

    # Combine into final document
    print("\nAssembling final document...")
    bible = combine_sections(paths, videos)
    Path(paths.bible_file).write_text(bible, encoding="utf-8")
    word_count = len(bible.split())
    print(f"\nJungle Bible saved: {paths.bible_file}")
    print(f"Total words: {word_count} (~{word_count * 4 // 3} tokens)")


if __name__ == "__main__":
    main()
