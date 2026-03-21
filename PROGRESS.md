# Punter Bot — Progress Tracker

## Phase 0: Foundation [COMPLETE]

- [x] Git repo initialized
- [x] Python venv + dependencies (flask, python-dotenv, requests, pytest, pytz, apscheduler)
- [x] SQLite schema (11 tables: players, weeks, picks, results, penalties, vault, rotation_queue, bet_slips, fixtures, team_aliases, fixture_events)
- [x] Database helper module (init_db, get_db, seed_players)
- [x] Flask app with /webhook and /health endpoints
- [x] Message parser (commands, picks, results, general)
- [x] Node.js WhatsApp bridge (whatsapp-web.js + Express)
- [x] 23 parser tests passing
- [x] End-to-end WhatsApp round-trip working
- [x] Dedicated bot WhatsApp account (WhatsApp Business — "The Betting Butler")

## Phase 1: MVP [COMPLETE]

### Pre-Implementation
- [x] Step 0a: Update requirements_document.md
- [x] Step 0b: Create PROGRESS.md (this file)

### Implementation Steps
- [x] Step 1: Player service & test mode (prefix parsing, phone lookup, bridge sender_phone)
- [x] Step 2: Butler message formatter (all bot responses in butler style)
- [x] Step 3: Week management service (create, close, complete weeks)
- [x] Step 4: Pick collection & storage (submit, update, track missing, all-picks-in)
- [x] Step 5: Result processing (record results, streak tracking, Ed-only)
- [x] Step 6: Penalties & vault (suggest, confirm, vault totals)
- [x] Step 7: Rotation management (standard rotation, penalty queue)
- [x] Step 8: Stats & commands (!stats, !leaderboard, !rotation, !vault, admin commands)
- [x] Step 9: Scheduler & reminders (APScheduler: Thu/Fri reminders, deadline, Mon recap)
- [x] Step 10: Tests & verification (73 unit tests passing)

### Post-Implementation Fixes
- [x] Bridge loads .env via dotenv (shared config with Flask)
- [x] Removed group discovery logging (GROUP_CHAT_ID now set)
- [x] Command args parser fixed (split all args, not just first)
- [x] Formal name: Mr Nialler -> Mr Niall
- [x] End-to-end WhatsApp testing: picks, results, all commands, penalties, rotation
- [x] Test data cleared — database ready for live weekend

## Decisions Made

| Decision | Choice | Reason |
|----------|--------|--------|
| Flask port | 5001 | Port 5000 used by macOS AirPlay Receiver |
| Bridge HTTP client | Node built-in `http` module | Node 18 experimental `fetch` fails on localhost |
| Bridge localhost URL | `127.0.0.1` (not `localhost`) | Node resolves `localhost` to IPv6 `::1`, Flask listens on IPv4 |
| Bridge message event | `message_create` | `message` only fires for others' messages; need own messages for test group |
| Bot identity | Separate WhatsApp Business account | Bot appears as "The Betting Butler", not the developer |
| Pick submission window | Wednesday 7PM - Friday 10PM | Earlier than original Thursday — picks sometimes come in earlier |
| Pick confirmation | Confirm on receipt, no response required | Less friction for players |
| Test mode | Prefix format (`Kev: pick text`) | Quick to type, explicit player attribution |
| Results processing | Ed only (by phone number) | Prevents banter with emojis being misread as results |
| Bridge .env loading | dotenv with path to project root .env | Single source of truth for config |
| Friday reminder time | 7PM (changed from 5PM) | Better fit for group's schedule |

## Known Issues & Gotchas

