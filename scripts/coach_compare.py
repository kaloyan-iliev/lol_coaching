"""
Coach disagreement report: for every Jungle Bible topic covered by 2+ coaches,
ask the LLM to separate consensus from genuine disagreement.

Complements generate_jungle_bible.py (whose sections merge coaches into one
voice) by making the differences explicit and citable.

Usage:
    python scripts/coach_compare.py                          # all topics, all coaches
    python scripts/coach_compare.py --topics pathing,ganking
    python scripts/coach_compare.py --coaches KireiLoL,JungleGapGG
    python scripts/coach_compare.py --dry-run                # show coverage, no LLM calls

Output: knowledge/coach_disagreements.md
"""

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from generate_jungle_bible import (
    TOPICS, load_transcript, load_videos_metadata, match_videos_to_topic, synthesize,
)

OUTPUT_FILE = os.path.join(config.KNOWLEDGE_DIR, "coach_disagreements.md")

COMPARE_PROMPT = """You are analyzing League of Legends jungle coaching content on the topic:
{title} ({description})

Below are transcripts from DIFFERENT coaches. Your job is comparative analysis,
NOT synthesis. Produce these subsections in markdown (### headers):

### Consensus
Where the coaches clearly agree. Brief bullet points.

### Disagreements
Situations where coaches give DIFFERENT advice for the same decision. For each:
- **The situation:** one line
- **What each coach says**, named, with their stated reasoning
- **Contextual or philosophical?** — is the difference explained by elo/champion/patch
  context, or is it a genuine difference in philosophy?
- **How to decide:** one practical line for a Diamond+ jungler

### Unique emphases
Important points only one coach makes (name the coach).

RULES:
- Only report REAL disagreements grounded in what the transcripts actually say.
  Do NOT manufacture disagreement. If there is none, write "No genuine
  disagreements found on this topic." under the Disagreements header.
- Always attribute views to the named coach.
- Keep it tight: this is a reference document, not an essay.

TRANSCRIPTS:
{transcript_block}
"""


def build_transcript_block(by_coach: dict[str, list[dict]], max_per_coach: int,
                           char_cap: int = 8000) -> str:
    block = ""
    for coach, vids in sorted(by_coach.items()):
        for v in vids[:max_per_coach]:
            text = load_transcript(v["id"]) or ""
            if len(text) > char_cap:
                text = text[:char_cap] + "\n[... truncated ...]"
            block += f"\n--- Coach: {coach} | Video: {v.get('title', v['id'])} ---\n{text}\n"
    return block


def main():
    parser = argparse.ArgumentParser(description="Where do the coaches disagree?")
    parser.add_argument("--topics", help="Comma-separated topic keys (default: all)")
    parser.add_argument("--coaches", help="Comma-separated coach filter (default: all)")
    parser.add_argument("--max-per-coach", type=int, default=2,
                        help="Max transcripts per coach per topic (token budget)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show per-topic coach coverage without LLM calls")
    parser.add_argument("--model", help="Override LLM model for the comparisons")
    args = parser.parse_args()

    if args.model:
        import generate_jungle_bible
        generate_jungle_bible.SYNTH_MODEL = args.model

    coaches = [c.strip() for c in args.coaches.split(",") if c.strip()] if args.coaches else None
    topic_keys = ([t.strip() for t in args.topics.split(",") if t.strip()]
                  if args.topics else list(TOPICS.keys()))
    for t in topic_keys:
        if t not in TOPICS:
            print(f"Unknown topic: {t}. Available: {', '.join(TOPICS)}")
            sys.exit(1)

    videos = load_videos_metadata(coaches=coaches)

    sections = []
    calls = 0
    for key in topic_keys:
        topic = TOPICS[key]
        matched = match_videos_to_topic(videos, key)
        by_coach: dict[str, list[dict]] = {}
        for v in matched:
            if load_transcript(v["id"]):
                by_coach.setdefault(v.get("coach", "unknown"), []).append(v)

        n_coaches = len(by_coach)
        coverage = ", ".join(f"{c}({len(vs)})" for c, vs in sorted(by_coach.items()))
        print(f"[{key}] {n_coaches} coaches: {coverage or 'none'}")

        if n_coaches < 2:
            sections.append(f"## {topic['title']}\n\n*Only covered by "
                            f"{coverage or 'no one'} — nothing to compare yet.*\n")
            continue
        if args.dry_run:
            continue

        if calls > 0:
            time.sleep(30)  # free-tier RPM + input-token/minute headroom
        block = build_transcript_block(by_coach, args.max_per_coach)
        prompt = COMPARE_PROMPT.format(
            title=topic["title"], description=topic["description"], transcript_block=block)
        print(f"  comparing ({len(block)} chars)...")
        try:
            result = synthesize(prompt)
        except Exception as e:
            print(f"  FAILED: {e}")
            sections.append(f"## {topic['title']}\n\n*Comparison failed: {e}*\n")
            continue
        calls += 1
        sections.append(f"## {topic['title']}\n\n{result}\n")

    if args.dry_run:
        print("\n(dry run - no report written)")
        return

    all_coaches = sorted({v.get("coach", "?") for v in videos})
    doc = (f"# Where the Coaches Disagree\n\n"
           f"*Generated {date.today().isoformat()} from transcripts by: "
           f"{', '.join(all_coaches)}. Companion to jungle_bible.md — the bible merges "
           f"coaches into one voice; this file keeps their differences visible.*\n\n---\n\n"
           + "\n---\n\n".join(sections))
    Path(OUTPUT_FILE).write_text(doc, encoding="utf-8")
    print(f"\nSaved: {OUTPUT_FILE} ({calls} topics compared)")


if __name__ == "__main__":
    main()
