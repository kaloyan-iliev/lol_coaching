# Roadmap & Status

Working notes on what's built, what's verified, and what comes next.
(Original long-term vision: `FULL_PLAN.md`; original MVP notes: `MVP_PLAN.md`.)

## Done (July 2026)

### Knowledge base (part 1)
- **93 videos across 3 coaches** (KireiLoL incl. VODs channel, JungleGapGG,
  Thomas Yuen) → transcripts → LLM tags → `knowledge/jungle_bible.md`
  (~34k words / ~45k tokens; per-topic synthesis capped at 24 transcripts
  round-robin across coaches)
- **Per-coach subset bibles** (`generate_jungle_bible.py --coaches X`) and a
  **coach-disagreement report** (`scripts/coach_compare.py` →
  `knowledge/coach_disagreements.md`, kept separate from the bible by design)
- **Video catalog + ingestion tooling**: `data/video_catalog.csv` (2,052 rows,
  7 channels/playlists incl. PerryJG and Veigarv2 scans, pipeline-status
  columns) via `scripts/video_catalog.py`; one-command ingestion via
  `scripts/ingest_videos.py ID... --coach X [--regen]`
- Q&A with timestamped YouTube citations: `scripts/ask_transcripts.py`
- Curation policy: [docs/KB_STRATEGY.md](docs/KB_STRATEGY.md)
- All LLM calls consolidated in `app/llm_client.py` — Gemini (3-flash-preview
  default + fallback chain) or OpenRouter (`$env:LLM_PROVIDER='openrouter'`)

### High-elo baseline (part 3)
- `scripts/riot_fetch_baseline.py` — Master+ **all-jungler** discovery on EUW
  (ladder scan, optional `--champion` filter, both junglers per match counted,
  resumable across daily dev-key expiry). **n=500 jungler-games / 250 matches.**
- `scripts/riot_build_baseline.py` — per-game facts + quartile stats →
  `_GENERIC (n=500)` + **22 per-champion baselines** (Ekko 55, LeeSin 28,
  Qiyana 25, Talon 22, Graves 22, ...), deterministic cross-checks
  (deaths & wards vs scoreboard: exact match)

### Game analyzer (part 4, v1)
- `analysis/` — clear-path reconstruction, deaths/ganks/objectives/counter-jungle/
  economy/vision extraction, derived flags. Position data is 60s snapshots →
  heuristic facts carry confidence labels.
- `scripts/review_game.py --riot-id "Name#TAG" --latest` — fact sheet +
  baseline deltas + flag-selected bible sections → one LLM call → timestamped
  review. Timestamp tripwire flags any cited moment not backed by a fact.

### Knowledge expansion (part 2)
- `scripts/channel_scan.py` — list a channel's videos via yt-dlp (no API key),
  human-in-the-loop selection into the catalog
- `scripts/generate_jungle_bible.py --incremental` — regenerates only sections
  whose transcript set changed (`knowledge/sections_meta.json`)

### v2 additions (July 2026)
- **House rules** (`knowledge/house_rules.md`): your own principles (HR ids)
  override all knowledge in every prompt; reviews must cite HR/guide concepts
  for meta claims or label them "(general reasoning, not from your coaches)".
- **Momentum**: team-gold swing detection with event drivers; reviews include
  "Momentum Turning Points" with proactive at-mm:ss directives.
- **Exact Riot stats** (`analysis/challenges.py`): precomputed jungle analytics
  in facts, flags, fact sheet, and baseline quartiles.
- **Pre-game draft analyzer**: `scripts/pregame.py` + Streamlit "Pre-Game
  Draft" tab → one-glance game-plan card (archetypes, win conditions,
  lane-by-lane, gank targets, early/mid/teamfight plan).
- **Data dictionary**: `docs/DATA_DICTIONARY.md` (+ `audit_data_dictionary.py
  --check` after each patch).

### v3.1 additions (2026-07-07/08)
- **Reviews organized by account/day**: `data/reviews/<Account>/<YYYY-MM-DD>/<match>.md`
  (recaps at account root); `review_game.py --last N` for multi-game runs.
- **LLM-as-judge** (`scripts/judge_review.py`): closes the "prioritization quality
  is unmeasured" gap. `--regression` regenerates reviews from cached facts and
  judges new-vs-stored (pairwise, both orderings, different model than the
  generator); `--score`/`--score-account` give absolute rubric scores (SaaS QA-gate
  seed). Calibrate on your taste via `knowledge/judge_anchors.md`. See KB_STRATEGY §3.

