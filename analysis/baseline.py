"""
Aggregate per-game facts from the Master+ Ekko dataset into baseline stats
(median / p25 / p75) used for comparison in game reviews.
"""

import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from analysis.challenges import BASELINE_CHALLENGE_KEYS


def _quartiles(values: list[float]) -> dict | None:
    values = [v for v in values if v is not None]
    if len(values) < 3:
        return None
    values = sorted(values)
    return {
        "p25": round(statistics.quantiles(values, n=4)[0], 1),
        "median": round(statistics.median(values), 1),
        "p75": round(statistics.quantiles(values, n=4)[2], 1),
        "n": len(values),
    }


def aggregate_baseline(all_facts: list[dict], champion: str = "Ekko") -> dict:
    n = len(all_facts)

    def collect(fn):
        return [fn(f) for f in all_facts]

    first_objective_participation = []
    for f in all_facts:
        firsts = {}
        for obj in f["objectives"]:
            firsts.setdefault(obj["type"], obj)
        for obj in firsts.values():
            first_objective_participation.append(1 if (obj["team"] == "ally" and obj["we_nearby"]) else 0)

    baseline = {
        "champion": champion,
        "role": "JUNGLE",
        "n_games": n,
        "patches": sorted({f["game_version"] for f in all_facts}),
        "win_rate": round(sum(1 for f in all_facts if f["win"]) / n, 2) if n else None,
        "cs_at_10": _quartiles(collect(lambda f: f["economy"]["cs_at_10"])),
        "cs_at_15": _quartiles(collect(lambda f: f["economy"]["cs_at_15"])),
        "first_gank_t_s": _quartiles(collect(lambda f: f["economy"]["first_gank_t"])),
        "first_reset_s": _quartiles(collect(lambda f: f["economy"]["first_reset_s"])),
        "full_clear_end_s": _quartiles(collect(lambda f: f["clear"]["full_clear_end_s"])),
        "deaths_before_14min": _quartiles(collect(
            lambda f: sum(1 for d in f["deaths"] if d["t"] < 840))),
        "deaths_total": _quartiles(collect(lambda f: len(f["deaths"]))),
        "gank_involvements": _quartiles(collect(lambda f: len(f["ganks"]))),
        "counter_jungle_episodes": _quartiles(collect(lambda f: len(f["counter_jungle"]))),
        "wards_placed": _quartiles(collect(lambda f: f["vision"]["wards_placed"])),
        "control_wards": _quartiles(collect(lambda f: f["vision"]["control_wards"])),
        "wards_killed": _quartiles(collect(lambda f: f["vision"]["wards_killed"])),
        "first_objective_participation_rate": (
            round(sum(first_objective_participation) / len(first_objective_participation), 2)
            if first_objective_participation else None),
        "challenges": {
            key: _quartiles(collect(
                lambda f, k=key: ((f.get("challenges") or {}).get("ours") or {}).get(k)))
            for key in BASELINE_CHALLENGE_KEYS
        },
        "note": (f"Master+ EUW {champion} jungle. Quartiles over small n - "
                 f"treat as reference range, not law."
                 + (" GENERIC baseline across ALL jungle champions - clear-speed and "
                    "CS metrics vary by champion, treat those loosely."
                    if champion == "_GENERIC" else "")),
    }
    return baseline
