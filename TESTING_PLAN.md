# Punter Bot — Testing Plan

Reference for MVP testing. Update status as flows are confirmed.

**Status key:** ✅ Confirmed | ⏳ Pending | ⬜ Not applicable / Phase 2+

---

## Pick flows

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 1 | **Single pick (with odds)** — Player sends e.g. `♟️ Dortmund 6/10` → bot confirms pick and who's still missing | ✅ | |
| 2 | **Single pick (no odds)** — Player sends e.g. `♟️ Scotland + 8` → bot confirms with placer name for odds | ✅ | |
| 3 | **Cumulative picks (new)** — Multi-line message with emojis → bot confirms only new picks | ✅ | |
| 4 | **Cumulative picks (update)** — Player edits a line and resends → bot confirms only the changed pick | ✅ | Bare team names (e.g. Villa) accepted; replacement detected |
| 5 | **Cumulative picks (unchanged resubmission)** — Player resends same message → bot does not re-confirm unchanged picks | ✅ | |
| 6 | **Pick outside window** — Pick sent outside Wed 7PM–Fri 10PM → bot ignores (unless TEST_MODE) | ⏳ | |
| 7 | **Late pick** — Pick after Fri 10PM → bot records as late and adds to penalty queue | ⏳ | |
| 8 | **Unknown player** — Pick from unrecognised sender → bot ignores | ⏳ | |
| 9 | **!picks** — Command shows recorded picks with formal display, odds shown once | ✅ | |

---

## Result flows

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 10 | **Result (win)** — Ed posts `Kev ✅` → bot records win and announces | ✅ | |
| 11 | **Result (loss)** — Ed posts `Nialler ❌` → bot records loss and announces | ✅ | |
| 12 | **Streak penalty suggestion** — Result causes 3rd/5th/7th/10th consecutive loss → bot suggests penalty for Ed | ⏳ | |
| 13 | **Result from non-admin** — Non-Ed posts result → bot ignores | ⏳ | |
| 14 | **Result for player with no pick** — Ed posts result for player with no pick → bot rejects | ⏳ | |
| 15 | **All results in** — Last result posted → bot sends weekend summary and completes week | ✅ | |

---

## Penalty flows

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 16 | **!confirm penalty** — Ed confirms suggested penalty → bot applies and updates vault/rotation | ⏳ | |
| 17 | **!confirm penalty (unauthorised)** — Non-Ed tries to confirm → bot rejects | ⏳ | |
| 18 | **Streak-3 penalty** — 3-loss penalty confirmed → player added to rotation queue to place next week | ⏳ | |

---

## Override & admin flows

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 19 | **!override [player] [win/loss]** — Ed overrides a result → bot updates | ✅ | |
| 20 | **!override (unauthorised)** — Non-Ed tries override → bot rejects | ⏳ | |
| 21 | **!resetweek** — Ed resets current week → picks and results cleared | ⏳ | |
| 22 | **!resetweek (unauthorised)** — Non-Ed tries reset → bot rejects | ⏳ | |

---

## Command flows

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 23 | **!stats** — Player requests own stats → bot shows win rate, streak, form | ⏳ | |
| 24 | **!stats [player]** — Player requests another player's stats → bot shows their stats | ⏳ | |
| 25 | **!leaderboard** — Player requests leaderboard → bot shows rankings | ⏳ | |
| 26 | **!rotation** — Player requests rotation → bot shows queue and next placer | ⏳ | |
| 27 | **!vault** — Player requests vault total → bot shows balance | ⏳ | |
| 28 | **!help** — Player requests help → bot lists commands | ⏳ | |
| 29 | **!status** — Superadmin requests status → bot shows system health (TEST_MODE: anyone) | ⏳ | |

---

