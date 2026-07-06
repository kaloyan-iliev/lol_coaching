# HANDOVER — Jungle Coach Project

*Written 2026-07-03. Read this first when resuming work. Companion docs:
[README](../README.md) (usage hub) · [BUSINESS_PLAN](BUSINESS_PLAN.md) (monetization) ·
[ROADMAP](../ROADMAP.md) · [DATA_DICTIONARY](DATA_DICTIONARY.md) · [CSV_TABLES_GUIDE](CSV_TABLES_GUIDE.md)*

> **Update 2026-07-04:** multi-coach KB (per-coach bible subsets, disagreement
> report), account-recap feature, yt-dlp transcript fallback, promo playbook —
> see [SESSION_2026-07-04.md](SESSION_2026-07-04.md) for state, blockers
> (Riot key expired, YouTube 429) and the exact next commands.

---

## 1. What this project is, in one paragraph

A personal AI jungle coach for League of Legends, built for a Diamond+ Ekko-jungle main on
EUW. It (a) synthesizes trusted coaches' YouTube content into a "Jungle Bible" knowledge
base, (b) downloads Master+ games from the Riot API and reduces them to deterministic
per-game facts + baseline statistics, (c) reviews the user's own games against both —
producing timestamped, hallucination-checked coaching — and (d) generates pre-game draft
plans. An approved plan exists to productize it as a freemium Discord bot ($4.99/mo).

## 2. Current functionality — what works TODAY and how to use it

Environment: `.venv\Scripts\python.exe` (uv-created, Python 3.14). Riot dev key in `.env`
expires every 24h (regenerate at developer.riotgames.com; all fetch jobs resume).

| I want to... | Command |
|---|---|
| Review my last ranked game | `.venv\Scripts\python.exe scripts\review_game.py --riot-id "ReaperOfMars#Drrw" --latest` |
| List my recent games first | `... review_game.py --riot-id "..." --list` then `--match EUW1_xxx` |
| See the fact sheet without spending an LLM call | add `--facts-only` |
| Get a pre-game plan | `... scripts\pregame.py --ours "Top,Jgl,Mid,Bot,Sup" --enemy "..."` |
| Browse a game's raw data as spreadsheets | `... scripts\export_game_csv.py --match EUW1_xxx` → `data/csv/{id}/` (8 tables) |
| Ask the knowledge base a question (with YouTube citations) | `... scripts\ask_transcripts.py "when do I invade?"` |
| Web UI (screenshot coach / Q&A / pregame) | `.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py` |
| **Recap my last N games (patterns + drafts)** | `... scripts\account_recap.py --riot-id "..." --games 20 --drafts 5` |
| Review the whole video library + pipeline status | `... scripts\video_catalog.py` → `data/video_catalog.csv` |
| Ingest picked videos end-to-end | `... scripts\ingest_videos.py ID1 ID2 --coach X [--regen]` |
| Per-coach bible / disagreement report | `... generate_jungle_bible.py --coaches X` / `... scripts\coach_compare.py` |
| Grow the baseline | `... scripts\riot_fetch_baseline.py --target N` then `riot_build_baseline.py` |
| Add a new coach's channel | `channel_scan.py <url> --coach X` → `--list X` → `--select ids --coach X` (or use `ingest_videos.py`) |
| Teach the AI my principles | edit `knowledge/house_rules.md` (HR ids; overrides everything) |
| Sanity-check data after a patch | `... scripts\audit_data_dictionary.py --check` and `riot_build_baseline.py --validate` |

Three data layers per game: raw (`data/riot/matches|timelines/`), parsed facts
(`data/riot/facts/`), readable (fact sheet embedded in `data/reviews/{id}.md`).

**Assets on disk (2026-07-05):** 500 Master+ EUW jungler-games (250 matches, patches
16.12–13) → `baselines/_generic.json` (n=500) + 22 per-champion baselines (Ekko n=55) ·
Jungle Bible ~34k words from **93 videos / 3 coaches** + per-coach subset bibles +
`coach_disagreements.md` · video catalog `data/video_catalog.csv` (2,052 rows, 7
channels/playlists incl. PerryJG 1,236 + Veigarv2 8, unselected) · 20-game account recap
+ smurf review validated · KB curation policy in `docs/KB_STRATEGY.md` · git remote:
github.com/kaloyan-iliev/lol_coaching (up to date as of 2026-07-06, commit de7d203).

## 3. Key insights from Riot game data (hard-won; don't rediscover)

**What the API gives:** match-v5 (155 fields/player incl. ~141 precomputed `challenges`
analytics — exact jungle stats like `jungleCsBefore10Minutes`, `moreEnemyJungleThanOpponent`,
`initialCrabCount`, `epicMonsterSteals`) + timeline (60s snapshots: position, gold incl.
UNSPENT, xp, 25 combat stats, 12 damage stats; event stream: kills w/ bounties + per-kill
damage arrays, items, wards, plates, objectives, skill-ups). Full map: DATA_DICTIONARY.md.

