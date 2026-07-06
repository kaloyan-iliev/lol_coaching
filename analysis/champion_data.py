"""
Deterministic champion facts from Riot Data Dragon (no API key, no LLM).

Grounds the pregame analyzer: instead of trusting the LLM's pretrained (stale)
champion knowledge, we inject current-patch facts - tags, resource, range,
passive + spell summaries - for all 10 drafted champions, plus the enemy
jungler's Master+ baseline when we have one.

Data is cached in data/ddragon/ per version; one ~10MB download per patch.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

DDRAGON_DIR = os.path.join(config.DATA_DIR, "ddragon")
VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHAMPS_URL = "https://ddragon.leagueoflegends.com/cdn/{v}/data/en_US/championFull.json"

_cache: dict | None = None


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def load_champion_data() -> dict | None:
    """{normalized_name: champion_dict}; None if DDragon is unreachable and no cache."""
    global _cache
    if _cache is not None:
        return _cache

    os.makedirs(DDRAGON_DIR, exist_ok=True)
    data = None
    try:
        import requests
        version = requests.get(VERSIONS_URL, timeout=10).json()[0]
        path = os.path.join(DDRAGON_DIR, f"championFull_{version}.json")
        if not os.path.exists(path):
            print(f"(downloading Data Dragon {version} champion data - one-time per patch)")
            raw = requests.get(CHAMPS_URL.format(v=version), timeout=60).json()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        # Offline: fall back to the newest cached version, if any
        cached = sorted(f for f in os.listdir(DDRAGON_DIR) if f.startswith("championFull_"))
        if cached:
            with open(os.path.join(DDRAGON_DIR, cached[-1]), encoding="utf-8") as f:
                data = json.load(f)
        else:
            print(f"(Data Dragon unavailable: {e} - champion facts will be skipped)")
            return None

    lookup = {}
    for champ in data["data"].values():
        entry = {"version": data.get("version", "?"), **champ}
        lookup[_norm(champ["id"])] = entry
        lookup[_norm(champ["name"])] = entry
    _cache = lookup
    return _cache


def champion_card(name: str) -> str:
    """Compact factual card for one champion, or an explicit UNKNOWN marker."""
    data = load_champion_data()
    champ = data.get(_norm(name)) if data else None
    if champ is None:
        return (f"### {name}\nUNKNOWN champion - not in our current-patch data. State this "
                f"explicitly and give only generic advice for their role. Do NOT substitute "
                f"a similarly-named champion.\n")

    lines = [f"### {champ['name']} - {champ.get('title', '')}"]
    lines.append(f"- Class: {'/'.join(champ.get('tags', []))} | Resource: "
                 f"{champ.get('partype', '?')} | Attack range: "
                 f"{champ.get('stats', {}).get('attackrange', '?')}")
    passive = champ.get("passive", {})
    if passive:
        lines.append(f"- Passive {passive.get('name', '')}: "
                     f"{_strip_html(passive.get('description', ''))[:220]}")
    for key, spell in zip(("Q", "W", "E", "R"), champ.get("spells", [])):
        cd = spell.get("cooldown", [])
        cd_str = f" (CD {cd[0]:.0f}-{cd[-1]:.0f}s)" if cd else ""
        lines.append(f"- {key} {spell.get('name', '')}{cd_str}: "
                     f"{_strip_html(spell.get('description', ''))[:220]}")
    return "\n".join(lines) + "\n"


def draft_facts_block(ours: list[str], enemy: list[str]) -> str | None:
    """Champion fact cards for all 10 drafted champions."""
    data = load_champion_data()
    if data is None:
        return None
    version = next(iter(data.values()))["version"]
    out = [f"# CHAMPION FACTS (Riot Data Dragon, patch data {version} - authoritative; "
           f"prefer these over your own memory of champions)\n"]
    out.append("## Our team\n")
    out.extend(champion_card(c) for c in ours)
    out.append("## Enemy team\n")
    out.extend(champion_card(c) for c in enemy)
    return "\n".join(out)


def _mmss(seconds) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def jungler_baseline_block(champion: str) -> str | None:
    """How Master+ players play this jungler, from our own fetched baseline."""
    path = os.path.join(config.BASELINES_DIR, f"{champion}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        b = json.load(f)

    def med(key, fmt=lambda x: x):
        stat = b.get(key)
        return fmt(stat["median"]) if stat and stat.get("median") is not None else "?"

    return (
        f"# ENEMY JUNGLER TENDENCIES - {b['champion']} at Master+ "
        f"(our own data, n={b['n_games']}, patches {'/'.join(b.get('patches', []))})\n"
        f"- Win rate: {b.get('win_rate', '?')}\n"
        f"- Full clear ends: {med('full_clear_end_s', _mmss)} | first reset: "
        f"{med('first_reset_s', _mmss)} | first gank: {med('first_gank_t_s', _mmss)}\n"
        f"- CS at 10: {med('cs_at_10')} | deaths before 14min: {med('deaths_before_14min')} "
        f"| counter-jungle episodes/game: {med('counter_jungle_episodes')}\n"
        f"- Gank involvements/game: {med('gank_involvements')} | first-objective "
        f"participation: {b.get('first_objective_participation_rate', '?')}\n"
        f"Use these numbers to time the early game plan (e.g. when their first gank "
        f"window opens vs ours).\n"
    )
