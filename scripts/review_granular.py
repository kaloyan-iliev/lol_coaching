"""
Granular coaching review: the same review pipeline as review_game.py (facts +
baseline + Jungle Bible -> one LLM call -> timestamped review), but the fact
sheet is AUGMENTED with map_state.py's anchor-aware reconstruction (zone
occupancy, jungler contact windows, power-spike windows) instead of relying
only on the standard 60s-frame facts. This gives the model tick-level pathing
and fight-timing grounding instead of 60s-snapshot guesswork for exactly the
questions those snapshots answer worst.

Fully offline - requires the game already cached (run review_game.py or
export_game_csv.py on it once first). No Riot API call.

Usage:
    python scripts/review_granular.py --match EUW1_xxx [--tick 15]

Output: data/reviews/<Account>/<day>/<match_id>_granular.md, saved ALONGSIDE
the standard review (never overwrites it) so the two can be compared -
including with judge_review.py --pair <standard> <granular>.
"""

import argparse
import os
import json
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import config
from riot import store
from riot.client import RiotClient
from analysis.narrative import build_fact_sheet
from analysis.timeline_facts import extract_facts
from review_game import (RANKED_SOLO_QUEUE, collect_fact_times, fetch_game,
                         generate_review_text, load_baseline, resolve_puuid,
                         review_out_path)
from map_state import item_map, state_ticks
from state_report import (CSV_DIR, contact_windows, load_item_gold_index,
                          load_kills, load_state_rows, mmss, power_spike_windows,
                          zone_occupancy)


def get_our_puuid(match: dict, facts: dict) -> str | None:
    p = next((p for p in match["info"]["participants"]
              if p.get("championName") == facts["champion"]
              and p.get("teamPosition") == facts["our_role"]), None)
    return p["puuid"] if p else None


def granular_block(rows, kills, gold_index, our_champ, enemy_champ, our_side, tick):
    occ_our = zone_occupancy(rows, our_champ)
    occ_enemy = zone_occupancy(rows, enemy_champ)
    cw = contact_windows(rows, our_champ, enemy_champ, kills)
    ps = power_spike_windows(rows, our_champ, enemy_champ, gold_index, kills)

    def fmt_occ(buckets, side):
        total = sum(buckets.values()) or 1
        own_jgl = f"{side}_jungle"
        enemy_jgl = "red_jungle" if side == "blue" else "blue_jungle"
        order = [("lane", "lane"), (own_jgl, "own jungle"),
                (enemy_jgl, "enemy jungle"), ("river", "river"), ("base", "base")]
        return ", ".join(f"{label} {100 * buckets.get(k, 0) // total}%"
                        for k, label in order if buckets.get(k))

    enemy_side = "red" if our_side == "blue" else "blue"
    lines = [
        f"## GRANULAR MOVEMENT DATA ({tick}s-tick reconstruction, anchor-aware "
        f"interpolation between item/kill/objective events - finer and more reliable "
        f"than the 60s-snapshot positions used elsewhere in this fact sheet; prefer "
        f"THESE timestamps for pathing/positioning/contact-decision claims)",
        "",
        f"- {our_champ} (you) zone occupancy: {fmt_occ(occ_our, our_side)}",
        f"- {enemy_champ} (enemy jungler) zone occupancy: {fmt_occ(occ_enemy, enemy_side)}",
        "",
        "### Jungler contact windows (within ~1 screen of each other)",
    ]
    if not cw:
        lines.append(f"No contact windows detected - {our_champ} and {enemy_champ} never "
                     f"came within contact range this game.")
    else:
        for w in cw:
            tag = "a fight happened here" if w["fight_nearby"] else \
                  "NO fight followed (avoided, denied, or a missed chance)"
            unc = " [position estimate uncertain here]" if w["uncertain"] else ""
            lines.append(f"- {mmss(w['t'])}: distance {w['dist']} units - {tag}{unc}")

    lines += ["", "### Power-spike windows (item+level advantage vs enemy jungler; "
                  "approximate - no HP/cooldown data)"]
    if not ps:
        lines.append("No clear item/level advantage swings detected either way.")
    else:
        for e in ps:
            tag = "a fight happened nearby" if e["fight_nearby"] else "no fight taken in this window"
            lines.append(f"- {mmss(e['t'])}: {our_champ} {e['state']} by ~{abs(e['adv_gold_est'])}g "
                        f"equivalent - {tag}")

    times_s = [w["t"] for w in cw] + [e["t"] for e in ps]
    return "\n".join(lines), times_s


