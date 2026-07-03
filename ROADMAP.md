# Roadmap & Status

Working notes on what's built, what's verified, and what comes next.
(Original long-term vision: `FULL_PLAN.md`; original MVP notes: `MVP_PLAN.md`.)

## Done (July 2026)

### Knowledge base (part 1)
- 38 KireiLoL videos → transcripts → LLM tags → `knowledge/jungle_bible.md` (~31k tokens)
- Q&A with timestamped YouTube citations: `scripts/ask_transcripts.py`
- All LLM calls consolidated in `app/llm_client.py` on the `google-genai` SDK

### High-elo baseline (part 3)
- `scripts/riot_fetch_baseline.py` — Master+ Ekko-jungle discovery on EUW
  (mastery-filtered ladder scan, resumable across daily dev-key expiry)
- `scripts/riot_build_baseline.py` — per-game facts + quartile baseline stats,
  with deterministic cross-checks (deaths & wards vs scoreboard: exact match)

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
- **Baseline: 50 Master+ EUW Ekko games**, all validated.

## Next steps (in rough priority order)

1. **Use it for a week.** Pregame card before games, review after. Add house
   rules whenever the AI's judgment differs from yours — that file is how the
   coach learns YOUR philosophy.
2. **Expand the coach roster.** JungleGapGG channel is already scanned
   (`channel_scan.py --list JungleGapGG`); pick fundamentals videos, run the
   chain, regenerate incrementally. Multi-coach input activates the bible's
   "when coaches disagree" synthesis.
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
7. **Later / research:** RAG (only if the bible outgrows ~100k tokens),
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
- Free Gemini tier → tagging runs sequentially with sleeps; reviews are 1 call.
