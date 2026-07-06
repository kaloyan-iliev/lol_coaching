"""
One-command ingestion: take video ids you picked from data/video_catalog.csv and
run them through the whole pipeline - catalog add -> transcript -> LLM tags ->
(optionally) incremental Jungle Bible regeneration.

Usage:
    python scripts/ingest_videos.py EITHK7DaAoc DsrE9FjG4CI --coach PerryJG
    python scripts/ingest_videos.py ID1 ID2 --coach Veigarv2 --regen

The id is looked up across all channel scans (so title/url/channel come along
automatically). --coach names the coach in the catalog; if omitted, the scan
file's name is used.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from add_video import add_video
from extract_transcripts import process_video
from auto_tag_transcripts import load_transcript, load_videos, save_videos, tag_transcript

SCANS_DIR = os.path.join(config.DATA_DIR, "channel_scans")


def find_in_scans(video_id: str) -> tuple[str, dict] | None:
    """(scan_name, scan_entry) for a video id, or None."""
    for scan_file in sorted(glob.glob(os.path.join(SCANS_DIR, "*.json"))):
        with open(scan_file, encoding="utf-8") as f:
            for v in json.load(f):
                if v["id"] == video_id:
                    return os.path.splitext(os.path.basename(scan_file))[0], v
    return None


def main():
    parser = argparse.ArgumentParser(description="Ingest videos end-to-end by id")
    parser.add_argument("ids", nargs="+", help="Video ids (from video_catalog.csv)")
    parser.add_argument("--coach", help="Coach name for the catalog (default: scan file name)")
    parser.add_argument("--regen", action="store_true",
                        help="Run generate_jungle_bible.py --incremental at the end")
    parser.add_argument("--model", help="LLM model override for tagging")
    args = parser.parse_args()

    tagged = 0
    for i, vid in enumerate(args.ids):
        print(f"\n=== [{i + 1}/{len(args.ids)}] {vid} ===")
        hit = find_in_scans(vid)
        if hit is None:
            print(f"  Not found in any channel scan - scan the channel/playlist first "
                  f"(scripts/channel_scan.py <url> --coach X)")
            continue
        scan_name, entry = hit
        coach = args.coach or scan_name

        # 1. catalog
        add_video(entry["url"], coach=coach, title=entry.get("title", ""), channel=scan_name)

        # 2. transcript
        clean_path = os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{vid}.txt")
        if os.path.exists(clean_path):
            print("  Transcript already on disk")
        else:
            result = process_video({"id": vid, "url": entry["url"],
                                    "title": entry.get("title", vid), "coach": coach,
                                    "tags": []})
            if result["status"] != "ok":
                print("  Transcript failed - if YouTube is IP-blocking, run "
                      "scripts/extract_transcripts_ytdlp.py later; skipping tagging")
                continue

        # 3. tags
        videos = load_videos()
        video = next((v for v in videos if v["id"] == vid), None)
        if video is None:
            continue
        if video.get("tags"):
            print("  Already tagged")
            continue
        if tagged > 0:
            time.sleep(10)  # LLM RPM headroom
        try:
            meta = tag_transcript(load_transcript(vid), model=args.model)
        except Exception as e:
            print(f"  Tagging FAILED ({e}) - rerun scripts/auto_tag_transcripts.py later")
            continue
        video.update({
            "title": meta.get("title", video.get("title", "")),
            "tags": meta.get("tags", []),
            "concepts": meta.get("concepts", []),
            "champion_focus": meta.get("champion_focus", ["general"]),
            "difficulty": meta.get("difficulty", "intermediate"),
            "summary": meta.get("summary", ""),
        })
        save_videos(videos)
        tagged += 1
        print(f"  Tagged: {meta.get('tags', [])}")

    print(f"\nIngested. Refresh the spreadsheet: python scripts/video_catalog.py")
    if args.regen:
        print("Regenerating Jungle Bible incrementally...")
        subprocess.run([sys.executable,
                        os.path.join(os.path.dirname(__file__), "generate_jungle_bible.py"),
                        "--incremental"])
    else:
        print("When done adding: python scripts/generate_jungle_bible.py --incremental")


if __name__ == "__main__":
    main()