- **npm cache permissions**: `~/.npm` had root-owned files. Fixed with `sudo chown -R $(whoami) ~/.npm`
- **getContact() fails on own messages**: `message_create` events for own messages don't have contact data. Fixed with try/catch fallback to `client.info.pushname`
- **Bot reply loops**: `message_create` captures bot's own replies. Fixed with `botSentMessages` tracking set in the bridge
- **urllib3 OpenSSL warning**: macOS system Python 3.9 uses LibreSSL 2.8.3. Harmless warning, can be ignored
- **Chromium zombie processes**: Killing the bridge with ctrl-C sometimes leaves Chromium running. Use `pkill -f "Chromium.*wwebjs_auth"` before restarting
- **`_shadow_message()` fixed**: Now calls working `llm_client.generate()` (re-implemented in Phase 2).
- **Abbreviation expansion fixed**: Short codes (ne, sf, gb) used `re.sub` without word boundaries, corrupting team names (e.g. "BourNew Englandmouth"). Fixed with `\b` anchors.
- **Parser false positives fixed**: Chat messages matched as picks — "The value" triggered "v" team-vs-team pattern, and long messages matched `_looks_like_pick`. Fixed with word boundaries on v/vs/@ and a 15-word length guard.

## Current State (2026-03-19)

- **Deployed on OCI**: Ubuntu 22.04 VM, Always Free tier (193.123.179.96)
- **All services running via PM2**: Bridge on :3000, Flask on :5001, health check
- **WhatsApp connected**: Bot authenticated and live in main group (447762550958-1423072447@g.us)
- **SSH access**: `ssh -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`
- **Tests**: 254 passing
- **Phase 2 complete**: Structured data, API integration, auto-resulting, market prices
- **Phase 3a implemented**: Live match events + smart auto-resulting (trial pending)
- **Phase 4 complete**: Multi-sport support (12 sports detected, fixture/odds/auto-result wired up)
- **Phase 5 complete**: UX polish, rotation logic fully correct
- **Admin phones configured**: Ed (`353871527436@c.us`) as ADMIN_PHONE, all 6 player phones stored in DB
- **LLM personality**: Butler persona live in main group (`LLM_ENABLED=true`)
- **LLM architecture**: Framing-only — butler adds opening/closing lines around templates, never rewrites structured content. Template text passed to LLM to prevent repetition. Reminders use opening only (no closing).
- **LLM functions**: `generate()`, `banter_reply()` implemented and working
- **Group isolation**: `group_id` on weeks table — test and main groups have separate week/pick spaces
- **API-Football**: Fixture caching, pick enrichment, smart auto-resulting (per-fixture on FT + Mon 10AM safety sweep)
- **Multi-sport**: Sport detection on every pick, sport-aware matching/aliases/odds; non-football API keys not yet configured
- **Match monitor**: Live events (goals, red cards) + auto-result on match end; feature-flagged `MATCH_MONITOR_ENABLED`
- **The Odds API**: Market price lookup on pick submission (best-effort, covers all 12 sports)
- **Rotation**: Sole loser auto-queued at front; penalty placements don't advance standard cursor (`placer_is_penalty` on weeks); same-week streak penalties sorted by rotation order

## Phase 0.5: Cloud Migration [LIVE]

### PM2 & Reliability
- [x] PM2 ecosystem.config.js for bridge + Flask + health check
- [x] PM2 auto-restart on crash
- [x] PM2 startup on machine reboot
- [x] Health check script (pings Flask + Bridge /health every 5 min)
- [x] Telegram alerting via @punteralerts_bot (down + recovery notifications)

### Oracle Cloud Migration
- [x] Sign up Oracle Cloud Always Free
- [x] Provision Ubuntu 22.04 VM (1 OCPU / 1GB RAM)
- [x] Migrate bot to OCI (bridge, Flask, health check running via PM2)
- [x] Install system deps for Chromium (libgbm1, libasound2, etc.)
- [x] Add swap (2GB) to handle Chromium memory on 1GB VM
- [x] Node 20 via nvm + run-with-node20.sh wrapper for bridge
- [x] Puppeteer timeout patches (protocolTimeout 5min, launch timeout 3min)
- [x] QR code endpoint (/qr) + PNG file for headless authentication
- [x] WhatsApp authenticated and bot live (2026-02-18)
- [x] First live message sent to main group (2026-02-19)
- [x] Ed's missed pick (Liverpool 3/4) recorded via webhook
- [x] Validate unattended Fri–Mon run (Week 1 complete)
- [ ] Test remote restart via OCI console

