"""
Map deterministic game flags to the most relevant Jungle Bible sections.
With 11 fixed sections, a lookup table beats RAG.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

# flag (prefix-matched) -> section keys, most relevant first
FLAG_SECTIONS = {
    "no_early_gank_involvement": ["ganking", "early_game"],
    "died_alone_in_enemy_jungle": ["vision", "pathing"],
    "early_river_death": ["early_game", "pathing"],
    "three_plus_deaths_before_14min": ["mental", "mid_game"],
    "first_dragon_lost_absent": ["objectives"],
    "first_horde_lost_absent": ["objectives"],
    "first_riftherald_lost_absent": ["objectives"],
    "first_baron_nashor_lost_absent": ["objectives", "late_game"],
    "low_cs_at_10": ["clearing", "pathing"],
    "no_control_wards": ["vision"],
    "big_early_gold_deficit_vs_jungler": ["early_game", "pathing"],
    "zero_counter_jungling": ["pathing", "mid_game"],
}

DEFAULT_SECTIONS = ["jungle_fundamentals"]
MAX_SECTIONS = 4


def select_section_keys(flags: list[str]) -> list[str]:
    """Rank sections by how many flags vote for them; cap at MAX_SECTIONS."""
    votes: dict[str, int] = {}
    for flag in flags:
        sections = FLAG_SECTIONS.get(flag)
        if sections is None:
            # prefix match (e.g. future first_<monster>_lost_absent types)
            for known, secs in FLAG_SECTIONS.items():
                if flag.startswith(known.split("_")[0]) and "lost_absent" in flag:
                    sections = secs
                    break
        for weight, key in enumerate(sections or []):
            votes[key] = votes.get(key, 0) + (2 if weight == 0 else 1)

    ranked = sorted(votes, key=votes.get, reverse=True)
    if not ranked:
        ranked = list(DEFAULT_SECTIONS)
    return ranked[:MAX_SECTIONS]


def load_sections(keys: list[str]) -> str:
    """Concatenate the selected section markdown files."""
    parts = []
    for key in keys:
        path = os.path.join(config.KNOWLEDGE_DIR, f"section_{key}.md")
        if os.path.exists(path):
            parts.append(Path(path).read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


def select_sections_for_flags(flags: list[str]) -> tuple[list[str], str]:
    keys = select_section_keys(flags)
    return keys, load_sections(keys)
