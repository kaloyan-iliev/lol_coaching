"""
Map-state reconstruction at any second of a game - denser than the API gives.

Riot's match-v5 timeline has a HARD 60s frame interval (no parameter changes it).
But events between frames are millisecond-exact and many pin a player to a known
position: an item purchase = at own base shop, a kill = at the death spot, an
elite-monster/plate/building kill = at that objective. Interpolating between
those anchors (instead of between 60s frames) and LABELING what is observed vs
estimated gives an LLM (or a human) a far less assumption-heavy picture.

Usage:
    python scripts/map_state.py --match EUW1_xxx --at 14:30      # full state at a second
    python scripts/map_state.py --match EUW1_xxx --tick 15       # per-15s table -> CSV
    python scripts/map_state.py --match EUW1_xxx --at 14:30 --window 25   # events context

Confidence labels per player/tick:
    observed     an anchor (frame or position-bearing event) within 2s
    anchored     interpolated between anchors < 45s apart (event-tightened)
    interp       interpolated between plain 60s frames
    dead         killed recently; shown at death spot until respawn estimate
    uncertain    adjacent anchors imply a teleport/recall jump - position unreliable
"""

import argparse
import bisect
import csv
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from analysis.jungle_camps import classify_zone, dist

CSV_DIR = os.path.join(config.DATA_DIR, "csv")
DDRAGON_DIR = os.path.join(config.DATA_DIR, "ddragon")
BASE_POS = {100: (554, 581), 200: (14043, 14173)}  # shop locations


def mmss(t_s: float) -> str:
    return f"{int(t_s) // 60:02d}:{int(t_s) % 60:02d}"


def parse_clock(s: str) -> int:
    if ":" in s:
        m, sec = s.split(":")
        return int(m) * 60 + int(sec)
    return int(s)


# --- DDragon item names (keyless download, cached on disk) --------------------

def item_map(game_version: str) -> dict[int, dict]:
    """itemId -> {name, gold} from DDragon; empty dict if unavailable."""
    major_minor = ".".join(game_version.split(".")[:2])
    path = os.path.join(DDRAGON_DIR, f"item_{major_minor}.1.json")
    if not os.path.exists(path):
        url = f"https://ddragon.leagueoflegends.com/cdn/{major_minor}.1/data/en_US/item.json"
        try:
            os.makedirs(DDRAGON_DIR, exist_ok=True)
            with urllib.request.urlopen(url, timeout=20) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
            print(f"(downloaded DDragon item data -> {path})")
        except Exception as e:
            print(f"(no DDragon item data: {e} - showing raw item ids)")
            return {}
    raw = json.load(open(path, encoding="utf-8"))["data"]
    return {int(k): {"name": v["name"], "gold": v["gold"]["total"]}
            for k, v in raw.items()}


# --- Anchor extraction ---------------------------------------------------------

RESPAWN_BASE_S = {1: 10, 2: 10, 3: 12, 4: 12, 5: 14, 6: 16, 7: 20, 8: 25,
                  9: 28, 10: 32.5, 11: 35, 12: 37.5, 13: 40, 14: 42.5,
                  15: 45, 16: 47.5, 17: 50, 18: 52.5}


def build_player_data(match: dict, timeline: dict):
    """Per player: position anchors, item events, level-up times, death spans,
    and the raw 60s frames (for gold/xp interpolation)."""
    participants = match["info"]["participants"]
    champs = {p["participantId"]: p["championName"] for p in participants}
    teams = {p["participantId"]: p["teamId"] for p in participants}
    frames = timeline["info"]["frames"]
    events = [ev for fr in frames for ev in fr.get("events", [])]

    anchors = {pid: [] for pid in champs}     # (t, x, y, kind)
    item_events = {pid: [] for pid in champs}  # (t, type, itemId, beforeId, afterId)
    levelups = {pid: [] for pid in champs}     # [t, ...]
    deaths = {pid: [] for pid in champs}       # (t, x, y)

    for fr in frames:
        t = fr["timestamp"] / 1000
        for pid_str, pf in fr["participantFrames"].items():
            pos = pf.get("position") or {}
            anchors[int(pid_str)].append((t, pos.get("x", 0), pos.get("y", 0), "frame"))

    for ev in events:
        t = ev["timestamp"] / 1000
        etype = ev.get("type")
        pos = ev.get("position") or {}
        if etype == "CHAMPION_KILL":
            vid, kid = ev.get("victimId"), ev.get("killerId")
            if vid in anchors:
                anchors[vid].append((t, pos.get("x", 0), pos.get("y", 0), "death"))
                deaths[vid].append((t, pos.get("x", 0), pos.get("y", 0)))
            if kid in anchors and kid:  # killerId 0 = executed
                anchors[kid].append((t, pos.get("x", 0), pos.get("y", 0), "kill"))
        elif etype in ("ITEM_PURCHASED", "ITEM_SOLD", "ITEM_DESTROYED", "ITEM_UNDO"):
            pid = ev.get("participantId")
            if pid in anchors:
                if etype in ("ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO"):
                    bx, by = BASE_POS[teams[pid]]  # shopping = at own base
                    anchors[pid].append((t, bx, by, "shop"))
                item_events[pid].append((t, etype, ev.get("itemId"),
                                         ev.get("beforeId"), ev.get("afterId")))
        elif etype == "ELITE_MONSTER_KILL":
            kid = ev.get("killerId")
            if kid in anchors and kid:
                anchors[kid].append((t, pos.get("x", 0), pos.get("y", 0), "monster"))
        elif etype in ("BUILDING_KILL", "TURRET_PLATE_DESTROYED"):
            kid = ev.get("killerId")
            if kid in anchors and kid and pos:
                anchors[kid].append((t, pos.get("x", 0), pos.get("y", 0), "structure"))
        elif etype == "SKILL_LEVEL_UP":
            pid = ev.get("participantId")
            if pid in levelups:
                levelups[pid].append(t)

    for pid in anchors:
        anchors[pid].sort(key=lambda a: a[0])
        levelups[pid].sort()
        deaths[pid].sort()
    return champs, teams, frames, events, anchors, item_events, levelups, deaths