### Deployment Hygiene (completed 2026-02-19)
- [x] **Git auth on server** — SSH key (ed25519) generated on OCI VM, added to GitHub, remote switched to SSH. `git pull` works.
- [x] **Puppeteer launch timeout patch permanent** — `postinstall` script in `bridge/package.json` auto-patches `puppeteer-core` timeout (30s -> 180s) after any `npm install`.
- [x] **PM2 state saved** — `pm2 save` run; all three processes auto-restart on VM reboot.
- [x] **Local changes committed and pushed** — All OCI deployment fixes committed and synced to server.
- [x] **Telegram alerting** — Health check sends alerts via Telegram bot (@punteralerts_bot) when Flask or Bridge goes down, and recovery notifications when they come back up.

## Phase 1.5: LLM Personality [LIVE — Main Group]

### Architecture (Rewritten 2026-02-23)
- [x] Groq API integration (llama-3.3-70b-versatile, free tier)
- [x] `src/llm_client.py` — complete rewrite; `generate()` replaced by `get_framing()` returning `{"opening": "...", "closing": "..."}`
- [x] `src/butler.py` — complete rewrite; LLM frames templates, never replaces them
- [x] `config/personality.yaml` — complete rewrite; new butler character config (Colonel Slade removed)
- [x] `src/app.py` — `_try_banter()` updated to call `butler.banter_reply()`
- [x] Feature flag: `LLM_ENABLED` in `.env` (currently `true` for main group)

### Butler Character (defined 2026-02-23)
The butler is formally nameless — the lads call him Botsu. He finds the whole enterprise faintly absurd and quietly charming. Warm beneath the formality. Serves faithfully, holds no opinions on selections, unflappable in chaos.

**Message structure:**
- Opening line (butler-voiced, one sentence)
- Structured template content (unchanged)
- Closing line (butler-voiced, one sentence — omitted for reminders)
- Slightly more latitude (two sentences) for week open/close
- LLM receives template text to avoid repeating information
- First pick of the week gets a special `pick_confirmed_first` scenario
- All-picks-in message includes a summary of every player's selection

**Player relationships:**
- Ed: Professional admiration — runs a tight ship, the butler approves
- Kev: Mild affection, never stated — simply a good egg
- DA: Gentle old-world formality — steady, treated accordingly
- Nug: Patient loyalty — he'll come good eventually
- Nialler: Philosophical acceptance — defies categorisation, peace made with this
- Pawn: Wry acknowledgment — built the butler, irony noted and risen above
- Brian (non-player): Diplomatic wariness — acknowledged occasionally, bait never taken; one perfectly calibrated remark that gives him nothing

**LLM scope:**
- ON: pick confirmations, result announcements, reminders, banter (direct mentions, Brian stirring)
- OFF: !picks, !stats, !leaderboard, !rotation, !vault, !help, bet slip, penalties (clean templates)

### Shadow Mode [FIXED]
- `_shadow_message()` now calls working `llm_client.generate()` (re-implemented in Phase 2)
- Bridge supports `GROUP_CHAT_IDS` for multi-group monitoring

### Kill Switch
To disable LLM quickly if needed:
```bash
sed -i 's/LLM_ENABLED=true/LLM_ENABLED=false/' ~/punter-bot/.env
pm2 restart all
```

## Phase 2: Structured Data & API Integration [COMPLETE]

### Step 0a: Fix Broken LLM Functions (2026-02-25)
- [x] `llm_client.generate()` — re-implemented as plain-text LLM call (not JSON framing)
- [x] `butler.banter_reply()` — implemented for Brian/bot mention banter
- [x] `_shadow_message()` now works — calls working `generate()`

### Step 0b: Group Isolation (2026-02-25)
- [x] Added `group_id` column to `weeks` table (with migration for existing data)
- [x] Updated `UNIQUE` constraint: `UNIQUE(week_number, season, group_id)`
- [x] All week_service functions accept `group_id` parameter
- [x] `app.py` stores `group_id` on Flask `g` object, threads through all handlers
- [x] Scheduler jobs pass `group_id` for main group
- [x] Test and main groups now fully isolated in the database

