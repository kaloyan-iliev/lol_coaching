# Promo Drafts & Publicity Playbook

*Drafted 2026-07-04. Companion to [BUSINESS_PLAN.md](BUSINESS_PLAN.md) §Go-to-market.
Nothing here goes public before: (1) fresh Riot key + product registration,
(2) one clear-path VOD validation, (3) generic all-jungler baseline built.*

## The disclosure principle: sell the WHAT, never the HOW

Talk about **inputs** (official Riot data, coaching methodology) and **outputs**
(timestamped reviews, pattern reports). Never the middle (pipeline, prompts,
grounding tricks, providers, which channels feed the knowledge base).

Specific numbers sound advanced and reveal nothing reproducible:

- "Reads the full match timeline — positions, gold, XP and combat state of all
  10 players, plus every kill, ward, objective and item event"
- "Compares your game against 140+ per-player stats from a Master+ baseline"
- "Reconstructs your clear path, your death contexts (numbers disadvantage,
  unspent gold, enemy jungler position) and the momentum turning points"
- "Every timestamp in a review is machine-verified against extracted match
  events before you see it"

Words to avoid: *scraping* (say "official Riot API"), *GPT/Gemini/prompt*,
any coach's name (until blessed), *bot* in first contact with mods (say "tool").
Required by Riot policy: an "isn't endorsed by Riot Games" boilerplate on the
landing page — keep promo posts consistent with it.

Honest note: the defensibility is NOT secrecy — any dev can guess "Riot API +
LLM". The moat is execution quality, the baseline data, coach relationships and
community trust. Secrecy just avoids handing over the recipe for free.

## Draft 1 — the giveaway thread (r/Jungle_Mains) — RUN THIS FIRST

**Title options:**
- "I built an AI jungle coach that reviews your game like a VOD session. Drop
  your Riot ID (EUW) and I'll review your last ranked jungle game in the comments — free"
- "Drop your EUW Riot ID — my jungle-coach AI will do a timestamped review of
  your last ranked game (built by a Diamond Ekko OTP, testing before launch)"

**Body:**

> Diamond jungle main here. For the past months I've been building myself an AI
> coach because I can't afford $30/session VOD reviews after every loss.
>
> It pulls your game from the official Riot API, breaks down the full timeline
> (every kill, objective, ward, gold swing and your clear path), compares you
> against a Master+ baseline on 140+ stats, and writes a timestamped review the
> way a human coach would: the 3 mistakes that actually cost the game, when they
> happened, and what to do instead. Every timestamp is machine-checked against
> real match events so it can't invent moments that didn't happen.
>
> I want to know if it's actually useful for other junglers before I put it
> anywhere, so: **drop your Riot ID + region below and I'll run your last ranked
> jungle game through it and post the review as a reply.** No signup, no link,
> nothing to click. Brutal feedback wanted — especially where the review is
> WRONG about your game, that's the data I need.
>
> (Caveats: jungle games only for now; positions come from Riot's timeline, so
> clear paths are reconstructions, labeled as such.)

**Rules for running it:** message the sub mods first; reply with reviews as
comments (paste key sections, not walls); note every "this is wrong" reply —
that's the quality KPI; if someone asks HOW it works: "official Riot API + a lot
of deterministic data engineering before any AI sees the game — the AI only gets
verified facts." Nothing more.

## Draft 2 — the data post (zero product mention in the post itself)

**Title:** "I analyzed 50 Master+ EUW jungle games with the Riot timeline API.
Here's what they do differently (first full clear, deaths, objective setups)"

Body = 4–6 genuinely interesting baseline findings with numbers (median full-clear
time, deaths before 10 by tier, counter-jungle frequency, unspent gold at death).
The tool appears only if asked in comments. This builds credibility and karma
before any launch post, and it's content the sub actually wants.

## Draft 3 — launch post (only after beta + testimonials)

Structure: 1 screenshot of a real review (permission-granted) + 2-line pitch +
3 short testimonial quotes + "free tier: 3 reviews/month, no card" + invite link.
Post to r/Jungle_Mains and r/ekkomains the same week the Discord bot is public.

## Where else (ranked by expected return)

1. **Jungle/champion-main Discord servers** (likely strongest): DM mods of ~10
   servers, offer the bot free for their community + a live demo day. Mods love
   exclusive utilities; every review posted in-channel is an ad.
2. **r/Jungle_Mains, r/ekkomains** — the drafts above.
3. **r/summonerschool** — strict no-self-promo: participate genuinely, do the
   data post (Draft 2) there, tool only in comments when asked.
4. **YouTube Shorts / TikTok** (~1/wk, 60s): screen recording — "AI reviews my
   ranked loss" → show 1 timestamped mistake + the fix. Low effort once the
   pipeline exists; compounding discovery channel.
5. **Coach partnerships** (after blessing emails): a coach reacting to the AI's
   review of a subscriber game is marketing that money can't buy.
6. **Patch-day pregame threads**: "AI game plans for the top-10 jungle picks on
   16.14" — recurring, useful, product-adjacent.

## FAQ answers to prepare (so replies never leak process)

- *"What model?"* → "A few different ones under the hood; the interesting part
  is the fact-extraction before the AI, not the AI."
- *"Does it hallucinate?"* → "Every timestamp is verified against match events;
  when a claim can't be verified it's labeled. That was most of the build effort."
- *"Open source?"* → "The analysis layer maybe someday; the coaching layer no."
- *"How is this different from Mobalytics/iTero?"* → "They show you dashboards
  and drafts. This reads YOUR timeline and tells you the 3 moments that lost the
  game, like a VOD review. Different job."
