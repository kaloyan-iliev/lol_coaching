"""
Pre-game draft analyzer CLI: paste both drafts, get the one-glance game plan.

Usage:
    python scripts/pregame.py --ours "Aatrox,Ekko,Ahri,Jinx,Leona" --enemy "Darius,LeeSin,Sylas,Caitlyn,Thresh"
    python scripts/pregame.py --ours "..." --enemy "..." --notes "their mid is smurfing" --no-save

Champion order is by role: Top, Jungle, Mid, Bot, Support.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.pregame import run_pregame, save_pregame


def main():
    parser = argparse.ArgumentParser(description="Pre-game draft analysis -> game-plan card")
    parser.add_argument("--ours", required=True, help="Our 5 champions, comma-separated (Top,Jgl,Mid,Bot,Sup)")
    parser.add_argument("--enemy", required=True, help="Enemy 5 champions, comma-separated (Top,Jgl,Mid,Bot,Sup)")
    parser.add_argument("--notes", default=None, help="Optional context (e.g. 'enemy top is a one-trick')")
    parser.add_argument("--no-save", action="store_true", help="Print only, don't save to data/pregame/")
    parser.add_argument("--show-prompt", action="store_true",
                        help="Print the assembled prompt and exit (no LLM call)")
    args = parser.parse_args()

    ours = args.ours.split(",")
    enemy = args.enemy.split(",")

    if args.show_prompt:
        from app.pregame import build_pregame_prompt
        print(build_pregame_prompt(ours, enemy, args.notes))
        return

    print("Generating game plan (1 LLM call)...")
    card = run_pregame(ours, enemy, args.notes)

    print("\n" + "=" * 70 + "\n")
    print(card)
    print("\n" + "=" * 70)

    if not args.no_save:
        path = save_pregame(card, ours, enemy)
        print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
