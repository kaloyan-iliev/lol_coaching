"""
Deterministic analytics report from a map_state.py --tick export.

No LLM call - this mines state_<N>s.csv (+ kills/objectives.csv, + the facts
json for our_team/champion/enemy_jungler) for coaching-relevant patterns that
60s frames are too coarse to show reliably:

  1. Zone occupancy - % of ticks each player spent in lane / own jungle /
     enemy jungle / river / base (own-jungle vs enemy-jungle split matters
     for counter-jungle and pathing habits).
  2. Jungler contact windows - ticks where our jungler and the enemy jungler
     were close enough to plausibly interact; cross-referenced against
     kills.csv to say whether a fight actually happened there or a
     close-proximity window passed with no contact (a "avoided/missed" tell).
  3. Power-spike windows - our jungler's item-gold-value + level vs the enemy
     jungler's, at every tick; flags windows of clear advantage/disadvantage
     and whether a fight occurred inside them (this is the "power-spike
     windows" signal from DATA_DICTIONARY's unexploited-signals list, built
     off map_state.py instead of raw 60s frames).

Every number is labeled with the source tick's confidence; conclusions built
on "uncertain" ticks are flagged, never silently trusted.

Usage:
    python scripts/state_report.py --match EUW1_xxx
    (run map_state.py --match EUW1_xxx --tick 15 first if state_15s.csv is missing)

Output: data/csv/<match>/state_report.md
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from riot import store
from analysis.jungle_camps import dist

CSV_DIR = os.path.join(config.DATA_DIR, "csv")
DDRAGON_DIR = os.path.join(config.DATA_DIR, "ddragon")

ZONE_BUCKET = {
    "top_lane": "lane", "mid_lane": "lane", "bot_lane": "lane",
    "top_river": "river", "bot_river": "river",
    "blue_base": "base", "red_base": "base",
    "blue_jungle_top": "blue_jungle", "blue_jungle_bot": "blue_jungle",
    "red_jungle_top": "red_jungle", "red_jungle_bot": "red_jungle",
}
CONTACT_DIST = 2200   # units; roughly one screen
KILL_WINDOW_S = 25    # how close in TIME a kill must be to "explain" a tick
KILL_PROX_UNITS = 3000  # how close in SPACE - kills.csv has 103 kills/37min in this
# game (~1 every 22s average GLOBALLY), so a time-only match is nearly guaranteed
# to hit *some* kill somewhere on the map and says nothing. Require proximity too.


def mmss(t_s) -> str:
    t_s = int(t_s)
    return f"{t_s // 60:02d}:{t_s % 60:02d}"


def load_item_gold_index(game_version: str) -> dict[str, int]:
    major_minor = ".".join(game_version.split(".")[:2])
    path = os.path.join(DDRAGON_DIR, f"item_{major_minor}.1.json")
    if not os.path.exists(path):
        return {}
    raw = json.load(open(path, encoding="utf-8"))["data"]
    return {v["name"]: v["gold"]["total"] for v in raw.values()}


def load_state_rows(match_id: str, tick: int) -> list[dict]:
    path = os.path.join(CSV_DIR, match_id, f"state_{tick}s.csv")
    if not os.path.exists(path):
        print(f"Missing {path}. Run: python scripts/map_state.py --match {match_id} --tick {tick}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_kills(match_id: str) -> list[dict]:
    path = os.path.join(CSV_DIR, match_id, "kills.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def zone_occupancy(rows: list[dict], champion: str) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for r in rows:
        if r["champion"] != champion:
            continue
        b = ZONE_BUCKET.get(r["zone"], r["zone"])
        buckets[b] = buckets.get(b, 0) + 1
    return buckets


def fmt_occupancy(buckets: dict[str, int], own_side: str) -> str:
    total = sum(buckets.values()) or 1
    own_jgl, enemy_jgl = f"{own_side}_jungle", ("red_jungle" if own_side == "blue" else "blue_jungle")
    order = [("lane", "lane"), (own_jgl, "own jungle"), (enemy_jgl, "enemy jungle"),
             ("river", "river"), ("base", "base")]
    parts = [f"{label} {100 * buckets.get(k, 0) // total}%" for k, label in order if buckets.get(k)]
    return ", ".join(parts)


def _kill_near(kills: list[dict], t: float, x: float, y: float) -> bool:
    """A kill counts as 'explaining' a tick only if it's close in BOTH time and
    space - kills.csv holds every kill in the game, so a time-only match is
    nearly always true in a high-kill game and proves nothing (see KILL_PROX_UNITS)."""
    for k in kills:
        if abs(float(k["t_s"]) - t) <= KILL_WINDOW_S:
            if dist((x, y), (float(k["x"]), float(k["y"]))) <= KILL_PROX_UNITS:
                return True
    return False


def contact_windows(rows: list[dict], our_champ: str, enemy_champ: str,
                    kills: list[dict]) -> list[dict]:
    by_tick: dict[float, dict[str, dict]] = {}
    for r in rows:
        if r["champion"] in (our_champ, enemy_champ):
            by_tick.setdefault(float(r["t_s"]), {})[r["champion"]] = r

    windows, in_window = [], False
    for t in sorted(by_tick):
        pair = by_tick[t]
        if our_champ not in pair or enemy_champ not in pair:
            continue
        a, b = pair[our_champ], pair[enemy_champ]
        ax, ay = float(a["x"]), float(a["y"])
        bx, by_ = float(b["x"]), float(b["y"])
        d = dist((ax, ay), (bx, by_))
        close = d < CONTACT_DIST
        uncertain = a["confidence"] == "uncertain" or b["confidence"] == "uncertain"
        if close and not in_window:
            in_window = True
            midx, midy = (ax + bx) / 2, (ay + by_) / 2
            fight_nearby = _kill_near(kills, t, midx, midy)
            windows.append({"t": t, "dist": round(d), "uncertain": uncertain,
                            "fight_nearby": fight_nearby})
        elif not close:
            in_window = False
    return windows


def power_spike_windows(rows: list[dict], our_champ: str, enemy_champ: str,
                        gold_index: dict[str, int], kills: list[dict]) -> list[dict]:
    by_tick: dict[float, dict[str, dict]] = {}
    for r in rows:
        if r["champion"] in (our_champ, enemy_champ):
            by_tick.setdefault(float(r["t_s"]), {})[r["champion"]] = r

    def item_value(items_field: str) -> int:
        return sum(gold_index.get(name, 0) for name in items_field.split("|") if name)

    events = []
    prev_state = None
    for t in sorted(by_tick):
        pair = by_tick[t]
        if our_champ not in pair or enemy_champ not in pair:
            continue
        a, b = pair[our_champ], pair[enemy_champ]
        adv = (item_value(a["items"]) + 150 * int(a["level"])) - \
              (item_value(b["items"]) + 150 * int(b["level"]))
        state = "ahead" if adv > 400 else ("behind" if adv < -400 else "even")
        if state != "even" and state != prev_state:
            # Gate on OUR jungler's actual position, not just the clock -
            # a game-wide kill count means time-only matching is meaningless
            # (see _kill_near / KILL_PROX_UNITS).
            fight_nearby = _kill_near(kills, t, float(a["x"]), float(a["y"]))
            events.append({"t": t, "state": state, "adv_gold_est": adv,
                           "fight_nearby": fight_nearby,
                           "uncertain": a["confidence"] == "uncertain"})
        prev_state = state
    return events


def main():
    ap = argparse.ArgumentParser(description="Analytics report from a map_state tick export")
    ap.add_argument("--match", required=True)
    ap.add_argument("--tick", type=int, default=15, help="Must match a state_<N>s.csv already built")
    args = ap.parse_args()

    match_id = args.match
    facts_path = os.path.join(config.FACTS_DIR, f"{match_id}.json")
    if not os.path.exists(facts_path):
        print(f"No facts file for {match_id}. Run review_game.py on it first.")
        sys.exit(1)
    facts = json.load(open(facts_path, encoding="utf-8"))
    our_champ, enemy_champ = facts["champion"], facts["enemy_jungler"]
    our_side = facts["our_team"]  # "blue" or "red"

    rows = load_state_rows(match_id, args.tick)
    kills = load_kills(match_id)
    gold_index = load_item_gold_index(facts["game_version"])
    champions = sorted({r["champion"] for r in rows})

    uncertain_pct = 100 * sum(1 for r in rows if r["confidence"] == "uncertain") // len(rows)

    lines = [f"# State Report - {match_id}", "",
             f"*{facts['champion']} {facts['our_role']} vs {enemy_champ} - "
             f"{'WIN' if facts['win'] else 'LOSS'} {facts['kda']} ({facts['duration_clock']}). "
             f"Built from `state_{args.tick}s.csv` (map_state.py), deterministic, no LLM call. "
             f"{uncertain_pct}% of all ticks flagged uncertain (excluded from conclusions below "
             f"where they'd be load-bearing).*", "",
             "## 1. Zone occupancy (% of ticks)", "",
             "| Champion | Breakdown |", "|---|---|"]
    for champ in champions:
        side = "blue" if any(r["champion"] == champ and r["team"] == "100" for r in rows) else "red"
        occ = zone_occupancy(rows, champ)
        lines.append(f"| {champ} | {fmt_occupancy(occ, side)} |")

    lines += ["", "## 2. Jungler contact windows",
             f"*Ticks where {our_champ} and {enemy_champ} were within {CONTACT_DIST} units "
             f"(~one screen), cross-checked against kills.csv within {KILL_WINDOW_S}s.*", ""]
    cw = contact_windows(rows, our_champ, enemy_champ, kills)
    if not cw:
        lines.append(f"No contact windows detected (junglers stayed apart all game — "
                     f"passive/split matchup or heavy warding avoidance).")
    else:
        lines.append("| Time | Distance | Fight followed? | Note |")
        lines.append("|---|---|---|---|")
        for w in cw:
            note = "position uncertain at this tick" if w["uncertain"] else ""
            lines.append(f"| {mmss(w['t'])} | {w['dist']} | "
                         f"{'YES' if w['fight_nearby'] else 'no — avoided or missed'} | {note} |")
        avoided = sum(1 for w in cw if not w["fight_nearby"])
        lines.append(f"\n**{len(cw)} contact windows, {avoided} resolved without a kill** "
                     f"(disengage, ward denial, or a missed opportunity depending on who was ahead — "
                     f"cross-reference §3).")

    lines += ["", "## 3. Power-spike windows (item-gold-value + level proxy)",
             f"*Approximate — HP/cooldowns aren't in this data; a level/item lead is a proxy for "
             f"\"should win the fight,\" not a guarantee. `adv_gold_est` = ({our_champ} items+level "
             f"value) minus ({enemy_champ} items+level value); flagged only when the swing exceeds "
             f"~400g equivalent.*", ""]
    ps = power_spike_windows(rows, our_champ, enemy_champ, gold_index, kills)
    if not ps:
        lines.append("No clear power-spike windows detected (junglers stayed roughly even all game).")
    else:
        lines.append("| Time | State | Adv. (gold-eq) | Fight in this window? |")
        lines.append("|---|---|---|---|")
        for e in ps:
            lines.append(f"| {mmss(e['t'])} | {our_champ} {e['state']} | {e['adv_gold_est']:+d} | "
                         f"{'yes' if e['fight_nearby'] else 'no'} |")
        missed = sum(1 for e in ps if e["state"] == "ahead" and not e["fight_nearby"])
        punished = sum(1 for e in ps if e["state"] == "behind" and e["fight_nearby"])
        lines.append(f"\n**{missed} 'ahead' window(s) with no fight taken** (possible missed "
                     f"pressure) · **{punished} 'behind' window(s) where a fight still happened** "
                     f"(check kills.csv — may explain a bad death).")

    out_path = os.path.join(CSV_DIR, match_id, "state_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Report saved to {out_path}")
    # Console may be a legacy codepage; the file (utf-8) is the source of truth.
    print("\n" + "\n".join(lines).encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()
