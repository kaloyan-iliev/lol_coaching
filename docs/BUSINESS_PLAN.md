# Business Plan — Jungle Coach as a Discord-Bot SaaS

Approved 2026-07-03. Decisions: Discord bot first; free tier 3 reviews/mo + $4.99/mo paid;
≤€20/mo infra; junglers only, any champion.

## Verified constraints
- **Riot policy** ([general policies](https://developer.riotgames.com/policies/general)): monetization allowed for registered + approved products; **permanent free tier mandatory**; paid content must be *transformative* (LLM coaching qualifies, raw data resale doesn't).
- **API keys** ([portal docs](https://developer.riotgames.com/docs/portal)): dev key expires daily; **Personal key doesn't expire but has the SAME rate limits (20/s, 100/2min) and is intended for small/private products — no rate increases**; a monetized public launch needs a **Production key** (higher limits, real approval process, weeks–months). Consequence: closed beta on Personal key; public launch gated on Production approval.
- **Price anchors**: iTero+ $2.99/mo, Mobalytics ~$6–10/mo → $4.99 positioned between.
- **Unit economics**: Gemini 2.5 Flash paid ≈ **$0.01/review** (~15k in / 2k out). Infra ≈ €12–17/mo → break-even ≈ 4 subscribers; 100 subs ≈ €370/mo net.
- **Payments**: Paddle (merchant of record — handles all EU VAT; ~5%+$0.50/txn). **Individuals/sole traders accepted, no incorporation required**; payouts to personal bank account. Still confirm Bulgarian income-tax registration with an accountant before first payout.

## Product
Discord bot: `/link riot_id region`, `/review`, `/games`, `/pregame`, `/usage`, `/upgrade`.
Reviews delivered as summary embed → thread with sectioned embeds → attached .md.
Free: 3 reviews/month + 1 pregame/day. Paid $4.99/mo: unlimited, advanced sections
(momentum turning points, exact stat line, trends), priority queue.

## Architecture (target)
One Hetzner CX22 (€4.40/mo) + Docker Compose: single Python process (discord.py bot +
SQLite-backed job queue, 3 workers + FastAPI Paddle webhooks) + Caddy (TLS + landing page).
SQLite WAL: users, usage, reviews (UNIQUE(match_id,puuid) dedupe), jobs, baselines,
webhook_events. Raw Riot JSON: gzipped flat files, 30-day TTL. `analysis/` reused untouched;
`scripts/review_game.py` extracted into `service/review_service.py`; shared per-host rate
limiters in `service/riot_pool.py`; `PLATFORM_TO_REGION` map for multi-region.

**Quota/abuse:** charge only successful reviews; cache hits free; free usage = max(per
discord_id, per puuid); 7-day re-link cooldown. Champion baselines: generic all-jungler
baseline + lazy per-champion (each fetched match contains 2 junglers; nightly aggregation;
user demand prioritizes).

## Milestones (~21 dev days over ~8 weeks)
| # | Milestone | Days | Gate |
|---|---|---|---|
| M0 | Riot product registration + Personal key + landing page (terms/privacy/refund) | 1 + wait | key issued, page live |
| M1 | Service extraction + SQLite (db, quota, riot_pool, review_service, jobs) | 4 | CLI runs via service; quota unit test |
| M2 | Discord bot v2 (cogs, worker, thread rendering) | 4 | /review E2E <90s in private server |
| M3 | Quotas, dedupe, multi-region (EUW+EUNE) | 2 | 4th free review blocked; dupe = no LLM call |
| M4 | Hetzner deploy (compose, Caddy, backups, healthz) | 2 | survives restart mid-job |
| M5 | Closed beta (~20 junglers) | 5 over 2–3wk | ≥50 reviews, <10% timestamp warnings, 5 testimonials |
| M6 | Paddle (checkout, webhooks, downgrade) | 3 + wait | sandbox E2E; idempotent webhooks |
| M7 | Baselines at scale (generic + per-champion nightly) | 3 | top-10 meta junglers n≥30 |
| M8 | Launch prep + Production key application | 2 | fresh account: link→review→upgrade unaided |

## Go-to-market
**Positioning:** "A jungle coach that reviews YOUR game like a VOD review — timestamped
mistakes, momentum turning points, pregame game plans — grounded in real coaching methodology."

**Funnel:** Reddit/Discord → install → `/link` → 3 free reviews → upgrade nudge → $4.99.
KPIs: installs, link-rate, reviews, free→paid % (target 3–5%), churn.

1. **Closed beta** (weeks 1–4): recruit ~20 junglers via r/Jungle_Mains + r/summonerschool
   beta-tester post; collect 5 permission-granted testimonial reviews.
2. **Reddit launch** (weeks 5–8): participate genuinely 2–3 weeks first; message mods before
   tool posts. Content by impact: (a) data posts from the baseline ("I analyzed 50 Master+
   jungle games..."), (b) live giveaway thread ("drop your Riot ID, AI reviews your last
   game in comments" — each reply is a $0.01 demo), (c) launch post in r/Jungle_Mains +
   r/ekkomains with testimonials. Parallel: offer bot to 10 jungle/mains Discord servers
   via mods — likely the strongest channel.
3. **Content flywheel** (~2h/wk): weekly "Master+ game reviewed by AI" post; patch-day
   pregame threads for top jungle picks.

Promo: first 100 subs get first month free (Paddle coupon); +2 free reviews per referral.
Budget: €0 paid ads.

## Risks
1. **Knowledge-base IP/ethics (top risk):** the bible is synthesized from KireiLoL et al.
   Before public launch: email the coaches — blessing / attribution / rev-share partnership
   (which doubles as marketing). Fallback: rebuild affected sections out.
2. **Production key approval** is discretionary and slow; beta runs on Personal key, but the
   public monetized launch should wait for (or be sized to) production approval.
3. **Review quality on strangers' games** — timestamp-warning rate is the quality KPI;
   warnings become automatic footnotes, not CLI prints.
4. Paddle/Discord approvals — real legal pages; no privileged intents; Lemon Squeezy fallback.
5. Solo-dev support — #bug-reports + admin cog from day one.

## Business gates
Beta exit: ≥50 reviews, <10% warning rate, 5 testimonials.
Launch month: 10 servers, 300 linked users, 10 paying subs.
Month 2 decision: if free→paid <1%, revisit pricing/gating before further spend.