### v3 additions (2026-07-04/05)
- **Account recap** (`scripts/account_recap.py --riot-id "..." --games 20
  --drafts 5`): multi-game pattern review — deterministic per-champion W/L
  summary, G-labeled game citations, remake filtering, per-game timestamp
  tripwire, retrospective draft analyses. First run on the user's 19 games:
  zero grounding warnings. THE candidate flagship/paid feature.
- **Any-jungler reviews**: generic + per-champion baselines mean strangers'
  games are reviewable (validated on a smurf game, clean tripwire).
- **LLM provider hardening**: model fallback chain, `--model` flags everywhere,
  OpenRouter backup provider, quota reality documented (Gemini free tier on
  this project = 20 req/day per model on ALL models; 250k input-tokens/min).

## Next steps (in rough priority order)

1. **Curation pass (user).** Open `data/video_catalog.csv`, tier the PerryJG
   (1,236 scanned) and Veigarv2 (8) videos per KB_STRATEGY §1, ingest picks
   with `ingest_videos.py <ids> --coach PerryJG`.
2. **Golden-question eval set** (~1h): 15–20 questions with approved answers in
   `knowledge/eval_questions.md`; re-ask after each bible regen (KB_STRATEGY §3).
   Plus: review 3–5 of your own games and turn every disagreement into a house
   rule — that file is how the coach learns YOUR philosophy (still ~2 rules).
2b. **VOD-validate one reconstructed clear** — still the hard gate before any
   public demo (HANDOVER §7 open question #1).
3. **Video citations in reviews** — for each Top-3 mistake, attach a
   "watch this" link (coach video + timestamp) for the underlying concept.
   The citation machinery already exists in `ask_transcripts.py`; needs a
   concept→video-moment index built from videos.json key_timestamps.
4. **Streamlit "Game Review" tab** — same functions as `review_game.py`, UI on top.
5. **Fight participation via damageStats** — top unexploited signal (see
   DATA_DICTIONARY §8): per-minute damage to champions catches "absent from
   every fight" and "present but did nothing" patterns.
6. **Per-champion baselines** — the analyzer is champion-agnostic; run
   `riot_fetch_baseline.py` variants for Diana etc. when you play them.
7. **Game-as-sequence / play-quality research** (user idea, designed 2026-07-04):
   encode each game as a compact event sequence ("token string") per jungler —
   e.g. `R3:15 gank_mid(+k, njgl_far) | 5:02 drake_setup(prio-, 2v3) | ...` built
   from the existing facts extractor. Uses: (a) **outcome-independent play
   grading** — judge each decision by its INPUTS (numbers, tempo, tracking,
   spikes) not its result, so "won but bad play" and "lost but right fight" are
   callable; deterministic input-features already exist (numbers_at_start,
   level/gold diff, enemy-jgl position); (b) **anomaly mining** — with 200+
   Master+ sequences, find what high-elo junglers do in state X vs what the
   user did (nearest-neighbor on state features, no ML training needed at
   first); (c) **good-in-loss / bad-in-win detection** — grade fights by input
   quality vs outcome, surface disagreements. Path: v1 = sequence serializer +
   LLM judging with grading rubric in the review prompt; v2 = statistical
   state-matching against the games KB; v3 (research) = train a small
   win-probability / decision model on thousands of games.
8. **Later / research:** RAG (only if the bible outgrows ~100k tokens),
   personalization (recurring-mistake tracking across your reviews),
   HuggingFace gptilt Challenger dataset as a bigger offline baseline,
   patch-drift checks in `analysis/jungle_camps.py` each major patch.

## Productization path (if this becomes a tool for others)

What exists is single-user by design. To serve other players/champions:
1. **Riot production API key** (apply at developer.riotgames.com with the app
   description; dev keys are personal-use only and expire daily).
2. **Per-champion baselines on demand** — the fetch pipeline is already
   champion-parameterizable; store `baseline_{champion}.json` per champ.
3. **Multi-tenant knowledge** — the bible stays shared; house_rules becomes
   per-user; reviews keyed by the user's Riot ID.
4. **Cost model** — reviews are 1 LLM call (~free at Flash pricing); the
   expensive part is baseline fetching per champion (API quota, not money).
5. **Riot policy check** — coaching tools on match-v5 data are generally fine;
   anything using live game data needs a compliance review.

## Known limitations (accepted for v1)
- Timeline positions every 60s; no smite/camp/summoner-spell events → clear
  reconstruction approximate, gank *attempts* without kills invisible.
- Dev key expires daily; all fetch jobs resume from `discovery_state.json`.
- Baseline n is small → reviews cite quartiles + n, never absolutes.
- Free Gemini tier = 20 req/day per model on this project (all models) →
  batch work paces with sleeps, walks the fallback chain, or runs on
  OpenRouter; reviews are 1 call.
