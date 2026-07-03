"""
Extract deterministic facts from every downloaded baseline game and aggregate
them into baseline stats.

Usage:
    python scripts/riot_build_baseline.py            # facts for all games + aggregate
    python scripts/riot_build_baseline.py --match EUW1_xxx   # one game, print facts
    python scripts/riot_build_baseline.py --validate # run cross-checks on all games
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from analysis.timeline_facts import extract_facts
from analysis.baseline import aggregate_baseline


def facts_path(match_id: str) -> str:
    return os.path.join(config.FACTS_DIR, f"{match_id}.json")


def build_facts(entry: dict, verbose: bool = False) -> dict | None:
    match_id = entry["match_id"]
    match = store.load_match(match_id)
    timeline = store.load_timeline(match_id)
    if match is None or timeline is None:
        print(f"  {match_id}: missing match/timeline JSON, skipping")
        return None
    facts = extract_facts(match, timeline, entry["ekko_puuid"])
    with open(facts_path(match_id), "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2, ensure_ascii=False)
    if verbose:
        print(json.dumps(facts, indent=2, ensure_ascii=False))
    return facts


def validate(entry: dict) -> list[str]:
    """Deterministic cross-checks between extracted facts and the match JSON."""
    problems = []
    match_id = entry["match_id"]
    match = store.load_match(match_id)
    if not os.path.exists(facts_path(match_id)):
        return [f"{match_id}: no facts file"]
    with open(facts_path(match_id), encoding="utf-8") as f:
        facts = json.load(f)

    participant = next(p for p in match["info"]["participants"]
                       if p["puuid"] == entry["ekko_puuid"])

    if len(facts["deaths"]) != participant["deaths"]:
        problems.append(f"{match_id}: death count {len(facts['deaths'])} != scoreboard {participant['deaths']}")

    total_jungle_cs = participant.get("neutralMinionsKilled", 0)
    clear_cs = facts["clear"]["jungle_cs_at_end"]
    if clear_cs is not None and clear_cs > total_jungle_cs:
        problems.append(f"{match_id}: clear jungle cs {clear_cs} > final total {total_jungle_cs}")

    if facts["vision"]["wards_placed"] != participant.get("wardsPlaced", 0):
        problems.append(f"{match_id}: wards placed {facts['vision']['wards_placed']} "
                        f"!= scoreboard {participant.get('wardsPlaced')}")

    return problems


def main():
    parser = argparse.ArgumentParser(description="Build facts + baseline stats from downloaded games")
    parser.add_argument("--match", help="Process a single match ID and print its facts")
    parser.add_argument("--validate", action="store_true", help="Run cross-checks on extracted facts")
    args = parser.parse_args()

    store.ensure_dirs()
    index = store.load_index()
    if not index:
        print("No games in index. Run riot_fetch_baseline.py first.")
        sys.exit(1)

    if args.match:
        entry = next((e for e in index if e["match_id"] == args.match), None)
        if entry is None:
            print(f"Match {args.match} not in index.")
            sys.exit(1)
        build_facts(entry, verbose=True)
        return

    if args.validate:
        all_problems = []
        for entry in index:
            all_problems.extend(validate(entry))
        if all_problems:
            print("VALIDATION PROBLEMS:")
            for p in all_problems:
                print(f"  - {p}")
            sys.exit(1)
        print(f"All {len(index)} games passed cross-checks.")
        return

    print(f"Extracting facts for {len(index)} games...")
    all_facts = []
    for entry in index:
        facts = build_facts(entry)
        if facts:
            all_facts.append(facts)
            print(f"  {entry['match_id']}: {facts['kda']}, "
                  f"cs@10={facts['economy']['cs_at_10']}, "
                  f"flags={len(facts['flags'])}")

    baseline = aggregate_baseline(all_facts)
    with open(config.BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)
    print(f"\nBaseline stats ({baseline['n_games']} games) saved to {config.BASELINE_FILE}")
    print(json.dumps({k: v for k, v in baseline.items()
                      if k in ("win_rate", "cs_at_10", "first_gank_t_s", "deaths_before_14min")},
                     indent=2))


if __name__ == "__main__":
    main()
