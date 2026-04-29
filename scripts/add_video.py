"""
Helper to quickly add videos to videos.json.

Usage:
    python scripts/add_video.py "https://youtube.com/watch?v=XXX" --coach JungleGapGG --tags pathing,fundamentals
    python scripts/add_video.py "https://youtube.com/watch?v=XXX"  # minimal, fill in details later
    python scripts/add_video.py --batch urls.txt --coach KireiLoL  # bulk add from file
    python scripts/add_video.py --list                              # show all videos
    python scripts/add_video.py --stats                             # show catalog stats
    python scripts/add_video.py --list-tags                         # show valid tags
"""

import argparse
import json
import os
import re
import sys

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


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def load_videos() -> list[dict]:
    if os.path.exists(config.VIDEOS_FILE):
        with open(config.VIDEOS_FILE, "r", encoding="utf-8") as f:
            videos = json.load(f)
            return [v for v in videos if not v.get("url", "").endswith("REPLACE_ME")]
    return []


def save_videos(videos: list[dict]):
    with open(config.VIDEOS_FILE, "w", encoding="utf-8") as f:
        json.dump(videos, f, indent=2, ensure_ascii=False)


def add_video(url: str, coach: str = "", tags: list[str] = None,
              title: str = "", champions: list[str] = None) -> dict | None:
    video_id = extract_video_id(url)
    videos = load_videos()

    if video_id in {v["id"] for v in videos}:
        print(f"  Already exists: {video_id}")
        return None

    entry = {
        "id": video_id,
        "url": url.strip(),
        "title": title or f"Video {video_id}",
        "coach": coach,
        "tags": tags or [],
        "concepts": [],
        "champion_focus": champions or ["general"],
    }

    videos.append(entry)
    save_videos(videos)
    print(f"  Added: {video_id} (coach: {coach}, tags: {tags or []})")
    return entry


def add_batch(file_path: str, coach: str = "", tags: list[str] = None):
    """Add videos from a text file (one URL per line)."""
    with open(file_path, "r") as f:
        urls = [line.strip() for line in f if line.strip().startswith("http")]

    print(f"Found {len(urls)} URLs in {file_path}\n")
    added = 0
    for url in urls:
        result = add_video(url, coach=coach, tags=tags or [])
        if result:
            added += 1

    print(f"\nAdded {added} new videos. Total: {len(load_videos())}")


def main():
    parser = argparse.ArgumentParser(description="Add videos to the coaching video catalog")
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument("--coach", default="", help="Coach name")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--title", default="", help="Video title")
    parser.add_argument("--champions", default="general", help="Champion focus (comma-separated)")
    parser.add_argument("--batch", help="Path to text file with one URL per line")
    parser.add_argument("--list", action="store_true", help="List all videos")
    parser.add_argument("--list-tags", action="store_true", help="List valid tags")
    parser.add_argument("--stats", action="store_true", help="Show catalog stats")

    args = parser.parse_args()

    if args.list_tags:
        print("Valid tags (matched to Jungle Bible topics):\n")
        for tag in sorted(VALID_TAGS):
            print(f"  {tag}")
        return

    if args.list:
        videos = load_videos()
        if not videos:
            print("No videos in catalog.")
            return
        for v in videos:
            tags_str = ", ".join(v.get("tags", []))
            has_transcript = os.path.exists(
                os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{v['id']}.txt")
            )
            status = "T" if has_transcript else " "
            print(f"  [{status}] [{v.get('coach','?'):15s}] {v['id']:13s} [{tags_str}] {v.get('title','')}")
        print(f"\nTotal: {len(videos)} videos  ([T] = transcript downloaded)")
        return

    if args.stats:
        videos = load_videos()
        coaches = {}
        all_tags = {}
        for v in videos:
            c = v.get("coach", "unknown")
            coaches[c] = coaches.get(c, 0) + 1
            for tag in v.get("tags", []):
                all_tags[tag] = all_tags.get(tag, 0) + 1

        transcript_count = sum(
            1 for v in videos
            if os.path.exists(os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{v['id']}.txt"))
        )

        print(f"Total videos: {len(videos)}")
        print(f"Transcripts: {transcript_count}/{len(videos)}\n")
        print("By coach:")
        for coach, count in sorted(coaches.items(), key=lambda x: -x[1]):
            print(f"  {coach}: {count}")
        if all_tags:
            print("\nBy tag:")
            for tag, count in sorted(all_tags.items(), key=lambda x: -x[1]):
                print(f"  {tag}: {count}")
        return

    if args.batch:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        add_batch(args.batch, coach=args.coach, tags=tags)
        return

    if not args.url:
        parser.print_help()
        return

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    champions = [c.strip() for c in args.champions.split(",") if c.strip()]
    add_video(args.url, coach=args.coach, tags=tags, title=args.title, champions=champions)
    print(f"Total: {len(load_videos())} videos")


if __name__ == "__main__":
    main()
