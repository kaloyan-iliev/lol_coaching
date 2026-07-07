"""
Analyze one of your games: deterministic facts + Master+ baseline + Jungle
Bible sections -> LLM coaching review with timestamped advice.

Usage:
    python scripts/review_game.py --riot-id "Name#TAG" --latest
    python scripts/review_game.py --riot-id "Name#TAG" --list        # recent jungle games
    python scripts/review_game.py --match EUW1_1234567890 --puuid <puuid>
    python scripts/review_game.py --riot-id "Name#TAG" --latest --facts-only
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from riot.client import RiotClient
from analysis.timeline_facts import extract_facts, mmss
from analysis.narrative import build_fact_sheet
from analysis.section_select import select_sections_for_flags

RANKED_SOLO_QUEUE = 420


def load_baseline(champion: str) -> dict | None:
    """Per-champion baseline if we have one, else the generic all-jungler baseline."""
    candidates = [
        os.path.join(config.BASELINES_DIR, f"{champion}.json"),
        os.path.join(config.BASELINES_DIR, "_generic.json"),
        config.BASELINE_FILE if champion == "Ekko" else None,  # legacy
    ]
    for path in candidates:
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return None


def resolve_puuid(client: RiotClient, riot_id: str) -> str:
    if "#" not in riot_id:
        print('Riot ID must be "Name#TAG"')
        sys.exit(1)
    name, tag = riot_id.split("#", 1)
    account = client.account_by_riot_id(name.strip(), tag.strip())
    if account is None:
        print(f"Riot ID not found: {riot_id}")
        sys.exit(1)
    return account["puuid"]


def fetch_game(client: RiotClient, match_id: str) -> tuple[dict, dict]:
    match = store.load_match(match_id)
    timeline = store.load_timeline(match_id)
    if match is None:
        match = client.match(match_id)
        if match is None:
            print(f"Match not found: {match_id}")
            sys.exit(1)
        store.save_match(match_id, match)
    if timeline is None:
        timeline = client.timeline(match_id)
        if timeline is None:
            print(f"Timeline not available for {match_id}")
            sys.exit(1)
        store.save_timeline(match_id, timeline)
    return match, timeline


def list_recent(client: RiotClient, puuid: str, count: int = 10):
    ids = client.match_ids(puuid, queue=RANKED_SOLO_QUEUE, count=count)
    print(f"Recent ranked games:")
    for match_id in ids:
        match, _ = None, None
        match = store.load_match(match_id) or client.match(match_id)
        if match is None:
            continue
        store.save_match(match_id, match)
        p = next((p for p in match["info"]["participants"] if p["puuid"] == puuid), None)
        if p is None:
            continue
        print(f"  {match_id}  {p['championName']:12s} {p.get('teamPosition', '?'):7s} "
              f"{'WIN ' if p['win'] else 'LOSS'} {p['kills']}/{p['deaths']}/{p['assists']} "
              f"({match['info']['gameDuration'] // 60}min)")


def collect_fact_times(facts: dict) -> set[int]:
    """All timestamps (seconds) present in a game's extracted facts."""
    fact_times = set()
    for d in facts["deaths"]:
        fact_times.add(d["t"])
    for g in facts["ganks"]:
        fact_times.add(g["t"])
    for o in facts["objectives"]:
        fact_times.add(o["t"])
    for c in facts["counter_jungle"]:
        fact_times.add(c["t"])
    for f_ in facts.get("teamfights", []):
        fact_times.add(f_["t_start"])
        fact_times.add(f_["t_end"])
    momentum = facts.get("momentum") or {}
    for s in momentum.get("swings", []):
        fact_times.add(s["t_start"])
        fact_times.add(s["t_end"])
    for p in momentum.get("team_gold_diff_curve", []):
        fact_times.add(p["t"])
    for p in facts["economy"]["gold_diff_vs_enemy_jgl_curve"]:
        fact_times.add(p["t"])
    for s in facts["clear"]["sequence"]:
        fact_times.update(s["t_window"])
    for key in ("first_gank_t", "first_reset_s"):
        if facts["economy"][key]:
            fact_times.add(facts["economy"][key])
    if facts["clear"]["full_clear_end_s"]:
        fact_times.add(facts["clear"]["full_clear_end_s"])
    return fact_times


def check_timestamps(review: str, facts: dict) -> list[str]:
    """Hallucination tripwire: every mm:ss cited in the review must be within
    90s of some fact timestamp and inside the game duration."""
    fact_times = collect_fact_times(facts)

    warnings = []
    for m in re.finditer(r"\b(\d{1,2}):([0-5]\d)\b", review):
        t = int(m.group(1)) * 60 + int(m.group(2))
        if t > facts["duration_s"]:
            warnings.append(f"{m.group(0)} is beyond game duration {facts['duration_clock']}")
        elif fact_times and min(abs(t - ft) for ft in fact_times) > 90:
            warnings.append(f"{m.group(0)} does not match any extracted fact (nearest is "
                            f">{90}s away) - possibly hallucinated")
    return warnings


def account_slug(match: dict, puuid: str) -> str:
    """Filesystem-safe account name of the reviewed player, e.g. 'Poledarden_6081'."""
    p = next((p for p in match["info"]["participants"] if p["puuid"] == puuid), None)
    if p and p.get("riotIdGameName"):
        name = f"{p['riotIdGameName']}_{p.get('riotIdTagline', '')}"
    else:
        name = puuid[:12]
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_")