### Step 1a: Schema Extensions (2026-02-25)
- [x] 3 new columns on `picks`: sport, api_fixture_id, market_price, confirmed_odds (competition, event_name, market_type, is_late removed in codebase cleanup)
- [x] New `fixtures` table (api_id, sport, competition, teams, kickoff, scores, status)
- [x] New `team_aliases` table (alias → canonical_name, COLLATE NOCASE)
- [x] 50+ team aliases seeded (Premier League, European clubs, Scottish)
- [x] Migration functions in `db.py` (ALTER TABLE, non-destructive)

### Step 1b: API-Football Client (2026-02-25)
- [x] `src/api/api_football.py` — full v3 client with local file caching
- [x] `src/services/fixture_service.py` — weekend fixture fetch (Fri-Mon), cache to DB
- [x] Scheduler job: fetch fixtures Wed 7:30PM (Europe/Dublin)
- [x] Priority leagues: EPL, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, Europa League, Scottish Prem, Six Nations, PRO14

### Step 1c: Pick Matching (2026-02-25)
- [x] `src/services/match_service.py` — three-tier matching:
  1. Alias table lookup (team_aliases)
  2. Fuzzy string matching (difflib)
  3. LLM fallback (Groq — send pick + fixture list, ask to match)
- [x] Best-effort enrichment in `pick_service.py` — never blocks pick submission
- [x] `_try_enrich()` called on every pick submit, wrapped in try/except

### Step 2: Auto-Resulting (2026-02-25)
- [x] `src/services/auto_result_service.py`
- [x] Handles win, BTTS, over/under, HT/FT bet types
- [x] Checks matched picks against completed fixtures (API-Football scores)
- [x] Records results, checks penalty streaks, builds butler-voiced announcements
- [x] Single-fixture auto-resulting via `auto_result_fixture()` (used by match monitor)
- [x] Scheduler: Monday 10AM safety sweep (replaces fixed Sun 8PM + Mon 10AM)

### Step 3: The Odds API (2026-02-25)
- [x] `src/api/odds_api.py` — batch odds fetch with 2hr cache TTL
- [x] Market price lookup on pick submission (wired into `_try_enrich()`)
- [x] Logs remaining API quota from response headers
- [x] Stores `market_price` alongside player-submitted odds

### Config & Tests (2026-02-25)
- [x] `API_FOOTBALL_KEY` and `ODDS_API_KEY` added to config.py and .env.example
- [x] Test fixtures updated (conftest.py)
- [x] 92 tests passing (up from 73)

## Phase 3: Live Match Events & Smart Auto-Resulting [IN PROGRESS]

### Step 1: Match Monitor Service (2026-02-25)
- [x] `src/services/match_monitor_service.py` — unified polling loop (events + auto-resulting)
- [x] Polls matched fixtures from kickoff through FT (every 10 min live, every 30 min extra time)
- [x] Extracts goals and red cards from API-Football `events` data
- [x] Posts live events to group: `⚽ Liverpool 1-0 Arsenal — Salah 23'`
- [x] Posts final score on match end: `FT: Liverpool 2-1 Arsenal`
- [x] Triggers auto-result immediately on FT (no waiting for cron)
- [x] Kickoff batching: fixtures sharing a date use single API call (essential for budget)
- [x] New `fixture_events` table for dedup (prevents duplicate event posts)
- [x] `extract_events(raw_json)` in fixture_service — parses goals + red cards
- [x] `match_event()` and `match_ended()` butler templates

### Step 2: Scheduler Integration (2026-02-25)
- [x] `schedule_match_monitor(fixture_api_id, kickoff, week_id)` — date-triggered polling
- [x] Scheduled automatically when a pick is matched to a fixture (via pick_service)
- [x] Startup recovery: `schedule_monitors_for_week()` re-schedules unresulted picks on restart
- [x] Removed Sunday 8PM cron job (replaced by per-fixture monitoring)
- [x] Kept Monday 10AM safety sweep (catches anything missed)

