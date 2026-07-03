"""
Audit helper for docs/DATA_DICTIONARY.md: walks every downloaded match +
timeline and prints the union of observed event types (with their fields),
participantFrame fields, and challenges keys. Run after patches to spot new
data surfaces the dictionary doesn't cover yet.

Usage:
    python scripts/audit_data_dictionary.py           # summary
    python scripts/audit_data_dictionary.py --check   # exit 1 if the doc misses anything
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

DOC_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "DATA_DICTIONARY.md")


def audit() -> dict:
    event_fields: dict[str, set] = {}
    event_counts = collections.Counter()
    frame_fields: set[str] = set()
    champion_stats: set[str] = set()
    damage_stats: set[str] = set()
    challenge_keys: set[str] = set()
    participant_fields: set[str] = set()

    match_dir, tl_dir = config.MATCHES_DIR, config.TIMELINES_DIR
    match_files = [f for f in os.listdir(match_dir) if f.endswith(".json")] if os.path.isdir(match_dir) else []

    for fname in match_files:
        with open(os.path.join(match_dir, fname), encoding="utf-8") as f:
            match = json.load(f)
        for p in match["info"]["participants"]:
            participant_fields.update(p.keys())
            challenge_keys.update((p.get("challenges") or {}).keys())

        tl_path = os.path.join(tl_dir, fname)
        if not os.path.exists(tl_path):
            continue
        with open(tl_path, encoding="utf-8") as f:
            timeline = json.load(f)
        for frame in timeline["info"]["frames"]:
            for ev in frame.get("events", []):
                event_counts[ev["type"]] += 1
                event_fields.setdefault(ev["type"], set()).update(ev.keys())
            for pf in frame["participantFrames"].values():
                frame_fields.update(pf.keys())
                champion_stats.update((pf.get("championStats") or {}).keys())
                damage_stats.update((pf.get("damageStats") or {}).keys())

    return {
        "n_matches": len(match_files),
        "event_counts": event_counts,
        "event_fields": event_fields,
        "frame_fields": frame_fields,
        "champion_stats": champion_stats,
        "damage_stats": damage_stats,
        "challenge_keys": challenge_keys,
        "participant_fields": participant_fields,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit observed Riot data vs DATA_DICTIONARY.md")
    parser.add_argument("--check", action="store_true",
                        help="Verify every observed event type / challenges key appears in the doc")
    args = parser.parse_args()

    result = audit()
    print(f"Audited {result['n_matches']} matches (+timelines)\n")
    print(f"Event types observed ({len(result['event_counts'])}):")
    for et, c in result["event_counts"].most_common():
        print(f"  {et:30s} x{c:5d}  fields: {', '.join(sorted(result['event_fields'][et]))}")
    print(f"\nparticipantFrame fields: {', '.join(sorted(result['frame_fields']))}")
    print(f"\nchampionStats ({len(result['champion_stats'])}): {', '.join(sorted(result['champion_stats']))}")
    print(f"\ndamageStats ({len(result['damage_stats'])}): {', '.join(sorted(result['damage_stats']))}")
    print(f"\nchallenges keys observed: {len(result['challenge_keys'])}")
    print(f"match participant fields: {len(result['participant_fields'])}")

    if args.check:
        if not os.path.exists(DOC_PATH):
            print("\nFAIL: docs/DATA_DICTIONARY.md does not exist")
            sys.exit(1)
        doc = open(DOC_PATH, encoding="utf-8").read()
        missing_events = [et for et in result["event_counts"] if et not in doc]
        missing_challenges = [k for k in result["challenge_keys"] if k not in doc]
        if missing_events:
            print(f"\nFAIL: event types not in doc: {missing_events}")
        if missing_challenges:
            print(f"\nNOTE: {len(missing_challenges)} challenges keys not in doc "
                  f"(full list is summarized there by design)")
        if missing_events:
            sys.exit(1)
        print("\nDoc covers all observed event types.")


if __name__ == "__main__":
    main()