def granular_review(match_id: str, tick: int, client: "RiotClient | None" = None,
                    puuid: str | None = None) -> str | None:
    """Produce one granular review; fetch+cache the game and facts if missing."""
    match = store.load_match(match_id)
    timeline = store.load_timeline(match_id)
    if (match is None or timeline is None) and client is not None:
        match, timeline = fetch_game(client, match_id)
    if match is None or timeline is None:
        print(f"Match/timeline not cached for {match_id} (pass --riot-id to fetch).")
        return None

    facts_path = os.path.join(config.FACTS_DIR, f"{match_id}.json")
    if os.path.exists(facts_path):
        facts = json.load(open(facts_path, encoding="utf-8"))
    elif puuid:
        facts = extract_facts(match, timeline, puuid)
        os.makedirs(config.FACTS_DIR, exist_ok=True)
        with open(facts_path, "w", encoding="utf-8") as f:
            json.dump(facts, f, indent=2, ensure_ascii=False)
    else:
        print(f"No cached facts for {match_id}. Run review_game.py --match {match_id} "
              f"first, or pass --riot-id so this can build them.")
        return None

    state_path = os.path.join(CSV_DIR, match_id, f"state_{tick}s.csv")
    if not os.path.exists(state_path):
        print(f"Building state_{tick}s.csv (not found)...")
        items_db = item_map(match["info"]["gameVersion"])
        state_ticks(match, timeline, tick, items_db)

    rows = load_state_rows(match_id, tick)
    kills = load_kills(match_id)
    gold_index = load_item_gold_index(facts["game_version"])
    our_champ, enemy_champ, our_side = facts["champion"], facts["enemy_jungler"], facts["our_team"]

    g_block, g_times = granular_block(rows, kills, gold_index, our_champ, enemy_champ,
                                      our_side, tick)

    baseline = load_baseline(facts["champion"])
    fact_sheet = build_fact_sheet(facts, baseline)
    combined = f"{fact_sheet}\n\n---\n\n{g_block}"

    print(f"Generating granular review for {match_id} ({our_champ} vs {enemy_champ})...")
    review, section_keys = generate_review_text(facts, combined, verbose=True)

    # Tripwire: standard fact times + this game's granular-window times
    fact_times = collect_fact_times(facts) | set(round(t) for t in g_times)
    warnings = []
    for m in re.finditer(r"\b(\d{1,2}):([0-5]\d)\b", review):
        t = int(m.group(1)) * 60 + int(m.group(2))
        if t > facts["duration_s"]:
            warnings.append(f"{m.group(0)} is beyond game duration {facts['duration_clock']}")
        elif fact_times and min(abs(t - ft) for ft in fact_times) > 90:
            warnings.append(f"{m.group(0)} does not match any extracted or granular fact "
                            f"- possibly hallucinated")

    our_puuid = get_our_puuid(match, facts)
    if our_puuid:
        out_path = review_out_path(match, our_puuid)[:-3] + "_granular.md"
    else:
        out_path = os.path.join(config.REVIEWS_DIR, "_unsorted", f"{match_id}_granular.md")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Granular Game Review: {match_id}\n\n{review}\n\n---\n\n"
                f"<details><summary>Fact sheet used (incl. granular movement data)</summary>\n\n"
                f"{combined}\n</details>\n")

    print(f"  saved -> {out_path}")
    if warnings:
        print("  TIMESTAMP WARNINGS: " + "; ".join(warnings))
    else:
        print("  timestamp check clean")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Coaching review augmented with map_state granular data")
    ap.add_argument("--match", help="Single match id")
    ap.add_argument("--riot-id", help='Fetch this account\'s games, e.g. "Name#TAG"')
    ap.add_argument("--last", type=int, help="Review the N most recent ranked games (with --riot-id)")
    ap.add_argument("--tick", type=int, default=15, help="Reconstruction tick seconds (e.g. 10)")
    args = ap.parse_args()

    client = None
    puuid = None
    if args.riot_id:
        store.ensure_dirs()
        client = RiotClient()
        puuid = resolve_puuid(client, args.riot_id)

    if args.match:
        match_ids = [args.match]
    elif args.riot_id:
        match_ids = client.match_ids(puuid, queue=RANKED_SOLO_QUEUE, count=args.last or 1)
    else:
        ap.error("need --match or --riot-id")

    saved = []
    for i, mid in enumerate(match_ids, 1):
        print(f"\n===== [{i}/{len(match_ids)}] {mid} =====")
        out = granular_review(mid, args.tick, client=client, puuid=puuid)
        if out:
            saved.append(out)

    print(f"\nDone. {len(saved)} granular review(s):")
    for s in saved:
        print(f"  {s}")


if __name__ == "__main__":
    main()
