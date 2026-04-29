"""
Extract transcripts from YouTube videos listed in data/videos.json.

Usage:
    python scripts/extract_transcripts.py                    # Process all videos
    python scripts/extract_transcripts.py --id example_001   # Process one video
    python scripts/extract_transcripts.py --url "https://youtube.com/watch?v=XXX"  # Quick single URL
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi

# Add parent dir to path so we can import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

# Cookie file path for bypassing YouTube IP bans
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "..", "www.youtube.com_cookies.txt")


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


def fetch_transcript(video_url: str) -> tuple[list[dict], str]:
    """
    Fetch transcript for a YouTube video.
    Returns (raw_segments, clean_text).

    raw_segments: [{"text": "...", "start": 0.0, "duration": 4.5}, ...]
    clean_text: Timestamped readable text
    """
    video_id = extract_video_id(video_url)

    # Use cookies if available to bypass IP bans
    import http.cookiejar
    import requests

    session = requests.Session()
    if os.path.exists(COOKIES_FILE):
        cj = http.cookiejar.MozillaCookieJar(COOKIES_FILE)
        cj.load(ignore_discard=True, ignore_expires=True)
        session.cookies = cj

    ytt_api = YouTubeTranscriptApi(http_client=session)
    raw_segments = ytt_api.fetch(video_id, languages=["en", "en-US", "en-GB"])

    # Build clean timestamped text
    lines = []
    for seg in raw_segments:
        start = seg.start
        text = seg.text
        minutes = int(start // 60)
        seconds = int(start % 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

    clean_text = "\n".join(lines)
    return raw_segments, clean_text


def process_video(video_entry: dict) -> dict:
    """
    Process a single video entry from videos.json.
    Returns a result dict with status and paths.
    """
    video_id = video_entry["id"]
    url = video_entry["url"]
    title = video_entry.get("title", video_id)
    coach = video_entry.get("coach", "unknown")
    tags = video_entry.get("tags", [])

    raw_path = os.path.join(config.TRANSCRIPTS_RAW_DIR, f"{video_id}.json")
    clean_path = os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{video_id}.txt")

    print(f"Processing: [{coach}] {title}")
    print(f"  URL: {url}")

    try:
        raw_segments, clean_text = fetch_transcript(url)
    except Exception as e:
        print(f"  FAILED: {e}")
        return {"id": video_id, "status": "failed", "error": str(e)}

    # Build header for clean transcript
    header = (
        f"# {title}\n"
        f"# Coach: {coach}\n"
        f"# Tags: {', '.join(tags)}\n"
        f"# URL: {url}\n"
        f"# Video ID: {video_id}\n"
        f"\n"
    )

    # Save raw JSON (convert segment objects to dicts)
    raw_dicts = [{"text": s.text, "start": s.start, "duration": s.duration} for s in raw_segments]
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_dicts, f, indent=2, ensure_ascii=False)

    # Save clean transcript
    with open(clean_path, "w", encoding="utf-8") as f:
        f.write(header + clean_text)

    word_count = len(clean_text.split())
    print(f"  OK - {word_count} words, {len(raw_segments)} segments")

    return {
        "id": video_id,
        "status": "ok",
        "word_count": word_count,
        "segments": len(raw_segments),
        "raw_path": raw_path,
        "clean_path": clean_path,
    }


def process_single_url(url: str) -> None:
    """Quick-process a single URL without needing videos.json."""
    video_id = extract_video_id(url)
    entry = {
        "id": video_id,
        "url": url,
        "title": f"Video {video_id}",
        "coach": "unknown",
        "tags": [],
    }
    result = process_video(entry)
    if result["status"] == "ok":
        print(f"\nTranscript saved to:")
        print(f"  Clean: {result['clean_path']}")
        print(f"  Raw:   {result['raw_path']}")


def process_all() -> None:
    """Process all videos from videos.json."""
    if not os.path.exists(config.VIDEOS_FILE):
        print(f"No videos.json found at {config.VIDEOS_FILE}")
        print("Create it first with your video entries. See data/videos.json for format.")
        sys.exit(1)

    with open(config.VIDEOS_FILE, "r", encoding="utf-8") as f:
        videos = json.load(f)

    if not videos:
        print("videos.json is empty. Add some video entries first.")
        sys.exit(1)

    print(f"Found {len(videos)} videos to process\n")

    results = {"ok": [], "failed": [], "skipped": []}

    for video in videos:
        if video.get("url", "").startswith("https://"):
            # Check if already processed
            clean_path = os.path.join(
                config.TRANSCRIPTS_CLEAN_DIR, f"{video['id']}.txt"
            )
            if os.path.exists(clean_path):
                print(f"Skipping (already exists): {video['id']}")
                results["skipped"].append(video["id"])
                continue

            result = process_video(video)
            results[result["status"]].append(result)
        else:
            print(f"Skipping (no valid URL): {video['id']}")
            results["skipped"].append(video["id"])

    # Summary
    print(f"\n{'='*50}")
    print(f"DONE: {len(results['ok'])} ok, {len(results['failed'])} failed, {len(results['skipped'])} skipped")

    if results["failed"]:
        print("\nFailed videos:")
        for r in results["failed"]:
            print(f"  - {r['id']}: {r.get('error', 'unknown error')}")


def process_by_id(video_id: str) -> None:
    """Process a single video by its ID in videos.json."""
    with open(config.VIDEOS_FILE, "r", encoding="utf-8") as f:
        videos = json.load(f)

    match = [v for v in videos if v["id"] == video_id]
    if not match:
        print(f"Video ID '{video_id}' not found in videos.json")
        sys.exit(1)

    result = process_video(match[0])
    if result["status"] == "ok":
        print(f"\nTranscript saved to:")
        print(f"  Clean: {result['clean_path']}")
        print(f"  Raw:   {result['raw_path']}")


def main():
    parser = argparse.ArgumentParser(description="Extract YouTube transcripts for LoL coaching videos")
    parser.add_argument("--id", help="Process a single video by ID from videos.json")
    parser.add_argument("--url", help="Quick-process a single YouTube URL")
    parser.add_argument("--force", action="store_true", help="Re-process even if transcript already exists")

    args = parser.parse_args()

    os.makedirs(config.TRANSCRIPTS_RAW_DIR, exist_ok=True)
    os.makedirs(config.TRANSCRIPTS_CLEAN_DIR, exist_ok=True)

    if args.url:
        process_single_url(args.url)
    elif args.id:
        process_by_id(args.id)
    else:
        process_all()


if __name__ == "__main__":
    main()
