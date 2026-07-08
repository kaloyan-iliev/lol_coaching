"""
LLM-as-judge for coaching reviews - the quality-measurement loop.

The tripwires prove a review doesn't INVENT facts; they say nothing about whether
its Top-3 mistakes are the RIGHT three, or whether a bible/prompt change made
reviews better or worse. This script closes that gap.

Design choices that matter (naive judge loops produce confident garbage):
  * The judge runs a DIFFERENT model than the generator (config.JUDGE_MODEL) to
    cut self-preference bias.
  * Comparisons are PAIRWISE (LLMs judge "A vs B" far better than "score 1-10"),
    and every pair is judged in BOTH orderings; a side only "wins" if it wins
    both, else it's a tie (kills position bias).
  * The fact sheet is handed to the judge as GROUND TRUTH; contradicting it is
    the heaviest penalty. Length and formatting are explicitly not rewarded.
  * Optional human calibration: knowledge/judge_anchors.md (if present) is fed
    as few-shot so the judge inherits YOUR taste, not its own.

Modes:
  --regression [--account NAME] [--limit N]
        For each stored review: rebuild facts from the cached match, regenerate a
        review with the CURRENT pipeline, judge new-vs-stored. Reports win-rate +
        per-criterion tallies. This is the "did my change help?" tool.
  --score PATH            Absolute rubric score (1-5 per criterion) of one review.
  --score-account NAME    Score every review under data/reviews/<NAME>/, tabulated.
  --pair FILE_A FILE_B    Head-to-head judge two reviews of the same game.

LLM cost: 2 judge calls per pair (both orderings); regression also spends 1
generator call per game. All free-tier friendly on gemini-3-flash/3.5-flash.
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import config
from riot import store
from analysis.timeline_facts import extract_facts
from analysis.narrative import build_fact_sheet
from review_game import generate_review_text, load_baseline

CRITERIA = {
    "prioritization": "Are the Top-3 mistakes the MOST game-deciding ones present in "
                      "the fact sheet? (missing the biggest mistake is the worst failure)",
    "grounding": "Is every claim traceable to the fact sheet, with no invented or "
                 "contradicted facts?",
    "actionability": "Are the fixes concrete and drillable, versus vague ('play better')?",
    "methodology": "Does it apply real coaching concepts (and label meta claims not "
                   "grounded in the provided knowledge)?",
    "specificity": "Is the advice specific to THIS game state rather than generic tips?",
}
ANCHORS_FILE = os.path.join(config.KNOWLEDGE_DIR, "judge_anchors.md")
JUDGE_DIR = os.path.join(config.REVIEWS_DIR, "_judge")


# --- Parsing stored reviews -------------------------------------------------

def parse_review(md: str) -> tuple[str, str | None]:
    """(review_body, embedded_fact_sheet_or_None) from a stored review .md."""
    fact_sheet = None
    m = re.search(r"<details>.*?Fact sheet used</summary>\s*(.*?)\s*</details>",
                  md, re.DOTALL)
    if m:
        fact_sheet = m.group(1).strip()
    body = re.split(r"\n---\n\n<details>", md, maxsplit=1)[0]
    body = re.sub(r"^# Game Review:.*?\n\n", "", body, count=1, flags=re.DOTALL).strip()
    return body, fact_sheet


def stored_reviews(account: str | None = None) -> list[tuple[str, str]]:
    """(match_id, path) for every per-game review on disk, optionally one account."""
    root = config.REVIEWS_DIR
    if account:
        root = os.path.join(root, account)
    out = []
    for path in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        name = os.path.basename(path)
        if name.startswith("account_recap") or os.sep + "_judge" + os.sep in path:
            continue
        m = re.match(r"([A-Z0-9]+_\d+)\.md", name)
        if m:
            out.append((m.group(1), path))
    return out


def puuid_for_review(match: dict, review_md: str) -> str | None:
    """Recover the reviewed player's puuid by matching the champion named in the
    stored review's fact sheet against the match participants."""
    _, fs = parse_review(review_md)
    if not fs:
        return None
    # Fact sheet Overview line: "- Champion: Ekko jungle (blue side), ..."
    m = re.search(r"Champion:\s*([A-Za-z' .]+?)\s+jungle", fs)
    if not m:
        return None
    champ = m.group(1).strip()
    p = next((p for p in match["info"]["participants"]
              if p.get("championName") == champ), None)
    return p["puuid"] if p else None


# --- The judge ---------------------------------------------------------------

def _anchors_block() -> str:
    if os.path.exists(ANCHORS_FILE):
        text = Path(ANCHORS_FILE).read_text(encoding="utf-8").strip()
        if text and not text.startswith("<!-- TEMPLATE"):
            return ("\n\nCALIBRATION - the human coach graded these examples; match "
                    f"their judgement:\n{text}\n")
    return ""


def _judge_call(prompt: str, model: str | None) -> dict:
    from app.llm_client import generate_text
    raw = generate_text(prompt, temperature=0.0, max_tokens=2000, json_mode=True,
                        model=model or config.JUDGE_MODEL)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[s:e])


