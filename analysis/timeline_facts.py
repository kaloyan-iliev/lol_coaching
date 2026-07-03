"""
Deterministic fact extraction from a match + timeline for one jungler.

Everything here is computed directly from Riot data - no LLM involved.
Facts that rely on position heuristics (ganks, participation) are labeled
"heuristic"; the review prompt must not upgrade them to certainties.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from analysis.jungle_camps import (
    LANE_ZONES, NEARBY_ALLY_RADIUS, OBJECTIVE_RADIUS,
    classify_zone, dist, is_enemy_jungle,
)
from analysis.pathing import reconstruct_clear, _frame_positions


def _participants(match: dict) -> list[dict]:
    return match["info"]["participants"]


def _find_participant(match: dict, puuid: str) -> dict:
    for p in _participants(match):
        if p["puuid"] == puuid:
            return p
    raise ValueError(f"puuid not found in match {match['metadata']['matchId']}")


def _find_enemy_jungler(match: dict, our_team_id: int) -> dict | None:
    for p in _participants(match):
        if p["teamId"] != our_team_id and p.get("teamPosition") == "JUNGLE":
            return p
    return None


def _champ_by_pid(match: dict) -> dict[int, str]:
    return {p["participantId"]: p["championName"] for p in _participants(match)}


def _team_by_pid(match: dict) -> dict[int, int]:
    return {p["participantId"]: p["teamId"] for p in _participants(match)}


def _all_events(timeline: dict) -> list[dict]:
    events = []
    for frame in timeline["info"]["frames"]:
        events.extend(frame.get("events", []))
    return events


def _positions_at_minute(timeline: dict, minute: int) -> dict[int, tuple[float, float]]:
    """Position of every participant at the given frame minute."""
    frames = timeline["info"]["frames"]
    idx = min(minute, len(frames) - 1)
    out = {}
    for pid_str, pf in frames[idx]["participantFrames"].items():
        pos = pf.get("position") or {}
        out[int(pid_str)] = (pos.get("x", 0), pos.get("y", 0))
    return out


def _snapshot_at(snapshots: list[dict], t_s: float) -> dict | None:
    """Snapshot at the frame nearest to time t (seconds)."""
    if not snapshots:
        return None
    return min(snapshots, key=lambda s: abs(s["t"] - t_s))


def mmss(t_s: float) -> str:
    return f"{int(t_s) // 60:02d}:{int(t_s) % 60:02d}"


ROLE_ORDER = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


def _team_comps(match: dict, our_team_id: int) -> dict:
    """Both drafts, ordered by role."""
    def comp(team_id):
        members = [p for p in _participants(match) if p["teamId"] == team_id]
        members.sort(key=lambda p: ROLE_ORDER.index(p["teamPosition"])
                     if p.get("teamPosition") in ROLE_ORDER else 9)
        return [{"champion": p["championName"],
                 "role": p.get("teamPosition", "?")} for p in members]
    return {"ours": comp(our_team_id),
            "enemy": comp(200 if our_team_id == 100 else 100)}


def _cluster_teamfights(events: list[dict], teams: dict[int, int], champs: dict[int, str],
                        timeline: dict, pid: int, team_id: int) -> list[dict]:
    """Group champion kills into fights: kills within 45s and 3500 units of each other."""
    kills = [ev for ev in events if ev.get("type") == "CHAMPION_KILL"]
    fights = []
    current = []
    for ev in kills:
        if current:
            last = current[-1]
            dt = (ev["timestamp"] - last["timestamp"]) / 1000
            lp, ep = last.get("position") or {}, ev.get("position") or {}
            dd = dist((lp.get("x", 0), lp.get("y", 0)), (ep.get("x", 0), ep.get("y", 0)))
            if dt > 45 or dd > 3500:
                fights.append(current)
                current = []
        current.append(ev)
    if current:
        fights.append(current)

    out = []
    for fight in fights:
        if len(fight) < 2:
            continue  # single kills are already covered by deaths/ganks
        t0 = fight[0]["timestamp"] / 1000
        t1 = fight[-1]["timestamp"] / 1000
        our_deaths = sum(1 for ev in fight if teams.get(ev.get("victimId")) == team_id)
        their_deaths = len(fight) - our_deaths
        involved = set()
        for ev in fight:
            involved.add(ev.get("victimId"))
            involved.add(ev.get("killerId"))
            involved.update(ev.get("assistingParticipantIds", []))
        involved.discard(None)
        involved.discard(0)
        we_involved = pid in involved

        # Numbers on each side near the fight start (heuristic: 60s snapshots)
        centroid_pos = fight[0].get("position") or {}
        centroid = (centroid_pos.get("x", 0), centroid_pos.get("y", 0))
        minute_positions = _positions_at_minute(timeline, round(t0 / 60))
        allies_near = sum(1 for p, pos in minute_positions.items()
                          if teams.get(p) == team_id and dist(pos, centroid) < 4000)
        enemies_near = sum(1 for p, pos in minute_positions.items()
                           if teams.get(p) != team_id and dist(pos, centroid) < 4000)

        zone = classify_zone(*centroid)
        out.append({
            "t_start": round(t0), "clock": mmss(t0), "t_end": round(t1),
            "zone": zone,
            "kills_total": len(fight),
            "our_deaths": our_deaths, "enemy_deaths": their_deaths,
            "result": ("won" if their_deaths > our_deaths
                       else "lost" if our_deaths > their_deaths else "even"),
            "we_involved": we_involved,
            "numbers_at_start": {"allies": allies_near, "enemies": enemies_near,
                                 "confidence": "heuristic (60s snapshots)"},
        })
    return out


def extract_facts(match: dict, timeline: dict, puuid: str) -> dict:
    us = _find_participant(match, puuid)
    pid = us["participantId"]
    team_id = us["teamId"]
    enemy_jgl = _find_enemy_jungler(match, team_id)
    champs = _champ_by_pid(match)
    teams = _team_by_pid(match)
    duration_s = match["info"]["gameDuration"]

    our_snaps = _frame_positions(timeline, pid)
    ejgl_snaps = _frame_positions(timeline, enemy_jgl["participantId"]) if enemy_jgl else []
    events = _all_events(timeline)

    def enemy_jgl_zone_at(t_s: float) -> str | None:
        snap = _snapshot_at(ejgl_snaps, t_s)
        if snap is None:
            return None
        return classify_zone(snap["x"], snap["y"])

    def gold_xp_diff_at(t_s: float) -> tuple[int | None, int | None]:
        if not ejgl_snaps:
            return None, None
        ours = _snapshot_at(our_snaps, t_s)
        theirs = _snapshot_at(ejgl_snaps, t_s)
        if not ours or not theirs:
            return None, None
        return ours["gold"] - theirs["gold"], ours["xp"] - theirs["xp"]

    # --- deaths ---
    deaths = []
    for ev in events:
        if ev.get("type") != "CHAMPION_KILL" or ev.get("victimId") != pid:
            continue
        t = ev["timestamp"] / 1000
        pos = ev.get("position") or {}
        zone = classify_zone(pos.get("x", 0), pos.get("y", 0))
        minute_positions = _positions_at_minute(timeline, round(t / 60))
        death_pos = (pos.get("x", 0), pos.get("y", 0))
        allies_nearby = sum(
            1 for other_pid, opos in minute_positions.items()
            if other_pid != pid and teams.get(other_pid) == team_id
            and dist(opos, death_pos) < NEARBY_ALLY_RADIUS
        )
        enemies_nearby = sum(
            1 for other_pid, opos in minute_positions.items()
            if teams.get(other_pid) != team_id
            and dist(opos, death_pos) < NEARBY_ALLY_RADIUS
        )
        gd, xd = gold_xp_diff_at(t)
        snap = _snapshot_at(our_snaps, t)
        death = {
            "t": round(t), "clock": mmss(t),
            "killer": champs.get(ev.get("killerId"), "unknown"),
            "assists": len(ev.get("assistingParticipantIds", [])),
            "zone": zone,
            "our_level": snap["level"] if snap else None,
            "allies_nearby": allies_nearby,
            "enemies_nearby": enemies_nearby,
            "enemy_jgl_zone": enemy_jgl_zone_at(t),
            "gold_diff_vs_enemy_jgl": gd,
            "flags": [],
        }
        if enemies_nearby - allies_nearby >= 2:
            death["flags"].append("outnumbered")
        if is_enemy_jungle(zone, team_id) and allies_nearby == 0:
            death["flags"].append("alone_in_enemy_jungle")
        if zone.endswith("_river") and t < 210:
            death["flags"].append("early_river_death")
        deaths.append(death)

    # --- kills / gank involvement (heuristic) ---
    ganks = []
    kills = 0
    assists_n = 0
    first_gank_t = None
    for ev in events:
        if ev.get("type") != "CHAMPION_KILL":
            continue
        involved_as_killer = ev.get("killerId") == pid
        involved_as_assist = pid in ev.get("assistingParticipantIds", [])
        if not (involved_as_killer or involved_as_assist):
            continue
        if teams.get(ev.get("victimId")) == team_id:
            continue
        t = ev["timestamp"] / 1000
        kills += 1 if involved_as_killer else 0
        assists_n += 1 if involved_as_assist else 0
        pos = ev.get("position") or {}
        zone = classify_zone(pos.get("x", 0), pos.get("y", 0))
        if zone in LANE_ZONES:
            ganks.append({
                "t": round(t), "clock": mmss(t),
                "lane": zone.replace("_lane", ""),
                "victim": champs.get(ev.get("victimId"), "unknown"),
                "result": "kill" if involved_as_killer else "assist",
                "enemy_jgl_zone": enemy_jgl_zone_at(t),
                "confidence": "heuristic",
            })
            if first_gank_t is None:
                first_gank_t = round(t)

    # --- objectives ---
    objectives = []
    for ev in events:
        if ev.get("type") != "ELITE_MONSTER_KILL":
            continue
        t = ev["timestamp"] / 1000
        killer_team = ev.get("killerTeamId")
        pos = ev.get("position") or {}
        minute_positions = _positions_at_minute(timeline, round(t / 60))
        our_pos = minute_positions.get(pid)
        we_near = our_pos is not None and dist(our_pos, (pos.get("x", 0), pos.get("y", 0))) < OBJECTIVE_RADIUS
        recent_deaths = [
            e for e in events
            if e.get("type") == "CHAMPION_KILL"
            and 0 <= t - e["timestamp"] / 1000 <= 60
        ]
        objectives.append({
            "t": round(t), "clock": mmss(t),
            "type": ev.get("monsterType", "?"),
            "subtype": ev.get("monsterSubType", ""),
            "team": "ally" if killer_team == team_id else "enemy",
            "we_secured": ev.get("killerId") == pid,
            "we_nearby": we_near,
            "kills_60s_before": len(recent_deaths),
            "participation_confidence": "heuristic",
        })

    # --- counter-jungle episodes (heuristic) ---
    counter_jungle = []
    prev = None
    for snap in our_snaps:
        zone = classify_zone(snap["x"], snap["y"])
        if prev is not None and is_enemy_jungle(zone, team_id):
            delta = snap["jungle_cs"] - prev["jungle_cs"]
            counter_jungle.append({
                "t": snap["t"], "clock": mmss(snap["t"]),
                "zone": zone,
                "jungle_cs_gained": max(delta, 0),
                "confidence": "heuristic",
            })
        prev = snap

    # --- economy ---
    def cs_at(minute: int):
        snap = next((s for s in our_snaps if s["t"] >= minute * 60), None)
        return (snap["lane_cs"] + snap["jungle_cs"]) if snap else None

    gold_diff_curve = []
    for snap in our_snaps:
        if snap["t"] % 120 < 60:  # every ~2 minutes keeps it compact
            gd, xd = gold_xp_diff_at(snap["t"])
            if gd is not None:
                gold_diff_curve.append({"t": snap["t"], "clock": mmss(snap["t"]),
                                        "gold_diff": gd, "xp_diff": xd})

    first_reset = next(
        (ev["timestamp"] / 1000 for ev in events
         if ev.get("type") == "ITEM_PURCHASED" and ev.get("participantId") == pid
         and ev["timestamp"] / 1000 > 120),
        None,
    )

    # --- vision ---
    wards_placed = sum(1 for ev in events
                       if ev.get("type") == "WARD_PLACED" and ev.get("creatorId") == pid)
    control_wards = sum(1 for ev in events
                        if ev.get("type") == "WARD_PLACED" and ev.get("creatorId") == pid
                        and ev.get("wardType") == "CONTROL_WARD")
    wards_killed = sum(1 for ev in events
                       if ev.get("type") == "WARD_KILL" and ev.get("killerId") == pid)

    # --- clear reconstruction ---
    clear = reconstruct_clear(timeline, pid, team_id)

    facts = {
        "match_id": match["metadata"]["matchId"],
        "champion": us["championName"],
        "win": us["win"],
        "duration_s": duration_s,
        "duration_clock": mmss(duration_s),
        "game_version": ".".join(match["info"].get("gameVersion", "").split(".")[:2]),
        "our_team": "blue" if team_id == 100 else "red",
        "our_role": us.get("teamPosition", "?"),
        "enemy_jungler": enemy_jgl["championName"] if enemy_jgl else "unknown",
        "kda": f"{us['kills']}/{us['deaths']}/{us['assists']}",
        "comps": _team_comps(match, team_id),
        "teamfights": _cluster_teamfights(events, teams, champs, timeline, pid, team_id),
        "clear": clear,
        "deaths": deaths,
        "ganks": ganks,
        "objectives": objectives,
        "counter_jungle": [c for c in counter_jungle if c["jungle_cs_gained"] > 0],
        "economy": {
            "cs_at_10": cs_at(10),
            "cs_at_15": cs_at(15),
            "first_reset_s": round(first_reset) if first_reset else None,
            "first_gank_t": first_gank_t,
            "gold_diff_vs_enemy_jgl_curve": gold_diff_curve,
        },
        "vision": {
            "wards_placed": wards_placed,
            "control_wards": control_wards,
            "wards_killed": wards_killed,
        },
    }
    facts["flags"] = derive_flags(facts)
    return facts


def derive_flags(facts: dict) -> list[str]:
    """Boolean signals that drive Jungle Bible section selection in reviews."""
    flags = []
    deaths = facts["deaths"]
    objectives = facts["objectives"]
    econ = facts["economy"]

    if econ["first_gank_t"] is None or econ["first_gank_t"] > 480:
        flags.append("no_early_gank_involvement")
    if any("alone_in_enemy_jungle" in d["flags"] for d in deaths):
        flags.append("died_alone_in_enemy_jungle")
    if any("early_river_death" in d["flags"] for d in deaths):
        flags.append("early_river_death")
    if sum(1 for d in deaths if d["t"] < 840) >= 3:
        flags.append("three_plus_deaths_before_14min")

    first_by_type: dict[str, dict] = {}
    for obj in objectives:
        first_by_type.setdefault(obj["type"], obj)
    for otype, obj in first_by_type.items():
        if obj["team"] == "enemy" and not obj["we_nearby"]:
            flags.append(f"first_{otype.lower()}_lost_absent")

    if econ["cs_at_10"] is not None and econ["cs_at_10"] < 55:
        flags.append("low_cs_at_10")
    if facts["vision"]["control_wards"] == 0:
        flags.append("no_control_wards")
    curve = econ["gold_diff_vs_enemy_jgl_curve"]
    if any(p["gold_diff"] < -1500 for p in curve if p["t"] < 900):
        flags.append("big_early_gold_deficit_vs_jungler")
    if not facts["counter_jungle"]:
        flags.append("zero_counter_jungling")
    if any("outnumbered" in d["flags"] for d in deaths):
        flags.append("died_outnumbered")
    if any(f["we_involved"] and f["result"] == "lost"
           and f["numbers_at_start"]["enemies"] > f["numbers_at_start"]["allies"]
           for f in facts["teamfights"]):
        flags.append("lost_outnumbered_teamfight")
    return flags