## Scheduled flows

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 30 | **Thursday 7PM reminder** — Bot posts reminder to group | ⏳ | |
| 31 | **Friday 5PM reminder** — Bot tags missing players | ⏳ | |
| 32 | **Friday 9:30PM reminder** — Bot sends final reminder (group only; DMs not implemented) | ⏳ | |
| 33 | **Friday 10PM close** — Bot closes the week | ⏳ | |
| 34 | **Week complete summary** — When last result posted, bot sends results + leaderboard + next placer | ✅ | Combined with flow 15 |

---

---

## Phase 0.5: Infrastructure & Reliability

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 35 | **PM2 manages both processes** — Bridge and Flask run under PM2 | ⏳ | `pm2 status` shows both online |
| 36 | **PM2 crash recovery** — Kill bridge or Flask → PM2 restarts within seconds | ⏳ | |
| 37 | **PM2 startup on reboot** — After machine restart, both processes auto-start | ⏳ | `pm2 startup` + `pm2 save` |
| 38 | **/health endpoint** — GET /health returns 200 and `{"status":"ok"}` | ⏳ | Used by health check script |
| 39 | **Health check script** — Pings /health every 5 min; alerts on failure | ⏳ | To be built |
| 40 | **Health check on OCI** — Telegram alert when bot unresponsive on cloud | ⬜ Phase 0.5 |
| 41 | **Oracle Cloud migration** — Bot runs on OCI unattended Fri–Mon | ⬜ Phase 0.5 |
| 42 | **Remote restart** — Restart bot via OCI console without laptop | ⬜ Phase 0.5 |

---

## Match monitor flows (Phase 3)

| # | Flow | Status | Notes |
|---|------|--------|-------|
| 43 | **Goal event posted** — Goal scored in monitored fixture → bot posts `⚽ Liverpool 1-0 Arsenal — Salah 23'` to monitor group | ⏳ | Trial weekend |
| 44 | **Red card event posted** — Red card in monitored fixture → bot posts `🟥` event to monitor group | ⏳ | Trial weekend |
| 45 | **No duplicate events** — Same goal polled twice → only posted once (fixture_events dedup) | ✅ | Unit tested |
| 46 | **FT triggers auto-result** — Match finishes → bot posts FT score and auto-results the linked pick | ⏳ | Trial weekend |
| 47 | **Manual result before auto-result** — Admin results a pick before match ends → auto-result skips it | ✅ | Unit tested |
| 48 | **Monitor scheduled on pick submit** — Pick matched to fixture → monitor scheduled at kickoff | ⏳ | |
| 49 | **Startup recovery** — Flask restarts during a match → monitors re-scheduled for unresulted picks | ⏳ | |
| 50 | **Monday night game** — Pick for Monday fixture → monitor runs Monday evening | ⏳ | |
| 51 | **API budget Saturday** — Batched polling stays within 100 req/day | ⏳ | Check Flask logs |
| 52 | **Monitor disabled** — `MATCH_MONITOR_ENABLED=false` → no polling, no events posted | ✅ | Unit tested |

---

## Not in scope (Phase 3b+)

| # | Flow | Status |
|---|------|--------|
| — | **Bet slip image reading** — OCR and parsing of bet slip screenshots | ⬜ Phase 3b |
| — | **DM reminders** — Individual DMs to missing players at 9:30PM | ⬜ Phase 3b |

---

## How to test

1. **Test group:** Use `TEST_MODE=true` to simulate players via prefix (e.g. `Kev: pick text`) or emoji in cumulative format.
2. **Flows 6–7:** Adjust system time or scheduler for testing outside window / late picks.
3. **Flows 30–34:** Wait for scheduled times or temporarily modify cron in `src/services/scheduler.py`.
4. **Admin flows:** In TEST_MODE, use `Ed:` prefix for admin commands.
5. **Phase 0.5 (35–38):** Run `pytest tests/test_health.py` for /health; use `pm2 status` and `pm2 restart` for PM2 flows.

---

## Version

- **Document:** Testing plan v0.12
- **Requirements:** See `requirements_document.md` (Version 0.21)
- **Last updated:** 2026-02-25
