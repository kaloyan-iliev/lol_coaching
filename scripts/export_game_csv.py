"""
Export a single game's data as CSV tables for eyeballing in Excel/VS Code.

Writes to data/csv/{match_id}/:
    participants.csv   - scoreboard + curated Riot challenge stats per player
    frames.csv         - per player per minute: position, zone, gold, xp, cs, damage
    team_gold.csv      - per minute team gold totals + diff
    kills.csv          - every champion kill: who/whom/where, bounties, numbers nearby
    objectives.csv     - elite monsters, buildings, turret plates
    wards.csv          - ward placed/killed events
    items.csv          - item purchase/sell/undo events
    skills.csv         - skill level-ups (slot order per player)

Usage:
    python scripts/export_game_csv.py --match EUW1_7898664752
    python scripts/export_game_csv.py --match EUW1_xxx --riot-id "Name#TAG"   # fetch if not local
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from analysis.jungle_camps import classify_zone, dist
from analysis.challenges import extract_challenges

CSV_DIR = os.path.join(config.DATA_DIR, "csv")


def _writer(out_dir: str, name: str, header: list[str]):
    f = open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow(header)
    return f, w


def mmss(t_s: float) -> str:
    return f"{int(t_s) // 60:02d}:{int(t_s) % 60:02d}"


def export(match: dict, timeline: dict, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    participants = match["info"]["participants"]
    champs = {p["participantId"]: p["championName"] for p in participants}
    teams = {p["participantId"]: p["teamId"] for p in participants}

    # --- participants.csv ---
    f, w = _writer(out_dir, "participants.csv", [
        "participantId", "champion", "team", "role", "win", "kills", "deaths", "assists",
        "goldEarned", "totalCS", "jungleCS", "wardsPlaced", "controlWards", "visionScore",
        "totalDamageToChampions", "damageTaken", "totalTimeSpentDead_s",
        *extract_challenges(participants[0]).keys(),
    ])
    for p in participants:
        ch = extract_challenges(p)
        w.writerow([
            p["participantId"], p["championName"], p["teamId"], p.get("teamPosition", ""),
            p["win"], p["kills"], p["deaths"], p["assists"],
            p.get("goldEarned"), p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
            p.get("neutralMinionsKilled"), p.get("wardsPlaced"), p.get("detectorWardsPlaced"),
            p.get("visionScore"), p.get("totalDamageDealtToChampions"),
            p.get("totalDamageTaken"), p.get("totalTimeSpentDead"),
            *ch.values(),
        ])
    f.close()

    # --- frames.csv + team_gold.csv ---
    f1, w1 = _writer(out_dir, "frames.csv", [
        "minute", "clock", "participantId", "champion", "team", "x", "y", "zone",
        "totalGold", "currentGold", "xp", "level", "laneCS", "jungleCS",
        "dmgToChamps_cum", "dmgTaken_cum", "dmgToChamps_delta", "ccApplied_ms",
    ])
    f2, w2 = _writer(out_dir, "team_gold.csv", [
        "minute", "clock", "blue_gold", "red_gold", "diff_blue_minus_red",
    ])
    prev_dmg: dict[int, int] = {}
    for frame in timeline["info"]["frames"]:
        t = frame["timestamp"] // 1000
        minute = round(t / 60)
        gold = {100: 0, 200: 0}
        for pid_str, pf in frame["participantFrames"].items():
            pid = int(pid_str)
            pos = pf.get("position") or {}
            x, y = pos.get("x", 0), pos.get("y", 0)
            dmg = (pf.get("damageStats") or {}).get("totalDamageDoneToChampions", 0)
            dmg_delta = dmg - prev_dmg.get(pid, 0)
            prev_dmg[pid] = dmg
            gold[teams[pid]] += pf.get("totalGold", 0)
            w1.writerow([
                minute, mmss(t), pid, champs[pid], teams[pid], x, y, classify_zone(x, y),
                pf.get("totalGold"), pf.get("currentGold"), pf.get("xp"), pf.get("level"),
                pf.get("minionsKilled"), pf.get("jungleMinionsKilled"),
                dmg, (pf.get("damageStats") or {}).get("totalDamageTaken", 0),
                dmg_delta, pf.get("timeEnemySpentControlled"),
            ])
        w2.writerow([minute, mmss(t), gold[100], gold[200], gold[100] - gold[200]])
    f1.close()
    f2.close()

    # --- event tables ---
    events = [ev for fr in timeline["info"]["frames"] for ev in fr.get("events", [])]

    def name(pid):
        return champs.get(pid, str(pid) if pid else "")

    f, w = _writer(out_dir, "kills.csv", [
        "clock", "t_s", "killer", "victim", "assists", "x", "y", "zone",
        "bounty", "shutdownBounty", "killStreak",
        "victim_allies_within_2500", "victim_enemies_within_2500",
    ])
    frames = timeline["info"]["frames"]
    for ev in events:
        if ev.get("type") != "CHAMPION_KILL":
            continue
        t = ev["timestamp"] / 1000
        pos = ev.get("position") or {}
        vteam = teams.get(ev.get("victimId"))
        idx = min(round(t / 60), len(frames) - 1)
        allies = enemies = 0
        for pid_str, pf in frames[idx]["participantFrames"].items():
            pid = int(pid_str)
            if pid == ev.get("victimId"):
                continue
            ppos = pf.get("position") or {}
            if dist((ppos.get("x", 0), ppos.get("y", 0)), (pos.get("x", 0), pos.get("y", 0))) < 2500:
                if teams[pid] == vteam:
                    allies += 1
                else:
                    enemies += 1
        w.writerow([
            mmss(t), round(t), name(ev.get("killerId")), name(ev.get("victimId")),
            "|".join(name(a) for a in ev.get("assistingParticipantIds", [])),
            pos.get("x"), pos.get("y"), classify_zone(pos.get("x", 0), pos.get("y", 0)),
            ev.get("bounty"), ev.get("shutdownBounty"), ev.get("killStreakLength"),
            allies, enemies,
        ])
    f.close()

    f, w = _writer(out_dir, "objectives.csv", [
        "clock", "t_s", "event", "detail", "team", "killer", "x", "y", "lane",
    ])
    for ev in events:
        t = ev["timestamp"] / 1000
        pos = ev.get("position") or {}
        etype = ev.get("type")
        if etype == "ELITE_MONSTER_KILL":
            w.writerow([mmss(t), round(t), etype,
                        f"{ev.get('monsterType')}{'/' + ev['monsterSubType'] if ev.get('monsterSubType') else ''}",
                        ev.get("killerTeamId"), name(ev.get("killerId")),
                        pos.get("x"), pos.get("y"), ""])
        elif etype == "BUILDING_KILL":
            w.writerow([mmss(t), round(t), etype,
                        f"{ev.get('buildingType')}/{ev.get('towerType', '')}",
                        ev.get("teamId"), name(ev.get("killerId")),
                        pos.get("x"), pos.get("y"), ev.get("laneType")])
        elif etype == "TURRET_PLATE_DESTROYED":
            w.writerow([mmss(t), round(t), etype, "PLATE", ev.get("teamId"),
                        name(ev.get("killerId")), pos.get("x"), pos.get("y"), ev.get("laneType")])
        elif etype in ("DRAGON_SOUL_GIVEN", "OBJECTIVE_BOUNTY_PRESTART", "OBJECTIVE_BOUNTY_FINISH"):
            w.writerow([mmss(t), round(t), etype, ev.get("name", ""), ev.get("teamId"), "", "", "", ""])
    f.close()

    f, w = _writer(out_dir, "wards.csv", ["clock", "t_s", "action", "wardType", "by"])
    for ev in events:
        t = ev["timestamp"] / 1000
        if ev.get("type") == "WARD_PLACED":
            w.writerow([mmss(t), round(t), "PLACED", ev.get("wardType"), name(ev.get("creatorId"))])
        elif ev.get("type") == "WARD_KILL":
            w.writerow([mmss(t), round(t), "KILLED", ev.get("wardType"), name(ev.get("killerId"))])
    f.close()

    f, w = _writer(out_dir, "items.csv", ["clock", "t_s", "action", "itemId", "by", "goldGain"])
    for ev in events:
        t = ev["timestamp"] / 1000
        etype = ev.get("type")
        if etype in ("ITEM_PURCHASED", "ITEM_SOLD", "ITEM_DESTROYED"):
            w.writerow([mmss(t), round(t), etype.replace("ITEM_", ""), ev.get("itemId"),
                        name(ev.get("participantId")), ""])
        elif etype == "ITEM_UNDO":
            w.writerow([mmss(t), round(t), "UNDO", f"{ev.get('beforeId')}->{ev.get('afterId')}",
                        name(ev.get("participantId")), ev.get("goldGain")])
    f.close()

    f, w = _writer(out_dir, "skills.csv", ["clock", "t_s", "champion", "skillSlot", "levelUpType"])
    for ev in events:
        if ev.get("type") != "SKILL_LEVEL_UP":
            continue
        t = ev["timestamp"] / 1000
        w.writerow([mmss(t), round(t), name(ev.get("participantId")),
                    ev.get("skillSlot"), ev.get("levelUpType")])
    f.close()


def main():
    parser = argparse.ArgumentParser(description="Export one game's data as CSV tables")
    parser.add_argument("--match", required=True, help="Match ID (e.g. EUW1_7898664752)")
    args = parser.parse_args()

    match = store.load_match(args.match)
    timeline = store.load_timeline(args.match)
    if match is None or timeline is None:
        print(f"Match/timeline not on disk for {args.match}. "
              f"Run review_game.py on it first (it downloads + caches).")
        sys.exit(1)

    out_dir = os.path.join(CSV_DIR, args.match)
    export(match, timeline, out_dir)
    files = sorted(os.listdir(out_dir))
    print(f"Exported {len(files)} tables to {out_dir}:")
    for fname in files:
        n_rows = sum(1 for _ in open(os.path.join(out_dir, fname), encoding="utf-8")) - 1
        print(f"  {fname:20s} {n_rows:5d} rows")


if __name__ == "__main__":
    main()
