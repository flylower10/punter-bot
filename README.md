# Punter Bot — The Betting Butler

WhatsApp bot that manages a weekly accumulator betting pool for the lads.

## Setup

### Python backend

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your config
```

### Node.js bridge

```bash
cd bridge
npm install
```

### Configuration

Edit `.env` with your settings:

- `GROUP_CHAT_ID` — WhatsApp group ID (leave blank on first run, the bridge will log group IDs to help you find it)
- `FLASK_PORT` — Python backend port (default: 5001)
- `BRIDGE_URL` — Bridge URL (default: http://localhost:3000)
- `DB_PATH` — SQLite database path (default: data/punter_bot.db)
- `TIMEZONE` — Your timezone (default: Europe/Dublin)

## Running

**One command (recommended):**
```bash
./scripts/start.sh
```
This cleans up any stale processes, starts Flask in the background, and runs the bridge in the foreground. Ctrl+C stops both.

**Or manually in two terminals:**

Terminal 1 — Python backend:
```bash
source venv/bin/activate
python -m src.app
```

Terminal 2 — WhatsApp bridge:
```bash
cd bridge
npm start
```

On first run, scan the QR code displayed in Terminal 2 with WhatsApp (Linked Devices). The session persists after the initial scan.

### Restarting

The bridge now **auto-cleans** stale Chrome on startup, so `cd bridge && npm start` usually works even after a crash. If you hit "detached Frame" or port-in-use:

```bash
./scripts/restart.sh
```

Then run `./scripts/start.sh` or start both services manually. The bridge will auto-reconnect on detached Frame when possible; Flask retries up to 3 times if the bridge is reconnecting.

## Production (OCI Cloud)

The bot runs on an Oracle Cloud Always Free Ubuntu 22.04 VM, managed by PM2.

**Server:** `ssh -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`

**SSH tunnel** (to access bridge locally): `ssh -L 3000:localhost:3000 -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`

**PM2 commands (on server):**
```bash
pm2 list                    # Status of all processes
pm2 logs punter-bridge      # Bridge logs
pm2 logs punter-flask       # Flask logs
pm2 restart punter-bridge   # Restart bridge
pm2 restart all             # Restart everything
```

**Deploying changes:**
```bash
# Local: commit and push
git add . && git commit -m "message" && git push

# Server: pull and restart
cd ~/punter-bot && git pull && pm2 restart all
```

**Health check & alerting:**
- Pings Flask and Bridge `/health` every 5 minutes
- Sends Telegram alerts via @punteralerts_bot if a service goes down
- Sends recovery notification when it comes back
- Config: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

**Key config (.env):**
- `TEST_MODE=false` for production
- `GROUP_CHAT_ID` or `GROUP_CHAT_IDS` for your group(s)
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for health alerts
- `LLM_ENABLED=false` — set to `true` to activate LLM personality
- `GROQ_API_KEY` — Groq API key (free tier)
- `API_FOOTBALL_KEY` — API-Football key (free tier: 100 req/day)
- `ODDS_API_KEY` — The Odds API key (free tier: 500 req/month)
- `SHADOW_GROUP_ID` — test group ID for shadow mode (LLM preview without affecting main group)
- `MATCH_MONITOR_ENABLED=false` — set to `true` to enable live match events + smart auto-resulting
- `MATCH_MONITOR_GROUP_ID` — group ID for match event posts (shadow group for trial, main group when live)
- See `MAIN_GROUP_READY.md` for the launch checklist

## LLM Personality

The bot can rewrite its template responses with a rotating weekly persona via Groq's free API. All config lives in `config/personality.yaml`.

**Shadow testing:** Set `SHADOW_GROUP_ID` in `.env`. Main group gets templates; test group gets LLM-enhanced versions of every message. Use `/test-webhook` to simulate picks/results/chat safely (only sends to test group).

```bash
# Simulate a message in the test group only
curl -X POST http://localhost:5001/test-webhook \
  -H 'Content-Type: application/json' \
  -d '{"sender": "Brian", "body": "Ed is going to lose again", "has_media": false}'
```

## Testing

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

## Project Structure

```
punter-bot/
├── bridge/                # Node.js WhatsApp bridge
│   ├── index.js
│   ├── package.json
│   └── run-with-node20.sh # nvm wrapper for OCI server
├── config/
│   └── personality.yaml   # LLM persona config (nicknames, scenarios, personas)
├── src/                   # Python backend
│   ├── app.py             # Flask app + webhook routes + shadow mode
│   ├── butler.py          # Message formatting (LLM-enhanced with template fallback)
│   ├── llm_client.py      # Groq API wrapper + persona management
│   ├── config.py          # Environment config
│   ├── db.py              # Database helpers + migrations
│   ├── schema.sql         # SQLite schema (11 tables)
│   ├── api/               # External API clients
│   │   ├── api_football.py  # API-Football v3 (fixtures, scores, events)
│   │   └── odds_api.py      # The Odds API (market prices)
│   ├── parsers/
│   │   └── message_parser.py
│   └── services/          # Business logic
│       ├── fixture_service.py       # Weekend fixture caching + event extraction
│       ├── match_service.py         # Pick-to-fixture matching (alias → fuzzy → LLM)
│       ├── auto_result_service.py   # Auto-resulting from completed fixtures
│       ├── match_monitor_service.py # Live match events + smart auto-resulting
│       ├── scheduler.py             # APScheduler jobs + match monitor scheduling
│       └── ...                      # picks, results, stats, rotation, etc.
├── scripts/
│   ├── health_check.py    # Health monitor + Telegram alerts
│   └── restart.sh
├── tests/
├── data/                  # SQLite DB (gitignored)
├── ecosystem.config.js    # PM2 process config
└── requirements.txt
```
