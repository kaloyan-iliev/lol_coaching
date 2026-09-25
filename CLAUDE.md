# CLAUDE.md — orientation for a new session

Personal AI jungle coach for a Diamond+ Ekko-jungle main on EUW. Read
[docs/HANDOVER.md](docs/HANDOVER.md) first — it is the resume-here doc (state, hard-won
Riot-data insights, honest critique, next steps). This file is only what a *new machine /
new session* needs before touching anything.

## Bootstrap on a fresh clone

```powershell
uv venv .venv                                              # Python 3.14
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
copy .env.example .env                                     # then fill in the keys
```

Always invoke via the venv interpreter: `.venv\Scripts\python.exe scripts\<x>.py`.
There is no package install and no `python -m`; scripts use `sys.path.insert` to reach
`analysis/`, `riot/`, `app/`. Paths are all `os.path.join` off the repo root — no absolute
paths anywhere, so macOS/Linux works with `.venv/bin/python` instead.

Two keys are required before anything does real work:
- `RIOT_API_KEY` — **dev keys expire every 24h**; regenerate at developer.riotgames.com.
  The key committed to the author's local `.env` is always stale by the next day. Every
  fetch script resumes from `data/riot/discovery_state.json`, so expiry mid-job is safe.
- `GEMINI_API_KEY` — free tier, and the free tier is the real constraint (see below).

## What a fresh clone has, and what it does NOT

**Tracked and ready to use immediately** (repo is ~7 MB packed):
`data/riot/facts/` (580 per-game fact files) · `data/riot/baselines/` (`_generic.json`
n=500 + 22 per-champion) · `match_index.json` + `discovery_state.json` · the whole
knowledge base (`knowledge/`, 124 transcripts in `data/transcripts/`) · 4 sample reviews
and 2 sample CSV exports kept as references.

**Deliberately gitignored — 245 MB of regenerable raw dumps:**
`data/riot/matches/` (24 MB) and `data/riot/timelines/` (221 MB), plus `data/reviews/`,
`data/csv/`, `.venv/`, `.env`.

Consequences on a fresh clone — read this before assuming something is broken:
- Reviewing a **new** game works out of the box: `review_game.py` fetches its own raw
  JSON on demand and caches it.
- Baselines are already built; you do **not** need the raw dumps to use them.
- Anything that re-reads the *historical* 500-game raw JSON does need a re-fetch first
  (days of dev-key quota): `audit_data_dictionary.py`, `map_state.py`/`state_report.py`
  on an old match, `account_recap.py` (it lists `data/riot/matches/`).

Note `data/reviews/` and `data/csv/` are gitignored but contain a few force-added sample
files. New reviews and CSV exports there are invisible to git by design — if you want one
committed, `git add -f` it deliberately.

## Free-tier LLM discipline (this shapes how you work here)

Gemini free tier on this project measured at **20 requests/day per model**, and quota
pools are **per model** — which is why the default is the newest flash
(`gemini-3.6-flash` in [config.py](config.py)) with a fallback chain
3.6→3.5→3-preview→3.5-lite→2.5. `GEMINI_PAID_API_KEY` exists in `.env` and is
**deliberately unwired**; do not wire it without asking. OpenRouter is the backup
provider (50 free req/day): `$env:LLM_PROVIDER='openrouter'`.

Practical rule: **do not burn LLM calls to explore.** `review_game.py --facts-only`
prints the full fact sheet for free, batch scripts pace themselves, and most analysis
(`state_report.py`, `riot_build_baseline.py`) is deterministic and costs nothing.

## Grounding rules — do not weaken these

- `knowledge/house_rules.md` (HR ids) outranks every other knowledge source in every
  prompt. When a review's judgment is wrong, the fix is a new house rule, not prompt edits.
- Every `mm:ss` in a generated review must match an extracted fact within ±90s; the
  tripwire flags the rest. Keep it wired into any new review path.
- Heuristic facts (60s-snapshot pathing, gank detection, reconstructed tick state) carry
  confidence labels — preserve them through prompts and never present them as exact.

## Conventions and known rough edges

- All LLM calls go through `app/llm_client.py`. Don't call provider SDKs directly.
- Deterministic extraction lives in `analysis/`; the LLM never computes numbers.
- **No tests, no CI.** The only checks are `riot_build_baseline.py --validate`
  (facts vs scoreboard) and `audit_data_dictionary.py --check`. pytest is planned for the
  M1 service extraction, not before.
- `app/discord_bot.py` is the stale single-user version; the SaaS bot is M2, unstarted.
- Verify LLM output on unfamiliar champions — the known failure mode is silent
  substitution of an unknown champion for a similar-sounding one.
