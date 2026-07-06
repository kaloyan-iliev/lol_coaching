# Executive Summary — LoL Jungle Coach

*Updated 2026-07-05. The single entry point for reviewing this project: what exists,
what it's worth, what's decided, what's still open — with links into every document.*

## What this is, in three sentences

A personal AI jungle coach that reviews League games like a human VOD reviewer: it
synthesizes trusted coaches' YouTube content into a knowledge base, reduces Riot API
match data into deterministic per-game facts benchmarked against 500 Master+ games, and
produces timestamped, hallucination-checked coaching — per game, across your last 20
games, and before the game (draft plans). An approved plan exists to productize it as a
freemium Discord bot ($4.99/mo). Its differentiator vs iTero/Mobalytics: narrative
coaching grounded in named methodology **paired with deterministic fact-checking** —
dashboards tell you what your numbers were; this tells you what to change and proves it
didn't make anything up.

## State snapshot (2026-07-05)

| Area | State |
|---|---|
| Knowledge base | 93 videos / 3 coaches → Jungle Bible ~34k words; per-coach bibles + disagreement report (generation completing in background) |
| Baselines | Generic n=500 + 22 per-champion (Ekko 55, LeeSin 28, Qiyana 25, …) — any jungler reviewable |
| Review features | Single-game review (timestamp tripwire) · **20-game account recap** (pattern analysis + retrospective drafts, zero grounding warnings) · pregame draft cards · screenshot coach/Q&A (Streamlit) |
| Ingestion tooling | `data/video_catalog.csv` (2,052 videos, 7 channels) + one-command `ingest_videos.py` |
| LLM providers | Gemini (free, 20 req/day/model — real constraint) + OpenRouter backup; paid key present but unwired by choice |
| Business | Discord-bot SaaS plan approved; M0 (Riot registration) not started; repo pushed (de7d203) |

## Reading order for a thorough review

1. **[docs/HANDOVER.md](docs/HANDOVER.md)** — the resume-here doc. §2 command table
   (everything that runs today), §3 hard-won Riot-data insights, §6 honest critique
   (items 5/10/12 now fixed), §7 open questions, §8 next steps. *Review focus: does the
   critique list match your own sense of the weak spots?*
2. **[ROADMAP.md](ROADMAP.md)** — what's built (v1/v2/v3) and the prioritized next steps.
   *Review focus: next-steps order — curation pass and golden-question evals are ranked
   above everything; agree?*
3. **[docs/KB_STRATEGY.md](docs/KB_STRATEGY.md)** — the curation playbook: source tiers,
   how dedup/distillation works, integrity mechanisms, VOD-vs-guide policy, saturation
   signals, why not RAG (yet). *Review focus: the tier policy in §1 — you apply it when
   picking PerryJG/Veigarv2 videos in the catalog.*
4. **[docs/BUSINESS_PLAN.md](docs/BUSINESS_PLAN.md)** — verified Riot policy constraints,
   unit economics ($0.01/review, break-even 4 subs), milestones M0–M8, go-to-market,
   risks (coach-IP is #1). *Review focus: the user-only actions — Riot registration,
   domain/name, coach outreach emails — all still yours to start.*
5. **[docs/SESSION_2026-07-04.md](docs/SESSION_2026-07-04.md)** — the last two days in
   detail: what was built, quota discoveries, exact commands for the queue.
6. **Reference docs:** [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) (every Riot
   field we exploit + unexploited signals) · [docs/CSV_TABLES_GUIDE.md](docs/CSV_TABLES_GUIDE.md)
   (per-game CSV tables) · [README.md](README.md) (setup + script reference) ·
   [FULL_PLAN.md](FULL_PLAN.md) / [MVP_PLAN.md](MVP_PLAN.md) (historical vision, status
   banners on top).

## Generated artifacts worth reviewing (the product itself)

- **Your 20-game recap**: `data/reviews/account_recap_ReaperOfMars_Drrw_2026-07-04.md` —
  verdict: builds early leads, fails to convert. Check: are the Top-5 recurring problems
  the RIGHT ones? Every disagreement → a house rule.
- **Smurf single-game review**: `data/reviews/EUW1_7909606924.md` (clean tripwire).
- **The Jungle Bible**: `knowledge/jungle_bible.md` (+ `jungle_bible_kireilol.md`,
  `jungle_bible_junglegapgg.md`) — spot-read a section you know well.
- **Coach disagreements**: `knowledge/coach_disagreements.md` — kept separate from the
  bible; merging is YOUR pending decision.
- **Video catalog**: `data/video_catalog.csv` — the curation worksheet.

## The plan from here (condensed)

1. **Curation pass** (you, ~1h): tier + pick PerryJG/Veigarv2 videos from the catalog →
   `ingest_videos.py`. 2. **Golden-question eval set** (~1h) → KB regression testing.
3. **Calibration** (you): review 3–5 own games, log disagreements as house rules; VOD-check
   one reconstructed clear (the gate for any public demo). 4. **M0**: Riot product
   registration + name/domain + coach emails (longest external waits — start early).
5. **M1+**: service extraction → Discord bot v2 → beta (see BUSINESS_PLAN milestones);
   account recap is the paid-tier anchor.

## Open decisions on your desk

- Merge (parts of) the disagreement report into the bible, or keep permanently separate?
- Product name + domain (blocks M0/landing page/Paddle).
- Coach outreach: email KireiLoL first (blessing/attribution/affiliate) — before launch.
- Paid LLM key: stays unwired per your call — and likely moot now that
  `gemini-3.5-flash`'s live free quota verified >20/day on this project.
