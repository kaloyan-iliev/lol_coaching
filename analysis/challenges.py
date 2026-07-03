"""
Curated subset of Riot's precomputed per-player analytics
(match participants[].challenges) - exact post-game values that replace or
validate our timeline heuristics. Single source of truth for facts, baseline,
and the fact sheet.
"""

# fact key (snake_case) -> Riot challenges key (camelCase)
CHALLENGE_FIELDS = {
    "initial_buff_count": "initialBuffCount",
    "initial_crab_count": "initialCrabCount",
    "jungle_cs_before_10m": "jungleCsBefore10Minutes",
    "more_enemy_jungle_than_opponent": "moreEnemyJungleThanOpponent",
    "kills_on_laners_early_as_jungler": "killsOnLanersEarlyJungleAsJungler",
    "jungler_kills_early_jungle": "junglerKillsEarlyJungle",
    "takedowns_before_jungle_minions": "takedownsBeforeJungleMinionSpawn",
    "epic_monster_steals": "epicMonsterSteals",
    "epic_monster_kills_within_30s_of_spawn": "epicMonsterKillsWithin30SecondsOfSpawn",
    "earliest_dragon_takedown_s": "earliestDragonTakedown",
    "scuttle_crab_kills": "scuttleCrabKills",
    "buffs_stolen": "buffsStolen",
    "vision_score_per_minute": "visionScorePerMinute",
    "control_wards_placed": "controlWardsPlaced",
    "ward_takedowns_before_20m": "wardTakedownsBefore20M",
    "danced_with_rift_herald": "dancedWithRiftHerald",
}

# Subset worth baseline quartiles (numeric, meaningful distributions)
BASELINE_CHALLENGE_KEYS = [
    "jungle_cs_before_10m",
    "more_enemy_jungle_than_opponent",
    "initial_crab_count",
    "scuttle_crab_kills",
    "vision_score_per_minute",
    "control_wards_placed",
    "ward_takedowns_before_20m",
    "kills_on_laners_early_as_jungler",
    "epic_monster_kills_within_30s_of_spawn",
    "earliest_dragon_takedown_s",
]


def extract_challenges(participant: dict) -> dict:
    """Pull the curated challenge values for one participant (None if missing)."""
    ch = participant.get("challenges", {}) or {}
    out = {}
    for fact_key, riot_key in CHALLENGE_FIELDS.items():
        val = ch.get(riot_key)
        if isinstance(val, float):
            val = round(val, 2)
        out[fact_key] = val
    return out
