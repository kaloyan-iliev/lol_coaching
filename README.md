# LoL Jungle Coach

Personal AI jungle-coaching tool grounded in methodology from trusted coaches (KireiLoL, JungleGapGG, PerryJG, ...). Three pillars:

1. **Knowledge base** — YouTube coaching videos → transcripts → LLM tagging → synthesized "Jungle Bible"
2. **High-elo baseline** — Master+ Ekko-jungle games pulled from the Riot API (EUW), reduced to deterministic per-game facts and aggregate stats
3. **Game analyzer** — your own games compared against the baseline + Jungle Bible → timestamped, actionable review

See `FULL_PLAN.md` (long-term vision) and `MVP_PLAN.md` (original MVP notes).

## Setup

```powershell
uv venv .venv
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
copy .env.example .env   # then fill in your keys
```

Keys in `.env`:
- `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey). Free tier is enough; scripts sleep between calls.
- `RIOT_API_KEY` — [Riot developer portal](https://developer.riotgames.com). **Dev keys expire every 24h** — regenerate before long fetch jobs. All fetch scripts are resumable, so an expired key mid-run loses nothing.
- `DISCORD_BOT_TOKEN` / `OPENAI_API_KEY` — optional.

## Pipeline scripts

| Script | Purpose |
|---|---|
| `scripts/add_video.py` | Add YouTube videos to the catalog (`data/videos.json`) |
| `scripts/extract_transcripts.py` | Download transcripts for cataloged videos |
| `scripts/auto_tag_transcripts.py` | LLM-tag + summarize each transcript into the catalog |
| `scripts/generate_jungle_bible.py` | Synthesize transcripts into `knowledge/jungle_bible.md` |
| `scripts/ask_transcripts.py` | Q&A over the bible with timestamped YouTube citations |
| `scripts/parse_patreon_links.py` | Extract YouTube links from a saved Patreon page |
| `scripts/riot_fetch_baseline.py` | Discover + download Master+ Ekko-jungle matches/timelines (EUW) |
| `scripts/riot_build_baseline.py` | Extract per-game facts and aggregate baseline stats |
| `scripts/review_game.py` | Analyze one of your games: facts + baseline + bible → coaching review |

Apps: `app/streamlit_app.py` (screenshot coach web UI), `app/discord_bot.py` (Discord bot). All LLM calls go through `app/llm_client.py` (google-genai SDK).

## Data layout

```
data/
  videos.json              # video catalog with LLM-generated tags/summaries
  transcripts/raw|clean/   # per-video transcripts
  url_lists/               # ad-hoc video URL lists (input for add_video --batch)
  riot/
    matches/  timelines/   # raw Riot API JSON (gitignored - large)
    facts/                 # deterministic per-game fact sheets
    match_index.json       # index of downloaded baseline games
    discovery_state.json   # resumable fetch progress
    baseline_ekko.json     # aggregate Master+ stats
  reviews/                 # generated game reviews (gitignored)
knowledge/
  jungle_bible.md          # THE distilled coaching guide
  section_*.md             # per-topic sections
```