### Step 3: Config & Testing (2026-02-25)
- [x] `MATCH_MONITOR_ENABLED` config flag (default `false` — trial mode)
- [x] `MATCH_MONITOR_GROUP_ID` — events posted to shadow group during trial
- [x] 115 tests passing (23 new: event extraction, dedup, auto-result, butler templates, polling)
- [x] `fixture_events` cleaned up in `!resetweek` and `!resetseason`

### Trial Plan
- [ ] Deploy to server with `MATCH_MONITOR_ENABLED=true`, `MATCH_MONITOR_GROUP_ID=<shadow_group>`
- [ ] Monitor one trial weekend (events + auto-resulting to test group only)
- [ ] Validate: events within 10 min, no duplicates, API budget < 100 req/day on Saturday
- [ ] After successful trial: switch `MATCH_MONITOR_GROUP_ID` to main group

### API Budget (with kickoff batching)
| Scenario | Requests | Notes |
|----------|----------|-------|
| Wed fixture fetch | ~14 | 14 priority leagues |
| Pick enrichment (Thu-Fri) | ~6-12 | Match + odds lookup |
| Match monitoring (Sat) | ~30-40 | Batched by kickoff time |
| Match monitoring (Sun) | ~15-25 | Fewer fixtures |
| Match monitoring (Mon) | ~10-15 | If Monday night picks |
| Monday 10AM sweep | ~5 | Safety net |
| **Daily peak (Saturday)** | **~50-65** | Comfortable with batching |

## Phase 4: Multi-Sport Support [COMPLETE]

### Sport Detection & Storage (2026-02-25)
- [x] `detect_sport()` in message_parser.py — keyword-based detection for 12 sports
- [x] Keywords: rugby, NFL, NBA, NHL, MMA, tennis, golf, boxing, darts, GAA, horse racing
- [x] Default → "football" when no sport keywords found
- [x] Every pick now has a `sport` field (parser detects, enrichment overrides if matched)
- [x] `submit_pick()` accepts `sport` parameter, passed from parser through app.py
- [x] 25 new sport detection tests

### Sport-Aware Aliases (2026-02-25)
- [x] `sport` column added to `team_aliases` table with `UNIQUE(alias, sport)` constraint
- [x] Migration: recreates table with new constraint (existing aliases get `sport='football'`)
- [x] Seeded: rugby (provinces, Six Nations), NFL abbreviations, NBA abbreviations
- [x] `_resolve_alias()` tries sport-specific alias first, falls back to any sport
- [x] Butler `PICK_ABBREVIATIONS` expanded with NFL/NBA abbreviations

### Generic API-Sports Client (2026-02-25)
- [x] `src/api/api_sports.py` — unified client for rugby, NFL, NBA, NHL, MMA
- [x] Config dict maps sport → base URL + API key config name
- [x] Same caching pattern as `api_football.py`
- [x] `normalize_fixture()` converts sport-specific responses to standard format
- [x] Skips silently if API key not configured for a sport

