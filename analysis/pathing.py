"""
Reconstruct a jungler's clear path from match-v5 timeline frames.

Positions come in 60s snapshots and the timeline has no per-camp kill events,
so this is an approximation: camps are inferred from jungleMinionsKilled
deltas matched against the camps nearest to the player's sampled positions.
Every inferred step carries a confidence label - downstream prompts must not
present "medium"/"low" steps as certain facts.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from analysis.jungle_camps import (
    CAMPS, SCUTTLE, CAMP_MONSTER_COUNTS, CAMP_RADIUS, dist, nearest_camp,
    side_of_team,
)


def _frame_positions(timeline: dict, participant_id: int) -> list[dict]:
    """Per-frame snapshots for one participant: t (s), position, jungle cs, level, gold, xp."""
    snapshots = []
    for frame in timeline["info"]["frames"]:
        pf = frame["participantFrames"].get(str(participant_id))
        if pf is None:
            continue
        pos = pf.get("position") or {}
        snapshots.append({
            "t": frame["timestamp"] // 1000,
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "jungle_cs": pf.get("jungleMinionsKilled", 0),
            "lane_cs": pf.get("minionsKilled", 0),
            "level": pf.get("level", 1),
            "gold": pf.get("totalGold", 0),
            "xp": pf.get("xp", 0),
        })
    return snapshots


def _camps_near(pos: tuple[float, float], max_dist: float = 2600) -> list[tuple[str, str, float]]:
    """All camps within max_dist of a position, nearest first."""
    found = []
    for side, camps in CAMPS.items():
        for name, cpos in camps.items():
            d = dist(pos, cpos)
            if d <= max_dist:
                found.append((side, name, d))
    for river, cpos in SCUTTLE.items():
        d = dist(pos, cpos)
        if d <= max_dist:
            found.append((river, "scuttle", d))
    return sorted(found, key=lambda c: c[2])


def reconstruct_clear(timeline: dict, participant_id: int, team_id: int,
                      until_s: int = 480) -> dict:
    """
    Infer the early clear sequence (default: first 8 minutes).

    Returns {"start_side", "sequence": [{camp, side, t_window, confidence}],
             "full_clear_end_s" (est), "level_at_end", "jungle_cs_at_end"}
    """
    snapshots = _frame_positions(timeline, participant_id)
    own_side = side_of_team(team_id)

    CAMP_RESPAWN_S = 150  # camps can't be re-cleared sooner than this

    sequence = []
    last_cleared: dict[tuple[str, str], int] = {}  # (side, camp) -> time last assigned
    prev = None
    for snap in snapshots:
        if snap["t"] > until_s:
            break
        if prev is not None:
            delta = snap["jungle_cs"] - prev["jungle_cs"]
            if delta > 0:
                # Camps plausibly cleared between prev and snap: near either endpoint
                candidates = {}
                for side, name, d in _camps_near((prev["x"], prev["y"])) + _camps_near((snap["x"], snap["y"])):
                    key = (side, name)
                    if key in last_cleared and prev["t"] - last_cleared[key] < CAMP_RESPAWN_S:
                        continue  # respawn timer hasn't elapsed - can't be this camp again
                    if key not in candidates or d < candidates[key]:
                        candidates[key] = d
                # Greedily pick camps whose monster counts fit the delta, nearest first
                remaining = delta
                picked = []
                for (side, name), d in sorted(candidates.items(), key=lambda kv: kv[1]):
                    count = CAMP_MONSTER_COUNTS.get(name, 1)
                    if remaining <= 0:
                        break
                    if count <= remaining + 2:  # tolerance for partial camps
                        picked.append((side, name, d))
                        remaining -= count
                        last_cleared[(side, name)] = snap["t"]
                confidence = "high" if len(picked) <= 1 else ("medium" if remaining <= 2 else "low")
                for side, name, d in picked:
                    sequence.append({
                        "camp": name,
                        "side": side if name != "scuttle" else side,  # river name for scuttle
                        "own_side": (side == own_side),
                        "t_window": [prev["t"], snap["t"]],
                        "confidence": confidence if d < CAMP_RADIUS else "low",
                    })
        prev = snap

    # Estimate full-clear end: time of the frame where the 6th distinct own-side camp appears
    distinct_own = []
    full_clear_end = None
    for step in sequence:
        if step["own_side"] and step["camp"] != "scuttle" and step["camp"] not in distinct_own:
            distinct_own.append(step["camp"])
            if len(distinct_own) == 6:
                full_clear_end = step["t_window"][1]
                break

    end_snap = None
    for snap in snapshots:
        if snap["t"] <= until_s:
            end_snap = snap

    start_side = None
    for step in sequence:
        if step["camp"] in ("blue_buff", "gromp", "wolves"):
            start_side = "blue_side_start"
        elif step["camp"] in ("red_buff", "krugs", "raptors"):
            start_side = "red_side_start"
        break

    return {
        "start": start_side or "unknown",
        "sequence": sequence,
        "full_clear_end_s": full_clear_end,
        "level_at_end": end_snap["level"] if end_snap else None,
        "jungle_cs_at_end": end_snap["jungle_cs"] if end_snap else None,
        "note": f"Inferred from 60s snapshots; times are windows, not exact. First {until_s // 60} minutes.",
    }
