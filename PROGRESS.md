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

## Current State

- **Both services running**: Flask on :5001, Bridge on :3000
- **WhatsApp connected**: Bot account authenticated via Linked Devices
- **Test group**: "Punter test" (120363407272021793@g.us)
- **Database**: Cleared and ready for live weekend testing
- **Tests**: 73 passing (31 parser + 42 service tests)
- **Phase 1 complete**: All services wired up, commands working, scheduler initialized
- **Next**: Live weekend test — copy picks from main group using `Kev: pick text` prefix format
- **Cumulative format** (2026-02-13): Emoji-based parsing added — copy thread-style messages (`[emoji] [pick]` per line) from main group; all 6 players have emojis configured (Ed 🍋, Kev 🧌, DA 👴🏻, Nug 🍗, Nialler 🔫, Pawn ♟️)
