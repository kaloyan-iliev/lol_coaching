"""
Discover and download Master+ jungle games (with timelines) from EUW to grow
the games knowledge base.

Every fetched match yields up to TWO jungler-game entries (one per team), so
the default mode keeps ANY ranked match - ~2 jungler-games per ~2 API calls.
Optionally filter discovery to one champion (mastery-based pre-filter).

Progress persists to data/riot/discovery_state.json after every player, so an
expired dev key (24h) or Ctrl+C loses nothing - just rerun.

Usage:
    python scripts/riot_fetch_baseline.py --target 150          # any jungler-games
    python scripts/riot_fetch_baseline.py --target 75 --champion Ekko
    python scripts/riot_fetch_baseline.py --status              # progress, no requests
    python scripts/riot_fetch_baseline.py --seed-riot-ids "Name1#TAG,Name2#TAG"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from riot.client import RiotClient, DevKeyExpired

CHAMPION_IDS = {"Ekko": 245}  # extend as needed for --champion mastery filtering
RANKED_SOLO_QUEUE = 420
MIN_GAME_DURATION_S = 900  # skip remakes / very short games
MATCHES_PER_PLAYER = 20    # recent ranked games to inspect per player


def find_junglers(match: dict, champion: str | None = None) -> list[dict]:
    """All JUNGLE participants in a valid match (optionally only one champion)."""
    info = match.get("info", {})
    if info.get("gameDuration", 0) < MIN_GAME_DURATION_S:
        return []
    junglers = [p for p in info.get("participants", [])
                if p.get("teamPosition") == "JUNGLE"]
    if champion:
        junglers = [p for p in junglers if p.get("championName") == champion]
    return junglers


def make_index_entry(match: dict, participant: dict, tier: str, source: str) -> dict:
    info = match["info"]
    return {
        "match_id": match["metadata"]["matchId"],
        "game_version": info.get("gameVersion", ""),
        "queue_id": info.get("queueId"),
        "game_creation": info.get("gameCreation"),
        "game_duration_s": info.get("gameDuration"),
        "puuid": participant["puuid"],
        "champion": participant["championName"],
        "participant_id": participant["participantId"],
        "team_id": participant["teamId"],
        "tier": tier,
        "win": participant["win"],
        "has_timeline": True,
        "source": source,
    }


def count_entries() -> int:
    return len(store.load_index())


def process_player(client: RiotClient, puuid: str, tier: str, state: dict,
                   target: int, source: str, champion: str | None) -> int:
    """Inspect one player's recent games; index all jungler-games found."""
    found = 0
    checked = set(state["checked_match_ids"])

    match_ids = client.match_ids(puuid, queue=RANKED_SOLO_QUEUE, count=MATCHES_PER_PLAYER)
    for match_id in match_ids:
        if match_id in checked:
            continue
        state["checked_match_ids"].append(match_id)

        match = client.match(match_id)
        if match is None:
            continue

        junglers = find_junglers(match, champion)
        if not junglers:
            continue

        timeline = client.timeline(match_id)
        if timeline is None or len(timeline.get("info", {}).get("frames", [])) <= 10:
            print(f"    {match_id}: timeline missing/short, skipping")
            continue

        store.save_match(match_id, match)
        store.save_timeline(match_id, timeline)
        # Index EVERY jungler in the match (not just the filtered one) - a
        # champion-filtered fetch still contributes the opponent's game
        for p in find_junglers(match):
            store.add_index_entry(make_index_entry(match, p, tier, source))
            found += 1

        total = count_entries()
        champs = "+".join(p["championName"] for p in find_junglers(match))
        print(f"    KEEPER {match_id} ({champs}, "
              f"{match['info']['gameDuration'] // 60}min) - total {total}")
        if total >= target:
            break

    return found


def run_seeds(client: RiotClient, riot_ids: list[str], state: dict, target: int,
              champion: str | None):
    """Process manually seeded players (e.g. from League of Graphs leaderboards)."""
    for riot_id in riot_ids:
        if count_entries() >= target:
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
        process_player(client, puuid, tier="SEED", state=state, target=target,
                       source="seed", champion=champion)
        if puuid not in state["scanned_puuids"]:
            state["scanned_puuids"].append(puuid)
        store.save_discovery_state(state)


