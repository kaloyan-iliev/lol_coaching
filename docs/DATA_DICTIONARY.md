# Data Dictionary — What We Pull From Riot Games

Every game we analyze produces two JSON files:

| File | Endpoint | Contents |
|---|---|---|
| `data/riot/matches/{id}.json` | match-v5 `/matches/{id}` | Final scoreboard: 155 fields per player (incl. ~141 precomputed `challenges` analytics), team objectives, bans |
| `data/riot/timelines/{id}.json` | match-v5 `/matches/{id}/timeline` | Per-minute snapshots for all 10 players + the full event stream |

Extracted facts (our layer): `data/riot/facts/{id}.json`. Baseline aggregates: `data/riot/baseline_ekko.json`.
Run `python scripts/audit_data_dictionary.py --check` after a patch to spot new fields this doc misses.

---

## 1. Match JSON — top level (`info`)

| Field | Meaning | Used by |
|---|---|---|
| `gameDuration`, `gameCreation` | length (s), start time | facts overview, fetch filters |
| `gameVersion` | patch (e.g. 16.13) | facts, baseline patch list |
| `queueId` | 420 = ranked solo | fetch filter |
| `participants[]`, `teams[]` | see below | — |

## 2. Match JSON — `participants[]` (10 entries, 155 fields each)

Core fields we use:

| Field | Meaning | Used by |
|---|---|---|
| `puuid`, `participantId`, `teamId` | identity + timeline join key | everything |
| `championName`, `teamPosition` | champion + role (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY) | comps, Ekko-jungle filter, role guard |
| `kills` / `deaths` / `assists`, `win` | scoreboard | facts, validation (deaths must match) |
| `neutralMinionsKilled` | total jungle CS | validation |
| `wardsPlaced`, `detectorWardsPlaced` | wards / control wards | validation of event-based counts |
| `goldEarned` | total gold | validation of momentum curve |
| `challenges{}` | see §3 | facts `challenges` key |

Notable unused: `totalTimeSpentDead`, `damageDealtToObjectives`, `totalDamageDealtToChampions`, `visionScore`, item0-6 (final build), summoner spells, runes (`perks`).

## 3. Match JSON — `participants[].challenges` (~141 Riot-precomputed analytics)

Exact post-game values — no heuristics needed. The curated set we extract (via [analysis/challenges.py](../analysis/challenges.py)):

| Group | Fields (fact key ← Riot key) | Signal |
|---|---|---|
| Jungle tempo | `initial_buff_count` ← initialBuffCount, `initial_crab_count` ← initialCrabCount, `jungle_cs_before_10m` ← jungleCsBefore10Minutes, `takedowns_before_jungle_minions` | first clear quality, crab control |
| Counter-jungle | `more_enemy_jungle_than_opponent` ← moreEnemyJungleThanOpponent (± CS), `buffs_stolen`, `scuttle_crab_kills` | who won the jungle-vs-jungle war (exact) |
| Ganking | `kills_on_laners_early_as_jungler`, `jungler_kills_early_jungle` | early gank success (exact) |
| Objectives | `epic_monster_steals`, `epic_monster_kills_within_30s_of_spawn`, `earliest_dragon_takedown_s`, `danced_with_rift_herald` | objective speed/steals |
| Vision | `vision_score_per_minute`, `control_wards_placed`, `ward_takedowns_before_20m` | vision game |

Baseline quartiles are computed for the numeric subset (`BASELINE_CHALLENGE_KEYS`).
Other interesting keys not yet used: `earlyLaningPhaseGoldExpAdvantage`, `maxLevelLeadLaneOpponent`, `pickKillWithAlly`, `killsNearEnemyTurret`, `saveAllyFromDeath`, `skillshotsDodged`, `enemyChampionImmobilizations`, `landSkillShotsEarlyGame`.

## 4. Match JSON — `teams[]`

| Field | Meaning | Used by |
|---|---|---|
| `objectives.{atakhan, baron, champion, dragon, horde, inhibitor, riftHerald, tower}.{first, kills}` | per-team objective totals + who got first | — (validation candidate; events cover the when/where) |
| `bans[]` | championId + pickTurn | — (pregame analyzer could use ban info) |

## 5. Timeline JSON — `participantFrames` (per player, every 60s)

