"""
Account recap: review your last N ranked games as ONE body of evidence -
recurring patterns instead of single-game mistakes, plus retrospective draft
analysis of the most recent games.

This is the prototype of the "review my last N losses and tell me why I keep
losing" product feature.

Usage:
    python scripts/account_recap.py --riot-id "Name#TAG"                    # last 20 games
    python scripts/account_recap.py --riot-id "Name#TAG" --games 10 --drafts 3
    python scripts/account_recap.py --riot-id "Name#TAG" --losses-only
    python scripts/account_recap.py --riot-id "Name#TAG" --facts-only      # no LLM calls
    python scripts/account_recap.py --puuid XXX --offline                  # cached matches only

LLM cost: 1 synthesis call + one call per draft analysis (default 5) = 6 calls.
Facts extraction is deterministic and free.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from riot.client import RiotClient
from analysis.timeline_facts import extract_facts
from analysis.narrative import build_fact_sheet
from review_game import (RANKED_SOLO_QUEUE, collect_fact_times, fetch_game,
                         load_baseline, resolve_puuid)

MIN_GAME_S = 300  # skip remakes/dodges

RECAP_SYSTEM_PROMPT = """You are an expert League of Legends jungle coach doing a
MULTI-GAME performance review for a Diamond+ player. You are given fact sheets
for their recent ranked games (deterministic data extracted from the Riot API,
with Master+ baseline comparisons where available).

Your job is to find PATTERNS ACROSS GAMES, not to re-review individual games.

OUTPUT FORMAT (markdown):

## The Verdict
One paragraph: the single biggest thing holding this player back, stated plainly.

## What You Are Doing Well
Bullet points. Each must cite at least one match id and a number from the sheets.
Real strengths only - no participation trophies.

## Recurring Problems (ranked by how many games they cost)
For each problem (max 5):
- **The pattern:** what keeps happening
- **The evidence:** match ids + timestamps/numbers from the fact sheets (a pattern
  needs evidence from at least 2 games; if it appears once, it is not a pattern)
- **Why it loses games:** the causal chain
- **The fix:** one concrete, drillable instruction

## Focus Plan for the Next 20 Games
Maximum 3 drills. Each must be measurable by the player themselves
(e.g. "full clear before 3:45 in every game" not "path better").

## Champion Pool Notes
Per champion played: one-line observation and whether the sample supports playing
it more or less. Use the win/loss records from PLAYER SUMMARY **verbatim** - do
NOT count games yourself.

RULES:
- Every claim must be traceable to the fact sheets. Cite games constantly using
  their labels, e.g. "G7 (Diana win)" - readers should never need to decode a
  raw match id. Use the raw match id only if asked.
- Aggregate numbers (totals, per-champion records) come from PLAYER SUMMARY;
  per-game numbers come from that game's fact sheet - never invent or recount.
- Deaths/objectives/gold facts are exact; clear paths, gank detection and
  fight-numbers are labeled approximations - treat them as such.
- If HOUSE RULES are present they override everything else.
- For meta claims not grounded in the provided knowledge, append
  "(general reasoning, not from your coaches)".
