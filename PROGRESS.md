# Punter Bot — Progress Tracker

## Phase 0: Foundation [COMPLETE]

- [x] Git repo initialized
- [x] Python venv + dependencies (flask, python-dotenv, requests, pytest, pytz, apscheduler)
- [x] SQLite schema (8 tables: players, weeks, picks, results, penalties, vault, rotation_queue, bet_slips)
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

## Current State (2026-02-25)

- **Deployed on OCI**: Ubuntu 22.04 VM, Always Free tier (193.123.179.96)
- **All services running via PM2**: Bridge on :3000, Flask on :5001, health check
- **WhatsApp connected**: Bot authenticated and live in main group (447762550958-1423072447@g.us)
- **SSH access**: `ssh -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`
- **Tests**: 115 passing (31 parser + 84 service/integration tests)
- **Phase 2 complete**: Structured data, API integration, auto-resulting, market prices
- **Phase 3a implemented**: Live match events + smart auto-resulting (trial pending)
- **Admin phones configured**: Ed (`353871527436@c.us`) as ADMIN_PHONE, all 6 player phones stored in DB
- **LLM personality**: Butler persona live in main group (`LLM_ENABLED=true`)
- **LLM architecture**: Framing-only — butler adds opening/closing lines around templates, never rewrites structured content
- **LLM functions**: `generate()`, `banter_reply()`, `reset_persona()` all implemented and working
- **Group isolation**: `group_id` on weeks table — test and main groups have separate week/pick spaces
- **API-Football**: Fixture caching (Wed 7:30PM), pick enrichment, smart auto-resulting (per-fixture on FT + Mon 10AM safety sweep)
- **Match monitor**: Live events (goals, red cards) + auto-result on match end; feature-flagged `MATCH_MONITOR_ENABLED`
- **The Odds API**: Market price lookup on pick submission (best-effort)
- **Friday reminder**: Updated to 7PM

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
- Closing line (butler-voiced, one sentence)
- Slightly more latitude (two sentences) for week open/close

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
- [x] `llm_client.reset_persona()` — implemented as no-op (returns None)
- [x] `_shadow_message()` now works — calls working `generate()`

### Step 0b: Group Isolation (2026-02-25)
- [x] Added `group_id` column to `weeks` table (with migration for existing data)
- [x] Updated `UNIQUE` constraint: `UNIQUE(week_number, season, group_id)`
- [x] All week_service functions accept `group_id` parameter
- [x] `app.py` stores `group_id` on Flask `g` object, threads through all handlers
- [x] Scheduler jobs pass `group_id` for main group
- [x] Test and main groups now fully isolated in the database

### Step 1a: Schema Extensions (2026-02-25)
- [x] 7 new columns on `picks`: sport, competition, event_name, market_type, api_fixture_id, market_price, confirmed_odds
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

## Phase 3b: Enhancements [PLANNED]

### Bet Slip Reader
- [ ] Bridge downloads image via `message.downloadMedia()`
- [ ] Groq Vision extracts picks, odds, stake, return from bet slip screenshot
- [ ] Populates `confirmed_odds` on matched picks
- [ ] Stores image + aggregate data in `bet_slips` table

### Other
- [ ] **Match start validation** — warn on picks for matches already kicked off
- [ ] Historical analytics / Punter Wrapped
- [ ] Web dashboard (low priority)

---

**Last Updated:** 2026-02-25
**Status:** ✅ Phase 3a Implemented — Live match events & smart auto-resulting (trial pending)
