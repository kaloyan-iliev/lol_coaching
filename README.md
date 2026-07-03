# LoL Jungle Coach

Personal AI jungle-coaching tool grounded in methodology from trusted coaches
(KireiLoL, JungleGapGG, PerryJG, ...) and hard data from the Riot API. Four pillars:

1. **Knowledge base** — YouTube coaching videos → transcripts → LLM tagging →
   synthesized "Jungle Bible", plus your own **house rules** that override everything
2. **High-elo baseline** — 50 Master+ Ekko-jungle EUW games reduced to
   deterministic facts and quartile stats
3. **Game analyzer** — your games vs the baseline + knowledge → timestamped,
   fact-grounded review with momentum turning points
4. **Pre-game draft analyzer** — paste both comps → one-glance game-plan card

## Documentation map

| Doc | What's in it |
|---|---|
| this README | setup, script reference, data layout, architecture |
| [ROADMAP.md](ROADMAP.md) | build status, next steps, productization path |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) | every Riot data field we pull, used-by map, unexploited signals |
| [docs/CSV_TABLES_GUIDE.md](docs/CSV_TABLES_GUIDE.md) | the per-game CSV tables: coaching uses + next-level feature queue |
| [knowledge/house_rules.md](knowledge/house_rules.md) | **your** coaching principles (HR ids) — highest-priority knowledge in every prompt; edit freely |
| [FULL_PLAN.md](FULL_PLAN.md) / [MVP_PLAN.md](MVP_PLAN.md) | original vision / MVP notes (historical) |

## Setup

```powershell
uv venv .venv
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
copy .env.example .env   # then fill in your keys
```

Keys in `.env`:
- `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey). Free tier is enough.
- `RIOT_API_KEY` — [Riot developer portal](https://developer.riotgames.com). **Dev keys expire every 24h** — regenerate before long fetch jobs. All fetch scripts resume where they left off.
- `DISCORD_BOT_TOKEN` / `OPENAI_API_KEY` — optional.

## Daily use

```powershell
# Before a game: paste both drafts, get the game plan (also a Streamlit tab)
.venv\Scripts\python.exe scripts\pregame.py --ours "Top,Jgl,Mid,Bot,Sup" --enemy "..."

# After a game: fact-grounded review with momentum turning points
.venv\Scripts\python.exe scripts\review_game.py --riot-id "Name#TAG" --latest

# Browse a game's data as CSV tables (Excel/VS Code)
.venv\Scripts\python.exe scripts\export_game_csv.py --match EUW1_xxx

# Web UI: screenshot coach + Q&A + pre-game draft
.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

When a review's judgment differs from yours, add a rule to
`knowledge/house_rules.md` — that file outranks everything else in every prompt.

## Script reference

| Script | Purpose |
|---|---|
| **Knowledge base** | |
| `scripts/channel_scan.py` | List a channel's videos (yt-dlp), select into the catalog |
| `scripts/add_video.py` | Add videos to `data/videos.json` |
| `scripts/extract_transcripts.py` | Download transcripts |
| `scripts/auto_tag_transcripts.py` | LLM-tag + summarize transcripts |
| `scripts/generate_jungle_bible.py` | Synthesize the bible (`--incremental` regenerates only changed sections) |
| `scripts/ask_transcripts.py` | Q&A with timestamped YouTube citations |
| `scripts/parse_patreon_links.py` | Extract YouTube links from saved Patreon HTML |
| **Riot data** | |
| `scripts/riot_fetch_baseline.py` | Discover + download Master+ Ekko-jungle games (resumable, `--status`, `--seed-riot-ids`) |
| `scripts/riot_build_baseline.py` | Facts for all games + `--validate` cross-checks + baseline quartiles |
| `scripts/export_game_csv.py` | One game → 8 CSV tables in `data/csv/{id}/` |
| `scripts/audit_data_dictionary.py` | Verify DATA_DICTIONARY covers all observed fields (`--check`) |
| **Coaching** | |
| `scripts/review_game.py` | Game review: facts + baseline + house rules + bible → LLM → timestamp-checked review |
| `scripts/pregame.py` | Draft analysis → game-plan card |

## Architecture (data flow)

```
YouTube channels ──channel_scan/add_video──> videos.json
      └─extract_transcripts──> data/transcripts/ ──auto_tag──> tags/summaries
            └─generate_jungle_bible──> knowledge/jungle_bible.md + section_*.md

Riot ladders ──riot_fetch_baseline──> data/riot/matches+timelines (raw JSON)
      └─riot_build_baseline──> data/riot/facts/*.json ──> baseline_ekko.json

Your game ──review_game──> facts (same extractor)
      └─ prompt = house_rules ▸ fact sheet (facts + baseline deltas) ▸ flag-selected bible sections
      └─ 1 Gemini call ──> data/reviews/{id}.md  (+ timestamp hallucination check)

Draft ──pregame──> prompt = house_rules ▸ fixed bible sections ▸ comps
      └─ 1 Gemini call ──> data/pregame/{ts}.md
```

Key modules: `riot/client.py` (rate-limited API), `analysis/timeline_facts.py`
(deterministic facts), `analysis/momentum.py` (gold swings), `analysis/challenges.py`
(exact Riot stats), `analysis/narrative.py` (fact sheet), `app/llm_client.py`
(all LLM calls, google-genai), `app/pregame.py` (draft analyzer).

## Data layout

```
data/
  videos.json              # video catalog with LLM tags/summaries
  transcripts/raw|clean/   # per-video transcripts
  channel_scans/           # channel listings awaiting selection
  url_lists/               # ad-hoc URL lists
  riot/
    matches/  timelines/   # raw Riot JSON (gitignored - large)
    facts/                 # parsed per-game facts (baseline + your games)
    match_index.json       # baseline dataset catalog
    discovery_state.json   # resumable fetch progress
    baseline_ekko.json     # Master+ quartiles (n=50)
  csv/{match_id}/          # 8 browsable tables per exported game
  reviews/                 # game reviews (gitignored)
  pregame/                 # game-plan cards
knowledge/
  jungle_bible.md          # distilled coaching guide (~31k tokens)
  section_*.md             # per-topic sections
  house_rules.md           # YOUR principles - override everything
  sections_meta.json       # incremental-regeneration bookkeeping
docs/                      # data dictionary + CSV guide
```

## Grounding guarantees (why reviews can be trusted)

- Every claim must cite a fact-sheet timestamp; a regex tripwire flags any
  mm:ss not backed by extracted facts.
- Meta valuations must cite house rules (HR ids) or guide concepts, or carry
  an explicit "(general reasoning, not from your coaches)" label.
- Heuristic facts (60s-snapshot pathing, gank detection) carry confidence
  labels the LLM must preserve.
- Facts cross-check against the scoreboard (`--validate`): death counts, ward
  counts, team gold — exact matches required.