"""

DRAFT_NOTE = ("Retrospective: this draft was from a real game the player already played "
              "(result: {result}). Analyze the draft as if pre-game - win conditions, "
              "jungle game plan, key threats - so the player can compare the plan "
              "against what actually happened.")


def cached_match_ids_for(puuid: str) -> list[str]:
    """Newest-first match ids on disk that include this player (offline mode)."""
    found = []
    for name in os.listdir(config.MATCHES_DIR):
        if not name.endswith(".json.gz") and not name.endswith(".json"):
            continue
        match_id = name.split(".json")[0]
        match = store.load_match(match_id)
        if match is None:
            continue
        info = match.get("info", {})
        if any(p.get("puuid") == puuid for p in info.get("participants", [])):
            found.append((info.get("gameEndTimestamp", 0), match_id))
    return [m for _, m in sorted(found, reverse=True)]


def check_match_ids(recap: str, analyzed: list[str]) -> list[str]:
    """Grounding tripwire: every match id cited must be one we actually analyzed."""
    cited = set(re.findall(r"\b[A-Z]+1_\d+\b", recap))
    return sorted(cited - set(analyzed))


def check_recap_timestamps(recap: str, games: list[dict]) -> list[str]:
    """Per-game tripwire: on any line citing exactly one game (by G-label or
    match id), every mm:ss must be inside that game's duration and within 90s
    of one of its facts."""
    by_ref = {g["match_id"]: g["facts"] for g in games}
    by_ref.update({f"G{i}": g["facts"] for i, g in enumerate(games, 1)})
    warnings = []
    for line in recap.splitlines():
        refs = set(re.findall(r"\b[A-Z]+1_\d+\b", line)) | set(re.findall(r"\bG\d+\b", line))
        if len(refs) != 1:
            continue  # 0 refs: can't attribute; 2+: ambiguous - skip
        match_id = refs.pop()
        facts = by_ref.get(match_id)
        if facts is None:
            continue  # phantom id - reported by check_match_ids
        fact_times = collect_fact_times(facts)
        for m in re.finditer(r"\b(\d{1,2}):([0-5]\d)\b", line):
            t = int(m.group(1)) * 60 + int(m.group(2))
            if t > facts["duration_s"]:
                warnings.append(f"{match_id}: {m.group(0)} is beyond game duration "
                                f"{facts['duration_clock']}")
            elif fact_times and min(abs(t - ft) for ft in fact_times) > 90:
                warnings.append(f"{match_id}: {m.group(0)} matches no extracted fact "
                                f"- possibly hallucinated")
    return warnings


def main():
    parser = argparse.ArgumentParser(description="Multi-game pattern review + draft recaps")
    parser.add_argument("--riot-id", help='Riot ID, e.g. "Name#TAG"')
    parser.add_argument("--puuid", help="Skip riot-id lookup (needed with --offline)")
    parser.add_argument("--games", type=int, default=20, help="How many recent ranked games")
    parser.add_argument("--drafts", type=int, default=5,
                        help="Retrospective draft analyses for the N most recent games (0 = skip)")
    parser.add_argument("--losses-only", action="store_true", help="Only analyze losses")
    parser.add_argument("--facts-only", action="store_true",
                        help="Collect facts + games table, skip all LLM calls")
    parser.add_argument("--offline", action="store_true",
                        help="Use only matches already on disk (no Riot API)")
    parser.add_argument("--model", help="Override LLM model (drafts + synthesis)")
    args = parser.parse_args()

    store.ensure_dirs()
    client = None if args.offline else RiotClient()

    if args.puuid:
        puuid = args.puuid
    elif args.riot_id and not args.offline:
        puuid = resolve_puuid(client, args.riot_id)
    else:
        print("Need --riot-id (online) or --puuid (offline).")
        sys.exit(1)
    label = args.riot_id or puuid[:12]

    if args.offline:
        match_ids = cached_match_ids_for(puuid)[: args.games]
        print(f"Offline mode: {len(match_ids)} cached games found for {label}")
    else:
        match_ids = client.match_ids(puuid, queue=RANKED_SOLO_QUEUE, count=args.games)
    if not match_ids:
        print("No games found.")
        sys.exit(1)

    # --- Deterministic pass: facts + fact sheets per game ---
    games = []  # {match_id, facts, sheet}
    for i, match_id in enumerate(match_ids, 1):
        print(f"[{i}/{len(match_ids)}] {match_id}...", end=" ")
        try:
            if args.offline:
                match, timeline = store.load_match(match_id), store.load_timeline(match_id)
                if match is None or timeline is None:
                    print("missing match/timeline on disk, skipping")
                    continue
            else:
                match, timeline = fetch_game(client, match_id)
            facts = extract_facts(match, timeline, puuid)
        except Exception as e:
            print(f"FAILED ({e}), skipping")
            continue

        os.makedirs(config.FACTS_DIR, exist_ok=True)
        with open(os.path.join(config.FACTS_DIR, f"{match_id}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(facts, f, indent=2, ensure_ascii=False)

        if facts["duration_s"] < MIN_GAME_S:
            print(f"{facts['champion']} {facts['duration_clock']} - remake, skipped")
            continue
        if args.losses_only and facts["win"]:
            print(f"{facts['champion']} WIN - skipped (losses only)")
            continue
        sheet = build_fact_sheet(facts, load_baseline(facts["champion"]))
        games.append({"match_id": match_id, "facts": facts, "sheet": sheet})
        print(f"{facts['champion']} {facts['our_role']} "
              f"{'WIN' if facts['win'] else 'LOSS'} {facts['kda']}")

    if not games:
        print("Nothing to analyze after filtering.")
        sys.exit(1)

    # --- Deterministic aggregates (the LLM must never count games itself) ---
    wins = sum(1 for g in games if g["facts"]["win"])
    per_champ: dict[str, list[int]] = {}
    for g in games:
        rec = per_champ.setdefault(g["facts"]["champion"], [0, 0])
        rec[0 if g["facts"]["win"] else 1] += 1
    champ_lines = [f"- {c}: {w + l} games ({w}W-{l}L)"
                   for c, (w, l) in sorted(per_champ.items(), key=lambda x: -sum(x[1]))]
    player_summary = (f"# PLAYER SUMMARY (deterministic - use VERBATIM, do not recount)\n"
                      f"- Total: {len(games)} games, {wins}W {len(games) - wins}L\n"
                      + "\n".join(champ_lines))

    table = "| G# | Champion | Role | Result | KDA | Length | Match |\n|---|---|---|---|---|---|---|\n"
    for i, g in enumerate(games, 1):
        f_ = g["facts"]
        table += (f"| G{i} | {f_['champion']} | {f_['our_role']} | "
                  f"{'WIN' if f_['win'] else 'LOSS'} | {f_['kda']} | {f_['duration_clock']} | "
                  f"{g['match_id']} |\n")

    # Recaps span days, so they live at the account-folder root
    # (per-game reviews go in data/reviews/<Account>/<YYYY-MM-DD>/)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", label).strip("_")
    out_dir = os.path.join(config.REVIEWS_DIR, safe)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"account_recap_{date.today().isoformat()}.md")

    champ_records = " · ".join(f"{c} {w}W-{l}L"
                               for c, (w, l) in sorted(per_champ.items(), key=lambda x: -sum(x[1])))
    header = (f"# Account Recap - {label}\n\n"
              f"*{len(games)} ranked games analyzed on {date.today().isoformat()} - "
              f"{wins}W {len(games) - wins}L ({champ_records})*\n\n{table}\n")

    if args.facts_only:
        Path(out_path).write_text(header + "\n*(facts-only run - no LLM analysis)*\n",
                                  encoding="utf-8")
        print(f"\nGames table saved to {out_path}")
        return

    # --- LLM pass 1: retrospective draft analyses ---
    draft_cards = []
    if args.drafts > 0:
        from app.pregame import run_pregame
        for g in games[: args.drafts]:
            f_ = g["facts"]
            ours = [c["champion"] for c in f_["comps"]["ours"]]
            enemy = [c["champion"] for c in f_["comps"]["enemy"]]
            result = "WIN" if f_["win"] else "LOSS"
            print(f"Draft analysis {g['match_id']} ({f_['champion']}, {result})...")
            try:
                card = run_pregame(ours, enemy, DRAFT_NOTE.format(result=result),
                                   model=args.model)
                draft_cards.append((g["match_id"], f_, card))
            except Exception as e:
                print(f"  FAILED: {e}")
            time.sleep(10)  # free-tier RPM headroom

    # --- LLM pass 2: cross-game synthesis ---
    from app.llm_client import generate_text, load_house_rules
    house_rules = load_house_rules()
    house_block = (f"# HOUSE RULES (override everything)\n\n{house_rules}\n\n---\n\n"
                   if house_rules else "")
    sheets_block = player_summary + "\n\n=====\n\n"
    sheets_block += "\n\n=====\n\n".join(
        f"GAME G{i} - {g['facts']['champion']} "
        f"{'WIN' if g['facts']['win'] else 'LOSS'} {g['facts']['kda']} "
        f"({g['facts']['duration_clock']}) [match id: {g['match_id']}]\n\n{g['sheet']}"
        for i, g in enumerate(games, 1))
    print(f"\nSynthesizing recap across {len(games)} games (1 LLM call, "
          f"~{len(sheets_block) // 4} tokens in)...")
    recap = generate_text(
        f"{house_block}{sheets_block}\n\n---\n\nWrite the multi-game recap now.",
        system=RECAP_SYSTEM_PROMPT, temperature=0.3, max_tokens=8000, model=args.model)

    phantom = check_match_ids(recap, [g["match_id"] for g in games])
    ts_warnings = check_recap_timestamps(recap, games)

    doc = header + "\n---\n\n" + recap + "\n"
    if phantom:
        doc += ("\n> **Grounding warning:** these cited match ids were NOT in the "
                f"analyzed set: {', '.join(phantom)}\n")
    if ts_warnings:
        doc += ("\n> **Timestamp warnings (possible hallucinations):**\n"
                + "".join(f"> - {w}\n" for w in ts_warnings))
    if draft_cards:
        doc += "\n---\n\n# Retrospective Draft Analyses\n"
        for match_id, f_, card in draft_cards:
            doc += (f"\n## {match_id} - {f_['champion']} "
                    f"({'WIN' if f_['win'] else 'LOSS'}, {f_['kda']})\n\n{card}\n")

    Path(out_path).write_text(doc, encoding="utf-8")
    print("\n" + "=" * 70 + "\n")
    print(recap)
    print("\n" + "=" * 70)
    if phantom:
        print(f"\nGROUNDING WARNING - phantom match ids cited: {', '.join(phantom)}")
    if ts_warnings:
        print(f"\nTIMESTAMP WARNINGS ({len(ts_warnings)}):")
        for w in ts_warnings:
            print(f"  - {w}")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