**What we exploit:** clear-path reconstruction (respawn-guarded camp inference), deaths with
numbers/zone/enemy-jungler-position/unspent-gold context, gank + counter-jungle heuristics,
teamfight clustering with numbers per side, team-gold momentum swings with event drivers,
exact challenge stats, draft comps, per-champion baselines (generic n=500; Ekko n=55).

**What the API can NOT give (hard limits):** positions only every 60s (no kiting/micro);
no smite, no camp-kill, no summoner-spell events; no ward positions; no wave states; no
vision-of information. Clear paths and gank detection are labeled approximations.

**Verified data quirks:** `wardType=UNDEFINED` polluted by champion objects (Shen blade
"placed" 136 wards); `timeEnemySpentControlled` inflated (relative use only); plate events
over-count (~44/game vs 30 max — semantics unresolved, quarantined); a few t=0 events lack
participantId; `challenges.controlWardsPlaced` ≠ event count (use `detectorWardsPlaced`).

**Best unexploited signals (ranked, from CSV_TABLES_GUIDE):** 1) power-spike windows
(items + levels vs enemy jungler → deterministic "fight now" calls; needs free DDragon
itemId→name map), 2) personal trend dashboard (challenges stacked across own games),
3) death-cause classifier, 4) objective setup-quality score, 5) pathing heatmap images.

## 4. Quality & grounding (why outputs can be trusted, and their limits)

- Timestamp tripwire: every mm:ss in a review must match an extracted fact (±90s) — catches
  invented events, NOT wrong prioritization.
- `house_rules.md` (HR ids) outranks all other knowledge in every prompt; meta claims must
  cite HR/guide concepts or carry "(general reasoning, not from your coaches)". This fixed a
  real caught failure (model invented "grubs > dragon in current meta").
- Facts cross-check vs scoreboard on `--validate`: deaths, wards, final team gold — exact.
- Known LLM failure mode: unknown champions get silently substituted (saw Locke→Lux in a
  pregame card); prompt now forbids it — but VERIFY on new champions.

## 5. Monetization (approved plan — full detail in BUSINESS_PLAN.md)

Discord bot, free 3 reviews/mo (Riot REQUIRES a permanent free tier) + $4.99/mo advanced.
Unit cost ~$0.01/review; Hetzner+Paddle ≈ €12–17/mo; break-even 4 subs. ~21 dev days in 9
milestones M0–M8. GTM: closed beta from r/Jungle_Mains → Reddit data posts + review
giveaway threads → Discord server partnerships. **Corrections from verification:** Personal
API key = dev-key rate limits (no increases) and "small private community" intent → beta
on Personal key, public monetized launch gated on Production key approval. Paddle accepts
individuals (no company needed); confirm Bulgarian tax registration before first payout.
**Top risk: the bible is built from other coaches' content — contact coaches (blessing /
attribution / rev-share) BEFORE public launch.**

## 6. Critique — honest weaknesses of what exists (self-review)

1. **Coordinates/zones never validated against ground truth.** Camp coords and the zone
   classifier were eyeballed from community sources and produce plausible outputs, but nobody
   has checked one reconstructed clear against its actual VOD. This is the decisive test and
   it hasn't been run (it's in Phase-2 verification, still pending).
2. **Gank detection only sees kills** → reviews systematically under-observe failed ganks
   and over-credit kill-lane presence. Partially mitigated by damage-delta fight signals.
3. **Baseline mixes patches and tiers** (16.12+16.13, Chall→Master). Fine for quartiles,
   noisy at tails; patch drift will silently skew it — needs a freshness policy.
4. **Numbers-at-fight from 60s snapshots** can misstate a fight's true numbers (players
   move a lot in 60s). Labeled heuristic, but users will quote it as fact.
5. ~~The knowledge base is one coach deep~~ **FIXED 2026-07-05**: 3 coaches ingested,
   per-coach subset bibles + disagreement report exist. Still KireiLoL-heavy (78/93) —
   the curation pass on PerryJG/Veigarv2 rebalances it (see docs/KB_STRATEGY.md).
6. **house_rules.md has 2 rules.** The whole grounding architecture leans on a file the
   user hasn't invested in yet. Every review disagreement should become a rule.
7. **No automated tests** beyond the `--validate` cross-checks; no CI. The service
   extraction (M1) is the right moment to add pytest for quota/facts/momentum.
8. **Streamlit app verified only to boot** (HTTP 200 + compiles) — full click-through of
   all 3 modes never done. `discord_bot.py` is the stale single-user version.
9. **sys.path.insert hacks everywhere** instead of a proper package — works, but will bite
   during the service extraction; fix as part of M1, not before.
