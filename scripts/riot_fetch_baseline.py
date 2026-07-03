"""
Discover and download Master+ Ekko-jungle matches (with timelines) from EUW
to build the baseline dataset.

Strategy (request-efficient, since Ekko jungle is rare at Master+):
  1. Pull Challenger/GM/Master ladder entries (3 requests).
  2. For each player (best first), check top-3 champion mastery (1 req) and
     skip anyone without Ekko in their top 3.
  3. For Ekko players: pull recent ranked match IDs, fetch matches, keep games
     where they played Ekko JUNGLE, and download the timeline for keepers.

Progress persists to data/riot/discovery_state.json after every player, so an
expired dev key (24h) or Ctrl+C loses nothing - just rerun.

Usage:
    python scripts/riot_fetch_baseline.py                    # fetch until target (default 25)
    python scripts/riot_fetch_baseline.py --target 30
    python scripts/riot_fetch_baseline.py --status           # show progress, no requests
    python scripts/riot_fetch_baseline.py --seed-riot-ids "Name1#TAG,Name2#TAG"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from riot.client import RiotClient, DevKeyExpired

EKKO_CHAMPION_ID = 245
RANKED_SOLO_QUEUE = 420
MIN_GAME_DURATION_S = 900  # skip remakes / very short games
MATCHES_PER_PLAYER = 20    # recent ranked games to inspect per Ekko player


def find_ekko_jungle_participant(match: dict) -> dict | None:
    """Return the participant dict if someone played Ekko jungle in this match."""
    info = match.get("info", {})
    if info.get("gameDuration", 0) < MIN_GAME_DURATION_S:
        return None
    for p in info.get("participants", []):
        if p.get("championName") == "Ekko" and p.get("teamPosition") == "JUNGLE":
            return p
    return None


def make_index_entry(match: dict, participant: dict, tier: str, source: str) -> dict:
    info = match["info"]
    return {
        "match_id": match["metadata"]["matchId"],
        "game_version": info.get("gameVersion", ""),
        "queue_id": info.get("queueId"),
        "game_creation": info.get("gameCreation"),
        "game_duration_s": info.get("gameDuration"),
        "ekko_puuid": participant["puuid"],
        "ekko_participant_id": participant["participantId"],
        "ekko_team_id": participant["teamId"],
        "tier": tier,
        "win": participant["win"],
        "has_timeline": True,
        "source": source,
    }


def process_player(client: RiotClient, puuid: str, tier: str, state: dict,
                   target: int, source: str) -> int:
    """Inspect one player's recent games; download Ekko-jungle keepers.
    Returns number of new baseline games found."""
    found = 0
    checked = set(state["checked_match_ids"])
    known = {e["match_id"] for e in store.load_index()}

    match_ids = client.match_ids(puuid, queue=RANKED_SOLO_QUEUE, count=MATCHES_PER_PLAYER)
    for match_id in match_ids:
        if match_id in checked or match_id in known:
            continue
        state["checked_match_ids"].append(match_id)

        match = client.match(match_id)
        if match is None:
            continue

        participant = find_ekko_jungle_participant(match)
        if participant is None:
            continue

        timeline = client.timeline(match_id)
        if timeline is None or len(timeline.get("info", {}).get("frames", [])) <= 10:
            print(f"    {match_id}: Ekko jungle found but timeline missing/short, skipping")
            continue

        store.save_match(match_id, match)
        store.save_timeline(match_id, timeline)
        store.add_index_entry(make_index_entry(match, participant, tier, source))
        found += 1
        total = len(store.load_index())
        print(f"    KEEPER {match_id} (win={participant['win']}, "
              f"{match['info']['gameDuration'] // 60}min) - total {total}")
        if total >= target:
            break

    return found


def run_seeds(client: RiotClient, riot_ids: list[str], state: dict, target: int):
    """Process manually seeded players (e.g. from League of Graphs Ekko leaderboard)."""
    for riot_id in riot_ids:
        if len(store.load_index()) >= target:
            break
        if "#" not in riot_id:
            print(f"  Skipping invalid Riot ID (need Name#TAG): {riot_id}")
            continue
        name, tag = riot_id.split("#", 1)
        print(f"  Seed player: {riot_id}")
        account = client.account_by_riot_id(name.strip(), tag.strip())
        if account is None:
            print("    not found")
            continue
        puuid = account["puuid"]
        process_player(client, puuid, tier="SEED", state=state, target=target, source="seed")
        if puuid not in state["scanned_puuids"]:
            state["scanned_puuids"].append(puuid)
        store.save_discovery_state(state)


def run_ladder_scan(client: RiotClient, state: dict, target: int, tiers: tuple[str, ...]):
    print("Fetching Master+ ladders...")
    entries = client.master_plus_entries(tiers=tiers)
    print(f"  {len(entries)} players on {'/'.join(tiers)} ladders\n")

    scanned = set(state["scanned_puuids"])

    for i, entry in enumerate(entries):
        if len(store.load_index()) >= target:
            break
        puuid = entry.get("puuid")
        if not puuid or puuid in scanned:
            continue

        mastery = client.top_mastery(puuid, count=3)
        has_ekko = any(m.get("championId") == EKKO_CHAMPION_ID for m in mastery)

        if has_ekko:
            print(f"  [{entry['tier']} #{i}] Ekko player found, checking recent games...")
            process_player(client, puuid, entry["tier"], state, target, source="ladder_scan")

        scanned.add(puuid)
        state["scanned_puuids"].append(puuid)
        store.save_discovery_state(state)

        if (i + 1) % 50 == 0:
            print(f"  ...scanned {len(scanned)} players, "
                  f"{len(store.load_index())}/{target} games found")


def show_status():
    state = store.load_discovery_state()
    index = store.load_index()
    print(f"Baseline games found : {len(index)}")
    print(f"Players scanned      : {len(state['scanned_puuids'])}")
    print(f"Matches checked      : {len(state['checked_match_ids'])}")
    if index:
        wins = sum(1 for e in index if e["win"])
        by_tier = {}
        for e in index:
            by_tier[e["tier"]] = by_tier.get(e["tier"], 0) + 1
        versions = sorted({".".join(e["game_version"].split(".")[:2]) for e in index})
        print(f"Win rate in dataset  : {wins}/{len(index)}")
        print(f"By tier              : {by_tier}")
        print(f"Patches              : {versions}")


def main():
    parser = argparse.ArgumentParser(description="Fetch Master+ Ekko-jungle baseline games from EUW")
    parser.add_argument("--target", type=int, default=25, help="Number of games to collect (default: 25)")
    parser.add_argument("--tiers", default="challenger,grandmaster,master",
                        help="Comma-separated tiers to scan, best first")
    parser.add_argument("--seed-riot-ids", default="",
                        help='Comma-separated "Name#TAG" players to check directly')
    parser.add_argument("--status", action="store_true", help="Show progress and exit (no API calls)")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    store.ensure_dirs()
    state = store.load_discovery_state()
    client = RiotClient()

    print(f"Target: {args.target} Master+ Ekko-jungle games "
          f"({config.RIOT_PLATFORM}/{config.RIOT_REGION})")
    print(f"Resuming: {len(state['scanned_puuids'])} players already scanned, "
          f"{len(store.load_index())} games already found\n")

    try:
        if args.seed_riot_ids:
            run_seeds(client, args.seed_riot_ids.split(","), state, args.target)
        else:
            tiers = tuple(t.strip().upper() for t in args.tiers.split(","))
            run_ladder_scan(client, state, args.target, tiers)
    except DevKeyExpired as e:
        store.save_discovery_state(state)
        print(f"\n{e}")
        sys.exit(1)
    except KeyboardInterrupt:
        store.save_discovery_state(state)
        print("\nInterrupted - progress saved.")
        sys.exit(1)

    store.save_discovery_state(state)
    print()
    show_status()
    total = len(store.load_index())
    if total >= args.target:
        print(f"\nDone - {total} games. Next: python scripts/riot_build_baseline.py")
    else:
        print(f"\nLadder scan exhausted at {total}/{args.target} games. "
              f"Try --seed-riot-ids with players from a site like League of Graphs "
              f"(Ekko EUW leaderboard).")


if __name__ == "__main__":
    main()