def review_out_path(match: dict, puuid: str) -> str:
    """Reviews live under data/reviews/<Account_Tag>/<YYYY-MM-DD>/<match_id>.md
    (game-end date, local time)."""
    from datetime import datetime

    day = datetime.fromtimestamp(
        match["info"]["gameEndTimestamp"] / 1000).strftime("%Y-%m-%d")
    out_dir = os.path.join(config.REVIEWS_DIR, account_slug(match, puuid), day)
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{match['metadata']['matchId']}.md")


def main():
    parser = argparse.ArgumentParser(description="LLM game review grounded in facts + Jungle Bible")
    parser.add_argument("--riot-id", help='Your Riot ID, e.g. "Name#TAG"')
    parser.add_argument("--latest", action="store_true", help="Review your most recent ranked game")
    parser.add_argument("--last", type=int, metavar="N", help="Review your N most recent ranked games")
    parser.add_argument("--match", help="Review a specific match ID")
    parser.add_argument("--puuid", help="Puuid to analyze (with --match, skips --riot-id lookup)")
    parser.add_argument("--list", action="store_true", help="List recent ranked games and exit")
    parser.add_argument("--facts-only", action="store_true", help="Print the fact sheet, skip the LLM")
    args = parser.parse_args()

    store.ensure_dirs()
    client = RiotClient()

    puuid = None
    if args.puuid:
        puuid = args.puuid
    elif args.riot_id:
        puuid = resolve_puuid(client, args.riot_id)
    else:
        print("Need --riot-id or --puuid")
        sys.exit(1)

    if args.list:
        list_recent(client, puuid)
        return

    if args.match:
        match_ids = [args.match]
    elif args.latest or args.last:
        n = args.last or 1
        match_ids = client.match_ids(puuid, queue=RANKED_SOLO_QUEUE, count=n)
        if not match_ids:
            print("No recent ranked games found.")
            sys.exit(1)
    else:
        print("Need --latest, --last N or --match")
        sys.exit(1)

    saved = []
    for i, match_id in enumerate(match_ids, 1):
        if len(match_ids) > 1:
            print(f"\n===== Game {i}/{len(match_ids)} =====")
        saved.append(run_review(client, match_id, puuid, args.facts_only))

    if len(saved) > 1:
        print("\nAll reviews saved:")
        for s in saved:
            if s:
                print(f"  {s}")


def run_review(client: RiotClient, match_id: str, puuid: str,
               facts_only: bool = False) -> str | None:
    """Fetch, analyze and review one game; returns the saved review path."""
    print(f"Analyzing {match_id}...")
    match, timeline = fetch_game(client, match_id)
    facts = extract_facts(match, timeline, puuid)

    # Persist the parsed layer for own games too (baseline games get theirs
    # from riot_build_baseline.py)
    facts_path = os.path.join(config.FACTS_DIR, f"{match_id}.json")
    os.makedirs(config.FACTS_DIR, exist_ok=True)
    with open(facts_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2, ensure_ascii=False)
    print(f"Facts saved to {facts_path}")

    baseline = load_baseline(facts["champion"])
    if baseline is None:
        print("(No baseline stats found - run riot_build_baseline.py for Master+ comparisons)")
    elif baseline.get("champion") == "_GENERIC":
        print(f"(No {facts['champion']}-specific baseline yet - using the generic "
              f"all-jungler baseline; clear-speed/CS comparisons are approximate)")

    if facts["our_role"] != "JUNGLE":
        print(f"\nWARNING: you played {facts['champion']} {facts['our_role']}, but this analyzer "
              f"is built for JUNGLE. Clear/pathing/counter-jungle facts will be meaningless; "
              f"deaths, teamfights and objectives are still valid.")

    fact_sheet = build_fact_sheet(facts, baseline)

    if facts_only:
        print("\n" + fact_sheet)
        return None

    section_keys, sections_text = select_sections_for_flags(facts["flags"])
    print(f"Flags: {', '.join(facts['flags']) or 'none'}")
    print(f"Bible sections selected: {', '.join(section_keys)}")

    system_prompt = Path(
        os.path.join(os.path.dirname(__file__), "..", "app", "prompts", "review_prompt.txt")
    ).read_text(encoding="utf-8")

    from app.llm_client import generate_text, load_house_rules
    house_rules = load_house_rules()
    house_block = (
        f"# HOUSE RULES (the player's own principles - these OVERRIDE everything below, "
        f"including COACHING KNOWLEDGE)\n\n{house_rules}\n\n---\n\n"
    ) if house_rules else ""

    user_prompt = (
        f"{house_block}"
        f"{fact_sheet}\n\n"
        f"---\n\n"
        f"# COACHING KNOWLEDGE (selected sections: {', '.join(section_keys)})\n\n"
        f"{sections_text}\n\n"
        f"---\n\n"
        f"Write the coaching review of this game now, following the output format."
    )

    print("Generating review (1 LLM call)...")
    review = generate_text(user_prompt, system=system_prompt, temperature=0.3, max_tokens=8000)

    warnings = check_timestamps(review, facts)

    out_path = review_out_path(match, puuid)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Game Review: {match_id}\n\n{review}\n\n---\n\n"
                f"<details><summary>Fact sheet used</summary>\n\n{fact_sheet}\n</details>\n")

    print("\n" + "=" * 70 + "\n")
    print(review)
    print("\n" + "=" * 70)
    if warnings:
        print("\nTIMESTAMP CHECK WARNINGS (possible hallucinations):")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\nTimestamp check: all cited moments match extracted facts.")
    print(f"\nSaved to {out_path}")
    return out_path


if __name__ == "__main__":
    main()
