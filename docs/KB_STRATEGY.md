# Knowledge-Base Strategy — the Curation Playbook

*Written 2026-07-05. How we grow the Jungle Bible without rotting it.
Companion docs: [HANDOVER](HANDOVER.md) · [ROADMAP](../ROADMAP.md).*

## The one-line strategy

Small expert domain + reviewable corpus + deterministic grounding on the output
side → **curated-markdown KB stuffed selectively into context**, not RAG.
Curation quality beats retrieval sophistication at our scale (93 videos). This
matches current (2026) practice for specialized playbook domains; enterprise RAG
is for corpora that are too big and too fast-moving to curate — ours isn't.

**Why our case is different from most KB builders:** the KB is paired with
deterministic grounding — Riot facts, timestamp tripwires, Master+ baselines.
Most teams have retrieval and no ground truth. The KB alone is copyable; the
pairing is the moat.

## 1. Input quality gate (human, at selection time)

The LLM synthesis can compress and dedupe; it cannot rescue a bad source.
Tier videos in `data/video_catalog.csv` before ingesting:

| Tier | What | Examples | Policy |
|---|---|---|---|
| S | Structured guides/frameworks | Perry "Jungle Fundamentals" playlist, JGG "ULTIMATE guide" | ingest all |
| A | Educational commentary with a thesis | "How to GAP with fundamentals", Kirei tempo videos | ingest selectively |
| B | VOD reviews / coaching sessions | KireiVODs, Veigarv2 coaching series | ingest few, for case-study value |
| skip | Rank-bait, tier lists, patch hype | "NEW BROKEN BUILD", most tier lists | never |

Watch age vs quality: older videos are often better (less algorithm-chasing);
meta-specific numbers from old patches are the exception — the synthesis prompt
already preserves-with-attribution rather than asserting them as current.

## 2. Distillation & dedup (automated, in synthesis)

- Per-topic LLM synthesis IS the dedup step: 24 transcripts saying the same
  scuttle rule come out as one paragraph. Implemented caps
  (`select_transcripts` in `scripts/generate_jungle_bible.py`): max 24
  transcripts/topic chosen round-robin across coaches (protects minority
  coaches), 12k chars per transcript, 25s pacing (token/min quotas).
- Keep each section ≤ ~4k tokens. Reviews inject only flag-selected sections
  (`analysis/section_select.py`), so **total bible size matters much less than
  per-section quality**. Bible is ~34k words / ~45k tokens as of 2026-07-05.

## 3. Integrity while expanding

- **Incremental regen** (`--incremental` + `knowledge/sections_meta.json`):
  only sections whose transcript set changed get rebuilt.
- **Diff before accepting**: after a regen, `git diff knowledge/section_*.md` —
  if a section changed only cosmetically, the new sources added nothing (see §5).
- **Golden-question eval set** (NEXT TO BUILD, ~1h): 15–20 jungle questions with
  user-approved answers in `knowledge/eval_questions.md`; re-ask via
  `ask_transcripts.py` after each regen. This is the KB's regression test —
  today nothing tells us whether a regen made answers better or worse.
- **House rules override everything** (`knowledge/house_rules.md`) — the user's
  judgment stays sovereign over any coach content.
- **Attribution audit**: per-coach subset bibles
  (`generate_jungle_bible.py --coaches X` → `knowledge/jungle_bible_<x>.md`)
  show what each coach actually contributes.
- **Disagreements stay a separate document** (`knowledge/coach_disagreements.md`
  via `scripts/coach_compare.py`) — merged into the bible only by explicit user
  decision, so synthesis never papers over real disputes.

## 4. VOD reviews vs guides — both, for different jobs

Guides teach principles; VOD reviews show *recognition* — what the principle
looks like in a messy real game state. That recognition gap is exactly what our
users lack. VOD transcripts are noisier, so ingest few (tier B). The higher-value
future use is not more bible prose: mine VODs for "situation → decision →
reasoning" triplets to use as few-shot examples in review prompts.

## 5. When is more TOO MUCH

Signals a topic is saturated:
1. Regenerated section diffs stop changing meaningfully when new sources are added.
2. Golden-question answers stop improving.
3. Section creeps past ~4k tokens (compression failing or topic too broad — split it).

When saturated, expand **breadth, not depth**: champion-specific notes, matchup
principles, new topics (e.g. wave-state reading for junglers) — not a fourth
pass over fundamentals. Coach #4 adds less than coach #2 did; that's expected
and fine — extra coaches then serve the disagreement report and marketing
(named methodology partnerships), not raw knowledge volume.

## 6. Where RAG eventually fits

`scripts/ask_transcripts.py` already does retrieval-with-citations in miniature.
Real RAG (embeddings) earns its place only for long-tail champion/matchup Q&A
over raw transcripts and patch notes — after the curated bible stops covering
>90% of review needs. Don't build it before that.