def frame_at(frames: list, t: float) -> tuple[dict, dict, float, float]:
    """(frame_before, frame_after, t_before, t_after) surrounding t."""
    times = [fr["timestamp"] / 1000 for fr in frames]
    i = bisect.bisect_right(times, t) - 1
    i = max(0, min(i, len(frames) - 1))
    j = min(i + 1, len(frames) - 1)
    return frames[i], frames[j], times[i], times[j]


def level_at(pid: int, t: float, frames, levelups) -> int:
    fb, _, _, _ = frame_at(frames, t)
    frame_level = fb["participantFrames"][str(pid)].get("level", 1)
    event_level = 1 + bisect.bisect_right(levelups[pid], t)  # lvl1 has no skill-up... approx
    return max(frame_level, min(event_level, 18))


def gold_at(pid: int, t: float, frames) -> tuple[int, int]:
    """(totalGold~, currentGold_at_last_frame) - total linearly interpolated."""
    fb, fa, tb, ta = frame_at(frames, t)
    pb, pa = fb["participantFrames"][str(pid)], fa["participantFrames"][str(pid)]
    if ta == tb:
        return pb.get("totalGold", 0), pb.get("currentGold", 0)
    frac = (t - tb) / (ta - tb)
    total = round(pb.get("totalGold", 0) + frac * (pa.get("totalGold", 0) - pb.get("totalGold", 0)))
    return total, pb.get("currentGold", 0)


def items_at(pid: int, t: float, item_events, items_db) -> list[str]:
    inv: list[int] = []
    for (et, etype, item_id, before, after) in item_events[pid]:
        if et > t:
            break
        if etype == "ITEM_PURCHASED" and item_id:
            inv.append(item_id)
        elif etype in ("ITEM_SOLD", "ITEM_DESTROYED") and item_id in inv:
            inv.remove(item_id)
        elif etype == "ITEM_UNDO":
            if before and before in inv:
                inv.remove(before)
            if after:
                inv.append(after)
    named = []
    for iid in inv:
        named.append(items_db.get(iid, {}).get("name", str(iid)))
    return named


def position_at(pid: int, t: float, anchors, deaths, teams, level: int = 18) -> dict:
    """{x, y, zone, confidence, note}."""
    # Dead right now? (respawn estimate by level; late-game multipliers ignored)
    for (dt, dx, dy) in reversed(deaths[pid]):
        if dt <= t:
            lvl_respawn = RESPAWN_BASE_S.get(level, 52.5)
            if t - dt <= lvl_respawn:
                return {"x": dx, "y": dy, "zone": classify_zone(dx, dy),
                        "confidence": "dead",
                        "note": f"died {mmss(dt)} ({round(t - dt)}s ago)"}
            break

    pts = anchors[pid]
    times = [a[0] for a in pts]
    i = bisect.bisect_right(times, t) - 1
    if i < 0:
        a = pts[0]
        return {"x": a[1], "y": a[2], "zone": classify_zone(a[1], a[2]),
                "confidence": "interp", "note": "before first anchor"}
    a_before = pts[i]
    a_after = pts[i + 1] if i + 1 < len(pts) else a_before

    if abs(a_before[0] - t) <= 2 or a_before[0] == a_after[0]:
        a = a_before if abs(a_before[0] - t) <= abs(a_after[0] - t) else a_after
        return {"x": a[1], "y": a[2], "zone": classify_zone(a[1], a[2]),
                "confidence": "observed", "note": f"{a[3]} @ {mmss(a[0])}"}

    gap = a_after[0] - a_before[0]
    jump = dist((a_before[1], a_before[2]), (a_after[1], a_after[2]))
    frac = (t - a_before[0]) / gap
    x = round(a_before[1] + frac * (a_after[1] - a_before[1]))
    y = round(a_before[2] + frac * (a_after[2] - a_before[2]))
    speed = jump / gap if gap else 0
    if speed > 700:  # faster than any champion walks -> recall/TP between anchors
        return {"x": x, "y": y, "zone": classify_zone(x, y),
                "confidence": "uncertain",
                "note": f"recall/TP likely between {mmss(a_before[0])} and {mmss(a_after[0])}"}
    conf = "anchored" if gap < 45 else "interp"
    return {"x": x, "y": y, "zone": classify_zone(x, y), "confidence": conf,
            "note": f"between {a_before[3]}@{mmss(a_before[0])} and {a_after[3]}@{mmss(a_after[0])}"}