def judge_pair_once(fact_sheet: str, review_a: str, review_b: str,
                    model: str | None) -> dict:
    crit_lines = "\n".join(f"- {k}: {v}" for k, v in CRITERIA.items())
    prompt = f"""You are a meticulous head coach evaluating two League of Legends
jungle game reviews (A and B) of the SAME game. The FACT SHEET below is ground
truth extracted deterministically from the Riot API.

Judge on these criteria:
{crit_lines}

Hard rules:
- A claim that CONTRADICTS the fact sheet is the heaviest penalty.
- Do NOT reward length or nicer formatting. A concise correct review beats a long one.
- The single most important criterion is prioritization: did it surface the
  mistakes that actually decided the game?
{_anchors_block()}
=== FACT SHEET (ground truth) ===
{fact_sheet}

=== REVIEW A ===
{review_a}

=== REVIEW B ===
{review_b}

Return ONLY JSON:
{{"per_criterion": {{{", ".join(f'"{k}": "A"|"B"|"tie"' for k in CRITERIA)}}},
  "winner": "A"|"B"|"tie",
  "reason": "one or two sentences citing the deciding difference"}}"""
    return _judge_call(prompt, model)


def judge_pair(fact_sheet: str, old: str, new: str, model: str | None) -> dict:
    """Judge OLD vs NEW in both orderings; 'new'/'old'/'tie' only when consistent."""
    r1 = judge_pair_once(fact_sheet, old, new, model)   # A=old, B=new
    time.sleep(6)
    r2 = judge_pair_once(fact_sheet, new, old, model)   # A=new, B=old

    def side(r, a_is):  # map an A/B/tie verdict to old/new/tie
        w = r.get("winner", "tie")
        return a_is if w == "A" else ("new" if a_is == "old" else "old") if w == "B" else "tie"

    v1, v2 = side(r1, "old"), side(r2, "new")
    winner = v1 if v1 == v2 else "tie"  # disagreement across orderings = position bias
    crit = {}
    for k in CRITERIA:
        c1 = side({"winner": r1["per_criterion"].get(k, "tie")}, "old")
        c2 = side({"winner": r2["per_criterion"].get(k, "tie")}, "new")
        crit[k] = c1 if c1 == c2 else "tie"
    return {"winner": winner, "per_criterion": crit,
            "reasons": [r1.get("reason", ""), r2.get("reason", "")],
            "position_bias": v1 != v2}


def score_review(fact_sheet: str, review: str, model: str | None) -> dict:
    crit_lines = "\n".join(f"- {k}: {v}" for k, v in CRITERIA.items())
    prompt = f"""You are a meticulous head coach scoring one jungle game review
against the FACT SHEET (ground truth from the Riot API). Score each criterion 1-5
(5 = excellent, 1 = poor). A claim contradicting the fact sheet caps grounding at 2.
Do not reward length.

Criteria:
{crit_lines}
{_anchors_block()}
=== FACT SHEET (ground truth) ===
{fact_sheet}

=== REVIEW ===
{review}

Return ONLY JSON:
{{"scores": {{{", ".join(f'"{k}": 1-5' for k in CRITERIA)}}},
  "overall": 1-5, "one_line": "the single biggest thing to improve"}}"""
    return _judge_call(prompt, model)


# --- Modes -------------------------------------------------------------------

def do_regression(account: str | None, limit: int | None, model: str | None):
    games = stored_reviews(account)
    if limit:
        games = games[:limit]
    if not games:
        print("No stored reviews found to regress against.")
        return

    print(f"Regression: {len(games)} games | generator={config.TEXT_MODEL} "
          f"| judge={model or config.JUDGE_MODEL}\n")
    tally = {"new": 0, "old": 0, "tie": 0}
    crit_tally = {k: {"new": 0, "old": 0, "tie": 0} for k in CRITERIA}
    rows, biased = [], 0

    for i, (match_id, path) in enumerate(games, 1):
        md = Path(path).read_text(encoding="utf-8")
        old_body, _ = parse_review(md)
        match, timeline = store.load_match(match_id), store.load_timeline(match_id)
        if match is None or timeline is None:
            print(f"[{i}/{len(games)}] {match_id}: match/timeline not cached, skip")
            continue
        puuid = puuid_for_review(match, md)
        if not puuid:
            print(f"[{i}/{len(games)}] {match_id}: could not recover puuid, skip")
            continue

        facts = extract_facts(match, timeline, puuid)
        fact_sheet = build_fact_sheet(facts, load_baseline(facts["champion"]))
        new_body, _ = generate_review_text(facts, fact_sheet, verbose=False)
        time.sleep(6)
        v = judge_pair(fact_sheet, old_body, new_body, model)

        tally[v["winner"]] += 1
        for k, s in v["per_criterion"].items():
            crit_tally[k][s] += 1
        biased += v["position_bias"]
        rows.append((match_id, v))
        print(f"[{i}/{len(games)}] {match_id}: {v['winner'].upper()}"
              f"{'  (position-biased -> tie)' if v['position_bias'] else ''}")
        time.sleep(6)

    n = sum(tally.values())
    print("\n" + "=" * 60)
    print(f"NEW wins {tally['new']}/{n} | OLD wins {tally['old']} | tie {tally['tie']}"
          f"  ({biased} inconclusive from position bias)")
    print("Per criterion (new/old/tie):")
    for k, t in crit_tally.items():
        print(f"  {k:15s} {t['new']}/{t['old']}/{t['tie']}")

    os.makedirs(JUDGE_DIR, exist_ok=True)
    out = os.path.join(JUDGE_DIR, f"regression_{date.today().isoformat()}.md")
    lines = [f"# Judge Regression - {date.today().isoformat()}", "",
             f"Generator `{config.TEXT_MODEL}` vs stored reviews, judged by "
             f"`{model or config.JUDGE_MODEL}` (pairwise, both orderings).", "",
             f"**NEW {tally['new']} / OLD {tally['old']} / tie {tally['tie']}** "
             f"(n={n}, {biased} position-biased).", "",
             "| Game | Winner | Deciding reason |", "|---|---|---|"]
    for match_id, v in rows:
        lines.append(f"| {match_id} | {v['winner']} | {v['reasons'][0][:140]} |")
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport: {out}")


