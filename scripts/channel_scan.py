"""
Scan a YouTube channel (or playlist) and select videos to add to the
knowledge-base catalog - the human-in-the-loop entry point for expanding
the Jungle Bible with new coaches.

Uses yt-dlp --flat-playlist (no API key needed) to list videos + metadata.

Usage:
    python scripts/channel_scan.py "https://www.youtube.com/@JungleGapGG/videos" --coach JungleGapGG
    python scripts/channel_scan.py --list JungleGapGG                 # show scanned videos
    python scripts/channel_scan.py --select id1,id2,id3 --coach JungleGapGG
    python scripts/channel_scan.py --select-all --coach JungleGapGG   # add everything scanned

After selecting, run the usual chain:
    python scripts/extract_transcripts.py
    python scripts/auto_tag_transcripts.py
    python scripts/generate_jungle_bible.py --incremental
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from add_video import add_video

SCANS_DIR = os.path.join(config.DATA_DIR, "channel_scans")


def scan_path(coach: str) -> str:
    return os.path.join(SCANS_DIR, f"{coach}.json")


def scan_channel(url: str, coach: str) -> list[dict]:
    """List all videos on a channel via yt-dlp (fast, metadata only)."""
    print(f"Scanning {url} (this can take ~30s for large channels)...")
    result = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--flat-playlist", "-J", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        print(f"yt-dlp failed:\n{result.stderr[-2000:]}")
        sys.exit(1)

    data = json.loads(result.stdout)
    entries = data.get("entries", [])
    # Channel pages can nest playlists (Videos/Shorts/Live tabs)
    flat = []
    for e in entries:
        if e.get("_type") == "playlist":
            flat.extend(e.get("entries", []))
        else:
            flat.append(e)

    videos = []
    for e in flat:
        if not e or not e.get("id"):
            continue
        videos.append({
            "id": e["id"],
            "title": e.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={e['id']}",
            "duration_s": e.get("duration"),
            "view_count": e.get("view_count"),
            "selected": False,
        })

    os.makedirs(SCANS_DIR, exist_ok=True)
    with open(scan_path(coach), "w", encoding="utf-8") as f:
        json.dump(videos, f, indent=2, ensure_ascii=False)
    print(f"Found {len(videos)} videos. Saved to {scan_path(coach)}")
    return videos


def load_scan(coach: str) -> list[dict]:
    path = scan_path(coach)
    if not os.path.exists(path):
        print(f"No scan found for '{coach}'. Scan the channel first.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_scan(coach: str):
    videos = load_scan(coach)
    already = set()
    if os.path.exists(config.VIDEOS_FILE):
        with open(config.VIDEOS_FILE, encoding="utf-8") as f:
            already = {v["id"] for v in json.load(f)}

    print(f"{'':2s} {'ID':13s} {'mins':>5s} {'views':>10s}  title")
    for v in sorted(videos, key=lambda x: -(x.get("view_count") or 0)):
        mark = "A" if v["id"] in already else ("x" if v.get("selected") else " ")
        mins = f"{(v['duration_s'] or 0) / 60:.0f}" if v.get("duration_s") else "?"
        views = f"{v['view_count']:,}" if v.get("view_count") else "?"
        print(f"[{mark}] {v['id']:13s} {mins:>5s} {views:>10s}  {v['title'][:80]}")
    print(f"\n{len(videos)} videos  ([A] = already in catalog, [x] = selected)")


def select_videos(coach: str, ids: list[str] | None, select_all: bool, scan_name: str | None = None):
    """scan_name: which scan file to read (defaults to coach). Lets one coach own
    several channels, e.g. scan 'KireiVODs' selected under coach 'KireiLoL'."""
    scan_name = scan_name or coach
    videos = load_scan(scan_name)
    targets = videos if select_all else [v for v in videos if v["id"] in set(ids or [])]
    if not targets:
        print("No matching videos to select.")
        return

    added = 0
    for v in targets:
        v["selected"] = True
        result = add_video(v["url"], coach=coach, title=v.get("title", ""), channel=scan_name)
        if result:
            added += 1

    with open(scan_path(scan_name), "w", encoding="utf-8") as f:
        json.dump(videos, f, indent=2, ensure_ascii=False)

    print(f"\nAdded {added} videos to the catalog. Next steps:")
    print("  python scripts/extract_transcripts.py")
    print("  python scripts/auto_tag_transcripts.py")
    print("  python scripts/generate_jungle_bible.py --incremental")


def main():
    parser = argparse.ArgumentParser(description="Scan a YouTube channel and select coaching videos")
    parser.add_argument("url", nargs="?", help="Channel or playlist URL to scan")
    parser.add_argument("--coach", help="Coach name (used as scan file name and catalog coach)")
    parser.add_argument("--list", metavar="COACH", help="List a previous scan")
    parser.add_argument("--select", help="Comma-separated video IDs to add to the catalog")
    parser.add_argument("--select-all", action="store_true", help="Add every scanned video")
    parser.add_argument("--scan", help="Scan file to select from when it differs from --coach "
                                       "(e.g. --scan KireiVODs --coach KireiLoL)")
    args = parser.parse_args()

    if args.list:
        list_scan(args.list)
        return

    if args.select or args.select_all:
        if not args.coach:
            print("--select needs --coach")
            sys.exit(1)
        ids = [i.strip() for i in args.select.split(",")] if args.select else None
        select_videos(args.coach, ids, args.select_all, scan_name=args.scan)
        return

    if args.url:
        if not args.coach:
            print("Scanning needs --coach (it names the scan file and the catalog coach).")
            sys.exit(1)
        coach = args.coach
        scan_channel(args.url, coach)
        print(f"\nReview the list with: python scripts/channel_scan.py --list {coach}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
