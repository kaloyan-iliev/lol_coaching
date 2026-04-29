"""
Extract YouTube links from a saved Patreon page.

How to use:
1. Open the Patreon collection page in your browser (logged in)
2. Right-click -> "Save as" -> save the HTML file
   OR Ctrl+A, Ctrl+C the page content and paste into a .txt file
   OR right-click -> View Page Source -> Ctrl+A, Ctrl+C into a .txt file
3. Run: python scripts/parse_patreon_links.py saved_page.html --coach CoachName

This will:
  - Find all YouTube URLs in the saved HTML/text
  - Add them to videos.json
  - Optionally extract transcript for each
"""

import argparse
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.add_video import add_video, load_videos


def extract_youtube_urls(text: str) -> list[str]:
    """Find all YouTube URLs in text/HTML."""
    patterns = [
        # Standard watch URLs
        r'https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11}[^\s"\'<>]*',
        # Short URLs
        r'https?://youtu\.be/[a-zA-Z0-9_-]{11}[^\s"\'<>]*',
        # Embed URLs
        r'https?://(?:www\.)?youtube\.com/embed/[a-zA-Z0-9_-]{11}[^\s"\'<>]*',
    ]

    urls = set()
    for pattern in patterns:
        for match in re.findall(pattern, text):
            # Clean up URL - remove trailing HTML artifacts
            clean = re.split(r'["\'>\\&]', match)[0]
            # Normalize to standard watch URL
            vid_match = re.search(r'(?:v=|/v/|youtu\.be/|/embed/)([a-zA-Z0-9_-]{11})', clean)
            if vid_match:
                vid_id = vid_match.group(1)
                urls.add(f"https://www.youtube.com/watch?v={vid_id}")

    return sorted(urls)


def main():
    parser = argparse.ArgumentParser(description="Extract YouTube links from saved Patreon page")
    parser.add_argument("file", help="Path to saved HTML or text file")
    parser.add_argument("--coach", default="", help="Coach name to assign to all videos")
    parser.add_argument("--tags", default="", help="Comma-separated tags for all videos")
    parser.add_argument("--dry-run", action="store_true", help="Just show found URLs, don't add")

    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    urls = extract_youtube_urls(content)

    if not urls:
        print("No YouTube URLs found in the file.")
        print("\nTips:")
        print("  - Make sure you saved the full page (View Source works best)")
        print("  - Patreon loads content dynamically - scroll down before saving")
        print("  - Try opening each post first, then saving")
        return

    print(f"Found {len(urls)} YouTube URLs:\n")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")

    if args.dry_run:
        print("\n(Dry run - not adding to videos.json)")
        return

    print(f"\nAdding to videos.json (coach: {args.coach or 'unset'})...")
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    added = 0
    for url in urls:
        result = add_video(url, coach=args.coach, tags=tags)
        if result:
            added += 1

    print(f"\nAdded {added} new videos. Total in catalog: {len(load_videos())}")
    print("\nNext steps:")
    print("  1. python scripts/extract_transcripts.py          # Download transcripts")
    print("  2. python scripts/auto_tag_transcripts.py         # Auto-tag with LLM")
    print("  3. python scripts/generate_jungle_bible.py        # Generate coaching guide")


if __name__ == "__main__":
    main()
