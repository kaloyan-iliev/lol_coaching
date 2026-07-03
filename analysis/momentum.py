"""
Team gold momentum: build per-minute team-gold curves and detect the game's
major gold swings, correlated with the events that caused them.

A swing is a change in team-gold difference of >= SWING_THRESHOLD within a
2-3 minute window. These are the "focus here" moments of a game review.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from analysis.jungle_camps import classify_zone

SWING_THRESHOLD_EARLY_G = 1500
SWING_THRESHOLD_LATE_G = 2500
LATE_GAME_S = 1200
SWING_WINDOWS = (2, 3)  # frames (~minutes)
MAX_SWINGS = 6


def _mmss(t_s: float) -> str:
    return f"{int(t_s) // 60:02d}:{int(t_s) % 60:02d}"


def team_gold_curve(timeline: dict, teams: dict[int, int], our_team_id: int) -> list[dict]:
    """Per-frame team gold totals and diff (ours - theirs)."""
    curve = []
    for frame in timeline["info"]["frames"]:
        t = frame["timestamp"] // 1000
        ours = theirs = 0
        for pid_str, pf in frame["participantFrames"].items():
            gold = pf.get("totalGold", 0)
            if teams.get(int(pid_str)) == our_team_id:
                ours += gold
            else:
                theirs += gold
        curve.append({"t": t, "clock": _mmss(t), "our_team_gold": ours,
                      "enemy_team_gold": theirs, "diff": ours - theirs})
    return curve


def _describe_drivers(t_start: int, t_end: int, events: list[dict], teamfights: list[dict],
                      teams: dict[int, int], our_team_id: int) -> list[str]:
    """What happened inside [t_start-30, t_end+15] that explains a swing."""
    lo, hi = t_start - 30, t_end + 15
    drivers = []

    fight_lines = [
        f"{f['result']} teamfight at {f['clock']} in {f['zone']} "
        f"({f['enemy_deaths']}-{f['our_deaths']} kills)"
        for f in teamfights if f["t_start"] <= hi and f["t_end"] >= lo
    ]
    drivers.extend(fight_lines[:3])

    buildings = {"we": 0, "enemy": 0}
    shutdown_ours = shutdown_theirs = 0
    for ev in events:
        t = ev["timestamp"] / 1000
        if not (lo <= t <= hi):
            continue
        etype = ev.get("type")
        if etype == "ELITE_MONSTER_KILL":
            side = "we" if ev.get("killerTeamId") == our_team_id else "enemy"
            drivers.append(f"{side} took {ev.get('monsterType', '?')} at {_mmss(t)}")
        elif etype == "BUILDING_KILL":
            # teamId on BUILDING_KILL is the team that LOST the building
            side = "we" if ev.get("teamId") != our_team_id else "enemy"
            buildings[side] += 1
        elif etype == "CHAMPION_KILL":
            gold = ev.get("bounty", 0) + ev.get("shutdownBounty", 0)
            if teams.get(ev.get("victimId")) == our_team_id:
                shutdown_theirs += gold
            else:
                shutdown_ours += gold

    for side, n in buildings.items():
        if n:
            drivers.append(f"{side} destroyed {n} building{'s' if n > 1 else ''}")
    if shutdown_ours - shutdown_theirs >= 500:
        drivers.append(f"kill gold to us +{shutdown_ours - shutdown_theirs}g")
    elif shutdown_theirs - shutdown_ours >= 500:
        drivers.append(f"kill gold to enemy +{shutdown_theirs - shutdown_ours}g")

    if not drivers:
        drivers.append("farm/macro drift (no single event)")
    return drivers[:6]


def detect_swings(curve: list[dict], events: list[dict], teamfights: list[dict],
                  teams: dict[int, int], our_team_id: int) -> list[dict]:
    """Find the game's major team-gold swings, largest first, capped at MAX_SWINGS."""
    triggers = []
    for i in range(len(curve)):
        for k in SWING_WINDOWS:
            if i - k < 0:
                continue
            delta = curve[i]["diff"] - curve[i - k]["diff"]
            threshold = (SWING_THRESHOLD_LATE_G if curve[i]["t"] >= LATE_GAME_S
                         else SWING_THRESHOLD_EARLY_G)
            if abs(delta) >= threshold:
                triggers.append({"i_start": i - k, "i_end": i, "delta": delta})

    # Pick the strongest NON-OVERLAPPING windows (chaining overlaps would collapse
    # a one-sided game into one useless mega-swing)
    triggers.sort(key=lambda tr: -abs(tr["delta"]))
    episodes = []
    for tr in triggers:
        if len(episodes) >= MAX_SWINGS:
            break
        if any(tr["i_start"] < ep["i_end"] and tr["i_end"] > ep["i_start"] for ep in episodes):
            continue
        episodes.append(tr)

    swings = []
    for ep in episodes:
        start, end = curve[ep["i_start"]], curve[ep["i_end"]]
        magnitude = end["diff"] - start["diff"]
        swings.append({
            "t_start": start["t"], "t_end": end["t"],
            "clock_start": start["clock"], "clock_end": end["clock"],
            "magnitude": magnitude,
            "direction": "gained" if magnitude > 0 else "lost",
            "diff_before": start["diff"], "diff_after": end["diff"],
            "drivers": _describe_drivers(start["t"], end["t"], events, teamfights,
                                         teams, our_team_id),
        })

    swings.sort(key=lambda s: -abs(s["magnitude"]))
    swings = swings[:MAX_SWINGS]
    swings.sort(key=lambda s: s["t_start"])
    return swings
