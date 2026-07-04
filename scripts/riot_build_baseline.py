"""
Build the games knowledge base: extract deterministic facts for every indexed
jungler-game and aggregate per-champion + generic baselines.

Also backfills opponents: every match on disk contains two junglers, so any
jungler not yet indexed is added for free (no API calls).

Usage:
    python scripts/riot_build_baseline.py            # backfill + facts + baselines
    python scripts/riot_build_baseline.py --entry EUW1_xxx:PUUID   # one entry, print facts
    python scripts/riot_build_baseline.py --validate # run cross-checks on all entries
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

MIN_GAMES_FOR_CHAMPION_BASELINE = 8


def facts_path(entry: dict) -> str:
    return os.path.join(config.FACTS_DIR,
                        f"{entry['match_id']}_{entry['participant_id']}.json")


def backfill_opponents():
    """Index junglers already on disk but missing from the index (free games)."""
    index = store.load_index()
    indexed = {(e["match_id"], e["puuid"]) for e in index}
    tiers_by_match = {e["match_id"]: e.get("tier", "?") for e in index}
    added = 0
    for match_id in sorted({e["match_id"] for e in index}):
        match = store.load_match(match_id)
        if match is None:
            continue
        for p in match["info"]["participants"]:
            if p.get("teamPosition") != "JUNGLE":
                continue
            if (match_id, p["puuid"]) in indexed:
                continue
            store.add_index_entry({
                "match_id": match_id,
                "game_version": match["info"].get("gameVersion", ""),
                "queue_id": match["info"].get("queueId"),
                "game_creation": match["info"].get("gameCreation"),
                "game_duration_s": match["info"].get("gameDuration"),
                "puuid": p["puuid"],
                "champion": p["championName"],
                "participant_id": p["participantId"],
                "team_id": p["teamId"],
                "tier": tiers_by_match.get(match_id, "?"),
                "win": p["win"],
                "has_timeline": True,
                "source": "opponent_backfill",
            })
            indexed.add((match_id, p["puuid"]))
            added += 1
    if added:
        print(f"Backfilled {added} opponent jungler-games (zero API calls)")


def build_facts(entry: dict, verbose: bool = False) -> dict | None:
    match_id = entry["match_id"]
    match = store.load_match(match_id)
    timeline = store.load_timeline(match_id)
    if match is None or timeline is None:
        print(f"  {match_id}: missing match/timeline JSON, skipping")
        return None
    facts = extract_facts(match, timeline, entry["puuid"])
    with open(facts_path(entry), "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2, ensure_ascii=False)
    if verbose:
        print(json.dumps(facts, indent=2, ensure_ascii=False))
    return facts


def validate(entry: dict) -> list[str]:
    """Deterministic cross-checks between extracted facts and the match JSON."""
    problems = []
    match_id = entry["match_id"]
    match = store.load_match(match_id)
    if not os.path.exists(facts_path(entry)):
        return [f"{match_id}/{entry['champion']}: no facts file"]
    with open(facts_path(entry), encoding="utf-8") as f:
        facts = json.load(f)

    participant = next(p for p in match["info"]["participants"]
                       if p["puuid"] == entry["puuid"])

    if len(facts["deaths"]) != participant["deaths"]:
        problems.append(f"{match_id}/{entry['champion']}: death count "
                        f"{len(facts['deaths'])} != scoreboard {participant['deaths']}")

    total_jungle_cs = participant.get("neutralMinionsKilled", 0)
    clear_cs = facts["clear"]["jungle_cs_at_end"]
    if clear_cs is not None and clear_cs > total_jungle_cs:
        problems.append(f"{match_id}/{entry['champion']}: clear jungle cs "
                        f"{clear_cs} > final total {total_jungle_cs}")

    if facts["vision"]["wards_placed"] != participant.get("wardsPlaced", 0):
        problems.append(f"{match_id}/{entry['champion']}: wards placed "
                        f"{facts['vision']['wards_placed']} != scoreboard "
                        f"{participant.get('wardsPlaced')}")

    detector_wards = participant.get("detectorWardsPlaced")
    if detector_wards is not None and facts["vision"]["control_wards"] != detector_wards:
        problems.append(f"{match_id}/{entry['champion']}: control wards from events "
                        f"{facts['vision']['control_wards']} != scoreboard "
                        f"detectorWardsPlaced {detector_wards}")

    timeline = store.load_timeline(match_id)
    if timeline is not None:
        from analysis.momentum import team_gold_curve
        teams = {p["participantId"]: p["teamId"] for p in match["info"]["participants"]}
        full_curve = team_gold_curve(timeline, teams, participant["teamId"])
        our_team = participant["teamId"]
        gold_by_team = {100: 0, 200: 0}
        for p in match["info"]["participants"]:
            gold_by_team[p["teamId"]] += p.get("goldEarned", 0)
        scoreboard_diff = gold_by_team[our_team] - gold_by_team[200 if our_team == 100 else 100]
        if full_curve and abs(full_curve[-1]["diff"] - scoreboard_diff) > 500:
            problems.append(f"{match_id}/{entry['champion']}: final-frame team-gold diff "
                            f"{full_curve[-1]['diff']} vs scoreboard {scoreboard_diff}")

    return problems


def write_baselines(all_facts: list[dict]):
    """Per-champion baselines (n >= MIN) + a generic all-jungler baseline."""
    os.makedirs(config.BASELINES_DIR, exist_ok=True)

    by_champ: dict[str, list[dict]] = {}
    for f in all_facts:
        by_champ.setdefault(f["champion"], []).append(f)

    written = []
    for champ, facts_list in sorted(by_champ.items(), key=lambda kv: -len(kv[1])):
        if len(facts_list) < MIN_GAMES_FOR_CHAMPION_BASELINE:
            continue
        baseline = aggregate_baseline(facts_list, champion=champ)
        path = os.path.join(config.BASELINES_DIR, f"{champ}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)
        written.append(f"{champ} (n={len(facts_list)})")

    generic = aggregate_baseline(all_facts, champion="_GENERIC")
    with open(os.path.join(config.BASELINES_DIR, "_generic.json"), "w", encoding="utf-8") as f:
        json.dump(generic, f, indent=2, ensure_ascii=False)
    written.append(f"_GENERIC (n={len(all_facts)})")

    # Keep the legacy Ekko file in sync if we have an Ekko baseline
    if "Ekko" in by_champ and len(by_champ["Ekko"]) >= MIN_GAMES_FOR_CHAMPION_BASELINE:
        with open(config.BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(aggregate_baseline(by_champ["Ekko"], champion="Ekko"), f,
                      indent=2, ensure_ascii=False)

    print(f"\nBaselines written to {config.BASELINES_DIR}:")
    for w in written:
        print(f"  {w}")


def main():
    parser = argparse.ArgumentParser(description="Build facts + baselines for the games KB")
    parser.add_argument("--entry", help='Process one entry: "MATCH_ID:PUUID", print facts')
    parser.add_argument("--validate", action="store_true", help="Run cross-checks on extracted facts")
    parser.add_argument("--no-backfill", action="store_true", help="Skip opponent backfill")
    args = parser.parse_args()

    store.ensure_dirs()

    if not args.no_backfill and not args.entry and not args.validate:
        backfill_opponents()

    index = store.load_index()
    if not index:
        print("No games in index. Run riot_fetch_baseline.py first.")
        sys.exit(1)

    if args.entry:
        match_id, puuid = args.entry.split(":", 1)
        entry = next((e for e in index if e["match_id"] == match_id and e["puuid"] == puuid), None)
        if entry is None:
            print(f"Entry not in index: {args.entry}")
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
        print(f"All {len(index)} jungler-games passed cross-checks.")
        return

    print(f"Extracting facts for {len(index)} jungler-games...")
    all_facts = []
    for entry in index:
        facts = build_facts(entry)
        if facts:
            all_facts.append(facts)

    print(f"  {len(all_facts)} facts files written")
    write_baselines(all_facts)


if __name__ == "__main__":
    main()