### Multi-Sport Fixture Fetching (2026-02-25)
- [x] `_cache_fixtures()` accepts `sport` parameter
- [x] `cache_normalized_fixtures()` for pre-normalized non-football fixtures
- [x] `fetch_weekend_fixtures()` loops through all configured sports
- [x] `get_upcoming_fixtures()` accepts optional `sport` filter
- [x] Football still uses existing `api_football.py` (don't break what works)
- [x] Scheduler's daily fetch job already calls updated `fetch_weekend_fixtures()`

### Sport-Aware Matching & Odds (2026-02-25)
- [x] `match_pick()` accepts `sport` parameter, filters fixtures by sport
- [x] LLM prompt includes sport context: "This is a {sport} pick"
- [x] Odds API extended with rugby, NFL, NBA, NHL, MMA, tennis, golf, boxing sport keys
- [x] `SPORT_PRIORITY_KEYS` map — sport-specific search order for odds lookup
- [x] `find_market_price()` and `get_best_odds_for_selection()` accept sport parameter

### Sport-Aware Auto-Resulting (2026-02-25)
- [x] `_evaluate_pick()` skips BTTS/HT-FT for non-football sports
- [x] `_evaluate_handicap()` added — works across all team sports
- [x] `_team_in_text()` strips sport-specific suffixes (" rugby", " rfc", " sc", " cf")

### Odds-Only Enrichment (2026-02-25)
- [x] Tennis, golf, boxing skip fixture matching entirely
- [x] `_try_enrich_odds_only()` queries Odds API directly for market prices
- [x] Stores `market_price` without `api_fixture_id`

### Config (2026-02-25)
- [x] `API_RUGBY_KEY`, `API_NFL_KEY`, `API_NBA_KEY`, `API_NHL_KEY`, `API_MMA_KEY` in config.py
- [x] All default to empty string (disabled until API keys configured on server)
- [x] conftest.py updated to monkeypatch all new keys

### API Coverage

| Sport | Fixtures | Odds | Auto-Result |
|-------|----------|------|-------------|
| Football | ✅ API-Football | ✅ | ✅ Done |
| Rugby | ✅ API-Sports | ✅ | ✅ Ready (needs API key) |
| NFL | ✅ API-Sports | ✅ | ✅ Ready (needs API key) |
| NBA | ✅ API-Sports | ✅ | ✅ Ready (needs API key) |
| NHL | ✅ API-Sports | ✅ | ✅ Ready (needs API key) |
| MMA/UFC | ✅ API-Sports | ✅ | Partial (fighter matching TBD) |
| Tennis | ❌ | ✅ | Prices only |
| Golf | ❌ | ✅ | Prices only |
| Boxing | ❌ | ✅ | Prices only |
| Darts | ❌ | ❌ | Manual only |
| GAA | ❌ | ❌ | Manual only |
| Horse Racing | ❌ | ❌ | Manual only |

### Remaining
- [ ] MMA/UFC fighter-specific resulting (fighter A beat fighter B, not team scores)
- [ ] Configure sport API keys on server when ready (rugby first for Six Nations)

## Phase 5: UX Polish & Rotation Fixes [COMPLETE — 2026-03-19]

### Display & Announcements
- [x] Ed-style result announcements: `Mr. Kevin ❌ — Liverpool to win @ 2/1`
- [x] Streak-multiplied loss emojis: ❌❌ for 2L, ❌❌❌ for 3L
- [x] Emoji form/streak in stats: ✅/❌ instead of W/L (form: `✅✅❌✅❌`, streak: `✅✅✅`)
- [x] Acca loss suppression: live events (goals, FT) suppressed once any pick has lost; result announcements still post
- [x] Kickoff-ordered picks: `!picks` and all-picks-in message ordered by fixture kickoff time with day headers and "Kickoff TBC" for unmatched picks
- [x] Kickoff-bundled display: same-kickoff picks grouped under single `⏰ time` header
- [x] Early kickoff warnings: `_early_kickoff_note()` on individual picks; `earliest_kickoff_warning()` on status — warns when any fixture kicks off before Saturday 12:30 PM Dublin time

### Submission Window
- [x] Dynamic opening: window opens immediately when previous week completes (all results in), not fixed to Wednesday 7PM
- [x] Closed-window reply: picks outside the window get a reply instead of silent drop

### Rotation Fixes (2026-03-19)
- [x] **Sole loser rule**: when exactly one player loses their pick for the week, they are automatically added to the front of the rotation queue at week completion (no Ed confirmation required)
- [x] **Penalty cursor fix**: added `placer_is_penalty` column on `weeks` table; penalty placements no longer advance the standard rotation cursor — standard rotation resumes from after the last non-penalty placer
- [x] **Same-week streak penalty ordering**: multiple streak penalties confirmed for the same week are re-sorted in rotation order after each confirmation, regardless of the order Ed confirms them
- [x] **Duplicate guard**: `add_to_penalty_queue` skips silently if player already has an unprocessed entry
- [x] Historical data migrated: Declan's week 4 penalty placement flagged as `placer_is_penalty=1`; Nug added to rotation queue as sole loser for week 4

### Other Fixes
- [x] Reject long messages as picks (>30 words)
- [x] Filter non-football fixtures by priority leagues before caching
- [x] Handicap-safe odds stripping: `(?<![+-])` lookbehind prevents `-10.5` handicaps being stripped
- [x] Sport-filtered fixture joins: prevent cross-sport fixture collisions
- [x] Emoji result parsing: `♟️❌` style results supported
- [x] Cache TTL fix: `refresh_fixture()` bypasses cache so match monitor polls get fresh data
- [x] Alias-aware auto-resulting: resolves abbreviations via alias table when substring matching fails
- [x] Cross-sport fallback: football-default picks retry with `sport=None` to match any cached fixture
- [x] Single API key: `API_FOOTBALL_KEY` shared across all api-sports.io products
- [x] Pick count in LLM context: `picks_so_far` passed to `pick_confirmed()` so LLM knows pick number

## Codebase Cleanup [COMPLETE — 2026-03-19]

- [x] Removed 5 dead functions: `_picks_kicker()`, `reset_persona()`, `week_has_loss()` (now restored — was used), `get_pending_penalty_for_player()` (nickname version), `lookup_player_by_emoji()`
- [x] Dropped 4 unused `picks` columns: `is_late`, `competition`, `event_name`, `market_type` — set during enrichment, never read back; DB migration drops them on next deploy
- [x] Consolidated penalty threshold maps into `PENALTY_THRESHOLDS` / `PENALTY_AMOUNTS` constants in `penalty_service.py` (was copy-pasted in `app.py` and `auto_result_service.py`)
- [x] Consolidated `get_upcoming_fixtures()` from 4 near-identical SQL branches into 1 parameterized query
- [x] Net: −76 lines across 13 files, 254 tests passing

## Phase 3b: Bet Slip Reader [COMPLETE — 2026-03-21]

### Bet Slip Reader
- [x] Bridge caches recent media messages in `recentMessages` Map (cap 50, FIFO eviction)
- [x] New `POST /media` endpoint on bridge — Flask pulls image on demand after validating placer
- [x] `llm_client.read_bet_slip()` — Groq vision (`meta-llama/llama-4-scout-17b-16e-instruct`) extracts stake, total_odds, potential_return, per-leg odds
- [x] `src/services/bet_slip_service.py` — fetch, extract, match legs → picks (difflib ≥0.6), persist; best-effort, never raises
- [x] `app.py` threads `message_id`, calls `process_bet_slip()` after `advance_rotation()`
- [x] 16 new tests (272 total)
- [x] Historical backfill: `scripts/backfill_betslip.py` (generic) + per-week scripts weeks 1–5
- [x] Weeks 1–5 backfilled: 5 bet_slips rows, 30 picks with confirmed_odds

### Remaining
- [ ] **Match start validation** — warn on picks for matches already kicked off

## Roadmap: Outstanding Items

### Match Monitor Trial (Phase 3a → Main Group)
- [ ] Enable `MATCH_MONITOR_ENABLED=true` on server
- [ ] Set `MATCH_MONITOR_GROUP_ID=<shadow_group>` for trial weekend
- [ ] Validate: events posting within 10 min, no duplicates, API budget < 100 req/day Saturday
- [ ] Switch `MATCH_MONITOR_GROUP_ID` to main group after successful trial

### Match Start Validation (Phase 3b remainder)
- [ ] Warn when a pick is submitted for a match that has already kicked off

### Multi-Sport API Keys (Phase 4)
- [ ] Configure rugby API key on server (Six Nations already in play)
- [ ] MMA/UFC fighter-specific auto-resulting (fighter A beat fighter B, not team scores)

### GAA
- [ ] Fixture API (RTÉ scraping — see `gaa-data-sources.md`)
- [ ] Odds (Betfair Exchange API)

### Low Priority / Future
- [ ] Historical analytics / Punter Wrapped
- [ ] Web dashboard
- [ ] Test remote restart via OCI console

---

**Last Updated:** 2026-03-21
**Status:** ✅ Phase 3b Complete — Bet slip reader live; 272 tests passing; weeks 1–5 backfilled
