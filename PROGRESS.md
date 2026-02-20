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

## Known Issues & Gotchas

- **npm cache permissions**: `~/.npm` had root-owned files. Fixed with `sudo chown -R $(whoami) ~/.npm`
- **getContact() fails on own messages**: `message_create` events for own messages don't have contact data. Fixed with try/catch fallback to `client.info.pushname`
- **Bot reply loops**: `message_create` captures bot's own replies. Fixed with `botSentMessages` tracking set in the bridge
- **urllib3 OpenSSL warning**: macOS system Python 3.9 uses LibreSSL 2.8.3. Harmless warning, can be ignored
- **Chromium zombie processes**: Killing the bridge with ctrl-C sometimes leaves Chromium running. Use `pkill -f "Chromium.*wwebjs_auth"` before restarting

## Current State (2026-02-20)

- **Deployed on OCI**: Ubuntu 22.04 VM, Always Free tier (193.123.179.96)
- **All services running via PM2**: Bridge on :3000, Flask on :5001, health check
- **WhatsApp connected**: Bot authenticated and live in main group (447762550958-1423072447@g.us)
- **SSH access**: `ssh -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`
- **SSH tunnel for bridge**: `ssh -L 3000:localhost:3000 -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`
- **Tests**: 73 passing (31 parser + 42 service tests)
- **Phase 1 complete**: All services wired up, commands working, scheduler initialized
- **LLM personality**: Shadow mode active — Colonel Slade only. Main group uses templates, test group gets LLM-enhanced versions
- **LLM scope**: Narrowed to pick confirmations, results, reminders, Brian banter only. Commands (!picks, !stats, etc.) use clean templates.
- **Cumulative format**: Emoji-based parsing — Ed 🍋, Kev 🧌, DA 👴🏻, Nug 🍗, Nialler 🔫, Pawn ♟️
- **!picks display**: Now shows player emojis alongside picks
- **This week**: Picks live — Ed (Liverpool 3/4), Aidan, Kev, DA recorded. Awaiting Niall, Nug.
- **Next**: Monitor shadow mode over the weekend, tune Colonel Slade if needed, then enable on main group

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
- [ ] Validate unattended Fri–Mon run
- [ ] Test remote restart via OCI console

### Deployment Hygiene (completed 2026-02-19)
- [x] **Git auth on server** — SSH key (ed25519) generated on OCI VM, added to GitHub, remote switched to SSH. `git pull` works.
- [x] **Puppeteer launch timeout patch permanent** — `postinstall` script in `bridge/package.json` auto-patches `puppeteer-core` timeout (30s -> 180s) after any `npm install`.
- [x] **PM2 state saved** — `pm2 save` run; all three processes auto-restart on VM reboot.
- [x] **Local changes committed and pushed** — All OCI deployment fixes committed and synced to server.
- [x] **Telegram alerting** — Health check sends alerts via Telegram bot (@punteralerts_bot) when Flask or Bridge goes down, and recovery notifications when they come back up. Replaces macOS desktop notifications.

## Phase 1.5: LLM Personality [LIVE — Shadow Testing]

### Architecture
- [x] Groq API integration (llama-3.3-70b-versatile, free tier)
- [x] `src/llm_client.py` — API wrapper with persona management
- [x] `config/personality.yaml` — all personality config in one YAML file, no code changes needed
- [x] `src/butler.py` — LLM enhances output; template fallback if LLM fails
- [x] Feature flag: `LLM_ENABLED` in `.env` (off for main group)

### Personas (rotate weekly — rotation logic preserved)
- [x] Colonel Slade — fierce military motivator (active, sole persona for now)
- [ ] Add more personas once Colonel Slade is tuned
- [x] Persona rotation logic built — selects randomly on new week creation

### Player Nicknames (replaces "Mr X" convention for LLM)
- [x] Ed: Ed, The Hospital Bed, Edmundo, Eddie Mc, Bitter Bitter Ed
- [x] Kev: Kev Mc, Monster Mc, Caoimh, Barreler
- [x] Ronan: Nugget, Nug, Goldie, Nugent
- [x] Niall: Nialler, Gun, Scrunnion
- [x] Aidan: Pawn, the Evil Pawn, MaHogAner, Mawner, Aidean Moghan
- [x] Declan: DA, Don, Dec, Father
- [x] Brian (non-player): The Folak Express, Folak

### Banter Rules
- [x] Bot responds to Brian only when he's stirring (provocative keyword detection)
- [x] Bot responds when directly mentioned ("butler", "bot", "betting butler")
- [x] No random banter on general chat — removed banter_rate
- [x] Responses are sharp: 1 sentence ideal, 2 max, max_tokens=60

### LLM Scope (narrowed after initial testing)
- [x] LLM ON: pick confirmations, result announcements, reminders, Brian banter
- [x] LLM OFF: !picks, !stats, !leaderboard, !rotation, !vault, !help, all_picks_in, bet slip, penalties
- [x] Commands use clean structured templates — no LLM rewriting

### Display Improvements
- [x] Player emojis shown in !picks output (🍋 Ed, ♟️ Pawn, 🧌 Kev, etc.)

### Shadow Testing Mode
- [x] `SHADOW_GROUP_ID` in `.env` — test group receives LLM-enhanced versions
- [x] Main group gets safe template responses (LLM off)
- [x] Shadow mode mirrors: original message + LLM response to test group
- [x] `/test-webhook` endpoint — processes picks/results/banter safely in test group only
- [ ] Validate shadow mode over the weekend with real messages
- [ ] Review LLM output quality and tune personality config
- [ ] Enable LLM on main group once satisfied

## Phase 2: Enhancements [PLANNED]

### Bet Slip & Other
- [ ] Bet slip image reading (OCR)
- [ ] Rotation queue visibility
- [ ] Monday recap

## Phase 3: Intelligence [PLANNED]

### API & Validation
- [ ] API integration (The Odds API, API-Football)
- [ ] **Match start validation** — Check if pick is for a match that has already started; warn or void (e.g. Thursday match picked on Friday after kick-off)
- [ ] Automatic result detection
- [ ] Live score updates
- [ ] Historical analytics