# --- Modes ---------------------------------------------------------------------

def state_at(match, timeline, t: float, items_db, window: int):
    champs, teams, frames, events, anchors, item_events, levelups, deaths = \
        build_player_data(match, timeline)

    print(f"\n# MAP STATE @ {mmss(t)}  ({match['metadata']['matchId']})\n")
    print(f"{'champion':13s} {'team':4s} {'zone':22s} {'conf':9s} {'lvl':>3s} "
          f"{'gold~':>6s}  items / note")
    for pid in sorted(champs, key=lambda p: (teams[p], p)):
        lvl = level_at(pid, t, frames, levelups)
        pos = position_at(pid, t, anchors, deaths, teams, level=lvl)
        total, _ = gold_at(pid, t, frames)
        items = items_at(pid, t, item_events, items_db)
        team = "BLUE" if teams[pid] == 100 else "RED"
        print(f"{champs[pid]:13s} {team:4s} {pos['zone']:22s} {pos['confidence']:9s} "
              f"{lvl:3d} {total:6d}  {', '.join(items[:6]) or '-'}")
        print(f"{'':13s} {'':4s} pos ({pos['x']},{pos['y']})  {pos['note']}")

    lo, hi = t - window, t + window
    nearby = [ev for ev in events
              if lo <= ev["timestamp"] / 1000 <= hi
              and ev.get("type") in ("CHAMPION_KILL", "ELITE_MONSTER_KILL",
                                     "BUILDING_KILL", "TURRET_PLATE_DESTROYED",
                                     "WARD_PLACED", "ITEM_PURCHASED")]
    if nearby:
        print(f"\n## Events within ±{window}s")
        for ev in nearby:
            et = ev["timestamp"] / 1000
            kind = ev["type"]
            who = champs.get(ev.get("killerId") or ev.get("participantId")
                             or ev.get("creatorId"), "?")
            extra = ""
            if kind == "CHAMPION_KILL":
                extra = f"killed {champs.get(ev.get('victimId'), '?')}"
            elif kind == "ELITE_MONSTER_KILL":
                extra = ev.get("monsterType", "")
            elif kind == "ITEM_PURCHASED":
                extra = items_db.get(ev.get("itemId"), {}).get("name", ev.get("itemId"))
            print(f"  {mmss(et)}  {kind:22s} {who:12s} {extra}")


def state_ticks(match, timeline, tick: int, items_db):
    champs, teams, frames, events, anchors, item_events, levelups, deaths = \
        build_player_data(match, timeline)
    duration = timeline["info"]["frames"][-1]["timestamp"] / 1000
    match_id = match["metadata"]["matchId"]
    out_dir = os.path.join(CSV_DIR, match_id)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"state_{tick}s.csv")

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "clock", "participantId", "champion", "team", "x", "y",
                    "zone", "confidence", "level", "totalGold_est", "items"])
        t = 0
        while t <= duration:
            for pid in sorted(champs):
                lvl = level_at(pid, t, frames, levelups)
                pos = position_at(pid, t, anchors, deaths, teams, level=lvl)
                total, _ = gold_at(pid, t, frames)
                items = items_at(pid, t, item_events, items_db)
                w.writerow([t, mmss(t), pid, champs[pid], teams[pid], pos["x"], pos["y"],
                            pos["zone"], pos["confidence"], lvl, total,
                            "|".join(items)])
            t += tick
    n = (int(duration) // tick + 1) * len(champs)
    print(f"Wrote {out} ({n} rows, every {tick}s)")
    conf_counts: dict[str, int] = {}
    with open(out, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conf_counts[row["confidence"]] = conf_counts.get(row["confidence"], 0) + 1
    total_rows = sum(conf_counts.values())
    print("Confidence mix: " + ", ".join(
        f"{k} {100 * v // total_rows}%" for k, v in sorted(conf_counts.items(), key=lambda x: -x[1])))


def main():
    ap = argparse.ArgumentParser(description="Reconstruct map state at any second")
    ap.add_argument("--match", required=True)
    ap.add_argument("--at", help="Timestamp mm:ss (or seconds) for a full state dump")
    ap.add_argument("--tick", type=int, help="Emit a state row every N seconds -> CSV")
    ap.add_argument("--window", type=int, default=20, help="±seconds of event context (--at)")
    args = ap.parse_args()

    match = store.load_match(args.match)
    timeline = store.load_timeline(args.match)
    if match is None or timeline is None:
        print(f"Match/timeline not cached for {args.match} - review or export it first.")
        sys.exit(1)
    items_db = item_map(match["info"]["gameVersion"])

    if args.at:
        state_at(match, timeline, parse_clock(args.at), items_db, args.window)
    elif args.tick:
        state_ticks(match, timeline, args.tick, items_db)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
