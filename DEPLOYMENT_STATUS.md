# Punter Bot OCI Deployment Status

*Last updated: 2026-02-18*

## What's Working

- **Flask app** – Runs on port 5001, DB initialized, scheduler OK
- **Health check** – Running under PM2
- **Node 20** – Bridge uses nvm's Node 20 via `run-with-node20.sh` (no more optional chaining errors)
- **Chrome/Chromium** – System Chromium installed; no more missing library errors
- **Swap** – 1 GB swap configured on OCI VM
- **QR code** – Displayed in logs and saved to `bridge/qr.png`; HTTP endpoint `/qr` added for viewing
- **Retry logic** – Bridge retries on timeout/context errors (up to 5 times with 15s delay)

## Current Blockers

### 1. Chrome Launch Timeout (30 seconds)

Puppeteer times out after 30 seconds waiting for the WebSocket endpoint. The OCI Always Free VM (1 GB RAM) is slow; Chrome needs more time to start. Our `timeout: 180000` in the bridge config and the Puppeteer patch are not taking effect—whatsapp-web.js appears to use Puppeteer in a way that bypasses our overrides.

### 2. Git Auth on Server

`git pull` fails with:
```
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/9tkdxzjnqy-hue/punter-bot.git/'
```

GitHub no longer accepts password auth. Need SSH key or Personal Access Token.

### 3. Flask & Health Check Stopped

Stopped to free RAM for bridge testing. Need to restart once bridge is stable.

---

## Plan for Tomorrow

### Step 1: Fix Git Auth on Server (~5 min)

**Option A – SSH (recommended)**
```bash
# On OCI server
cd ~/punter-bot
git remote set-url origin git@github.com:9tkdxzjnqy-hue/punter-bot.git
# Ensure SSH key is added to GitHub (Settings → SSH keys)
git pull
```

**Option B – Personal Access Token**
- GitHub → Settings → Developer settings → Personal access tokens → Generate new token
- Use token as password when `git pull` prompts

### Step 2: Fix Puppeteer Timeout (~15–30 min)

**Option A – Patch puppeteer-core on server (quick fix)**

Edit the file directly on the OCI server:
```bash
nano ~/punter-bot/bridge/node_modules/puppeteer-core/lib/cjs/puppeteer/node/BrowserLauncher.js
```

Find line ~76:
```javascript
timeout = 30000,
```
Change to:
```javascript
timeout = 180000,
```

Save and restart:
```bash
pm2 restart punter-bridge
pm2 logs punter-bridge
```

*Note: This patch is lost on `npm install`. Re-apply after any `npm install` in bridge, or add a postinstall script.*

**Option B – Upgrade OCI VM**
- Move from Always Free 1 GB to a paid shape (e.g. 2 GB RAM)
- Chrome may start fast enough to avoid timeout

**Option C – Run bridge on Mac**
- Keep Flask on OCI; run bridge locally on Mac
- Requires exposing bridge to internet or using a tunnel

### Step 3: Restart Flask & Health Check

```bash
pm2 start punter-flask punter-health-check
```

### Step 4: Test the Bot

1. View QR at http://localhost:3000/qr (via SSH tunnel: `ssh -L 3000:localhost:3000 -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96`)
2. Scan with punter bot phone (WhatsApp → Linked Devices → Link a Device)
3. Send `!help` in the WhatsApp group

---

## Key Paths & Commands

| Item | Path/Command |
|------|--------------|
| Project on OCI | `~/punter-bot` |
| SSH | `ssh -i ~/Documents/Oracle/ssh-key-2026-02-18.key ubuntu@193.123.179.96` |
| PM2 config | `ecosystem.config.js` |
| Bridge | `bridge/index.js` |
| PM2 logs | `pm2 logs punter-bridge` |
| PM2 status | `pm2 status` |

---

## Session Notes

- OCI instance: Ubuntu 22.04, VM.Standard.E2.1.Micro (1 GB RAM)
- Region: UK South (London)
- Bridge uses system Chromium (`/usr/bin/chromium-browser` or `/usr/bin/chromium`)
