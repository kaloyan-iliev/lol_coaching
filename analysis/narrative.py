"""
Turn extracted facts + baseline stats into a compact, LLM-ready fact sheet
(structured-summarization style: overview, metrics vs baseline, chronological
key events). Target: 2-4k tokens.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from analysis.timeline_facts import mmss


def _vs_baseline(value, stat: dict | None, unit: str = "") -> str:
    if value is None:
        return "unknown"
    if not stat:
        return f"{value}{unit}"
    return (f"{value}{unit} (Master+ median {stat['median']}{unit}, "
            f"p25-p75 {stat['p25']}-{stat['p75']}{unit}, n={stat['n']})")


def _fmt_time_stat(value_s, stat: dict | None) -> str:
    if value_s is None:
        return "never"
    if not stat:
        return mmss(value_s)
    return (f"{mmss(value_s)} (Master+ median {mmss(stat['median'])}, "
            f"p25-p75 {mmss(stat['p25'])}-{mmss(stat['p75'])}, n={stat['n']})")


def build_fact_sheet(facts: dict, baseline: dict | None = None) -> str:
    b = baseline or {}
    econ = facts["economy"]
    clear = facts["clear"]

    lines = []
    lines.append("# GAME FACT SHEET (deterministic - extracted from Riot match data)")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Champion: {facts['champion']} jungle ({facts['our_team']} side), "
                 f"result: {'WIN' if facts['win'] else 'LOSS'}, KDA {facts['kda']}")
    lines.append(f"- Duration: {facts['duration_clock']}, patch {facts['game_version']}, "
                 f"enemy jungler: {facts['enemy_jungler']}")
    if b:
        lines.append(f"- Baseline: {b.get('n_games')} Master+ EUW Ekko-jungle games, "
                     f"patches {', '.join(b.get('patches', []))}")

    comps = facts.get("comps")
    if comps:
        lines.append("")
        lines.append("## Draft")
        ours = ", ".join(f"{c['champion']} ({c['role'].lower()})" for c in comps["ours"])
        theirs = ", ".join(f"{c['champion']} ({c['role'].lower()})" for c in comps["enemy"])
        lines.append(f"- Our team: {ours}")
        lines.append(f"- Enemy team: {theirs}")

    lines.append("")
    lines.append("## First clear (inferred from 60s snapshots - times approximate)")
    lines.append(f"- Start: {clear['start']}")
    seq = clear["sequence"][:12]
    if seq:
        steps = ", ".join(
            f"{s['camp']}[{mmss(s['t_window'][0])}-{mmss(s['t_window'][1])}"
            f"{'' if s['confidence'] == 'high' else ', ' + s['confidence'] + ' confidence'}]"
            for s in seq)
        lines.append(f"- Camps: {steps}")
    lines.append(f"- Full clear complete: "
                 f"{_fmt_time_stat(clear['full_clear_end_s'], b.get('full_clear_end_s'))}")

    lines.append("")
    lines.append("## Economy vs Master+ baseline")
    lines.append(f"- CS@10: {_vs_baseline(econ['cs_at_10'], b.get('cs_at_10'))}")
    lines.append(f"- CS@15: {_vs_baseline(econ['cs_at_15'], b.get('cs_at_15'))}")
    lines.append(f"- First kill involvement in a lane (gank): "
                 f"{_fmt_time_stat(econ['first_gank_t'], b.get('first_gank_t_s'))}")
    lines.append(f"- First reset (est. from first shop purchase): "
                 f"{_fmt_time_stat(econ['first_reset_s'], b.get('first_reset_s'))}")
    curve = econ["gold_diff_vs_enemy_jgl_curve"]
    if curve:
        pts = ", ".join(f"{p['clock']}: {p['gold_diff']:+d}g" for p in curve)
        lines.append(f"- Gold diff vs enemy jungler over time: {pts}")

    lines.append("")
    lines.append(f"## Deaths ({len(facts['deaths'])} total"
                 + (f", Master+ median {b['deaths_total']['median']}" if b.get("deaths_total") else "")
                 + ")")
    for d in facts["deaths"]:
        extra = f", flags: {'/'.join(d['flags'])}" if d["flags"] else ""
        ejgl = f", enemy jgl was in {d['enemy_jgl_zone']}" if d.get("enemy_jgl_zone") else ""
        numbers = (f"numbers nearby: {d['allies_nearby']} allies vs {d.get('enemies_nearby', '?')} enemies"
                   if d.get("enemies_nearby") is not None
                   else f"allies within 2500 units: {d['allies_nearby']}")
        gold = (f", gold vs enemy jgl: {d['gold_diff_vs_enemy_jgl']:+d}g"
                if d.get("gold_diff_vs_enemy_jgl") is not None else "")
        lines.append(f"- {d['clock']} killed by {d['killer']} (+{d['assists']} assists) in {d['zone']}, "
                     f"level {d['our_level']}, {numbers}{gold}{ejgl}{extra}")

    lines.append("")
    lines.append(f"## Kill involvement in lanes / ganks ({len(facts['ganks'])}, heuristic: "
                 "only kills are visible, not gank attempts)")
    for g in facts["ganks"]:
        ejgl = f" (enemy jungler was in {g['enemy_jgl_zone']} at the time)" if g.get("enemy_jgl_zone") else ""
        lines.append(f"- {g['clock']} {g['result']} on {g['victim']} in {g['lane']} lane{ejgl}")

    tf = facts.get("teamfights", [])
    lines.append("")
    lines.append(f"## Teamfights / skirmishes ({len(tf)} detected - clusters of 2+ kills, heuristic)")
    for f_ in tf:
        nums = f_["numbers_at_start"]
        lines.append(f"- {f_['clock']} in {f_['zone']}: {f_['result'].upper()} "
                     f"({f_['enemy_deaths']} enemy deaths vs {f_['our_deaths']} ours), "
                     f"numbers at start ~{nums['allies']}v{nums['enemies']} "
                     f"({'we were involved' if f_['we_involved'] else 'we were NOT involved'})")

    obj_names = {
        "HORDE": "HORDE (void grubs)",
        "RIFTHERALD": "RIFTHERALD (Rift Herald)",
        "BARON_NASHOR": "BARON_NASHOR (Baron)",
    }
    lines.append("")
    lines.append("## Objectives (chronological)")
    for o in facts["objectives"]:
        who = "OUR team" if o["team"] == "ally" else "ENEMY team"
        involvement = ("we secured it" if o["we_secured"]
                       else ("we were nearby" if o["we_nearby"] else "we were NOT nearby"))
        sub = f" ({o['subtype']})" if o["subtype"] else ""
        oname = obj_names.get(o["type"], o["type"])
        lines.append(f"- {o['clock']} {who} took {oname}{sub} - {involvement}; "
                     f"{o['kills_60s_before']} kills in the 60s before")

    lines.append("")
    lines.append(f"## Counter-jungling ({len(facts['counter_jungle'])} episodes detected, heuristic)")
    for c in facts["counter_jungle"][:8]:
        lines.append(f"- ~{c['clock']} in {c['zone']}: +{c['jungle_cs_gained']} jungle cs")

    v = facts["vision"]
    lines.append("")
    lines.append("## Vision")
    lines.append(f"- Wards placed: {_vs_baseline(v['wards_placed'], b.get('wards_placed'))}, "
                 f"control wards: {_vs_baseline(v['control_wards'], b.get('control_wards'))}, "
                 f"wards killed: {_vs_baseline(v['wards_killed'], b.get('wards_killed'))}")

    lines.append("")
    lines.append("## Automatic flags (deterministic triggers, not judgments)")
    for flag in facts["flags"]:
        lines.append(f"- {flag}")

    return "\n".join(lines)