def run_ladder_scan(client: RiotClient, state: dict, target: int,
                    tiers: tuple[str, ...], champion: str | None):
    print("Fetching Master+ ladders...")
    entries = client.master_plus_entries(tiers=tiers)
    print(f"  {len(entries)} players on {'/'.join(tiers)} ladders\n")

    scanned = set(state["scanned_puuids"])
    champion_id = CHAMPION_IDS.get(champion) if champion else None

    for i, entry in enumerate(entries):
        if count_entries() >= target:
            break
        puuid = entry.get("puuid")
        if not puuid or puuid in scanned:
            continue

        eligible = True
        if champion_id:
            # Champion mode: 1 mastery call filters ~95% of players
            mastery = client.top_mastery(puuid, count=3)
            eligible = any(m.get("championId") == champion_id for m in mastery)
            if eligible:
                print(f"  [{entry['tier']} #{i}] {champion} player found, checking games...")

        if eligible:
            process_player(client, puuid, entry["tier"], state, target,
                           source="ladder_scan", champion=champion)

        scanned.add(puuid)
        state["scanned_puuids"].append(puuid)
        store.save_discovery_state(state)

        if (i + 1) % 50 == 0:
            print(f"  ...scanned {len(scanned)} players, "
                  f"{count_entries()}/{target} jungler-games indexed")


def show_status():
    state = store.load_discovery_state()
    index = store.load_index()
    print(f"Jungler-games indexed : {len(index)}")
    print(f"Unique matches        : {len({e['match_id'] for e in index})}")
    print(f"Players scanned       : {len(state['scanned_puuids'])}")
    print(f"Matches checked       : {len(state['checked_match_ids'])}")
    if index:
        by_champ = {}
        for e in index:
            by_champ[e.get("champion", "?")] = by_champ.get(e.get("champion", "?"), 0) + 1
        top = sorted(by_champ.items(), key=lambda kv: -kv[1])[:15]
        versions = sorted({".".join(e["game_version"].split(".")[:2]) for e in index})
        print(f"Top champions         : {', '.join(f'{c} x{n}' for c, n in top)}")
        print(f"Patches               : {versions}")


def main():
    parser = argparse.ArgumentParser(description="Grow the Master+ jungler-games knowledge base (EUW)")
    parser.add_argument("--target", type=int, default=150,
                        help="Total jungler-game entries to reach (default: 150)")
    parser.add_argument("--champion", default=None,
                        help="Only fetch matches where this champion jungles (e.g. Ekko)")
    parser.add_argument("--tiers", default="challenger,grandmaster,master",
                        help="Comma-separated tiers to scan, best first")
    parser.add_argument("--seed-riot-ids", default="",
                        help='Comma-separated "Name#TAG" players to check directly')
    parser.add_argument("--status", action="store_true", help="Show progress and exit (no API calls)")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.champion and args.champion not in CHAMPION_IDS:
        print(f"No champion ID known for '{args.champion}'. Add it to CHAMPION_IDS "
              f"(see Data Dragon champion.json) or run without --champion.")
        sys.exit(1)

    store.ensure_dirs()
    state = store.load_discovery_state()
    client = RiotClient()

    mode = f"{args.champion}-jungle games" if args.champion else "jungler-games (any champion)"
    print(f"Target: {args.target} {mode} ({config.RIOT_PLATFORM}/{config.RIOT_REGION})")
    print(f"Resuming: {len(state['scanned_puuids'])} players already scanned, "
          f"{count_entries()} entries already indexed\n")

    try:
        if args.seed_riot_ids:
            run_seeds(client, args.seed_riot_ids.split(","), state, args.target, args.champion)
        else:
            tiers = tuple(t.strip().upper() for t in args.tiers.split(","))
            run_ladder_scan(client, state, args.target, tiers, args.champion)
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
    if count_entries() >= args.target:
        print(f"\nDone. Next: python scripts/riot_build_baseline.py")


if __name__ == "__main__":
    main()