10. ~~LLM single-dependency~~ **FIXED 2026-07-05**: default `gemini-3-flash-preview`
    with a fallback chain, `--model` flags everywhere, and OpenRouter as a second
    provider (`$env:LLM_PROVIDER='openrouter'`). Quota reality on this project:
    **20 req/day per model on ALL Gemini models** + 250k input-tokens/min; OpenRouter
    free = 50 req/day. `GEMINI_PAID_API_KEY` exists in .env, deliberately unwired.
11. **Prioritization quality is unmeasured.** The tripwire proves reviews don't invent
    facts, but nothing measures whether the Top-3 mistakes are the RIGHT top-3. Only the
    user's VOD judgment can calibrate this — do it for 5 games and log disagreements.
12. ~~Free-tier fetch throughput~~ **DONE 2026-07-05**: two-junglers-per-match trick
    delivered n=500 + 22 per-champion baselines in one overnight fetch (M7 gate
    effectively met).

## 7. Open questions / things to verify next session

- [ ] Reconstruct one of the user's clears and check vs the actual VOD (decisive pathing test).
- [ ] Plate-event semantics (44/game vs 30 max) — check one game vs VOD or Riot docs.
- [ ] Do `challenges` fields exist on all regions/older patches? (Only EUW 16.12+ observed.)
- [ ] ATAKHAN monsterType name — assumed, never observed in our 50 games.
- [ ] Gemini model roadmap — is 2.5 Flash still the right default? (knowledge cutoff risk)
- [ ] Riot production-key expectations for LLM products — any precedent/policy nuance?
- [ ] Whether Riot allows "review giveaway" threads under its API ToS (almost certainly yes
      — public data, but confirm before the Reddit stunt).

## 8. Next steps (priority order)

**User-only actions (nobody else can do these):**
1. Register the product on Riot Developer Portal + apply for the Personal key (longest wait).
2. Pick a product name + buy the domain (blocks landing page, Paddle, Riot registration).
3. Email KireiLoL (and later JungleGapGG) about using their methodology commercially.
4. Review 3–5 of your own games with the tool and turn every disagreement into a house rule.

**Technical (in order):**
0. **KB curation pass + golden-question eval set** (see docs/KB_STRATEGY.md §1/§3 and
   ROADMAP next-steps 1–2) — cheap, unblocks quality measurement before more scale.
1. **M1 service extraction** (started conceptually, no code yet): `service/` package —
   db.py (SQLite WAL + migrations), quota.py, riot_pool.py (shared per-host limiters),
   review_service.py (extracted from scripts/review_game.py), jobs.py. Schema is designed
   (see BUSINESS_PLAN.md §Architecture). Add pytest here.
2. M2 Discord bot v2 → M3 quotas/multi-region → M4 Hetzner deploy → M5 beta (see milestones).
   The **account recap** (`scripts/account_recap.py`) is the paid-tier anchor feature.
3. Feature queue (independent of SaaS track): power-spike windows, ingest JungleGapGG
   selections, video citations in reviews, trend dashboard.

## 9. Making it simpler to interact (UI thinking)

Current friction: everything is CLI with a long venv path; Streamlit exists but lacks the
game-review flow (its 3 modes are screenshot/Q&A/pregame).

- **Cheapest win (1–2h):** `coach.bat` in repo root — menu: [1] review latest [2] pregame
  [3] open Streamlit; plus a "Game Review" tab in Streamlit (riot-id box → recent-games list
  → click to review → rendered markdown + download). All logic already exists in
  `scripts/review_game.py`; it's pure wiring.
- **The real answer is the Discord bot (M2)** — it *is* the simple UI, for you and for
  customers: `/review` after every game, review arrives in a thread. Building the Streamlit
  review tab first is still worthwhile as the local debug surface.
- **Not recommended now:** a web app with accounts (that's the post-validation step per the
  business plan) or a desktop overlay (Riot policy gray zone).

## 10. Session log (what was done, compressed)

1. **Phase 0**: google-genai migration, consolidated LLM client, README, repo hygiene.
   (Note: `.env` was never actually committed — early scare was a misread.)
2. **Phases 1–3**: Riot client (rate-limited, resumable) → 50-game Master+ Ekko baseline →
   deterministic facts (deaths/ganks/objectives/teamfights/counter-jungle) → hybrid reviewer
   with timestamp tripwire. Verified on the user's real games (Ekko loss + Diana loss).
3. **Phase 4**: channel-scan pipeline + incremental bible regeneration.
4. **v2**: house rules grounding (fixed a caught hallucination), momentum swing detection
   with proactive directives, exact Riot challenge stats, pre-game draft analyzer
   (CLI + Streamlit tab), DATA_DICTIONARY + audit script.
5. **Data deep-dive**: CSV exporter (8 tables/game), mined new signals (unspent gold at
   death, missed-fight context, level diff) — shipped same day; plates quarantined.
6. **Business plan**: researched Riot monetization policy, pricing anchors, unit economics;
   approved Discord-bot SaaS plan (BUSINESS_PLAN.md); M1 implementation NOT started.

All work is committed and pushed to `main` (12 commits ahead of the initial state).
