"""
Fallback transcript extractor using yt-dlp auto-subtitles (json3).

Use when youtube-transcript-api gets IP-blocked (429 / RequestBlocked) - yt-dlp
uses different endpoints and degrades more gracefully. Produces byte-compatible
outputs with extract_transcripts.py: data/transcripts/raw/{id}.json (segments)
and data/transcripts/clean/{id}.txt (timestamped text with catalog header).

Usage:
    python scripts/extract_transcripts_ytdlp.py               # all catalog videos missing a transcript
    python scripts/extract_transcripts_ytdlp.py --id VIDEO_ID
    python scripts/extract_transcripts_ytdlp.py --rounds 6 --wait 900   # keep retrying (background)

Rate-limit etiquette: sleeps between videos; on a 429 round it backs off --wait
seconds before retrying the remainder. Rounds stop early when nothing is missing.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

SLEEP_BETWEEN = 20  # seconds between successful downloads - stay under the radar


def missing_videos() -> list[dict]:
    with open(config.VIDEOS_FILE, encoding="utf-8") as f:
        videos = json.load(f)
    return [v for v in videos
            if not os.path.exists(os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{v['id']}.txt"))]


def json3_to_segments(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    segments = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs or "tStartMs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text:
            continue
        segments.append({
            "text": text,
            "start": ev["tStartMs"] / 1000.0,
            "duration": ev.get("dDurationMs", 0) / 1000.0,
        })
    return segments


def fetch_one(video: dict) -> str | None:
    """Download auto-subs via yt-dlp into temp, convert, save. Returns error or None."""
    vid = video["id"]
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--skip-download",
             "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
             "--sub-format", "json3", "--retry-sleep", "fragment:30",
             "-o", os.path.join(tmp, "%(id)s"), video["url"]],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        files = glob.glob(os.path.join(tmp, "*.json3"))
        if not files:
            err = (result.stderr or "").strip().splitlines()
            return err[-1][:200] if err else "no subtitle file produced"
        # Prefer en-orig (unprocessed auto track) over translated variants
        files.sort(key=lambda p: ("en-orig" not in p, p))
        segments = json3_to_segments(files[0])
        if not segments:
            return "subtitle file empty"

        lines = [f"[{int(s['start'] // 60):02d}:{int(s['start'] % 60):02d}] {s['text']}"
                 for s in segments]
        header = (f"# {video.get('title', vid)}\n"
                  f"# Coach: {video.get('coach', 'unknown')}\n"
                  f"# Tags: {', '.join(video.get('tags', []))}\n"
                  f"# URL: {video['url']}\n"
                  f"# Video ID: {vid}\n\n")
        os.makedirs(config.TRANSCRIPTS_RAW_DIR, exist_ok=True)
        os.makedirs(config.TRANSCRIPTS_CLEAN_DIR, exist_ok=True)
        with open(os.path.join(config.TRANSCRIPTS_RAW_DIR, f"{vid}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        with open(os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{vid}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(header + "\n".join(lines))
        print(f"  OK - {len(segments)} segments, {sum(len(s['text'].split()) for s in segments)} words")
        return None


def main():
    parser = argparse.ArgumentParser(description="yt-dlp fallback transcript extractor")
    parser.add_argument("--id", help="Only this video id")
    parser.add_argument("--rounds", type=int, default=1, help="Retry rounds for failures")
    parser.add_argument("--wait", type=int, default=900,
                        help="Seconds to wait between retry rounds (default 15 min)")
    args = parser.parse_args()

    for round_no in range(1, args.rounds + 1):
        todo = missing_videos()
        if args.id:
            todo = [v for v in todo if v["id"] == args.id]
        if not todo:
            print("Nothing missing - done.")
            return
        print(f"--- Round {round_no}/{args.rounds}: {len(todo)} transcripts missing ---")
        rate_limited = False
        for i, v in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {v['id']} [{v.get('coach', '?')}] {v.get('title', '')[:60]}")
            err = fetch_one(v)
            if err:
                print(f"  FAILED: {err}")
                if "429" in err or "Too Many Requests" in err:
                    rate_limited = True
                    break  # no point hammering; back off the whole round
            time.sleep(SLEEP_BETWEEN)
        still = len(missing_videos()) if not args.id else 0
        if still == 0:
            print("All transcripts fetched.")
            return
        if round_no < args.rounds:
            reason = "429 rate limit" if rate_limited else f"{still} still missing"
            print(f"({reason} - waiting {args.wait}s before next round)")
            time.sleep(args.wait)

    print(f"Finished. Still missing: {len(missing_videos())}")


if __name__ == "__main__":
    main()
