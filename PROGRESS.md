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
- **`_shadow_message()` broken**: Still calls old `llm_client.generate()` which no longer exists. Non-critical — wrapped in try/except so main group unaffected. Needs fix before shadow mode works again.

## Current State (2026-02-23)

- **Deployed on OCI**: Ubuntu 22.04 VM, Always Free tier (193.123.179.96)
- **All services running via PM2**: Bridge on :3000, Flask on :5001, health check
- **WhatsApp connected**: Bot authenticated and live in main group (447762550958-1423072447@g.us)
- **SSH access**: `ssh -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`
- **Tests**: 73 passing (31 parser + 42 service tests)
- **Phase 1 complete**: All services wired up, commands working, scheduler initialized
- **Admin phones configured**: Ed (`353871527436@c.us`) as ADMIN_PHONE, all 6 player phones stored in DB
- **LLM personality**: Butler persona live in main group (`LLM_ENABLED=true`)
- **LLM architecture**: Framing-only — butler adds opening/closing lines around templates, never rewrites structured content
- **Shadow mode**: `_shadow_message()` currently broken — needs fix before shadow testing resumes
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

### Shadow Mode [BROKEN — needs fix]
- `_shadow_message()` in `app.py` still calls old `llm_client.generate()` — throws silent error
- Main group unaffected (wrapped in try/except)
- Fix required before shadow testing can resume next weekend
- Bridge only reads `GROUP_CHAT_ID` (singular) — does not support `GROUP_CHAT_IDS` for multi-group monitoring

### Kill Switch
To disable LLM quickly if needed:
```bash
sed -i 's/LLM_ENABLED=true/LLM_ENABLED=false/' ~/punter-bot/.env
pm2 restart all
```

## Phase 2: Enhancements [PLANNED]

### Bet Slip & Other
- [ ] Bet slip image reading (OCR)
- [ ] Monday recap (currently week summary fires when last result is in)
- [ ] Fix `_shadow_message()` for shadow testing to resume

## Phase 3: Intelligence [PLANNED]

### API & Validation
- [ ] API integration (The Odds API, API-Football)
- [ ] **Match start validation** — Check if pick is for a match that has already started; warn or void
- [ ] Automatic result detection
- [ ] Live score updates
- [ ] Historical analytics
