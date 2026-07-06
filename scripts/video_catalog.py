"""
Video catalog spreadsheet: one row per known video across ALL channel scans and
the ingestion catalog (videos.json), with pipeline status columns - the review
surface for deciding what to ingest next.

Usage:
    python scripts/video_catalog.py            # writes data/video_catalog.csv + prints summary
    python scripts/video_catalog.py --summary  # just the per-channel summary table

Columns: channel, coach, video_id, title, duration_min, views, in_catalog,
transcribed, tagged, used_in_kb, difficulty, tags, champion_focus, summary, url

To ingest videos you like from the spreadsheet:
    python scripts/ingest_videos.py ID1 ID2 ... [--coach Name] [--regen]
"""

import argparse
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

SCANS_DIR = os.path.join(config.DATA_DIR, "channel_scans")
OUTPUT_CSV = os.path.join(config.DATA_DIR, "video_catalog.csv")
SECTIONS_META = os.path.join(config.KNOWLEDGE_DIR, "sections_meta.json")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def kb_video_ids() -> set[str]:
    """Video ids that fed at least one Jungle Bible section at last generation."""
    meta = load_json(SECTIONS_META, {})
    used = set()
    for ids in meta.values():
        used.update(ids)
    return used


def build_rows() -> list[dict]:
    catalog = {v["id"]: v for v in load_json(config.VIDEOS_FILE, [])}
    used_in_kb = kb_video_ids()

    rows: dict[str, dict] = {}
    for scan_file in sorted(glob.glob(os.path.join(SCANS_DIR, "*.json"))):
        channel = os.path.splitext(os.path.basename(scan_file))[0]
        for v in load_json(scan_file, []):
            if v["id"] not in rows:  # first scan wins as the channel of record
                rows[v["id"]] = {"channel": channel, "scan": v}

    # Catalog entries that never came from a scan (manually added early videos)
    for vid, v in catalog.items():
        if vid not in rows:
            rows[vid] = {"channel": v.get("channel") or v.get("coach", "manual"),
                         "scan": {"id": vid, "title": v.get("title", ""),
                                  "url": v.get("url", ""), "duration_s": None,
                                  "view_count": None}}

    out = []
    for vid, r in rows.items():
        scan, cat = r["scan"], catalog.get(vid)
        transcribed = os.path.exists(os.path.join(config.TRANSCRIPTS_CLEAN_DIR, f"{vid}.txt"))
        out.append({
            "channel": r["channel"],
            "coach": (cat or {}).get("coach", ""),
            "video_id": vid,
            "title": (cat or {}).get("title") or scan.get("title", ""),
            "duration_min": round(scan["duration_s"] / 60) if scan.get("duration_s") else "",
            "views": scan.get("view_count") or "",
            "in_catalog": "yes" if cat else "",
            "transcribed": "yes" if transcribed else "",
            "tagged": "yes" if cat and cat.get("tags") else "",
            "used_in_kb": "yes" if vid in used_in_kb else "",
            "difficulty": (cat or {}).get("difficulty", ""),
            "tags": ", ".join((cat or {}).get("tags", [])),
            "champion_focus": ", ".join((cat or {}).get("champion_focus", [])),
            "summary": (cat or {}).get("summary", ""),
            "url": (cat or {}).get("url") or scan.get("url", ""),
        })
    out.sort(key=lambda x: (x["channel"], x["in_catalog"] != "yes", x["title"].lower()))
    return out


def print_summary(rows: list[dict]):
    by_channel: dict[str, list[dict]] = {}
    for r in rows:
        by_channel.setdefault(r["channel"], []).append(r)
    print(f"{'channel':24s} {'scanned':>8s} {'in_catalog':>10s} {'transcribed':>11s} {'in_KB':>6s}")
    for ch, rs in sorted(by_channel.items()):
        print(f"{ch:24s} {len(rs):8d} {sum(1 for r in rs if r['in_catalog']):10d} "
              f"{sum(1 for r in rs if r['transcribed']):11d} "
              f"{sum(1 for r in rs if r['used_in_kb']):6d}")
    print(f"{'TOTAL':24s} {len(rows):8d} {sum(1 for r in rows if r['in_catalog']):10d} "
          f"{sum(1 for r in rows if r['transcribed']):11d} "
          f"{sum(1 for r in rows if r['used_in_kb']):6d}")


def main():
    parser = argparse.ArgumentParser(description="Video catalog spreadsheet + pipeline status")
    parser.add_argument("--summary", action="store_true", help="Print summary only, no CSV")
    args = parser.parse_args()

    rows = build_rows()
    print_summary(rows)

    if not args.summary:
        # utf-8-sig so Excel opens it with correct characters
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nSpreadsheet: {OUTPUT_CSV} ({len(rows)} rows)")
        print("Ingest picks with: python scripts/ingest_videos.py ID1 ID2 ... --coach Name")


if __name__ == "__main__":
    main()
