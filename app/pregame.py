"""
Pre-game draft analyzer: both team comps in -> one-glance game-plan card out.
Shared by scripts/pregame.py (CLI) and the Streamlit "Pre-Game Draft" tab.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from analysis.section_select import load_sections

ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"]
PREGAME_SECTIONS = ["matchups", "ganking", "objectives", "late_game"]

SYSTEM_PROMPT = Path(
    os.path.join(os.path.dirname(__file__), "prompts", "pregame_prompt.txt")
).read_text(encoding="utf-8")


def _clean(names: list[str]) -> list[str]:
    return [n.strip().title() for n in names if n.strip()]


def build_pregame_prompt(ours: list[str], enemy: list[str], notes: str | None = None) -> str:
    """User prompt: house rules > coaching knowledge > the draft."""
    from app.llm_client import load_house_rules

    ours, enemy = _clean(ours), _clean(enemy)
    if len(ours) != 5 or len(enemy) != 5:
        raise ValueError(f"Need exactly 5 champions per team (got {len(ours)} vs {len(enemy)})")

    draft = "\n".join(
        f"- {role}: {o} vs {e}" for role, o, e in zip(ROLES, ours, enemy)
    )

    house_rules = load_house_rules()
    house_block = (
        f"# HOUSE RULES (the player's own principles - these OVERRIDE everything below)\n\n"
        f"{house_rules}\n\n---\n\n"
    ) if house_rules else ""

    sections_text = load_sections(PREGAME_SECTIONS)
    notes_block = f"\nPlayer notes: {notes}\n" if notes else ""

    # Deterministic grounding: current-patch champion facts + enemy jungler baseline
    from analysis.champion_data import draft_facts_block, jungler_baseline_block
    facts = draft_facts_block(ours, enemy)
    facts_block = f"{facts}\n\n---\n\n" if facts else ""
    enemy_jgl = jungler_baseline_block(enemy[1])
    enemy_jgl_block = f"{enemy_jgl}\n---\n\n" if enemy_jgl else ""

    return (
        f"{house_block}"
        f"# COACHING KNOWLEDGE (sections: {', '.join(PREGAME_SECTIONS)})\n\n"
        f"{sections_text}\n\n---\n\n"
        f"{facts_block}"
        f"{enemy_jgl_block}"
        f"# THE DRAFT (our champion vs enemy champion per role)\n"
        f"The player is the JUNGLER on our team ({ours[1]}).\n\n"
        f"{draft}\n"
        f"{notes_block}\n"
        f"Produce the game-plan card now, following the output format exactly."
    )


def run_pregame(ours: list[str], enemy: list[str], notes: str | None = None,
                model: str | None = None) -> str:
    """One LLM call -> game-plan card markdown."""
    from app.llm_client import generate_text

    prompt = build_pregame_prompt(ours, enemy, notes)
    return generate_text(prompt, system=SYSTEM_PROMPT, temperature=0.4, max_tokens=6000,
                         model=model)


def save_pregame(card_md: str, ours: list[str], enemy: list[str]) -> str:
    """Save the card to data/pregame/; returns the path."""
    ours, enemy = _clean(ours), _clean(enemy)
    os.makedirs(config.PREGAME_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{stamp}_{ours[1]}_vs_{enemy[1]}.md"
    path = os.path.join(config.PREGAME_DIR, fname)
    header = (
        f"# Pre-Game Plan: {' / '.join(ours)}\n"
        f"### vs {' / '.join(enemy)}\n\n---\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + card_md)
    return path
