# CSV Tables Guide — Analysis & Coaching Uses

What each table in `data/csv/{match_id}/` contains, what it enables today, and
what "next level" features it unlocks. Based on inspecting EUW1_7898664752
(the Diana game). Generate tables with:
`python scripts/export_game_csv.py --match <ID>`

---

## 1. frames.csv — the heartbeat table (10 players × ~26 minutes, 18 cols)

`minute, clock, participantId, champion, team, x, y, zone, totalGold,
currentGold, xp, level, laneCS, jungleCS, dmgToChamps_cum, dmgTaken_cum,
dmgToChamps_delta, ccApplied_ms`

The core time-series. Everything positional and economic flows from here.

**Coaching uses (available now):**
- Zone occupancy profile: in the Diana game she spent 15 of 26 minutes in her
  own two jungle quadrants and **0 minutes in enemy jungle** — the
  "lost_counter_jungle_battle" stat, visualized.
- `currentGold` at any moment → "you had 933g unspent at that fight" (shipped).
- `dmgToChamps_delta` per minute → fight participation without kills (shipped).
- Level curves for all 10 players → who is spiking 6/11/16 first, not just us.

**Next level:**
- **Heatmap / pathing plot** — x,y per minute per player onto a map image
  (Jungle-Path-Tracker style); side-by-side you vs enemy jungler.
- **Proximity analysis** — distance between you and each teammate per minute →
  "you played 80% of the game topside while your win condition was bot".
- **Tempo model** — minutes where you were in base or dead vs enemy jungler's
  location → "his 3 best ganks happened during your resets".
- CAVEAT: `ccApplied_ms` (timeEnemySpentControlled) is known to be inflated by
  Riot; use only for relative comparisons within one game.

## 2. kills.csv — every kill with tactical context (41 rows, 13 cols)

`clock, t_s, killer, victim, assists, x, y, zone, bounty, shutdownBounty,
killStreak, victim_allies_within_2500, victim_enemies_within_2500`

**Coaching uses:**
- The numbers columns quantify "died to numbers" for ALL 10 players: in this
  game 11 of 41 kills had the victim outnumbered by 2+. League-wide pattern:
  most deaths are number-disadvantage deaths, not mechanical ones.
- `bounty + shutdownBounty` → which deaths were expensive (feeding a shutdown).
- Kill locations by zone → where the game was actually decided.

**Next level:**
- **Death-cause classifier**: outnumbered / even-but-lower-level /
  even-but-item-deficit (join with items.csv) / isolated pick — per death,
  deterministic, feeds the review.
- **Shutdown economics**: track your bounty over time → "you were worth 700g
  at 15:28 and gave it away in a 1v1 you didn't need to take".

## 3. objectives.csv — epic monsters, buildings, plates (75 rows)

`clock, t_s, event, detail, team, killer, x, y, lane`

**Coaching uses:**
- Objective timeline vs your position (join with frames.csv) → the shipped
  "we were NOT nearby" facts.
- DRAGON_SOUL_GIVEN + OBJECTIVE_BOUNTY events → comeback windows.

**Next level:**
- **Setup-quality score**: for each objective, count wards placed near the pit
  (wards.csv) and allies in quadrant (frames.csv) in the 90s before spawn →
  "your team took 0 of 4 dragons that spawned while you had no bot-side vision".
- ⚠ TURRET_PLATE_DESTROYED semantics unclear (44 events > 30-plate max) —
  verify against a VOD before using plate counts.

## 4. participants.csv — scoreboard + Riot analytics (10 rows, 33 cols)

Identity, KDA, gold, CS, vision, damage, `totalTimeSpentDead_s`, plus the 16
curated challenge stats for every player (not just you).

**Coaching uses:**
- The jungler-vs-jungler row comparison is the post-game report card: in this
  game Ekko had `jungle_cs_before_10m` 77.45 vs Diana 60.65, and
  `more_enemy_jungle_than_opponent` -39.7 vs -56.7 (both got invaded, Ekko less).
- `totalTimeSpentDead_s` — "you were dead 85s before 25 minutes" is tempo lost.

**Next level:**
- **Cross-game trend table**: stack this row across all your reviewed games →
  personal dashboard (are your crabs/vision/counter-jungle numbers improving?).
- This is the natural input for the **personalization** roadmap item
  (recurring-weakness detection).

## 5. team_gold.csv — momentum backbone (26 rows)

`minute, clock, blue_gold, red_gold, diff_blue_minus_red`

Small but decisive: the shipped swing detection reads this. Row 1 of the Diana
game already shows +590 blue at 01:00 — the level-1 fight priced in gold.

**Next level:** win-probability proxy curve (gold diff + objectives held) →
"the game was still even at 14:00; it was lost between 17:00 and 19:00" —
sharper prioritization of which mistakes actually mattered.

## 6. wards.csv — vision events (253 rows)

`clock, t_s, action, wardType, by`

**Coaching uses:**
- Ward cadence vs objective spawns: did anyone ward before the 14:21 dragon?
- Ward takedowns by the enemy → when your vision was denied.

**Quirks found:**
- No positions (Riot doesn't expose ward x,y) — timing analysis only.
- `UNDEFINED` ward type is polluted by champion mechanics: Shen "placed" 136
  UNDEFINED wards in this game (his spirit blade!). Filter to
  YELLOW_TRINKET/CONTROL_WARD/SIGHT_WARD/BLUE_TRINKET for real vision analysis.
  (Our jungler facts are unaffected for Ekko — validated vs scoreboard — but
  don't trust raw counts for champions with placeable objects.)

**Next level:** vision-tempo correlation — "each time you cleared a bot-side
ward, your team took the next objective" style patterns.

## 7. items.csv — economy actions (369 rows)

`clock, t_s, action, itemId, by, goldGain`

**Coaching uses (needs one addition):**
- itemIds are opaque numbers — needs the free Data Dragon `item.json` map
  (itemId → name, gold, tags). With it: build timelines, component efficiency,
  and completed-item power spikes.

**Next level:**
- **Power-spike windows**: completed legendary item (>2500g) + LEVEL_UP 6/11/16
  vs the same for the enemy jungler → deterministic "fight now / don't fight"
  windows for the review to cite. This is the #2 unexploited signal in
  DATA_DICTIONARY §8 and items.csv + frames.csv is exactly what it needs.
- Reset quality: gold at recall vs gold spent → "you based with 1400g and
  spent 300g".

## 8. skills.csv — ability points (136 rows)

`clock, t_s, champion, skillSlot, levelUpType`

**Coaching uses:** skill max order per champion (Diana: Q first, W second max
in this game); catches wrong-max mistakes on your champ.
**Next level:** low value for jungle coaching beyond sanity checks; skip.

---

## Priority queue for "next level interactions"

1. **Power-spike windows** (items + frames + levels) — deterministic "fight
   now" advice, the biggest coaching gap the LLM currently guesses at.
2. **Personal trend dashboard** (participants.csv stacked across games) —
   feeds personalization; trivially a Streamlit tab.
3. **Death-cause classifier** (kills + frames + items) — upgrades every death
   fact from "what happened" to "why it happened".
4. **Objective setup-quality score** (objectives + wards + frames).
5. **Pathing heatmap image** (frames x,y) — visual VOD companion.

## Known data quirks (all verified on real data)
- `wardType=UNDEFINED` includes champion objects (Shen blade) — filter it.
- A few events at 00:00 have no participantId (system events) — ignore.
- `ccApplied_ms` inflated; relative use only.
- Plate events over-count (44 > 30 max); semantics unverified.