def do_score(path: str, model: str | None):
    md = Path(path).read_text(encoding="utf-8")
    body, fs = parse_review(md)
    if not fs:
        print("No embedded fact sheet in that review - cannot score without ground truth.")
        return
    r = score_review(fs, body, model)
    print(f"\n{os.path.basename(path)}  (judge={model or config.JUDGE_MODEL})")
    for k, s in r.get("scores", {}).items():
        print(f"  {k:15s} {s}/5")
    print(f"  {'OVERALL':15s} {r.get('overall', '?')}/5")
    print(f"  -> {r.get('one_line', '')}")


def do_score_account(account: str, model: str | None):
    games = stored_reviews(account)
    if not games:
        print(f"No reviews under data/reviews/{account}/")
        return
    print(f"Scoring {len(games)} reviews for {account} (judge={model or config.JUDGE_MODEL})\n")
    totals = {k: 0 for k in CRITERIA}
    overalls, n = 0, 0
    for match_id, path in games:
        body, fs = parse_review(Path(path).read_text(encoding="utf-8"))
        if not fs:
            continue
        r = score_review(fs, body, model)
        sc = r.get("scores", {})
        for k in CRITERIA:
            totals[k] += sc.get(k, 0)
        overalls += r.get("overall", 0)
        n += 1
        print(f"  {match_id}  overall {r.get('overall','?')}/5  {r.get('one_line','')[:70]}")
        time.sleep(6)
    if n:
        print("\nAverages:")
        for k in CRITERIA:
            print(f"  {k:15s} {totals[k]/n:.1f}/5")
        print(f"  {'OVERALL':15s} {overalls/n:.1f}/5")


def do_pair(file_a: str, file_b: str, model: str | None):
    a_body, a_fs = parse_review(Path(file_a).read_text(encoding="utf-8"))
    b_body, _ = parse_review(Path(file_b).read_text(encoding="utf-8"))
    if not a_fs:
        print("First review has no embedded fact sheet to use as ground truth.")
        return
    v = judge_pair(a_fs, a_body, b_body, model)  # A treated as 'old', B as 'new'
    label = {"old": os.path.basename(file_a), "new": os.path.basename(file_b),
             "tie": "tie"}[v["winner"]]
    print(f"\nWinner: {label}" + ("  (position-biased -> inconclusive)"
                                  if v["position_bias"] else ""))
    print("Per criterion:", v["per_criterion"])
    for r in v["reasons"]:
        print(" -", r)


def main():
    ap = argparse.ArgumentParser(description="LLM-as-judge for coaching reviews")
    ap.add_argument("--regression", action="store_true",
                    help="Regenerate reviews with the current pipeline and judge vs stored")
    ap.add_argument("--account", help="Limit to one account folder")
    ap.add_argument("--limit", type=int, help="Cap number of games (regression)")
    ap.add_argument("--score", metavar="PATH", help="Absolute-score one review file")
    ap.add_argument("--score-account", metavar="NAME", help="Score all of an account's reviews")
    ap.add_argument("--pair", nargs=2, metavar=("A", "B"), help="Head-to-head two reviews")
    ap.add_argument("--model", help="Override judge model (default config.JUDGE_MODEL)")
    args = ap.parse_args()

    if args.regression:
        do_regression(args.account, args.limit, args.model)
    elif args.score:
        do_score(args.score, args.model)
    elif args.score_account:
        do_score_account(args.score_account, args.model)
    elif args.pair:
        do_pair(args.pair[0], args.pair[1], args.model)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