| Field | Meaning | Used by |
|---|---|---|
| `position {x,y}` | map coords (0–14820) | zones, pathing, numbers-at-fight, enemy-jgl tracking |
| `totalGold`, `currentGold` | earned / unspent gold | gold diff vs enemy jgl, momentum curve, (unspent-gold-death detection possible) |
| `xp`, `level` | experience | xp diff, clear reconstruction |
| `minionsKilled`, `jungleMinionsKilled` | lane / jungle CS | CS@10/15, camp inference |
| `timeEnemySpentControlled` | CC applied to enemies (ms) | — (teamfight contribution signal) |
| `championStats{}` (25) | live combat stats: AD, AP, armor, MR, AS, haste, HP, moveSpeed, vamp… | — (power-spike detection: compare stat jumps after item completions) |
| `damageStats{}` (12) | cumulative damage done/taken split phys/magic/true, incl. `totalDamageDoneToChampions` | — (fight participation per minute even without kills; "you dealt 0 champ damage 10:00–14:00") |

## 6. Timeline JSON — event stream (18 types observed across 44 games)

| Event | Key fields | Used by | Unexploited signal |
|---|---|---|---|
| `CHAMPION_KILL` | killerId, victimId, assists, position, `bounty`, `shutdownBounty`, `killStreakLength`, `victimDamageDealt/Received[]` | deaths, ganks, teamfights, momentum drivers | per-kill damage arrays → who ACTUALLY did the damage; bounty economics |
| `CHAMPION_SPECIAL_KILL` | killType, multiKillLength | — | multikills, first blood |
| `ELITE_MONSTER_KILL` | monsterType (DRAGON/HORDE/RIFTHERALD/BARON_NASHOR/ATAKHAN), monsterSubType, killerTeamId, position, bounty | objectives, momentum drivers | — |
| `BUILDING_KILL` | buildingType, towerType, laneType, teamId (loser), position | momentum drivers | tower-trade maps |
| `TURRET_PLATE_DESTROYED` | killerId, laneType, teamId, position | — | plate gold as lane-prio proxy per lane |
| `WARD_PLACED` / `WARD_KILL` | creatorId/killerId, wardType (YELLOW_TRINKET/CONTROL_WARD/BLUE_TRINKET…) | vision counts | ward timing vs objective spawns (no position, sadly) |
| `ITEM_PURCHASED`, `ITEM_SOLD`, `ITEM_UNDO`, `ITEM_DESTROYED` | itemId, participantId | first-reset estimate | item spike timing (needs DDragon itemId→name map); component vs completed |
| `SKILL_LEVEL_UP` | skillSlot, levelUpType | — | skill order (max order per champion) |
| `LEVEL_UP` | level | clear reconstruction | level-6/11/16 spike windows vs enemy |
| `DRAGON_SOUL_GIVEN` | name, teamId | — | soul-point pressure games |
| `OBJECTIVE_BOUNTY_PRESTART`, `OBJECTIVE_BOUNTY_FINISH` | teamId, actualStartTime | — | comeback-mechanic windows |
| `PAUSE_END`, `GAME_END` | timestamps, winningTeam | — | — |

## 7. Known gaps (things the API does NOT give us)

- No smite events, no camp-kill events → clear order is inferred (see [analysis/pathing.py](../analysis/pathing.py)), ±60s.
- No summoner spell usage (flash timers invisible).
- Positions only every 60s → in-between movement, kiting, sidesteps invisible.
- No wave states (minion positions), no vision-of-enemy info (what YOU could see), no chat/pings.
- Ward positions are not in WARD_PLACED events.

## 8. Highest-value unexploited signals (ranked)

1. ~~Fight participation via `damageStats` deltas~~ — **SHIPPED**: missed teamfights now carry `our_zone_at_start` + `our_champ_dmg_during`; deaths carry `unspent_gold`; the jungler gold curve carries `level_diff`.
2. **Power-spike detection** — item completions (ITEM_PURCHASED of completed items) + championStats jumps + LEVEL_UP 6/11/16 vs the enemy jungler → "fight now" windows.
3. **Plates by lane** (`TURRET_PLATE_DESTROYED`) — ⚠ semantics unclear: we observed ~44 plate events per game vs a 30-plate theoretical max, so the event does not map 1:1 to plates. Verify against a known VOD before using.
4. **Kill-contribution arrays** (`victimDamageReceived`) — distinguishes carrying fights from KDA padding.
5. **More `challenges` fields** — laning advantages, immobilizations landed, skillshots dodged.
