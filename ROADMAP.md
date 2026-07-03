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

## Next steps (in rough priority order)

1. **Review your own games.** `python scripts/review_game.py --riot-id "YourName#TAG" --list`
   then `--latest`. Compare the review's Top-3 mistakes against your own VOD
   judgment for 2-3 games; tune `app/prompts/review_prompt.txt` where it's off.
2. **Expand the coach roster.** JungleGapGG channel is already scanned
   (`channel_scan.py --list JungleGapGG`); pick fundamentals videos, run the
   chain, regenerate incrementally. Multi-coach input activates the bible's
   "when coaches disagree" synthesis.
3. **Grow the baseline.** Rerun `riot_fetch_baseline.py --target 50` with fresh
   dev keys over a few days; consider `--seed-riot-ids` with Ekko one-tricks
   from League of Graphs. Re-run `riot_build_baseline.py` after.
4. **Streamlit "Game Review" tab** — same functions as `review_game.py`, UI on top.
5. **Champion-agnostic reviews** — the analyzer is already champion-agnostic
   except the baseline; add per-champion baselines when you play others.
6. **Video citations in reviews** — for each Top-3 mistake, attach a
   "watch this" link (coach video + timestamp) for the underlying concept.
   The citation machinery already exists in `ask_transcripts.py`; needs a
   concept→video-moment index built from videos.json key_timestamps.
7. **Later / research:** RAG (only if the bible outgrows ~100k tokens),
   personalization (recurring-mistake tracking across your reviews),
   HuggingFace gptilt Challenger dataset as a bigger offline baseline,
   patch-drift checks in `analysis/jungle_camps.py` each major patch.

## Known limitations (accepted for v1)
- Timeline positions every 60s; no smite/camp/summoner-spell events → clear
  reconstruction approximate, gank *attempts* without kills invisible.
- Dev key expires daily; all fetch jobs resume from `discovery_state.json`.
- Baseline n is small → reviews cite quartiles + n, never absolutes.
- Free Gemini tier → tagging runs sequentially with sleeps; reviews are 1 call.
